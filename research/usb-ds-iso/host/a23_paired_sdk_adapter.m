#import "a23_paired_sdk_adapter.h"
#include <stdatomic.h>
#include <mach/mach_time.h>
#include <string.h>

static BOOL adapterError(NSError **error,NSString *why) {
    if(error)*error=[NSError errorWithDomain:@"A23PairedSDK" code:1 userInfo:@{NSLocalizedDescriptionKey:why}];
    return NO;
}
// SDK accessor bodies retain the old adapter's exact API calls. Only the
// burst selector/value is distinct; the paired lease enforces its finite scope.
@interface A23PairedSDKInterface : NSObject <A23PairedInterface>
- (instancetype)initWithInterface:(IOUSBHostInterface *)interface;
@end
@implementation A23PairedSDKInterface {
    IOUSBHostInterface *_interface;
    IOUSBHostPipe *_pipe;
}
- (instancetype)initWithInterface:(IOUSBHostInterface *)interface
{
    if ((self = [super init])) _interface = interface;
    return self;
}
- (NSDictionary *)descriptorBytes:(NSError **)error
{
    const IOUSBDeviceDescriptor *device = _interface.deviceDescriptor;
    const IOUSBConfigurationDescriptor *config = _interface.configurationDescriptor;
    const IOUSBInterfaceDescriptor *active = _interface.interfaceDescriptor;
    // Cache-owned pointers are valid only while the SDK object remains alive.
    // A device descriptor lookup may issue GET_DESCRIPTOR: not read-only USB.
    if (!device || !config || !active || device->bLength != 18 || config->bLength != 9 ||
        active->bLength != 9 || active->bInterfaceNumber != 2 || active->bAlternateSetting != 0) {
        adapterError(error,@"Missing/invalid active SDK descriptor"); return nil;
    }
    const uint8_t *c = (const uint8_t *)config;
    NSUInteger length = (NSUInteger)c[2] | (NSUInteger)c[3] << 8;
    if (length < 9 || length > 65535) { adapterError(error,@"Invalid cached configuration length"); return nil; }
    return @{@"device_descriptor":[NSData dataWithBytes:device length:18],
        @"configuration_descriptor":[NSData dataWithBytes:config length:length],
        @"active_interface":[NSData dataWithBytes:active length:9]};
}
- (id<A23TransactionTransport>)copyTransport:(NSError **)error
{
    if (_pipe) { adapterError(error,@"Pipe already copied"); return nil; }
    _pipe = [_interface copyPipeWithAddress:0x83 error:error];
    return _pipe ? [[A23ExistingPipeTransport alloc] initWithPipe:_pipe] : nil;
}
- (NSData *)currentEndpointBytes
{
    const IOUSBHostIOSourceDescriptors *descriptors = _pipe.descriptors;
    return descriptors ? [NSData dataWithBytes:&descriptors->descriptor length:7] : nil;
}
- (NSMutableData *)allocate:(NSUInteger)length shared:(BOOL)shared error:(NSError **)error
{
    if (@available(macOS 26.4, *)) {
        return [_interface dataWithCapacity:length options:shared ? IOUSBHostObjectDataOptionsKernelUserShared :
            IOUSBHostObjectDataOptionsNone error:error];
    }
    adapterError(error,@"SDK mapped data requires macOS26.4+"); return nil;
}
- (NSDictionary *)readStatus
{
    NSAssert(A23NoTDControlAllowed(0xc1,0x51,0,2,168),@"Fixed no-TD STATUS tuple required");
    NSMutableData *data = [NSMutableData dataWithLength:168]; NSUInteger transferred = 0;
    IOUSBDeviceRequest request = {0};
    request.bmRequestType = 0xc1; request.bRequest = 0x51;
    request.wValue = 0; request.wIndex = 2; request.wLength = 168;
    NSError *error = nil; uint64_t begin = mach_absolute_time();
    BOOL accepted = [_interface sendDeviceRequest:request data:data bytesTransferred:&transferred
        completionTimeout:3.0 error:&error];
    uint64_t end = mach_absolute_time();
    NSMutableDictionary *observation = [@{@"source":@"sdk_control_reply", @"accepted":@(accepted),
        @"bytes_transferred":@(transferred), @"begin_ticks":@(begin), @"end_ticks":@(end),
        @"control":@{@"request_type":@0xc1, @"request":@0x51, @"value":@0, @"index":@2,
                     @"length":@168, @"timeout_ms":@3000}} mutableCopy];
    if (error) observation[@"error"] = @{@"domain":error.domain, @"code":@(error.code)};
    // Report count unchanged, including overflow. Never read beyond capacity or
    // pad a short reply to 168 bytes as if the bytes had arrived from USB.
    return @{@"data":[data subdataWithRange:NSMakeRange(0,MIN(transferred,data.length))],
        @"observation":observation};
}
- (NSDictionary *)readFrameSample
{
    IOUSBHostTime atTime = 0; uint64_t begin = mach_absolute_time();
    uint64_t frame = [_interface frameNumberWithTime:&atTime]; uint64_t end = mach_absolute_time();
    return @{@"source":@"sdk_frame_number",@"current_frame":@(frame),@"frame_time":@(atTime),
        @"begin_ticks":@(begin),@"end_ticks":@(end)};
}
- (BOOL)enqueueScopedBurst:(uint16_t)first completion:(IOUSBHostCompletionHandler)completion error:(NSError **)error
{
    if (!first || !completion) return adapterError(error,@"Scoped sequence/completion required");
    IOUSBDeviceRequest request={.bmRequestType=0x41,.bRequest=0x54,.wValue=first,.wIndex=2,.wLength=0};
    return [_interface enqueueDeviceRequest:request data:nil completionTimeout:0.016 error:error completionHandler:completion];
}
- (void)destroy
{
    _pipe = nil;
    [_interface destroy]; _interface = nil;
}
@end

