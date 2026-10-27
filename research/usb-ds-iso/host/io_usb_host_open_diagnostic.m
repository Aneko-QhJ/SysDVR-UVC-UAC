// One explicitly requested preparation diagnosis. No STATUS, frame query,
// enqueue, abort, reset, seize, configuration change, or device TD entry exists.
#import "io_usb_host_sdk_adapter.h"
#include <IOKit/IOKitLib.h>
#include <fcntl.h>
#include <unistd.h>
#ifdef A23_DIAGNOSTIC_PARENT_TRACE
#import <objc/runtime.h>
#endif

static NSDictionary *errorDetails(NSError *error)
{
    if (!error) return @{};
    NSMutableDictionary *result = [@{@"domain":error.domain,@"code":@(error.code),
        @"code_u32":@((uint32_t)error.code),@"description":error.localizedDescription} mutableCopy];
    if (error.localizedFailureReason) result[@"failure_reason"] = error.localizedFailureReason;
    if (error.localizedRecoverySuggestion) result[@"recovery_suggestion"] = error.localizedRecoverySuggestion;
    result[@"user_info_description"] = error.userInfo.description;
    return result;
}
static BOOL record(int fd, NSString *stage, NSString *phase, NSDictionary *details)
{
    NSData *bytes = [NSJSONSerialization dataWithJSONObject:@{@"schema":@"A23-SDK-open-diagnostic-1",
        @"stage":stage,@"phase":phase,@"details":details,@"iso_submissions":@0,@"status_requests":@0}
        options:NSJSONWritingSortedKeys error:NULL];
    if (!bytes || bytes.length > 65536) return NO;
    const uint8_t *p = bytes.bytes; NSUInteger left = bytes.length;
    while (left) { ssize_t n = write(fd,p,left); if (n<=0) return NO; p+=n; left-=(NSUInteger)n; }
    return write(fd,"\n",1)==1 && fsync(fd)==0;
}
#ifdef A23_DIAGNOSTIC_PARENT_TRACE
// This process only: observe the original parent's open result before the
// subclass overwrites its NSError. Preserve all original arguments and result.
static BOOL installParentTrace(int fd)
{
    SEL selector = NSSelectorFromString(@"openWithOptions:error:");
    Method method = class_getInstanceMethod(IOUSBHostObject.class,selector);
    if (!method || method_getNumberOfArguments(method)!=4) return NO;
    char *type = method_copyReturnType(method);
    BOOL correct = type && (!strcmp(type,@encode(BOOL))); free(type);
    if (!correct) return NO;
    IMP original = method_getImplementation(method);
    BOOL (*call)(id,SEL,NSUInteger,NSError *__autoreleasing *) = (void *)original;
    IMP observer = imp_implementationWithBlock(^BOOL(id object,NSUInteger options,NSError *__autoreleasing *error) {
        if (!record(fd,@"parent_open_with_options",@"begin",@{@"options":@(options)})) return NO;
        BOOL ok = call(object,selector,options,error);
        record(fd,@"parent_open_with_options",@"end",@{@"ok":@(ok),@"error":errorDetails(error ? *error : nil)});
        return ok;
    });
    return observer && method_setImplementation(method,observer)==original;
}
#endif
int main(int argc, const char *argv[])
{
    @autoreleasepool {
        if (argc==2 && !strcmp(argv[1],"--describe")) {
            puts("{\"schema\":\"A23-SDK-open-diagnostic-plan-1\",\"max_opens\":1,\"iso_submissions\":0,\"status_requests\":0,\"standard_descriptor_requests_possible\":true}");
            return 0;
        }
        if (argc!=3 || strcmp(argv[1],"--diagnose-once")) return 2;
        int parent = open(argv[2],O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
        int claim = parent>=0 ? openat(parent,"OPEN_DIAGNOSTIC_CLAIMED",O_CREAT|O_EXCL|O_NOFOLLOW|O_WRONLY,0600) : -1;
        if (claim<0) { if (parent>=0) close(parent); return 2; }
        BOOL claimed = fsync(claim)==0 && fsync(parent)==0; close(claim);
        int fd = claimed ? openat(parent,"open-diagnostic.jsonl",O_CREAT|O_EXCL|O_NOFOLLOW|O_WRONLY,0600) : -1;
        if (fd<0) { close(parent); return 2; }
        if (fsync(parent)!=0) { close(fd); close(parent); return 2; }
#ifdef A23_DIAGNOSTIC_PARENT_TRACE
        if (!installParentTrace(fd)) { close(fd); close(parent); return 2; }
#endif
        dispatch_queue_t queue = dispatch_queue_create("a23.sdk.open-diagnostic",DISPATCH_QUEUE_SERIAL);
        __block int code = 1;
        dispatch_sync(queue, ^{
            io_iterator_t iterator = IO_OBJECT_NULL; NSMutableArray *tokens = [NSMutableArray array];
            io_service_t service; id<A23AdapterInterface> interface = nil;
            id<A23TransactionTransport> transport = nil; NSMutableData *raw = nil, *transactions = nil;
            A23DormantSDKOperations *operations = [A23DormantSDKOperations new]; NSError *error = nil;
            NSString *stage = @"matching";
            do {
                if (!record(fd,stage,@"begin",@{})) break;
                CFMutableDictionaryRef matching = A23CreateMatchingDictionary();
                kern_return_t status = matching ? IOServiceGetMatchingServices(kIOMainPortDefault,matching,&iterator) : kIOReturnError;
                if (!status) while ((service=IOIteratorNext(iterator))) [tokens addObject:@(service)];
                if (iterator) { IOObjectRelease(iterator); iterator = IO_OBJECT_NULL; }
                if (!record(fd,stage,@"end",@{@"registry_result_u32":@((uint32_t)status),@"count":@(tokens.count)}) || status || tokens.count!=1) break;
                service = [tokens[0] unsignedIntValue]; stage = @"identity_before";
                if (!record(fd,stage,@"begin",@{})) break;
                NSDictionary *before = [operations identityForService:service error:&error];
                if (!record(fd,stage,@"end",@{@"ok":@(before!=nil),@"identity":before ?: @{},@"error":errorDetails(error)}) || !before) break;
                stage = @"sdk_init"; error = nil;
                if (!record(fd,stage,@"begin",@{})) break;
                interface = [operations openService:service queue:queue interest:^(uint32_t message) { (void)message; } error:&error];
                if (!record(fd,stage,@"end",@{@"ok":@(interface!=nil),@"error":errorDetails(error)}) || !interface) break;
                stage = @"identity_after"; error = nil;
                if (!record(fd,stage,@"begin",@{})) break;
                NSDictionary *after = [operations identityForService:service error:&error];
                if (!record(fd,stage,@"end",@{@"ok":@([before isEqual:after]),@"identity":after ?: @{},@"error":errorDetails(error)}) || ![before isEqual:after]) break;
                stage = @"descriptors"; error = nil;
                if (!record(fd,stage,@"begin",@{})) break;
                NSDictionary *descriptors = [interface descriptorBytes:&error];
                BOOL valid = descriptors && A23ValidateDescriptors(descriptors[@"device_descriptor"],descriptors[@"configuration_descriptor"],[after[@"connection_speed"] unsignedIntegerValue],&error)!=nil;
                if (!record(fd,stage,@"end",@{@"ok":@(valid),@"error":errorDetails(error)}) || !valid) break;
                stage = @"copy_pipe_83"; error = nil;
                if (!record(fd,stage,@"begin",@{})) break;
                transport = [interface copyTransport:&error]; NSData *endpoint = interface.currentEndpointBytes;
                const uint8_t expected[] = {7,5,0x83,1,0,1,1};
                valid = transport && [endpoint isEqual:[NSData dataWithBytes:expected length:sizeof(expected)]];
                if (!record(fd,stage,@"end",@{@"ok":@(valid),@"error":errorDetails(error)}) || !valid) break;
                stage = @"allocate_raw_184320"; error = nil;
                if (!record(fd,stage,@"begin",@{})) break;
                raw = [interface allocate:184320 shared:NO error:&error];
                if (!record(fd,stage,@"end",@{@"ok":@(raw.length==184320),@"length":@(raw.length),@"error":errorDetails(error)}) || raw.length!=184320) break;
                stage = @"allocate_transactions_26880"; error = nil;
                if (!record(fd,stage,@"begin",@{})) break;
                transactions = [interface allocate:26880 shared:YES error:&error];
                if (!record(fd,stage,@"end",@{@"ok":@(transactions.length==26880),@"length":@(transactions.length),@"error":errorDetails(error)}) || transactions.length!=26880) break;
                code = 0;
            } while (0);
            // No I/O was enqueued: these are preparation allocations only.
            transactions = nil; raw = nil; transport = nil;
            [interface destroy]; interface = nil;
            for (NSNumber *token in tokens) IOObjectRelease(token.unsignedIntValue);
            if (!record(fd,@"cleanup",@"end",@{@"exit_code":@(code),@"last_stage":stage,@"resources_released":@YES})) code=1;
        });
        close(fd); close(parent); return code;
    }
}
