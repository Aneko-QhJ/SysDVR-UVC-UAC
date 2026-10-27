#import "a23_short24_capture.h"
#include <mach/mach_time.h>
#include <stdatomic.h>
#include <string.h>

_Static_assert(sizeof(IOUSBHostIsochronousTransaction)==28,"SDK transaction layout");
uint64_t A23Short24NowNanoseconds(void) {
    mach_timebase_info_data_t t;mach_timebase_info(&t);
    return (uint64_t)(((__uint128_t)mach_absolute_time()*t.numer)/t.denom);
}
static BOOL fail(NSError **error,NSString *why) {
    if(error)*error=[NSError errorWithDomain:@"A23Short24" code:1 userInfo:@{NSLocalizedDescriptionKey:why}];
    return NO;
}
static BOOL number(id n) {
    return [n isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)n)!=CFBooleanGetTypeID() &&
        !CFNumberIsFloatType((__bridge CFNumberRef)n) && [n compare:@0]!=NSOrderedAscending;
}
static BOOL flag(id n) {
    return [n isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)n)==CFBooleanGetTypeID() && [n boolValue];
}
static NSDictionary *errorInfo(NSError *error){return error?@{@"domain":error.domain,@"code":@(error.code)}:@{};}
static uint32_t word(NSData *d,unsigned n) {uint32_t v;memcpy(&v,(const uint8_t *)d.bytes+n*4,4);return v;}

@implementation A23Short24SDKIO {
    IOUSBHostInterface *_interface;IOUSBHostPipe *_pipe;dispatch_queue_t _queue;
    NSMutableData *_dataStorage,*_transactionStorage;
}
- (instancetype)initWithInterface:(IOUSBHostInterface *)interface pipe:(IOUSBHostPipe *)pipe
    queue:(dispatch_queue_t)queue speed:(NSUInteger)speed error:(NSError **)error {
    if(!interface || !pipe || !queue || speed!=3){fail(error,@"HS prepared objects required");return nil;}
    dispatch_assert_queue(queue);
    const IOUSBInterfaceDescriptor *a=interface.interfaceDescriptor;
    const IOUSBHostIOSourceDescriptors *source=pipe.descriptors;
    const uint8_t *ep=source?(const uint8_t *)&source->descriptor:NULL;
    if(!a || a->bLength!=9 || a->bInterfaceNumber!=2 || a->bAlternateSetting || a->bNumEndpoints!=1 ||
       a->bInterfaceClass!=0xff || a->bInterfaceSubClass!=0x49 || a->bInterfaceProtocol!=1 ||
       !ep || memcmp(ep,(uint8_t[]){7,5,0x83,1,0,1,1},7)) {
        fail(error,@"active interface/endpoint mismatch");return nil;
    }
    if((self=[super init])) {
        _interface=interface;_pipe=pipe;_queue=queue;
        if(@available(macOS 26.4,*)) {
            _dataStorage=[interface dataWithCapacity:3072 options:IOUSBHostObjectDataOptionsNone error:error];
            _transactionStorage=[interface dataWithCapacity:3584 options:IOUSBHostObjectDataOptionsKernelUserShared error:error];
        } else {fail(error,@"mapped storage requires macOS26.4+");return nil;}
        if(_dataStorage.length!=3072 || _transactionStorage.length!=3584) {
            fail(error,@"short24 allocation sizes");return nil;
        }
    }return self;
}
- (BOOL)simulation{return NO;}
- (NSMutableData *)dataStorage{return _dataStorage;}
- (NSMutableData *)transactionStorage{return _transactionStorage;}
- (NSDictionary *)readStatus {
    dispatch_assert_queue(_queue);NSMutableData *data=[NSMutableData dataWithLength:168];NSUInteger count=0;
    IOUSBDeviceRequest request={.bmRequestType=0xc1,.bRequest=0x51,.wValue=0,.wIndex=2,.wLength=168};
    NSError *error=nil;uint64_t begin=A23Short24NowNanoseconds();
    BOOL ok=[_interface sendDeviceRequest:request data:data bytesTransferred:&count completionTimeout:3.0 error:&error];
    NSMutableDictionary *o=[@{@"accepted":@(ok),@"bytes_transferred":@(count),@"begin_ns":@(begin),@"end_ns":@(A23Short24NowNanoseconds()),
        @"control":@[@0xc1,@0x51,@0,@2,@168],@"source":@"sdk_control_reply"} mutableCopy];
    if(error)o[@"error"]=@{@"domain":error.domain,@"code":@(error.code)};
    return @{@"data":[data subdataWithRange:NSMakeRange(0,MIN(count,data.length))],@"observation":o};
}
- (NSDictionary *)frameSample {
    dispatch_assert_queue(_queue);uint64_t begin=A23Short24NowNanoseconds();IOUSBHostTime at=0;
    uint64_t frame=[_interface frameNumberWithTime:&at];
    return @{@"current_frame":@(frame),@"begin_ns":@(begin),@"end_ns":@(A23Short24NowNanoseconds())};
}
- (BOOL)enqueueISO:(uint64_t)frame completion:(IOUSBHostIsochronousTransactionCompletionHandler)completion error:(NSError **)error {
    dispatch_assert_queue(_queue);
    return [_pipe enqueueIORequestWithData:_dataStorage transactionList:_transactionStorage.mutableBytes
        transactionListCount:128 firstFrameNumber:frame options:IOUSBHostIsochronousTransferOptionsNone
        error:error completionHandler:completion];
}
- (BOOL)enqueueBurst:(uint16_t)first completion:(IOUSBHostCompletionHandler)completion error:(NSError **)error {
    dispatch_assert_queue(_queue);
    IOUSBDeviceRequest request={.bmRequestType=0x41,.bRequest=0x54,.wValue=first,.wIndex=2,.wLength=0};
    return [_interface enqueueDeviceRequest:request data:nil completionTimeout:0.016 error:error completionHandler:completion];
}
- (BOOL)abortISO:(NSError **)error {
    dispatch_assert_queue(_queue);return [_pipe abortWithOption:IOUSBHostAbortOptionAsynchronous error:error];
}
@end

