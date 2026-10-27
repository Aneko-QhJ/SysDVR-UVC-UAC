#import "io_usb_host_no_td_driver.h"
#include <CommonCrypto/CommonDigest.h>
#include <IOKit/IOMessage.h>
#include <IOKit/IOKitLib.h>
#include <fcntl.h>
#include <signal.h>
#include <unistd.h>
static volatile sig_atomic_t exitWanted;
static void requestExitSignal(int number) { (void)number; exitWanted = 1; }

static NSString *digest(NSData *data)
{
    unsigned char bytes[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(data.bytes,(CC_LONG)data.length,bytes);
    NSMutableString *text = [NSMutableString string];
    for (NSUInteger i=0;i<sizeof(bytes);++i) [text appendFormat:@"%02x",bytes[i]];
    return text;
}
static NSData *canonical(id value)
{ return value && [NSJSONSerialization isValidJSONObject:value] ?
    [NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingSortedKeys error:NULL] : nil; }
static BOOL saveResult(NSString *directory,NSString *name,NSDictionary *value)
{
    NSData *data = canonical(value);
    NSString *path = [directory stringByAppendingPathComponent:name];
    if (!data || ![data writeToFile:path options:NSDataWritingWithoutOverwriting error:NULL]) return NO;
    int fd = open(path.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW);
    BOOL ok = fd>=0 && fsync(fd)==0 && [[NSData dataWithContentsOfFile:path] isEqual:data];
    if (fd>=0) close(fd);
    fd = open(directory.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    ok = ok && fd>=0 && fsync(fd)==0; if (fd>=0) close(fd); return ok;
}

int main(int argc,const char *argv[])
{
    @autoreleasepool {
        if (argc==2 && !strcmp(argv[1],"--describe")) {
            puts([[NSString alloc] initWithData:canonical(A23HardwareNoTDObservationPlan()) encoding:NSUTF8StringEncoding].UTF8String);
            return 0;
        }
        if (argc!=3 || strcmp(argv[1],"--acquire-once")) {
            fputs("Use --describe for an offline plan. Acquisition requires the separately prepared one-use workflow.\n",stderr); return 2;
        }
        // Verify the consumed receipt and atomically claim it before creating
        // operations, querying registry, or opening any SDK object.
        NSString *directory = @(argv[2]);
        NSData *raw = [NSData dataWithContentsOfFile:[directory stringByAppendingPathComponent:@"authorization.json"]];
        NSDictionary *receipt = raw.length>0 && raw.length<=16384 ? [NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL] : nil;
        NSData *binary = [NSData dataWithContentsOfFile:@(argv[0])];
        if (!binary.length || ![receipt isKindOfClass:NSDictionary.class] || ![receipt[@"schema"] isEqual:@"A23-IOUSBHost-consumed-receipt-1"] ||
            ![receipt[@"receiver_sha256"] isEqual:digest(binary)] || ![canonical(receipt[@"plan"]) isEqual:canonical(A23HardwareNoTDObservationPlan())] ||
            ![receipt[@"attempt_consumed"] isKindOfClass:NSNumber.class] ||
            CFGetTypeID((__bridge CFTypeRef)receipt[@"attempt_consumed"])!=CFBooleanGetTypeID() ||
            ![receipt[@"attempt_consumed"] boolValue]) {
            fputs("Missing/changed consumed receipt; no USB accessed.\n",stderr); return 2;
        }
        int parent = open(directory.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
        int claim = parent>=0 ? openat(parent,"RECEIVER_CLAIMED",O_CREAT|O_EXCL|O_NOFOLLOW|O_WRONLY,0600) : -1;
        if (claim<0) { if (parent>=0) close(parent); fputs("Receipt already claimed or output invalid; no USB accessed.\n",stderr); return 2; }
        BOOL claimed = fsync(claim)==0 && fsync(parent)==0; close(claim); close(parent); if (!claimed) return 2;
        if (@available(macOS 26.4,*)) {} else { fputs("Mapped SDK API requires macOS 26.4+.\n",stderr); return 2; }
        dispatch_queue_t queue = dispatch_queue_create("a23.io-usb-host.no-td",DISPATCH_QUEUE_SERIAL);
        A23LocalMachClock *clock = [A23LocalMachClock new];
        A23NoTDDriver *driver = [[A23NoTDDriver alloc] initWithDirectory:directory queue:queue clock:clock];
        if (!driver) return 2;
        driver.interruptionRequested = ^BOOL { return exitWanted!=0; };
        dispatch_source_t timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,queue);
        __block BOOL reported = NO;
        dispatch_source_set_timer(timer,dispatch_time(DISPATCH_TIME_NOW,10000000),10000000,1000000);
        dispatch_source_set_event_handler(timer,^{
            [driver poll];
            NSDictionary *result = @{@"schema":@"A23-IOUSBHost-receiver-result-1",@"execution_mode":@"hardware",
                @"finished":@(driver.finished),@"unresolved":@(driver.unresolved),@"exit_code":@(driver.exitCode),
                @"storage_retained":@(driver.session.storageRetained),@"resources_retained":@(driver.session.resourcesRetained),
                @"hardware_verified":@NO,@"baseline_accepted":@NO};
            if (driver.unresolved && !reported) {
                reported = YES; saveResult(directory,@"retained.json",result);
                fputs("Request unresolved: retaining buffers/interface; no resubmit or forced exit.\n",stderr); fflush(stderr);
            }
            if (driver.finished) {
                BOOL saved = saveResult(directory,@"receiver-result.json",result);
                exit(saved ? driver.exitCode : 1);
            }
        });
        // Handle graceful exit on the owner queue. Never tear down outstanding DMA.
        signal(SIGINT,requestExitSignal); signal(SIGTERM,requestExitSignal);
        dispatch_async(queue,^{
            A23DormantSDKOperations *operations = [A23DormantSDKOperations new];
            CFMutableDictionaryRef matching = exitWanted ? NULL : A23CreateMatchingDictionary(); io_iterator_t iterator = IO_OBJECT_NULL;
            kern_return_t status = matching ? IOServiceGetMatchingServices(kIOMainPortDefault,matching,&iterator) : kIOReturnError; // Consumes matching.
            NSMutableArray *services = [NSMutableArray array]; io_service_t service;
            if (status==KERN_SUCCESS) while ((service=IOIteratorNext(iterator))) [services addObject:@(service)];
            if (iterator) IOObjectRelease(iterator);
            NSMutableArray *candidates = [NSMutableArray array];
            NSError *identityError = nil;
            if (services.count==1) {
                NSDictionary *identity = [operations identityForService:[services[0] unsignedIntValue] error:&identityError];
                if (identity) { NSMutableDictionary *candidate = [identity mutableCopy]; candidate[@"service_token"] = services[0]; [candidates addObject:candidate]; }
            } else if (services.count>1) { // Preserve ambiguity; never open any of them.
                for (NSUInteger i=0;i<services.count;++i) [candidates addObject:@{}];
            }
            NSMutableDictionary *selection = [@{@"matched_service_count":@(services.count),@"registry_result_u32":@((uint32_t)status),
                @"execution_mode":@"hardware",@"hardware_verified":@NO} mutableCopy];
            if (identityError) selection[@"identity_error"] = @{@"domain":identityError.domain,@"code":@(identityError.code)};
            if (!saveResult(directory,@"selection.json",selection)) {
                [candidates removeAllObjects]; fputs("Failed to persist selection; no interface opened.\n",stderr);
            }
            uint64_t interfaceID = [candidates.firstObject[@"interface_id"] unsignedLongLongValue];
            A23AdapterSDKProvider *provider = [[A23AdapterSDKProvider alloc] initWithOperations:operations queue:queue
                interest:^(uint32_t message) {
                    if (message==kIOMessageServiceIsTerminated) [driver detachedRegistryID:interfaceID];
                    else if (message==kIOMessageServiceIsRequestingClose) [driver requestExit];
                }];
            [driver startCandidates:candidates provider:provider];
            for (NSNumber *token in services) IOObjectRelease(token.unsignedIntValue);
        });
        dispatch_resume(timer);
        dispatch_main();
    }
}