@implementation A23PairedSDKOperations
- (id<A23AdapterInterface>)openService:(io_service_t)service queue:(dispatch_queue_t)queue
    interest:(A23AdapterInterest)interest error:(NSError **)error
{
    IOUSBHostInterface *interface = [[IOUSBHostInterface alloc] initWithIOService:service
        options:IOUSBHostObjectInitOptionsNone queue:queue error:error
        interestHandler:^(IOUSBHostObject *object, uint32_t message, void *argument) {
            (void)object; (void)argument;
            // Paired provider latches native ingress atomically, then queues state.
            interest(message);
        }];
    return interface ? [[A23PairedSDKInterface alloc] initWithInterface:interface] : nil;
}
@end


static BOOL positive(id v) {
    return [v isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)v)!=CFBooleanGetTypeID() &&
        !CFNumberIsFloatType((__bridge CFNumberRef)v) && [v compare:@0]==NSOrderedDescending;
}
static NSDictionary *identity(id v) {
    if(![v isKindOfClass:NSDictionary.class])return nil;
    NSMutableDictionary *copy=[NSMutableDictionary new];
    for(NSString *k in @[@"device_id",@"interface_id",@"parent_device_id",@"connection_speed"]){
        if(!positive(v[k]))return nil;copy[k]=v[k];}
    if(![copy[@"device_id"] isEqual:copy[@"parent_device_id"]] || [copy[@"device_id"] isEqual:copy[@"interface_id"]] || ![copy[@"connection_speed"] isEqual:@3])return nil;
    return [copy copy];
}
@interface A23PairSignal : NSObject { @public atomic_bool arrived; }
@end
@implementation A23PairSignal
- (instancetype)init {if((self=[super init]))atomic_init(&arrived,false);return self;}
@end

