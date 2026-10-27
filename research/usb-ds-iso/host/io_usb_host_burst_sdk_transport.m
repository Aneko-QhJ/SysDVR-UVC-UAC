#import "io_usb_host_burst_sdk_transport.h"
#import "../../../source/uvc/iso_probe_protocol.h"
#include <CommonCrypto/CommonDigest.h>
#include <mach/mach_time.h>
#include <stdatomic.h>
#include <string.h>

static BOOL fail(NSError **error,NSString *reason)
{
    if (error) *error=[NSError errorWithDomain:@"A23DormantBurstSDK" code:1 userInfo:@{NSLocalizedDescriptionKey:reason}];
    return NO;
}
static BOOL number(id value)
{
    return [value isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)value)!=CFBooleanGetTypeID() &&
        !CFNumberIsFloatType((__bridge CFNumberRef)value) && ![[value description] hasPrefix:@"-"];
}
static BOOL flag(id value,BOOL expected)
{ return [value isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)value)==CFBooleanGetTypeID() && [value boolValue]==expected; }
static NSString *sha(NSData *data)
{
    unsigned char bytes[CC_SHA256_DIGEST_LENGTH];CC_SHA256(data.bytes,(CC_LONG)data.length,bytes);
    NSMutableString *s=[NSMutableString string];for(unsigned i=0;i<sizeof(bytes);++i)[s appendFormat:@"%02x",bytes[i]];return s;
}
static BOOL replyValid(NSDictionary *reply)
{
    NSData *raw=reply[@"data"];NSDictionary *o=reply[@"observation"],*control=o[@"control"];
    NSDictionary *expected=@{@"request_type":@193,@"request":@81,@"value":@0,@"index":@2,@"length":@168,@"timeout_ms":@3000};
    BOOL tuple=[control isKindOfClass:NSDictionary.class] && control.count==expected.count;
    for(NSString *key in expected)tuple=tuple && number(control[key]) && [control[key] isEqual:expected[key]];
    return [raw isKindOfClass:NSData.class] && raw.length==168 && [o[@"source"] isEqual:@"sdk_control_reply"] &&
        flag(o[@"accepted"],YES) && !o[@"error"] && number(o[@"bytes_transferred"]) && [o[@"bytes_transferred"] unsignedLongLongValue]==168 &&
        number(o[@"begin_ticks"]) && number(o[@"end_ticks"]) && [o[@"begin_ticks"] unsignedLongLongValue]>0 &&
        [o[@"begin_ticks"] unsignedLongLongValue]<=[o[@"end_ticks"] unsignedLongLongValue] && tuple;
}

