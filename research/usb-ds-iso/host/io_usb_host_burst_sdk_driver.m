#import "io_usb_host_burst_sdk_driver.h"
#include <CommonCrypto/CommonDigest.h>

static NSString *sha(NSData *data)
{
    unsigned char bytes[CC_SHA256_DIGEST_LENGTH];CC_SHA256(data.bytes,(CC_LONG)data.length,bytes);
    NSMutableString *s=[NSMutableString string];for(unsigned i=0;i<sizeof(bytes);++i)[s appendFormat:@"%02x",bytes[i]];return s;
}
NSDictionary *A23DormantBurstSDKPlan(void)
{
    return @{@"schema":@"A23-burst-sdk-plan-1",@"backend":@"iousbhost-single-burst-1",
        @"scenario":@{@"kind":@"single_burst",@"first_sequence":@1},@"first_frame_lead":@64,
        @"transaction_count":@960,@"request_bytes_per_transaction":@192,@"transfer_options":@0,
        @"max_submissions":@1,@"max_device_triggers":@1,@"max_async_aborts":@1,@"repeat":@0,
        @"runtime_budget":A23RuntimeBudget(),@"control_deadline_ns":@16000000,@"iso_deadline_ns":@2000000000,
        @"exit_wait_ns":@1000000000,@"closed_observation_ns":@250000000,
        @"hardware_entry_enabled":@NO,@"hardware_verified":@NO,@"allow_next_burst":@NO};
}
@implementation A23DormantBurstSDKDriver {
    id<A23PreparedBurstResources> _resources;NSString *_directory,*_sessionID;
    dispatch_queue_t _queue;id<A23RuntimeClock> _clock;id<A23SessionJournal> _journal;
    A23DormantBurstSDKTransport *_transport;NSDictionary *_binding;NSMutableArray *_reasons;
    NSUInteger _index;uint64_t _submittedAt,_triggerStart,_exitAt,_closedAt;
    BOOL _started,_journalFailed,_saveAttempted,_saved,_exitRequested,_unresolved,_finished,_closedObserved;
    BOOL _retainedCheckpointAttempted,_retainedCheckpointSaved,_finalCheckpointAttempted,_finalCheckpointSaved;
    A23DormantBurstSDKDriver *_hold;
}
- (instancetype)initWithResources:(id<A23PreparedBurstResources>)resources directory:(NSString *)directory
    queue:(dispatch_queue_t)queue clock:(id<A23RuntimeClock>)clock journal:(id<A23SessionJournal>)journal error:(NSError **)error
{
    if(!resources || !directory || !queue || !clock || !clock.numerator || !clock.denominator || !journal)return nil;
    dispatch_assert_queue(queue);
    if((self=[super init])){
        _resources=resources;_directory=[directory copy];_queue=queue;_clock=clock;_journal=journal;
        _sessionID=NSUUID.UUID.UUIDString;_reasons=[NSMutableArray array];
        __weak A23DormantBurstSDKDriver *weak=self;
        _transport=[[A23DormantBurstSDKTransport alloc] initWithResources:resources queue:queue clock:clock event:^BOOL(NSDictionary *event){
            return [weak adapterEvent:event];
        } error:error];
        if(!_transport)return nil;
        NSDictionary *d=resources.descriptorBytes;NSMutableDictionary *hashes=[NSMutableDictionary dictionary],*bytes=[NSMutableDictionary dictionary];
        for(NSString *key in @[@"device_descriptor",@"configuration_descriptor",@"active_interface"]){
            NSData *raw=d[key];if(![raw isKindOfClass:NSData.class] || raw.length>1024)return nil;
            hashes[key]=sha(raw);bytes[key]=[raw base64EncodedStringWithOptions:0];
        }
        _binding=@{@"session_id":_sessionID,@"identity":[resources.identity copy],@"descriptor_sha256":[hashes copy]};
        if(![self emit:@"prepared" details:@{@"binding":_binding,@"descriptor_base64":bytes,@"plan":A23DormantBurstSDKPlan(),
            @"timebase_numerator":@(_clock.numerator),@"timebase_denominator":@(_clock.denominator)}])return nil;
    }return self;
}
- (BOOL)emit:(NSString *)name details:(NSDictionary *)details
{
    if(_journalFailed)return NO;
    NSDictionary *e=@{@"schema":@"A23-burst-sdk-session-event-1",@"backend":@"iousbhost-single-burst-1",
        @"session_id":_sessionID,@"index":@(++_index),@"ticks":@(_clock.nowTicks),@"event":name,@"details":details,
        @"hardware_entry_enabled":@NO,@"hardware_verified":@NO};
    if(![_journal append:e error:NULL]){_journalFailed=YES;[_reasons addObject:@"journal_failed"];return NO;}return YES;
}
- (BOOL)adapterEvent:(NSDictionary *)event
{
    if([event[@"event"] isEqual:@"trigger_return"])_triggerStart=[event[@"details"][@"start_ticks"] unsignedLongLongValue];
    return [self emit:@"adapter" details:event];
}
- (void)stop:(NSString *)reason
{
    if(![_reasons containsObject:reason]){[_reasons addObject:reason];[self emit:@"stop" details:@{@"reason":reason}];}
}
- (BOOL)interrupted
{
    if(_interruptionRequested && _interruptionRequested()){[self stop:@"interrupted"];[self requestExit];return YES;}return NO;
}
- (BOOL)start
{
    dispatch_assert_queue(_queue);if(_started || _finished || _exitRequested)return NO;
    _started=YES;_hold=self;
    if([self interrupted])return NO;
    if(![self emit:@"before_intent" details:@{}] || ![_transport recordBefore:[_resources readStatus]]){
        [self stop:@"before_failed"];[self requestExit];return NO;
    }
    if([self interrupted])return NO;
    if(![self emit:@"frame_intent" details:@{}] || ![_transport recordFrame:[_resources readFrameSample]]){
        [self stop:@"frame_failed"];[self requestExit];return NO;
    }
    if([self interrupted])return NO;
    _submittedAt=_clock.nowTicks;
    if(![_transport submitISO]){[self stop:@"iso_admission_failed"];[self requestExit];[self poll];return NO;}
    if([self interrupted])return NO;
    BOOL triggered=[_transport triggerOnce];
    if(!triggered){[self stop:@"trigger_not_admitted"];[self requestExit];}
    return triggered;
}
- (BOOL)elapsed:(uint64_t)start end:(uint64_t)end atLeast:(uint64_t)limit
{
    uint64_t ns=0;
    if(!start || end<start || !A23TicksToNanoseconds(end-start,_clock.numerator,_clock.denominator,&ns)){
        [self stop:@"invalid_clock"];return YES;
    }return ns>=limit;
}
- (void)requestExit
{
    dispatch_assert_queue(_queue);if(_exitRequested || _finished)return;
    _exitRequested=YES;_exitAt=_clock.nowTicks;[self stop:@"exit_requested"];[self emit:@"exit_requested" details:@{}];
    if(_transport.owner.state!=A23TransactionPrepared)[_transport requestAbortOnce];
}
- (void)detachedRegistryID:(uint64_t)registryID
{
    dispatch_assert_queue(_queue);
    if([_transport detachedRegistryID:registryID]){[self stop:@"detached"];[self requestExit];}
}
- (void)poll
{
    dispatch_assert_queue(_queue);if(_finished || (!_started && !_exitRequested))return;
    [self interrupted];NSDictionary *t=_transport.result;A23TransactionOwner *owner=_transport.owner;
    if(_triggerStart){
        uint64_t arrival=_transport.controlArrivalTicks;
        // Compare native ingress when available. Queue/disk delay alone does
        // not turn a timely callback into a late SDK completion.
        if((arrival && [self elapsed:_triggerStart end:arrival atLeast:16000001]) ||
            (!arrival && [t[@"control_pending"] boolValue] && [self elapsed:_triggerStart end:_clock.nowTicks atLeast:16000000])){
            [self stop:@"control_deadline"];[self requestExit];
        }
    }
    BOOL pending=owner.state==A23TransactionPending || owner.state==A23TransactionCancelPending || owner.state==A23TransactionRetained;
    uint64_t isoArrival=_transport.isoArrivalTicks;
    if(_submittedAt && [t[@"iso_accepted"] boolValue] &&
        ((isoArrival && [self elapsed:_submittedAt end:isoArrival atLeast:2000000001]) ||
            (!isoArrival && pending && [self elapsed:_submittedAt end:_clock.nowTicks atLeast:2000000000]))){
        [self stop:@"iso_deadline"];[self requestExit];
    }
    if([t[@"failure_reasons"] count] || _journalFailed){[self stop:@"adapter_failed"];[self requestExit];}
    if(owner && (owner.state==A23TransactionCompleted || owner.state==A23TransactionRejected) && !_saveAttempted){
        _saveAttempted=YES;NSError *error=nil;
        // Save own ISO as soon as possible, even with control still pending.
        // Commit/ack releases owner's buffer references, not the SDK lease.
        if([self emit:@"save_intent" details:@{@"name":@"transfer",@"binding":_binding}])
            _saved=A23SaveBurstHardwareObservation(owner,_directory,@"transfer",_binding,&error);
        [self emit:@"save_result" details:@{@"saved":@(_saved),@"error":error ? A23PreparationErrorDetails(error) : (id)NSNull.null}];
        if(!_saved){[self stop:@"save_failed"];[self requestExit];}
    }
    t=_transport.result;
    if(_saved && owner.state==A23TransactionCompleted && owner.callbackCount==1 &&
        ![t[@"control_pending"] boolValue] && ![t[@"after_reads"] unsignedLongLongValue] && ![t[@"detached"] boolValue])[_transport readAfter];
    t=_transport.result;
    if([t[@"failure_reasons"] count]){[self stop:@"adapter_failed"];[self requestExit];}
    // A failure to commit our journal prevents destruction, even when the
    // transport's earlier records were successful.
    if(!_journalFailed && (owner.state==A23TransactionPrepared || _saved))[_transport closeAfterOwnerAcknowledged];
    t=_transport.result;
    if([t[@"closed"] boolValue]){
        _resources=nil;
        if(!_closedObserved){_closedObserved=YES;_closedAt=_clock.nowTicks;[self emit:@"closed_observed" details:@{}];}
        if([self elapsed:_closedAt end:_clock.nowTicks atLeast:250000000] && !_finalCheckpointAttempted){
            _unresolved=NO;_finalCheckpointAttempted=YES;_finished=YES;
            // The checkpoint says finished. Its successful write is confirmed
            // only in the later journal record, never self-certified inside it.
            NSError *error=nil;
            _finalCheckpointSaved=A23SaveBurstCheckpoint(self.result,_directory,@"final",&error);
            [self emit:@"final_checkpoint" details:@{@"saved":@(_finalCheckpointSaved),@"error":error ? A23PreparationErrorDetails(error) : (id)NSNull.null}];
            if(!_finalCheckpointSaved)[self stop:@"final_checkpoint_failed"];
            _hold=nil;
        }return;
    }
    if(_exitRequested && [self elapsed:_exitAt end:_clock.nowTicks atLeast:1000000000] && !_retainedCheckpointAttempted){
        _unresolved=YES;_retainedCheckpointAttempted=YES;NSError *error=nil;
        _retainedCheckpointSaved=A23SaveBurstCheckpoint(self.result,_directory,@"retained",&error);
        [self emit:@"retained_checkpoint" details:@{@"saved":@(_retainedCheckpointSaved),@"error":error ? A23PreparationErrorDetails(error) : (id)NSNull.null}];
        if(!_retainedCheckpointSaved)[self stop:@"retained_checkpoint_failed"];
        // Keep self, lease and poll capability alive. A late own completion
        // may still be saved and closed, retaining all prior failure reasons.
    }
}
- (NSDictionary *)result
{
    dispatch_assert_queue(_queue);
    NSDictionary *t=_transport.result;BOOL failed=_reasons.count || [t[@"failure_reasons"] count] || _journalFailed;
    return @{@"schema":@"A23-burst-sdk-checkpoint-1",@"backend":@"iousbhost-single-burst-1",@"binding":_binding,
        @"started":@(_started),@"ticks":@(_clock.nowTicks),@"finished":@(_finished),@"unresolved":@(_unresolved),
        @"exit_code":@((_finished && !failed) ? 0 : 1),@"core_saved":@(_saved),@"save_attempted":@(_saveAttempted),
        @"exit_requested":@(_exitRequested),@"journal_failed":@(_journalFailed),@"failure_reasons":[_reasons copy],@"transport":t,
        @"submitted_at_ticks":@(_submittedAt),@"trigger_start_ticks":@(_triggerStart),@"exit_at_ticks":@(_exitAt),
        @"retained_checkpoint_saved":@(_retainedCheckpointSaved),@"final_checkpoint_saved":@(_finalCheckpointSaved),
        @"hardware_entry_enabled":@NO,@"hardware_verified":@NO,@"baseline_accepted":@NO,@"allow_next_burst":@NO,
        @"callback_drain_verified":@NO,@"usb_strict_pass":@NO};
}
@end
