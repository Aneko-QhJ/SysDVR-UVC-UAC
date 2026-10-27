#import "io_usb_host_burst_executor.h"
#import "../../../source/uvc/iso_probe_protocol.h"
#import <CommonCrypto/CommonDigest.h>
#include <stdatomic.h>
#include <string.h>
#include <mach/mach_time.h>

NSDictionary *A23BurstExecutorSimulationPlan(void)
{
    return @{@"schema":@"A23-burst-executor-plan-1",@"execution_mode":@"simulation",@"max_submissions":@1,
        @"max_device_triggers":@1,@"max_async_aborts":@1,@"max_status_reads":@2,@"repeat":@0,
        @"transaction_count":@960,@"request_count":@192,@"first_frame_lead":@64,@"first_sequence":@1,
        @"trigger_timeout_ns":@16000000,@"max_trigger_gap_ns":@8000000,@"max_trigger_end_age_ns":@48000000,
        @"completion_deadline_ns":@2000000000,@"exit_grace_ns":@1000000000,
        @"hardware_entry_enabled":@NO,@"hardware_verified":@NO,@"allow_next_burst":@NO};
}
static NSString *hashData(NSData *data)
{
    unsigned char h[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(data.bytes,(CC_LONG)data.length,h);
    NSMutableString *s=[NSMutableString string]; for (unsigned i=0;i<sizeof(h);++i) [s appendFormat:@"%02x",h[i]]; return s;
}
static BOOL u64(id n)
{
    return [n isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)n)!=CFBooleanGetTypeID() &&
        !CFNumberIsFloatType((__bridge CFNumberRef)n) && ![[n description] hasPrefix:@"-"];
}
// Latch at callback ingress, before A23TransactionOwner dispatches its handler.
@interface BurstIngress : NSObject <A23TransactionTransport>
@property id<A23TransactionTransport> target;
@property(readonly) BOOL arrived;
@end
@implementation BurstIngress { atomic_bool _arrived; }
- (instancetype)init { if ((self=[super init])) atomic_init(&_arrived,false); return self; }
- (BOOL)arrived { return atomic_load_explicit(&_arrived,memory_order_acquire); }
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows
    transactionListCount:(NSUInteger)count firstFrameNumber:(uint64_t)frame options:(IOUSBHostIsochronousTransferOptions)options
    error:(NSError **)error completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion
{
    return [_target enqueueIORequestWithData:data transactionList:rows transactionListCount:count firstFrameNumber:frame
        options:options error:error completionHandler:^(IOReturn status,IOUSBHostIsochronousTransaction *p) {
            atomic_store_explicit(&self->_arrived,true,memory_order_release); completion(status,p);
        }];
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error { return [_target abortWithOption:option error:error]; }
@end
@implementation A23BurstSimulationExecutor {
    NSString *_directory; dispatch_queue_t _queue; id<A23RuntimeClock> _clock; id<A23BurstMockOperations> _ops;
    BOOL (^_journal)(NSDictionary *); A23TransactionOwner *_owner; BurstIngress *_ingress; A23BudgetTransport *_guard;
    BOOL _started,_journalFailed,_stopped,_detached,_closed,_saved,_controlPending,_controlReturned,_enqueueAccepted;
    BOOL _after,_isoHandled,_unresolved; NSUInteger _index,_triggers,_controls,_aborts;
    uint64_t _submitAt,_triggerAt,_stopAt; NSDictionary *_sample; NSMutableArray *_failures;
}
- (instancetype)initWithDirectory:(NSString *)directory queue:(dispatch_queue_t)queue clock:(id<A23RuntimeClock>)clock
    operations:(id<A23BurstMockOperations>)operations journal:(BOOL (^)(NSDictionary *))journal
{
    if (!directory || !queue || !clock || !operations || !journal || !operations.simulationOnly) return nil;
    if ((self=[super init])) {
        _directory=[directory copy];_queue=queue;_clock=clock;_ops=operations;_journal=[journal copy];_failures=[NSMutableArray array];
        _owner=[[A23TransactionOwner alloc] initWithData:[NSMutableData dataWithLength:184320]
            transactions:[NSMutableData dataWithLength:26880] queue:queue];
    } return self;
}
- (BOOL)event:(NSString *)name details:(NSDictionary *)details
{
    if (_journalFailed) return NO;
    NSDictionary *row=@{@"schema":@"A23-burst-executor-event-1",@"execution_mode":@"simulation",@"index":@(++_index),
        @"ticks":@([_clock nowTicks]),@"event":name,@"details":details};
    if (!_journal(row)) { _journalFailed=YES;_stopped=YES;[_failures addObject:@"journal_failed"];return NO; } return YES;
}
- (void)stop:(NSString *)reason
{
    if (![_failures containsObject:reason]) { [_failures addObject:reason]; [self event:@"stop" details:@{@"reason":reason}]; }
    _stopped=YES;if (!_stopAt) _stopAt=[_clock nowTicks];
}
- (BOOL)startBefore:(NSData *)before sample:(NSDictionary *)sample
{
    dispatch_assert_queue(_queue);if (_started) return NO;_started=YES;
    if (![self event:@"begin" details:@{@"plan":A23BurstExecutorSimulationPlan()}]) return NO;
    if (![self event:@"status_before" details:@{@"raw_base64":[before base64EncodedStringWithOptions:0],@"sha256":hashData(before)}]) return NO;
    IsoProbeStatus s={0};if (before.length==sizeof(s)) memcpy(&s,before.bytes,sizeof(s));
    BOOL fresh=before.length==168 && s.magic==ISO_PROBE_STATUS_MAGIC && s.version==1 && s.endpoint==0x83 &&
        !s.sequence && !s.state && !s.post_result && !s.urb_id && !s.report_id && !s.requested && !s.transferred &&
        !s.urb_status && !s.report_count && !s.report_result && (s.speed==0 || s.speed==3);
    BOOL frame=u64(sample[@"current_frame"]) && u64(sample[@"begin_ticks"]) && u64(sample[@"end_ticks"]) &&
        [sample[@"current_frame"] unsignedLongLongValue]>0 && [sample[@"current_frame"] unsignedLongLongValue]<=UINT64_MAX-64;
    if (!fresh || !frame) { [self stop:fresh ? @"invalid_frame" : @"invalid_before"];[self tryClose];return NO; }
    _sample=[sample copy];_ingress=[BurstIngress new];_ingress.target=_ops;
    _guard=[[A23BudgetTransport alloc] initWithTransport:_ingress clock:_clock sample:sample];
    __weak A23BurstSimulationExecutor *weakSelf=self;
    [_owner observeCompletions:^(NSDictionary *details) {
        A23BurstSimulationExecutor *self=weakSelf;if (!self) return;
        [self event:@"iso_callback" details:details];
        if ([details[@"count"] unsignedLongLongValue]!=1 || [details[@"pointer_mismatch"] boolValue]) [self stop:@"invalid_iso_callback"];
    }];
    if (![self event:@"iso_begin" details:@{@"first_frame":@([sample[@"current_frame"] unsignedLongLongValue]+64),
        @"sample":sample,@"timebase_numerator":@(_clock.numerator),@"timebase_denominator":@(_clock.denominator)}]) return NO;
    _submitAt=[_clock nowTicks];
    _enqueueAccepted=[_owner submitTo:_guard firstFrame:[sample[@"current_frame"] unsignedLongLongValue]+64 finished:^(NSDictionary *snapshot) {
        A23BurstSimulationExecutor *self=weakSelf;if (!self) return;
        [self event:@"iso_snapshot" details:@{@"callback_arrival_ticks":snapshot[@"callback_arrival_ticks"],
            @"overall_u32":snapshot[@"overall_u32"] ?: [NSNull null],@"raw_sha256":hashData(snapshot[@"raw"]),
            @"transactions_sha256":hashData(snapshot[@"transactions"])}];
    }];
    if (![self event:@"iso_return" details:@{@"accepted":@(_enqueueAccepted),@"admission":_guard.result ?: @{}}]) return _enqueueAccepted;
    if (!_enqueueAccepted || ![_guard.result[@"budget_pass"] boolValue]) [self stop:@"iso_not_admitted_or_slow"];
    if (_ingress.arrived) [self stop:@"iso_arrived_before_trigger"];
    if (!_stopped && [self event:@"trigger_intent" details:@{@"next_attempt":@1}]) [self triggerOnce];
    if (_stopped) [self requestExit];[self poll];return _enqueueAccepted;
}
- (void)triggerOnce
{
    uint64_t now=[_clock nowTicks],gap=0,age=0,ret=[_guard.result[@"return_ticks"] unsignedLongLongValue];
    uint64_t begin=[_sample[@"begin_ticks"] unsignedLongLongValue];
    BOOL budget=now>=ret && now>=begin && A23TicksToNanoseconds(now-ret,_clock.numerator,_clock.denominator,&gap) &&
        A23TicksToNanoseconds(now-begin,_clock.numerator,_clock.denominator,&age) && gap<=8000000 && age<=32000000;
    if (!budget || _stopped || _detached || _ingress.arrived || _owner.state!=A23TransactionPending || _triggers) {
        [self stop:@"trigger_final_check_failed"];return;
    }
    // One-use intent was durable before this final check. Mark attempted before
    // invoking transport; even rejection/timeout cannot authorize another call.
    _triggers=1;_controlPending=YES;_triggerAt=now;
    IOUSBDeviceRequest request={.bmRequestType=0x41,.bRequest=0x54,.wValue=1,.wIndex=2,.wLength=0};
    NSError *error=nil;
    BOOL accepted=[_ops enqueueBurst:request timeout:0.016 completion:^(IOReturn status,NSUInteger bytes) {
        uint64_t arrival=mach_absolute_time();dispatch_async(self->_queue,^{
            ++self->_controls;[self event:@"control_callback" details:@{@"count":@(self->_controls),@"status_u32":@((uint32_t)status),
                @"bytes":@(bytes),@"arrival_ticks":@(arrival)}];
            if (self->_controls!=1) [self stop:@"duplicate_control_callback"];
            else { self->_controlPending=NO;if (status || bytes) [self stop:@"control_completion_failed"]; }
            [self poll];
        });
    } error:&error];
    _controlReturned=YES;
    [self event:@"trigger_return" details:@{@"accepted":@(accepted),@"attempt":@1,@"request_type":@0x41,@"request":@0x54,
        @"value":@1,@"index":@2,@"length":@0,@"timeout_ns":@16000000,@"start_ticks":@(now),@"gap_ns":@(gap),@"age_ns":@(age),
        @"error":error ? @{@"domain":error.domain,@"code":@(error.code)} : (id)[NSNull null]}];
    if (!accepted) { _controlPending=NO;[self stop:@"trigger_enqueue_failed"]; }
    else if (error) [self stop:@"trigger_accepted_with_error"];
}
- (void)requestExit
{
    dispatch_assert_queue(_queue);if (!_stopped) [self stop:@"exit_requested"];
    if (!_journalFailed && !_detached && !_ingress.arrived && _owner.state==A23TransactionPending && !_aborts) {
        if ([self event:@"abort_intent" details:@{@"attempt":@1}]) {
            _aborts=1;BOOL accepted=[_owner deadlineReached];[self event:@"abort_return" details:@{@"accepted":@(accepted)}];
        }
    }
}
- (void)detached { dispatch_assert_queue(_queue);_detached=YES;[self stop:@"detached"];[self requestExit]; }
- (void)tryClose
{
    if (_closed || _journalFailed || _controlPending || (_triggers && !_controlReturned)) return;
    BOOL prepared=_owner.state==A23TransactionPrepared;
    if (!prepared && (!_saved || _owner.storageRetained || _owner.state==A23TransactionRetained)) return;
    if (![self event:@"close_begin" details:@{@"control_pending":@NO,@"saved":@(_saved),@"prepared":@(prepared)}]) return;
    [_ops closeMockResources];_closed=YES;_unresolved=NO;
    [self event:@"closed" details:@{}];if (prepared) _owner=nil;
}
- (void)poll
{
    dispatch_assert_queue(_queue);
    if (_closed || _journalFailed) return;
    if (!_isoHandled && (_owner.state==A23TransactionCompleted || _owner.state==A23TransactionRejected)) {
        _isoHandled=YES;
        if (_owner.state==A23TransactionCompleted && !_after) {
            _after=YES;NSData *after=[_ops readAfterStatus];
            if (![self event:@"status_after" details:@{@"raw_base64":[after base64EncodedStringWithOptions:0],@"sha256":hashData(after)}]) return;
            if (after.length!=168) [self stop:@"invalid_after"];
        }
        if (![self event:@"save_begin" details:@{}]) return;
        BOOL ok=A23SaveSimulationEvidence(_owner,_directory,@"transfer",@{@"kind":@"single_burst",@"first_sequence":@1},NULL);
        if (!ok) { [self stop:@"save_failed"];return; }
        _saved=YES;NSData *manifest=[NSData dataWithContentsOfFile:[_directory stringByAppendingPathComponent:@"transfer/SHA256SUMS"]];
        if (![self event:@"bundle_committed" details:@{@"manifest_sha256":hashData(manifest),@"callback_count":@(_owner.callbackCount)}]) return;
    }
    uint64_t now=[_clock nowTicks],elapsed=0;
    if (_controlPending && now>=_triggerAt && A23TicksToNanoseconds(now-_triggerAt,_clock.numerator,_clock.denominator,&elapsed) && elapsed>=16000000)
        [self stop:@"control_deadline_observed"];
    if (_owner.state==A23TransactionPending && now>=_submitAt && A23TicksToNanoseconds(now-_submitAt,_clock.numerator,_clock.denominator,&elapsed) && elapsed>=2000000000)
        [self stop:@"iso_deadline_observed"];
    if (_stopped) [self requestExit];
    if (_stopAt && now>=_stopAt && A23TicksToNanoseconds(now-_stopAt,_clock.numerator,_clock.denominator,&elapsed) && elapsed>=1000000000) _unresolved=YES;
    [self tryClose];
}
- (NSDictionary *)result
{
    dispatch_assert_queue(_queue);
    return @{@"schema":@"A23-burst-executor-result-1",@"execution_mode":@"simulation",@"started":@(_started),
        @"closed":@(_closed),@"saved":@(_saved),@"control_pending":@(_controlPending),@"control_callbacks":@(_controls),
        @"trigger_attempts":@(_triggers),@"host_aborts":@(_aborts),@"iso_callbacks":@(_owner.callbackCount),
        @"storage_retained":@(_owner.storageRetained),@"unresolved":@(_unresolved),@"failure_reasons":[_failures copy],
        @"journal_failed":@(_journalFailed),@"hardware_entry_enabled":@NO,@"hardware_verified":@NO,@"allow_next_burst":@NO,
        @"baseline_accepted":@NO,@"usb_strict_pass":@NO,@"callback_drain_verified":@NO};
}
@end