@implementation A23DormantBurstSDKTransport {
    id<A23PreparedBurstResources> _resources;dispatch_queue_t _queue;id<A23RuntimeClock> _clock;
    BOOL (^_event)(NSDictionary *);A23TransactionOwner *_owner;A23SDKBudgetTransport *_budget;
    NSDictionary *_sample,*_identity;NSMutableArray *_reasons;
    BOOL _before,_frame,_submitted,_accepted,_triggered,_controlPending,_controlReturned,_after,_closed,_detached,_journalFailed;
    NSUInteger _index,_controls,_aborts;atomic_bool _isoArrived;
    atomic_uint_fast64_t _controlArrival,_isoArrival;
    uint64_t _readyTicks,_beforeEnd;
    A23DormantBurstSDKTransport *_hold;
}
- (instancetype)initWithResources:(id<A23PreparedBurstResources>)resources queue:(dispatch_queue_t)queue
    clock:(id<A23RuntimeClock>)clock event:(BOOL (^)(NSDictionary *))event error:(NSError **)error
{
    if (!resources || !queue || !clock || !event || ![resources conformsToProtocol:@protocol(A23PreparedBurstResources)] ||
        !resources.sdkResources || !resources.supportsSingleBurst || ![resources respondsToSelector:@selector(descriptorBytes)] ||
        ![resources respondsToSelector:@selector(readStatus)] || ![resources respondsToSelector:@selector(readFrameSample)]) {
        fail(error,@"Prepared SDK burst capability required");return nil;
    }
    dispatch_assert_queue(queue);NSDictionary *identity=resources.identity,*d=resources.descriptorBytes;
    BOOL valid=YES;for(NSString *key in @[@"device_id",@"interface_id",@"parent_device_id"])
        valid=valid && number(identity[key]) && [identity[key] unsignedLongLongValue]>0;
    NSData *active=d[@"active_interface"];const uint8_t *a=active.bytes;
    valid=valid && [identity[@"device_id"] isEqual:identity[@"parent_device_id"]] &&
        A23ValidateDescriptors(d[@"device_descriptor"],d[@"configuration_descriptor"],3,error)!=nil &&
        active.length==9 && a[0]==9 && a[1]==4 && a[2]==2 && a[3]==0 && a[4]==1 && a[5]==0xff && a[6]==0x49 && a[7]==1 &&
        resources.dataStorage.length==184320 && resources.transactionStorage.length==26880 &&
        resources.dataStorage!=resources.transactionStorage && resources.transport;
    if(!valid){fail(error,@"Prepared SDK identity/descriptors/storage mismatch");return nil;}
    if((self=[super init])){
        _resources=resources;_queue=queue;_clock=clock;_event=[event copy];_identity=[identity copy];_reasons=[NSMutableArray array];
        _readyTicks=clock.nowTicks;
        atomic_init(&_isoArrived,false);
        atomic_init(&_controlArrival,0);
        atomic_init(&_isoArrival,0);
        _owner=[[A23TransactionOwner alloc] initWithData:resources.dataStorage transactions:resources.transactionStorage queue:queue];
        if(!_owner){fail(error,@"Owner storage rejected");return nil;}
        __weak A23DormantBurstSDKTransport *weak=self;
        [_owner observeCompletions:^(NSDictionary *details){
            A23DormantBurstSDKTransport *s=weak;if(!s)return;
            NSMutableDictionary *observed=[details mutableCopy];observed[@"sdk_arrival_ticks"]=@(s.isoArrivalTicks);
            [s emit:@"iso_callback" details:observed];
            if([details[@"count"] unsignedLongLongValue]!=1 || [details[@"pointer_mismatch"] boolValue]) [s stop:@"invalid_iso_callback"];
        }];
    }return self;
}
- (BOOL)simulationOnly { return NO; }
- (BOOL)emit:(NSString *)name details:(NSDictionary *)details
{
    if(_journalFailed)return NO;
    NSDictionary *row=@{@"schema":@"A23-burst-sdk-adapter-event-1",@"backend_role":@"sdk_capability_adapter",@"index":@(++_index),
        @"ticks":@(_clock.nowTicks),@"event":name,@"details":details,@"hardware_verified":@NO,@"hardware_entry_enabled":@NO};
    if(!_event(row)){_journalFailed=YES;[_reasons addObject:@"journal_failed"];return NO;}return YES;
}
- (void)stop:(NSString *)reason
{
    if(![_reasons containsObject:reason]){[_reasons addObject:reason];[self emit:@"stop" details:@{@"reason":reason}];}
}
- (BOOL)recordBefore:(NSDictionary *)reply
{
    dispatch_assert_queue(_queue);if(_before || _submitted || _closed || _detached || _reasons.count)return NO;
    NSData *raw=reply[@"data"];
    if(![raw isKindOfClass:NSData.class] || raw.length>2048){[self stop:@"invalid_before_container"];return NO;}
    if(![self emit:@"status_before" details:@{@"raw_base64":[raw base64EncodedStringWithOptions:0],@"sha256":sha(raw),
        @"observation":reply[@"observation"] ?: @{}}])return NO;
    IsoProbeStatus status={0};if(raw.length==sizeof(status))memcpy(&status,raw.bytes,sizeof(status));
    BOOL fresh=replyValid(reply) && [reply[@"observation"][@"begin_ticks"] unsignedLongLongValue]>=_readyTicks &&
        [reply[@"observation"][@"end_ticks"] unsignedLongLongValue]<=_clock.nowTicks &&
        status.magic==ISO_PROBE_STATUS_MAGIC && status.version==1 && status.endpoint==0x83 &&
        !status.sequence && !status.state && !status.post_result && !status.urb_id && !status.report_id && !status.requested &&
        !status.transferred && !status.urb_status && !status.report_count && !status.report_result && (status.speed==0 || status.speed==3);
    if(!fresh){[self stop:@"invalid_before"];return NO;}_before=YES;_beforeEnd=[reply[@"observation"][@"end_ticks"] unsignedLongLongValue];return YES;
}
- (BOOL)recordFrame:(NSDictionary *)sample
{
    dispatch_assert_queue(_queue);if(!_before || _frame || _submitted || _closed || _detached || _reasons.count)return NO;
    BOOL valid=[sample[@"source"] isEqual:@"sdk_frame_number"] && number(sample[@"current_frame"]) && number(sample[@"frame_time"]) &&
        number(sample[@"begin_ticks"]) && number(sample[@"end_ticks"]) && [sample[@"current_frame"] unsignedLongLongValue]>0 &&
        [sample[@"current_frame"] unsignedLongLongValue]<=UINT64_MAX-64 && [sample[@"begin_ticks"] unsignedLongLongValue]>0 &&
        [sample[@"begin_ticks"] unsignedLongLongValue]>=_beforeEnd &&
        [sample[@"begin_ticks"] unsignedLongLongValue]<=[sample[@"end_ticks"] unsignedLongLongValue] &&
        [sample[@"end_ticks"] unsignedLongLongValue]<=_clock.nowTicks;
    if(!valid){[self stop:@"invalid_frame"];return NO;}
    _sample=[sample copy];_frame=YES;
    return [self emit:@"frame_sample" details:@{@"sample":sample,@"first_frame":@([sample[@"current_frame"] unsignedLongLongValue]+64),
        @"timebase_numerator":@(_clock.numerator),@"timebase_denominator":@(_clock.denominator)}];
}
- (BOOL)submitISO
{
    dispatch_assert_queue(_queue);if(!_before || !_frame || _submitted || _closed || _detached || _reasons.count)return NO;
    if(![self emit:@"iso_intent" details:@{@"attempt":@1}])return NO;
    if(_detached || _reasons.count)return NO;
    _submitted=YES;_hold=self;
    _budget=[[A23SDKBudgetTransport alloc] initWithTransport:_resources.transport clock:_clock sample:_sample];
    __weak A23DormantBurstSDKTransport *weak=self;
    _accepted=[_owner submitTo:self firstFrame:[_sample[@"current_frame"] unsignedLongLongValue]+64 finished:^(NSDictionary *snapshot){
        A23DormantBurstSDKTransport *s=weak;if(!s)return;
        [s emit:@"iso_snapshot" details:@{@"raw_sha256":sha(snapshot[@"raw"]),@"transactions_sha256":sha(snapshot[@"transactions"]),
            @"overall_u32":snapshot[@"overall_u32"] ?: (id)[NSNull null],@"arrival_ticks":snapshot[@"callback_arrival_ticks"]}];
    }];
    [self emit:@"iso_return" details:@{@"accepted":@(_accepted),@"admission":_budget.result ?: @{}}];
    if(!_accepted || ![_budget.result[@"budget_pass"] boolValue])[self stop:@"iso_not_admitted_or_slow"];
    return _accepted;
}
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows
    transactionListCount:(NSUInteger)count firstFrameNumber:(uint64_t)frame options:(IOUSBHostIsochronousTransferOptions)options
    error:(NSError **)error completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion
{
    dispatch_assert_queue(_queue);
    if(!_submitted || _owner.state!=A23TransactionPending || _budget.result || count!=960 || options ||
        frame!=[_sample[@"current_frame"] unsignedLongLongValue]+64 || data!=_resources.dataStorage ||
        rows!=_resources.transactionStorage.mutableBytes || !completion || _detached || _journalFailed)
        return fail(error,@"Fixed SDK ISO ownership/tuple mismatch");
    for(unsigned i=0;i<960;++i)if(rows[i].requestCount!=192 || rows[i].offset!=i*192 || rows[i].options ||
        rows[i].completeCount || rows[i].timeStamp || rows[i].status!=kIOReturnInvalid)return fail(error,@"ISO initializer mismatch");
    return [_budget enqueueIORequestWithData:data transactionList:rows transactionListCount:count firstFrameNumber:frame options:options
        error:error completionHandler:^(IOReturn status,IOUSBHostIsochronousTransaction *p){
            uint64_t expected=0,arrival=mach_absolute_time();
            atomic_compare_exchange_strong_explicit(&self->_isoArrival,&expected,arrival,memory_order_release,memory_order_relaxed);
            atomic_store_explicit(&self->_isoArrived,true,memory_order_release);completion(status,p);
        }];
}
- (BOOL)triggerOnce
{
    dispatch_assert_queue(_queue);
    if(!_submitted || !_accepted || _triggered || _closed || _detached || _reasons.count ||
        _owner.state!=A23TransactionPending || atomic_load_explicit(&_isoArrived,memory_order_acquire))return NO;
    if(![self emit:@"trigger_intent" details:@{@"attempt":@1}])return NO;
    uint64_t now=_clock.nowTicks,ret=[_budget.result[@"return_ticks"] unsignedLongLongValue],begin=[_sample[@"begin_ticks"] unsignedLongLongValue],gap=0,age=0;
    BOOL valid=now>=ret && now>=begin && A23TicksToNanoseconds(now-ret,_clock.numerator,_clock.denominator,&gap) &&
        A23TicksToNanoseconds(now-begin,_clock.numerator,_clock.denominator,&age) && gap<=8000000 && age<=32000000;
    if(!valid || _detached || _reasons.count || _owner.state!=A23TransactionPending || atomic_load_explicit(&_isoArrived,memory_order_acquire)){
        [self stop:@"trigger_final_check_failed"];return NO;
    }
    _triggered=YES;_controlPending=YES;NSError *error=nil;
    BOOL accepted=[_resources enqueueSequenceOneBurst:^(IOReturn status,NSUInteger bytes){
        uint64_t arrival=mach_absolute_time(),expected=0;
        atomic_compare_exchange_strong_explicit(&self->_controlArrival,&expected,arrival,memory_order_release,memory_order_relaxed);
        dispatch_async(self->_queue,^{
            ++self->_controls;
            [self emit:@"control_callback" details:@{@"status_u32":@((uint32_t)status),@"bytes":@(bytes),@"count":@(self->_controls),@"arrival_ticks":@(arrival)}];
            if(self->_controls!=1)[self stop:@"duplicate_control_callback"];
            else{self->_controlPending=NO;if(status || bytes)[self stop:@"control_completion_failed"];}
        });
    } error:&error];
    _controlReturned=YES;
    [self emit:@"trigger_return" details:@{@"accepted":@(accepted),@"request_type":@65,@"request":@84,@"value":@1,@"index":@2,@"length":@0,
        @"timeout_ns":@16000000,@"start_ticks":@(now),@"gap_ns":@(gap),@"age_ns":@(age),
        @"error":error ? A23PreparationErrorDetails(error) : (id)[NSNull null]}];
    if(!accepted){_controlPending=NO;[self stop:@"trigger_enqueue_failed"];}else if(error)[self stop:@"trigger_accepted_with_error"];
    return accepted;
}
- (NSDictionary *)readAfter
{
    dispatch_assert_queue(_queue);
    if(!_submitted || !_accepted || _after || _closed || _detached || _journalFailed || _controlPending ||
        (_triggered && !_controlReturned) || _owner.state!=A23TransactionCompleted || _owner.callbackCount!=1)return nil;
    if(![self emit:@"after_intent" details:@{}])return nil;
    if(_detached || _journalFailed)return nil;
    _after=YES;NSDictionary *reply=[_resources readStatus];NSData *raw=reply[@"data"];
    if(![raw isKindOfClass:NSData.class] || raw.length>2048){[self stop:@"invalid_after_container"];return nil;}
    [self emit:@"status_after" details:@{@"raw_base64":[raw base64EncodedStringWithOptions:0],@"sha256":sha(raw),@"observation":reply[@"observation"] ?: @{}}];
    if(!replyValid(reply) || [reply[@"observation"][@"begin_ticks"] unsignedLongLongValue]<[_owner.evidence[@"callback_arrival_ticks"] unsignedLongLongValue] ||
        [reply[@"observation"][@"end_ticks"] unsignedLongLongValue]>_clock.nowTicks)[self stop:@"invalid_after_observation"];
    return reply;
}
- (BOOL)requestAbortOnce
{
    dispatch_assert_queue(_queue);[self stop:@"exit_requested"];
    if(_closed || _detached || _journalFailed || _aborts || _owner.state!=A23TransactionPending ||
        atomic_load_explicit(&_isoArrived,memory_order_acquire))return NO;
    if(![self emit:@"abort_intent" details:@{@"attempt":@1}])return NO;
    if(_detached || atomic_load_explicit(&_isoArrived,memory_order_acquire))return NO;
    return [_owner deadlineReached];
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error
{
    dispatch_assert_queue(_queue);
    if(option!=IOUSBHostAbortOptionAsynchronous || _aborts || _owner.state!=A23TransactionCancelPending || _closed || _detached || _journalFailed ||
        atomic_load_explicit(&_isoArrived,memory_order_acquire))
        return fail(error,@"No additional or synchronous host abort");
    _aborts=1;BOOL accepted=[_budget abortWithOption:option error:error];
    [self emit:@"abort_return" details:@{@"accepted":@(accepted),@"error":error && *error ? A23PreparationErrorDetails(*error) : (id)[NSNull null]}];return accepted;
}
- (BOOL)detachedRegistryID:(uint64_t)registryID
{
    dispatch_assert_queue(_queue);if(registryID!=[_identity[@"device_id"] unsignedLongLongValue] && registryID!=[_identity[@"interface_id"] unsignedLongLongValue])return NO;
    _detached=YES;[self stop:@"detached"];return YES;
}
- (BOOL)closeAfterOwnerAcknowledged
{
    dispatch_assert_queue(_queue);if(_closed)return YES;
    BOOL prepared=_owner.state==A23TransactionPrepared;
    BOOL done=_owner.state==A23TransactionCompleted || _owner.state==A23TransactionRejected;
    if(_journalFailed || _controlPending || (_triggered && !_controlReturned) ||
        (!prepared && (!done || _owner.storageRetained || (_accepted && !_after && !_detached))))return NO;
    if(![self emit:@"close_intent" details:@{@"prepared":@(prepared),@"owner_acknowledged":@((BOOL)!_owner.storageRetained)}])return NO;
    if(prepared)_owner=nil; // No I/O began; drop mapped owners before destroy.
    [_resources closeWhenNoIO];_resources=nil;_closed=YES;_budget=nil;
    [self emit:@"closed" details:@{}];_hold=nil;return YES;
}
- (A23TransactionOwner *)owner { dispatch_assert_queue(_queue);return _owner; }
- (uint64_t)controlArrivalTicks { return atomic_load_explicit(&_controlArrival,memory_order_acquire); }
- (uint64_t)isoArrivalTicks { return atomic_load_explicit(&_isoArrival,memory_order_acquire); }
- (NSDictionary *)result
{
    dispatch_assert_queue(_queue);
    return @{@"schema":@"A23-burst-sdk-adapter-result-1",@"backend_role":@"sdk_capability_adapter",@"closed":@(_closed),
        @"iso_attempts":@((NSUInteger)_submitted),@"iso_accepted":@(_accepted),@"iso_callbacks":@(_owner.callbackCount),@"trigger_attempts":@((NSUInteger)_triggered),
        @"control_pending":@(_controlPending),@"control_callbacks":@(_controls),@"after_reads":@((NSUInteger)_after),@"host_aborts":@(_aborts),
        @"storage_retained":@(_owner.storageRetained),@"detached":@(_detached),@"journal_failed":@(_journalFailed),@"failure_reasons":[_reasons copy],
        @"hardware_entry_enabled":@NO,@"hardware_verified":@NO,@"baseline_accepted":@NO,@"allow_next_burst":@NO,@"callback_drain_verified":@NO};
}
@end