@implementation A23Short24Capture {
    id<A23Short24IO> _io;dispatch_queue_t _queue;uint64_t (^_clock)(void);NSString *_recipe;uint16_t _first;
    NSMutableArray *_events,*_reasons;NSData *_before,*_after,*_raw,*_transactions;NSDictionary *_sample;
    A23Short24Capture *_hold;BOOL _started,_stopped,_isoAttempted,_isoAccepted,_triggered,_aborted,_afterRead;
    BOOL _isoPending,_controlPending,_isoHandled,_controlHandled,_ownershipUnknown;uintptr_t _address;
    uint64_t _submitted,_triggerAt,_enqueueReturn,_preparedAt;uint32_t _overall,_controlStatus;NSUInteger _controlBytes;
    atomic_uint _isoCount,_controlCount;atomic_uint_fast64_t _isoArrival,_controlArrival;atomic_bool _fault;
}
- (instancetype)initWithIO:(id<A23Short24IO>)io queue:(dispatch_queue_t)queue
    clockNanoseconds:(uint64_t (^)(void))clock recipe:(NSString *)recipe firstSequence:(uint16_t)first {
    if(!io || !queue || !clock || first==0 || first>65520 || recipe.length!=64 ||
       [recipe rangeOfCharacterFromSet:[[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"] invertedSet]].location!=NSNotFound ||
       io.dataStorage.length!=3072 || io.transactionStorage.length!=3584)return nil;
    dispatch_assert_queue(queue);
    uintptr_t a=(uintptr_t)io.dataStorage.mutableBytes,b=(uintptr_t)io.transactionStorage.mutableBytes;
    if(!a || !b || b%4 || a>UINTPTR_MAX-3072 || b>UINTPTR_MAX-3584 || (a<b+3584 && b<a+3072))return nil;
    if((self=[super init])) {
        _io=io;_queue=queue;_clock=[clock copy];_recipe=[recipe copy];_first=first;_preparedAt=clock();
        _events=[NSMutableArray array];_reasons=[NSMutableArray array];
        atomic_init(&_isoCount,0);atomic_init(&_controlCount,0);atomic_init(&_isoArrival,0);
        atomic_init(&_controlArrival,0);atomic_init(&_fault,false);
        memset(io.dataStorage.mutableBytes,0,3072);memset(io.transactionStorage.mutableBytes,0,3584);
        IOUSBHostIsochronousTransaction *rows=io.transactionStorage.mutableBytes;
        for(unsigned i=0;i<128;i++){rows[i].status=kIOReturnInvalid;rows[i].requestCount=24;rows[i].offset=i*24;}
    }return self;
}
- (void)event:(NSString *)name details:(NSDictionary *)details {
    if(_events.count<64)[_events addObject:@{@"event":name,@"ns":@(_clock()),@"details":details}];
    else {_stopped=YES;atomic_store(&_fault,true);if(![_reasons containsObject:@"event_capacity"])[_reasons addObject:@"event_capacity"];}
}
- (void)stop:(NSString *)why {
    _stopped=YES;if(![_reasons containsObject:why]){[_reasons addObject:why];[self event:@"stop" details:@{@"reason":why}];}
}
- (BOOL)replyValid:(NSDictionary *)reply lower:(uint64_t)lower {
    NSData *data=reply[@"data"];NSDictionary *o=reply[@"observation"];
    return [data isKindOfClass:NSData.class] && data.length==168 && flag(o[@"accepted"]) && !o[@"error"] &&
        number(o[@"bytes_transferred"]) && [o[@"bytes_transferred"] unsignedLongLongValue]==168 &&
        number(o[@"begin_ns"]) && number(o[@"end_ns"]) && [o[@"begin_ns"] unsignedLongLongValue]>=lower &&
        [o[@"end_ns"] unsignedLongLongValue]>=[o[@"begin_ns"] unsignedLongLongValue] &&
        [o[@"end_ns"] unsignedLongLongValue]<=_clock() && [o[@"source"] isEqual:@"sdk_control_reply"] &&
        [o[@"control"] isEqual:@[@0xc1,@0x51,@0,@2,@168]];
}
- (BOOL)start {
    dispatch_assert_queue(_queue);if(_started || _stopped || atomic_load(&_fault))return NO;
    _started=YES;_hold=self;NSDictionary *before=[_io readStatus];_before=[before[@"data"] copy];
    [self event:@"before" details:before[@"observation"] ?: @{}];
    BOOL fresh=[self replyValid:before lower:_preparedAt] && word(_before,0)==0x31505349 && word(_before,1)==1 &&
        word(_before,11)==0x83 && (word(_before,10)==0 || word(_before,10)==3);
    for(unsigned n=2;fresh && n<14;n++)if(n!=10 && n!=11 && word(_before,n))fresh=NO;
    if(!fresh){[self stop:@"before_invalid"];return NO;}
    _sample=[[_io frameSample] copy];uint64_t now=_clock();
    BOOL sample=number(_sample[@"current_frame"]) && [_sample[@"current_frame"] unsignedLongLongValue]>0 &&
        [_sample[@"current_frame"] unsignedLongLongValue]<=UINT64_MAX-32 &&
        number(_sample[@"begin_ns"]) && number(_sample[@"end_ns"]) &&
        [_sample[@"begin_ns"] unsignedLongLongValue]>=[before[@"observation"][@"end_ns"] unsignedLongLongValue] &&
        [_sample[@"end_ns"] unsignedLongLongValue]>=[_sample[@"begin_ns"] unsignedLongLongValue] &&
        [_sample[@"end_ns"] unsignedLongLongValue]<=now && now-[_sample[@"begin_ns"] unsignedLongLongValue]<=2000000;
    if(!sample || atomic_load(&_fault)){[self stop:@"frame_invalid_or_interest"];return NO;}
    [self event:@"iso_intent" details:@{@"first_frame":@([_sample[@"current_frame"] unsignedLongLongValue]+32)}];
    _isoAttempted=YES;_isoPending=YES;_address=(uintptr_t)_io.transactionStorage.mutableBytes;_submitted=_clock();
    NSError *error=nil;
    _isoAccepted=[_io enqueueISO:[_sample[@"current_frame"] unsignedLongLongValue]+32
        completion:^(IOReturn status,IOUSBHostIsochronousTransaction *rows) {
            uint64_t arrival=self->_clock();unsigned count=atomic_fetch_add(&self->_isoCount,1)+1;
            if(count==1)atomic_store(&self->_isoArrival,arrival);else atomic_store(&self->_fault,true);
            dispatch_async(self->_queue,^{
                [self event:@"iso_callback" details:@{@"count":@(count),@"arrival_ns":@(arrival),@"status_u32":@((uint32_t)status),
                    @"pointer_match":@((BOOL)((uintptr_t)rows==self->_address))}];
                if(count!=1){[self stop:@"duplicate_iso"];return;}
                self->_overall=(uint32_t)status;self->_isoPending=NO;self->_isoHandled=YES;
                self->_raw=[NSData dataWithData:self->_io.dataStorage];self->_transactions=[NSData dataWithData:self->_io.transactionStorage];
                if((uintptr_t)rows!=self->_address){self->_ownershipUnknown=YES;[self stop:@"foreign_transaction_pointer"];}
                if(status!=kIOReturnSuccess)[self stop:@"iso_native_error"];
            });
        } error:&error];
    _enqueueReturn=_clock();[self event:@"iso_return" details:@{@"accepted":@(_isoAccepted),@"error":@((BOOL)(error!=nil)),@"error_info":errorInfo(error)}];
    if(!_isoAccepted || error || _enqueueReturn<_submitted || _enqueueReturn-_submitted>8000000 ||
       _enqueueReturn-[_sample[@"begin_ns"] unsignedLongLongValue]>16000000) {
        if(!_isoAccepted || error)_ownershipUnknown=YES;
        [self stop:@"iso_enqueue_rejected_or_budget"];[self poll];return NO;
    }
    if(_stopped || atomic_load(&_fault) || atomic_load(&_isoCount) || _clock()<_enqueueReturn ||
       _clock()-_enqueueReturn>8000000 || _clock()-[_sample[@"begin_ns"] unsignedLongLongValue]>32000000) {
        [self stop:@"trigger_admission"];[self poll];return NO;
    }
    [self event:@"burst_intent" details:@{@"first_sequence":@(_first)}];
    now=_clock();
    if(_stopped || atomic_load(&_fault) || atomic_load(&_isoCount) || now<_enqueueReturn ||
       now-_enqueueReturn>8000000 || now-[_sample[@"begin_ns"] unsignedLongLongValue]>32000000) {
        [self stop:@"trigger_admission"];[self poll];return NO;
    }
    _triggered=YES;_controlPending=YES;_triggerAt=now;
    error=nil;BOOL triggered=[_io enqueueBurst:_first completion:^(IOReturn status,NSUInteger bytes) {
        uint64_t arrival=self->_clock();unsigned count=atomic_fetch_add(&self->_controlCount,1)+1;
        if(count==1)atomic_store(&self->_controlArrival,arrival);else atomic_store(&self->_fault,true);
        dispatch_async(self->_queue,^{
            [self event:@"control_callback" details:@{@"count":@(count),@"arrival_ns":@(arrival),@"status_u32":@((uint32_t)status),@"bytes":@(bytes)}];
            if(count!=1){[self stop:@"duplicate_control"];return;}
            self->_controlHandled=YES;self->_controlPending=NO;self->_controlStatus=(uint32_t)status;self->_controlBytes=bytes;
            if(status!=kIOReturnSuccess || bytes)[self stop:@"control_native_error"];
        });
    } error:&error];
    [self event:@"burst_return" details:@{@"accepted":@(triggered),@"error":@((BOOL)(error!=nil)),@"error_info":errorInfo(error)}];
    if(!triggered || error){_ownershipUnknown=YES;[self stop:@"burst_enqueue_rejected"];}
    [self poll];return triggered && !_stopped;
}
- (void)poll {
    dispatch_assert_queue(_queue);if(!_started)return;
    if(atomic_load(&_fault))[self stop:@"ingress_fault"];
    uint64_t now=_clock(),iso=atomic_load(&_isoArrival),control=atomic_load(&_controlArrival);
    if(_triggered && ((control && control>=_triggerAt && control-_triggerAt>16000000) ||
        (!control && now>=_triggerAt && now-_triggerAt>16000000)))[self stop:@"control_deadline"];
    if(_isoAttempted && ((iso && iso>=_submitted && iso-_submitted>2000000000) ||
        (!iso && now>=_submitted && now-_submitted>2000000000)))[self stop:@"iso_deadline"];
    if(_stopped && _isoAccepted && !_aborted && !iso) {
        _aborted=YES;NSError *error=nil;BOOL ok=[_io abortISO:&error];
        [self event:@"abort_return" details:@{@"accepted":@(ok),@"error":@((BOOL)(error!=nil)),@"error_info":errorInfo(error)}];
        if(!ok || error)[self stop:@"abort_error"];
    }
    if(!_stopped && _isoHandled && _controlHandled && !_afterRead) {
        _afterRead=YES;NSDictionary *reply=[_io readStatus];_after=[reply[@"data"] copy];
        [self event:@"after" details:reply[@"observation"] ?: @{}];
        if(![self replyValid:reply lower:MAX(iso,control)])[self stop:@"after_invalid"];
    }
}
- (void)requestStop {dispatch_assert_queue(_queue);[self stop:@"requested_stop"];[self poll];}
- (void)providerInterest:(uint32_t)message {
    atomic_store(&_fault,true);dispatch_async(_queue,^{[self event:@"interest" details:@{@"message_u32":@(message)}];
        [self stop:@"provider_interest"];[self poll];});
}
- (NSDictionary *)result {
    dispatch_assert_queue(_queue);
    return @{@"schema":@"A23-short24-session-1",@"first_sequence":@(_first),@"recipe":_recipe,
        @"execution_mode":_io.simulation?@"injected_model":@"sdk_observation",@"started":@(_started),
        @"iso_attempts":@((unsigned)_isoAttempted),@"iso_accepted":@(_isoAccepted),@"burst_attempts":@((unsigned)_triggered),
        @"iso_callbacks":@(atomic_load(&_isoCount)),@"control_callbacks":@(atomic_load(&_controlCount)),
        @"iso_arrival_ns":@(atomic_load(&_isoArrival)),@"control_arrival_ns":@(atomic_load(&_controlArrival)),
        @"submit_ns":@(_submitted),@"trigger_ns":@(_triggerAt),@"overall_u32":@(_overall),
        @"enqueue_return_ns":@(_enqueueReturn),@"frame_sample":_sample ?: @{},@"packet_bytes":@24,@"transaction_count":@128,
        @"control_status_u32":@(_controlStatus),@"control_bytes":@(_controlBytes),
        @"after_reads":@((unsigned)_afterRead),@"abort_attempts":@((unsigned)_aborted),@"stopped":@(_stopped),
        @"io_unresolved":@((BOOL)(_isoPending || _controlPending || _ownershipUnknown)),@"resources_retained":@(_started),
        @"observation_complete":@((BOOL)(_afterRead && !_stopped && !atomic_load(&_fault))),
        @"process_exit_authorized":@NO,@"buffer_reuse_verified":@NO,@"callback_drain_verified":@NO,
        @"hardware_verified":@NO,@"continuous_audio_verified":@NO,@"failure_reasons":[_reasons copy],@"events":[_events copy]};
}
- (NSDictionary *)snapshot {
    dispatch_assert_queue(_queue);return @{@"metadata":self.result,@"before":_before ?: [NSData data],@"after":_after ?: [NSData data],
        @"raw":_raw ?: [NSData dataWithData:_io.dataStorage],@"transactions":_transactions ?: [NSData dataWithData:_io.transactionStorage]};
}
@end
