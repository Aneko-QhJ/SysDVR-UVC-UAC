#import "io_usb_host_sdk_adapter.h"
#include <IOKit/IOKitLib.h>
#include <mach/mach_time.h>
#include <string.h>

static BOOL adapterError(NSError **error, NSString *message)
{
    if (error) *error = [NSError errorWithDomain:@"A23SDKAdapter" code:1
        userInfo:@{NSLocalizedDescriptionKey:message}];
    return NO;
}
static void preparationFailure(NSError **error, NSString *stage)
{
    if (!error) return;
    if (!*error) adapterError(error,@"Post-open descriptor/pipe/allocation mismatch");
    NSMutableDictionary *info = [(*error).userInfo mutableCopy];
    info[@"A23PreparationStage"] = stage;
    *error = [NSError errorWithDomain:(*error).domain code:(*error).code userInfo:info];
}
static BOOL identityValue(id value)
{
    return [value isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)value) != CFBooleanGetTypeID() &&
        !CFNumberIsFloatType((__bridge CFNumberRef)value) && [value compare:@0] == NSOrderedDescending;
}

@interface A23SDKInterface : NSObject <A23AdapterBurstInterface>
- (instancetype)initWithInterface:(IOUSBHostInterface *)interface;
@end
@implementation A23SDKInterface {
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
- (BOOL)enqueueSequenceOneBurst:(IOUSBHostCompletionHandler)completion error:(NSError **)error
{
    IOUSBDeviceRequest request={.bmRequestType=0x41,.bRequest=0x54,.wValue=1,.wIndex=2,.wLength=0};
    // Requested SDK timeout only; no claim of a 16ms hardware deadline.
    return [_interface enqueueDeviceRequest:request data:nil completionTimeout:0.016 error:error completionHandler:completion];
}
- (void)destroy
{
    _pipe = nil;
    [_interface destroy]; _interface = nil;
}
@end

@implementation A23DormantSDKOperations
- (BOOL)simulation { return NO; }
- (BOOL)retainService:(io_service_t)service error:(NSError **)error
{
    if (service && IOObjectRetain(service) == KERN_SUCCESS) return YES;
    return adapterError(error,@"Service reference retain failed");
}
- (void)releaseService:(io_service_t)service { if (service) IOObjectRelease(service); }
- (NSDictionary *)identityForService:(io_service_t)service error:(NSError **)error
{
    uint64_t interfaceID = 0, deviceID = 0; io_registry_entry_t parent = IO_OBJECT_NULL;
    if (!service || !IOObjectConformsTo(service,"IOUSBHostInterface") ||
        IORegistryEntryGetRegistryEntryID(service,&interfaceID) != KERN_SUCCESS ||
        IORegistryEntryGetParentEntry(service,kIOServicePlane,&parent) != KERN_SUCCESS) {
        adapterError(error,@"No stable interface service"); return nil;
    }
    BOOL valid = IOObjectConformsTo(parent,"IOUSBHostDevice") &&
        IORegistryEntryGetRegistryEntryID(parent,&deviceID) == KERN_SUCCESS && interfaceID && deviceID;
    CFTypeRef property = valid ? IORegistryEntryCreateCFProperty(parent,CFSTR(kUSBHostMatchingPropertySpeed),
        kCFAllocatorDefault,0) : NULL;
    NSNumber *speed = property && CFGetTypeID(property) == CFNumberGetTypeID() ? (__bridge NSNumber *)property : nil;
    NSDictionary *identity = valid && speed ? @{@"device_id":@(deviceID),@"interface_id":@(interfaceID),
        @"parent_device_id":@(deviceID),@"connection_speed":speed} : nil;
    if (property) CFRelease(property);
    IOObjectRelease(parent);
    if (!identity) adapterError(error,@"Missing parent identity/speed");
    return identity;
}
- (id<A23AdapterInterface>)openService:(io_service_t)service queue:(dispatch_queue_t)queue
    interest:(A23AdapterInterest)interest error:(NSError **)error
{
    IOUSBHostInterface *interface = [[IOUSBHostInterface alloc] initWithIOService:service
        options:IOUSBHostObjectInitOptionsNone queue:queue error:error
        interestHandler:^(IOUSBHostObject *object, uint32_t message, void *argument) {
            (void)object; (void)argument;
            // SDK interest queue is distinct. Do not mutate session state here.
            dispatch_async(queue, ^{ interest(message); });
        }];
    return interface ? [[A23SDKInterface alloc] initWithInterface:interface] : nil;
}
@end

@interface A23ServiceReference : NSObject
- (nullable instancetype)initWithService:(io_service_t)service operations:(id<A23AdapterOperations>)operations error:(NSError **)error;
- (void)releaseReference;
@end
@implementation A23ServiceReference {
    io_service_t _service;
    id<A23AdapterOperations> _operations;
}
- (instancetype)initWithService:(io_service_t)service operations:(id<A23AdapterOperations>)operations error:(NSError **)error
{
    if ((self = [super init])) {
        if (![operations retainService:service error:error]) return nil;
        _service = service; _operations = operations;
    }
    return self;
}
- (void)releaseReference
{
    if (_service) { [_operations releaseService:_service]; _service = IO_OBJECT_NULL; _operations = nil; }
}
- (void)dealloc { [self releaseReference]; }
@end

@interface A23AdapterLease : NSObject <A23PreparedBurstResources>
@property NSDictionary *identity;
@property NSMutableData *dataStorage, *transactionStorage;
@property id<A23TransactionTransport> transport;
@property id<A23AdapterInterface> interface;
@property A23ServiceReference *serviceReference;
@property NSDictionary *descriptorBytes;
@property BOOL sdkResources;
@property BOOL burstAttempted;
@end
@implementation A23AdapterLease
- (NSDictionary *)readStatus { return [_interface readStatus]; }
- (NSDictionary *)readFrameSample { return [_interface respondsToSelector:@selector(readFrameSample)] ? [_interface readFrameSample] : nil; }
- (BOOL)supportsSingleBurst { return [_interface respondsToSelector:@selector(enqueueSequenceOneBurst:error:)]; }
- (BOOL)enqueueSequenceOneBurst:(IOUSBHostCompletionHandler)completion error:(NSError **)error
{
    if (!_sdkResources || !self.supportsSingleBurst || _burstAttempted) return adapterError(error,@"Not an unused prepared SDK burst capability");
    _burstAttempted=YES;
    return [(id<A23AdapterBurstInterface>)_interface enqueueSequenceOneBurst:completion error:error];
}
- (void)closeWhenNoIO
{
    _transport = nil;
    _dataStorage = nil; _transactionStorage = nil;
    [_interface destroy]; _interface = nil;
    [_serviceReference releaseReference]; _serviceReference = nil;
}
@end

@implementation A23AdapterSimulationProvider {
    id<A23AdapterOperations> _operations;
    dispatch_queue_t _queue;
    A23AdapterInterest _interest;
    __weak id<A23SessionResources> _openedResources;
}
- (instancetype)initWithOperations:(id<A23AdapterOperations>)operations
    queue:(dispatch_queue_t)queue interest:(A23AdapterInterest)interest
{
    if (!operations || !queue || !interest) return nil;
    if ((self = [super init])) { _operations = operations; _queue = queue; _interest = [interest copy]; }
    return self;
}
- (BOOL)requiresSimulation { return YES; }
- (id<A23SessionResources>)openedResources { return _openedResources; }
- (id<A23SessionResources>)openCandidate:(NSDictionary *)candidate error:(NSError **)error
{
    dispatch_assert_queue(_queue);
    if (_operations.simulation != [self requiresSimulation]) { adapterError(error,@"Provider/operations mode mismatch"); preparationFailure(error,@"provider_mode"); return nil; }
    NSNumber *token = candidate[@"service_token"];
    if (![token isKindOfClass:[NSNumber class]] || CFGetTypeID((__bridge CFTypeRef)token) == CFBooleanGetTypeID() ||
        CFNumberIsFloatType((__bridge CFNumberRef)token) || [token compare:@0] != NSOrderedDescending ||
        token.unsignedLongLongValue > UINT32_MAX) { adapterError(error,@"Invalid borrowed service token"); preparationFailure(error,@"service_token"); return nil; }
    io_service_t service = token.unsignedIntValue;
    A23ServiceReference *reference = [[A23ServiceReference alloc] initWithService:service operations:_operations error:error];
    if (!reference) { preparationFailure(error,@"retain_service"); return nil; }
    NSDictionary *before = [_operations identityForService:service error:error];
    for (NSString *key in @[@"device_id",@"interface_id",@"parent_device_id",@"connection_speed"])
        if (!identityValue(before[key]) || !identityValue(candidate[key]) || ![before[key] isEqual:candidate[key]]) {
            adapterError(error,@"Pre-open identity mismatch"); preparationFailure(error,@"identity_before"); return nil;
        }
    id<A23AdapterInterface> interface = [_operations openService:service queue:_queue interest:_interest error:error];
    if (!interface) { preparationFailure(error,@"sdk_init"); return nil; }
    A23AdapterLease *lease = [A23AdapterLease new]; lease.interface = interface; lease.serviceReference = reference;
    NSDictionary *after = [_operations identityForService:service error:error];
    BOOL identityValid = [before isEqual:after];
    for (NSString *key in @[@"device_id",@"interface_id",@"parent_device_id",@"connection_speed"])
        identityValid = identityValid && identityValue(after[key]);
    if (!identityValid) { [lease closeWhenNoIO]; preparationFailure(error,@"identity_after"); return nil; }
    NSString *stage = @"descriptors";
    NSDictionary *descriptors = [interface descriptorBytes:error];
    NSData *active = descriptors[@"active_interface"];
    const uint8_t *a = active.bytes;
    BOOL valid = identityValid && active.length == 9 && a[0] == 9 && a[1] == 4 && a[2] == 2 && a[3] == 0 &&
        a[4] == 1 && a[5] == 0xff && a[6] == 0x49 && a[7] == 1 &&
        A23ValidateDescriptors(descriptors[@"device_descriptor"],descriptors[@"configuration_descriptor"],
            [after[@"connection_speed"] unsignedIntegerValue],error) != nil &&
        (![self requiresSimulation] || ([descriptors[@"configuration_descriptor"] isEqual:candidate[@"configuration_descriptor"]] &&
        [descriptors[@"device_descriptor"] isEqual:candidate[@"device_descriptor"]]));
    if (valid) { stage = @"copy_pipe_83"; lease.transport = [interface copyTransport:error]; }
    NSData *endpoint = valid && lease.transport ? interface.currentEndpointBytes : nil;
    const uint8_t *e = endpoint.bytes;
    if (valid && lease.transport) stage = @"endpoint_83";
    valid = valid && lease.transport && endpoint.length == 7 && e[0] == 7 && e[1] == 5 && e[2] == 0x83 &&
        e[3] == 1 && e[4] == 0 && e[5] == 1 && e[6] == 1;
    if (valid) { stage = @"allocate_raw_184320"; lease.dataStorage = [interface allocate:184320 shared:NO error:error]; }
    if (valid && lease.dataStorage.length == 184320) {
        stage = @"allocate_transactions_26880"; lease.transactionStorage = [interface allocate:26880 shared:YES error:error];
    }
    valid = valid && lease.dataStorage.length == 184320 && lease.transactionStorage.length == 26880 &&
        lease.dataStorage != lease.transactionStorage;
    if (!valid) {
        [lease closeWhenNoIO];
        preparationFailure(error,stage);
        return nil;
    }
    // Explicit initialization. SDK mapped allocations need not arrive zeroed.
    memset(lease.dataStorage.mutableBytes,0,lease.dataStorage.length);
    memset(lease.transactionStorage.mutableBytes,0,lease.transactionStorage.length);
    lease.identity = @{@"device_id":before[@"device_id"],@"interface_id":before[@"interface_id"],
        @"parent_device_id":before[@"parent_device_id"]};
    lease.descriptorBytes = descriptors; lease.sdkResources = ![self requiresSimulation]; _openedResources = lease;
    return lease;
}
@end
@implementation A23AdapterSDKProvider
- (BOOL)requiresSimulation { return NO; }
@end