@interface A23PairLease : NSObject <A23PairedResources,A23TransactionTransport>
@property id<A23AdapterOperations> operations;
@property id<A23PairedInterface> interface;
@property id<A23TransactionTransport> pipe;
@property NSDictionary *identity,*descriptorBytes;
@property NSArray<NSMutableData *> *dataStores,*transactionStores;
@property A23PairSignal *signal;
@property NSMutableArray *partialStores;
@property BOOL simulationMode;
@property dispatch_queue_t queue;
@property(nonatomic) io_service_t service;
@property uint16_t first;
@property(nonatomic) BOOL ready;
- (BOOL)preparationHealthy;
- (void)pin;
@end
@implementation A23PairLease {
    BOOL _reference,_closed,_touched,_invalid,_abortAttempted;
    NSUInteger _isoAttempts,_triggers,_statusReads,_frameReads,_aborts;
    uintptr_t _dataAddress[2],_rowAddress[2];
    atomic_uint _isoCount[2],_controlCount[2];atomic_bool _badIngress,_triggerEntered[2],_isoOK[2],_controlOK[2];
    BOOL _accepted[2];A23PairLease *_hold;
}
- (instancetype)init {
    if((self=[super init])){_dataStores=@[];_transactionStores=@[];_identity=@{};_descriptorBytes=@{};_partialStores=[NSMutableArray new];_signal=[A23PairSignal new];
        atomic_init(&_badIngress,false);
        for(unsigned i=0;i<2;++i){atomic_init(&_isoCount[i],0);atomic_init(&_controlCount[i],0);atomic_init(&_triggerEntered[i],false);atomic_init(&_isoOK[i],false);atomic_init(&_controlOK[i],false);}}
    return self;
}
- (void)setService:(io_service_t)service {_service=service;_reference=service!=0;_hold=self;}
- (void)pin {_hold=self;_invalid=YES;}
- (BOOL)preparationHealthy {return !_closed && _operations.simulation==_simulationMode && !atomic_load(&_signal->arrived) && !atomic_load(&_badIngress);}
- (BOOL)offlineSimulation {return _simulationMode;}
- (BOOL)sdkResources {return !_simulationMode && _ready && !_closed;}
- (id<A23TransactionTransport>)transport {return self;}
- (void)setReady:(BOOL)ready {
    _ready=ready;
    if(ready)for(unsigned n=0;n<2;++n){_dataAddress[n]=(uintptr_t)_dataStores[n].mutableBytes;_rowAddress[n]=(uintptr_t)_transactionStores[n].mutableBytes;}
}
- (BOOL)check {
    dispatch_assert_queue(_queue);
    if(!_ready || _closed)return NO;
    BOOL valid=[self preparationHealthy] && !_invalid && _dataStores.count==2 && _transactionStores.count==2;
    for(unsigned n=0;valid && n<2;++n)valid=_dataStores[n].length==184320 && _transactionStores[n].length==26880 &&
        (uintptr_t)_dataStores[n].mutableBytes==_dataAddress[n] && (uintptr_t)_transactionStores[n].mutableBytes==_rowAddress[n];
    if(!valid)[self pin];return valid;
}
- (BOOL)terminal:(NSUInteger)n {
    return atomic_load(&_isoCount[n])==1 && atomic_load(&_controlCount[n])==1 && atomic_load(&_isoOK[n]) && atomic_load(&_controlOK[n]);
}
- (NSDictionary *)readStatus {
    if(![self check])return @{};
    BOOL order=(_statusReads==0 && _isoAttempts==0) ||
        ((_statusReads==1 || _statusReads==2) && _isoAttempts==1 && [self terminal:0]) ||
        (_statusReads==3 && _isoAttempts==2 && [self terminal:1]);
    if(!order){[self pin];return @{};}
    _touched=YES;_hold=self;++_statusReads;NSDictionary *reply=[_interface readStatus];
    if(![reply isKindOfClass:NSDictionary.class]){[self pin];return @{};}
    NSData *raw=reply[@"data"];NSDictionary *o=reply[@"observation"];
    id accepted=[o isKindOfClass:NSDictionary.class] ? o[@"accepted"] : nil;
    id count=[o isKindOfClass:NSDictionary.class] ? o[@"bytes_transferred"] : nil;
    if(![raw isKindOfClass:NSData.class] || raw.length!=168 || ![accepted isKindOfClass:NSNumber.class] ||
        CFGetTypeID((__bridge CFTypeRef)accepted)!=CFBooleanGetTypeID() || ![accepted boolValue] || o[@"error"] || !positive(count) || ![count isEqual:@168])[self pin];
    return reply; // Preserve short/error/count observations without relabeling.
}
- (NSDictionary *)readFrameSample {
    if(![self check])return @{};
    if(_frameReads>=2 || _isoAttempts!=_frameReads || _statusReads!=1+_frameReads*2 || (_frameReads && ![self terminal:0])){[self pin];return @{};}
    _touched=YES;_hold=self;++_frameReads;return [_interface readFrameSample];
}
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows transactionListCount:(NSUInteger)count
    firstFrameNumber:(uint64_t)frame options:(IOUSBHostIsochronousTransferOptions)options error:(NSError **)error
    completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion {
    if(![self check])return adapterError(error,@"Paired lease is not usable");NSUInteger n=_isoAttempts;
    BOOL valid=n<2 && _frameReads==n+1 && _statusReads==1+n*2 && (!n || [self terminal:0]) && frame && options==0 && count==960 && completion;
    if(valid)valid=data==_dataStores[n] && (uintptr_t)rows==_rowAddress[n];
    if(valid)for(unsigned i=0;i<960;++i)if(rows[i].status!=kIOReturnInvalid || rows[i].requestCount!=192 || rows[i].offset!=i*192 || rows[i].completeCount || rows[i].options || rows[i].timeStamp){valid=NO;break;}
    if(!valid){[self pin];return adapterError(error,@"Fixed paired epoch/ISO tuple rejected");}
    _touched=YES;_hold=self;++_isoAttempts;
    NSError *nativeError=nil;
    BOOL accepted=[_pipe enqueueIORequestWithData:data transactionList:rows transactionListCount:count firstFrameNumber:frame options:options error:&nativeError
        completionHandler:^(IOReturn status,IOUSBHostIsochronousTransaction *p){
            unsigned calls=atomic_fetch_add(&self->_isoCount[n],1)+1;
            BOOL ok=calls==1 && !status && (uintptr_t)p==self->_rowAddress[n] && atomic_load(&self->_triggerEntered[n]);
            if(ok)atomic_store(&self->_isoOK[n],true);else atomic_store(&self->_badIngress,true);
            completion(status,p);
        }];
    _accepted[n]=accepted;if(error)*error=nativeError;if(!accepted || nativeError)[self pin];return accepted;
}
- (BOOL)enqueueBurst:(uint16_t)first completion:(IOUSBHostCompletionHandler)completion error:(NSError **)error {
    if(![self check])return adapterError(error,@"Paired lease is not usable");NSUInteger n=_triggers;
    if(n>=2 || first!=_first+n*16 || _isoAttempts!=n+1 || !_accepted[n] || atomic_load(&_isoCount[n]) || !completion){
        [self pin];return adapterError(error,@"Fixed paired BURST tuple/order rejected");}
    ++_triggers;_touched=YES;_hold=self;atomic_store(&_triggerEntered[n],true);
    NSError *nativeError=nil;
    BOOL accepted=[_interface enqueueScopedBurst:first completion:^(IOReturn status,NSUInteger bytes){
        unsigned calls=atomic_fetch_add(&self->_controlCount[n],1)+1;
        if(calls==1 && !status && !bytes)atomic_store(&self->_controlOK[n],true);else atomic_store(&self->_badIngress,true);
        completion(status,bytes);
    } error:&nativeError];
    if(error)*error=nativeError;if(!accepted || nativeError)[self pin];return accepted;
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error {
    dispatch_assert_queue(_queue);
    if(!_ready || _closed || atomic_load(&_signal->arrived) || !_isoAttempts || _abortAttempted || option!=IOUSBHostAbortOptionAsynchronous || atomic_load(&_isoCount[_isoAttempts-1]))return NO;
    _abortAttempted=YES;_invalid=YES;_hold=self;++_aborts;return [_pipe abortWithOption:option error:error];
}
- (BOOL)closeUnused {
    dispatch_assert_queue(_queue);if(_closed)return YES;
    if(_touched){_hold=self;return NO;}
    if(_invalid || ![self preparationHealthy]){[self pin];return NO;}
    _closed=YES;_ready=NO;_dataStores=@[];_transactionStores=@[];[_partialStores removeAllObjects];_pipe=nil;
    [_interface destroy];_interface=nil;
    if(_reference){[_operations releaseService:_service];_reference=NO;_service=0;}
    _operations=nil;_hold=nil;return YES;
}
- (NSDictionary *)result {
    dispatch_assert_queue(_queue);if(_ready)[self check];
    return @{@"schema":@"A23-paired-resource-result-1",@"execution_mode":_simulationMode ? @"offline_simulation" : @"sdk_capability",@"ready":@(_ready),@"closed_unused":@(_closed),@"runtime_touched":@(_touched),
        @"poisoned":@((BOOL)(_invalid || atomic_load(&_badIngress) || atomic_load(&_signal->arrived))),@"interest_seen":@(atomic_load(&_signal->arrived)),
        @"iso_attempts":@(_isoAttempts),@"trigger_attempts":@(_triggers),@"status_reads":@(_statusReads),@"frame_reads":@(_frameReads),@"aborts":@(_aborts),
        @"iso_callbacks":@[@(atomic_load(&_isoCount[0])),@(atomic_load(&_isoCount[1]))],@"control_callbacks":@[@(atomic_load(&_controlCount[0])),@(atomic_load(&_controlCount[1]))],
        @"service_retained":@(_reference),@"store_count":@(_dataStores.count+_transactionStores.count+_partialStores.count),@"continuation_save_verified":@NO,
        @"callback_drain_verified":@NO,@"hardware_entry_enabled":@NO,@"hardware_verified":@NO};
}
@end

@implementation A23PairedSimulationProvider {
    id<A23AdapterOperations> _operations;dispatch_queue_t _queue;A23AdapterInterest _interest;uint16_t _first;
    BOOL _attempted,_quarantined,_cleaned;NSString *_stage;id<A23PairedResources> _failure;
}
- (instancetype)initWithOperations:(id<A23AdapterOperations>)operations queue:(dispatch_queue_t)queue interest:(A23AdapterInterest)interest firstSequence:(uint16_t)first {
    if(!operations || !queue || !interest || first<81 || first>65504 || first%16!=1)return nil;
    if((self=[super init])){_operations=operations;_queue=queue;_interest=[interest copy];_first=first;_stage=@"not_attempted";}return self;
}
- (BOOL)requiresSimulation {return YES;}
- (id<A23PairedResources>)openCandidate:(NSDictionary *)candidate error:(NSError **)error {
    NSError *nativeError=nil;id<A23PairedResources> lease=[self prepareCandidate:candidate error:&nativeError];
    if(error)*error=nativeError;return lease;
}
- (id<A23PairedResources>)prepareCandidate:(NSDictionary *)candidate error:(NSError **)error {
    dispatch_assert_queue(_queue);if(error)*error=nil;
    if(_attempted){adapterError(error,@"Preparation attempt already consumed");return nil;}_attempted=YES;
    _stage=@"operations_mode";
    BOOL mode=_operations.simulation;
    if(mode!=[self requiresSimulation]){adapterError(error,@"Provider/operations mode mismatch");return nil;}
    _stage=@"candidate";if(![candidate isKindOfClass:NSDictionary.class]){adapterError(error,@"Candidate dictionary required");return nil;}
    id token=candidate[@"service_token"];NSDictionary *expected=identity(candidate);
    if(!positive(token) || [token unsignedLongLongValue]>UINT32_MAX || !expected){adapterError(error,@"Fixed borrowed token/HS identity required");return nil;}
    A23PairLease *lease=[A23PairLease new];lease.queue=_queue;lease.operations=_operations;lease.simulationMode=mode;lease.first=_first;
    _stage=@"retain_service";BOOL retained=[_operations retainService:[token unsignedIntValue] error:error];
    if(!retained)return nil;lease.service=[token unsignedIntValue];
    BOOL valid=!(error && *error);NSDictionary *before=nil;
    if(valid){_stage=@"identity_before";before=identity([_operations identityForService:lease.service error:error]);valid=before && [before isEqual:expected] && !(error && *error);}
    if(valid){
        _stage=@"sdk_open";A23PairSignal *signal=lease.signal;__weak A23PairLease *weak=lease;
        A23AdapterInterest interest=_interest;dispatch_queue_t q=_queue;
        lease.interface=(id<A23PairedInterface>)[_operations openService:lease.service queue:q interest:^(uint32_t message){
            atomic_store(&signal->arrived,true);
            dispatch_async(q,^{[weak pin];interest(message);});
        } error:error];
        valid=lease.interface && [lease.interface respondsToSelector:@selector(enqueueScopedBurst:completion:error:)] &&
            [lease.interface respondsToSelector:@selector(readFrameSample)] && !(error && *error) && [lease preparationHealthy];
    }
    if(valid){_stage=@"identity_after_open";valid=[before isEqual:identity([_operations identityForService:lease.service error:error])] && !(error && *error) && [lease preparationHealthy];}
    if(valid){
        _stage=@"descriptors";NSDictionary *raw=[lease.interface descriptorBytes:error];NSMutableDictionary *desc=[NSMutableDictionary new];
        valid=[raw isKindOfClass:NSDictionary.class] && !(error && *error);
        if(valid)for(NSString *k in @[@"device_descriptor",@"configuration_descriptor",@"active_interface"]){id v=raw[k];if(![v isKindOfClass:NSData.class] || [v length]>1024){valid=NO;break;}desc[k]=[v copy];}
        if(valid){NSData *active=desc[@"active_interface"];const uint8_t *a=active.bytes;
            valid=A23ValidateDescriptors(desc[@"device_descriptor"],desc[@"configuration_descriptor"],3,error)!=nil && active.length==9 &&
                a[0]==9 && a[1]==4 && a[2]==2 && a[3]==0 && a[4]==1 && a[5]==0xff && a[6]==0x49 && a[7]==1;}
        lease.descriptorBytes=[desc copy];valid=valid && [lease preparationHealthy];
    }
    if(valid){_stage=@"copy_pipe";lease.pipe=[lease.interface copyTransport:error];valid=lease.pipe && !(error && *error) && [lease preparationHealthy];}
    if(valid){_stage=@"endpoint";NSData *endpoint=[lease.interface currentEndpointBytes];const uint8_t *e=endpoint.bytes;
        valid=[endpoint isKindOfClass:NSData.class] && endpoint.length==7 && e[0]==7 && e[1]==5 && e[2]==0x83 && e[3]==1 && e[4]==0 && e[5]==1 && e[6]==1 && [lease preparationHealthy];}
    NSMutableArray<NSMutableData *> *all=[NSMutableArray new];
    for(NSUInteger i=0;valid && i<4;++i){
        _stage=[NSString stringWithFormat:@"allocate_%lu",(unsigned long)i];NSUInteger size=i%2 ? 26880 : 184320;
        NSMutableData *data=[lease.interface allocate:size shared:(BOOL)(i%2) error:error];
        if(data)[lease.partialStores addObject:data];
        valid=[data isKindOfClass:NSMutableData.class] && data.length==size && !(error && *error) && [lease preparationHealthy];
        if(valid){uintptr_t x=(uintptr_t)data.mutableBytes;valid=x && x<=UINTPTR_MAX-size && (!(i%2) || x%_Alignof(IOUSBHostIsochronousTransaction)==0);
            for(NSMutableData *old in all){uintptr_t y=(uintptr_t)old.mutableBytes;valid=valid && (x+size<=y || y+old.length<=x);}}
        if(valid)[all addObject:data];
    }
    if(valid){_stage=@"identity_after_allocations";valid=[before isEqual:identity([_operations identityForService:lease.service error:error])] && !(error && *error) && [lease preparationHealthy];}
    if(!valid){
        if(!error || !*error)adapterError(error,[NSString stringWithFormat:@"Paired preparation failed at %@",_stage]);
        _cleaned=[lease closeUnused];_quarantined=!_cleaned;if(_quarantined)_failure=lease;return nil;
    }
    lease.dataStores=@[all[0],all[2]];lease.transactionStores=@[all[1],all[3]];
    for(NSMutableData *data in all)memset(data.mutableBytes,0,data.length);
    [lease.partialStores removeAllObjects];
    if(![lease preparationHealthy]){_stage=@"publish_interest";adapterError(error,@"Interest/mode changed before publication");[lease pin];_failure=lease;_quarantined=YES;return nil;}
    lease.identity=@{@"device_id":before[@"device_id"],@"interface_id":before[@"interface_id"],@"parent_device_id":before[@"parent_device_id"]};
    lease.ready=YES;_stage=@"prepared";return lease;
}
- (id<A23PairedResources>)retainedFailure {dispatch_assert_queue(_queue);return _failure;}
- (NSDictionary *)result {dispatch_assert_queue(_queue);return @{@"schema":@"A23-paired-provider-result-1",@"attempt_consumed":@(_attempted),@"stage":_stage,
    @"failed_preparation_cleaned":@(_cleaned),@"failed_preparation_quarantined":@(_quarantined),@"hardware_entry_enabled":@NO,@"hardware_verified":@NO};}
@end
@implementation A23PairedSDKProvider
- (BOOL)requiresSimulation {return NO;}
@end
