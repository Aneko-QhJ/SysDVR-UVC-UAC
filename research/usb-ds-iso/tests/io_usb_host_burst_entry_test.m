// Reuse protocol-generated STATUS and SDK-role injection without real SDK objects.
#define main coordinatorFixtureMain
#include "io_usb_host_burst_sdk_driver_test.m"
#undef main
#import "../host/io_usb_host_burst_entry.h"
@interface MissingBurstResources : NSObject <A23SessionResources>
@property NSDictionary *identity;
@property NSMutableData *dataStorage,*transactionStorage;
@property id<A23TransactionTransport> transport;
@property NSUInteger closes;
@end
@implementation MissingBurstResources
- (void)closeWhenNoIO { ++_closes; }
@end
@interface EntryProvider : NSObject <A23SessionProvider>
@property A23AdapterSDKProvider *provider;
@property NSString *fault;
@property(copy) void (^afterOpen)(void);
@property MissingBurstResources *missing;
@end
@implementation EntryProvider
- (id<A23SessionResources>)openCandidate:(NSDictionary *)c error:(NSError **)error
{
    if([_fault isEqual:@"open-failed"]){if(error)*error=[NSError errorWithDomain:@"injected-open" code:9 userInfo:nil];return nil;}
    if([_fault isEqual:@"missing-capability"]){_missing=[MissingBurstResources new];return _missing;}
    id<A23SessionResources> r=[_provider openCandidate:c error:error];if(_afterOpen)_afterOpen();return r;
}
@end
int main(int argc,const char *argv[])
{
    @autoreleasepool {
        if(argc==4 && !strcmp(argv[1],"--claim-only")){
            NSError *e=nil;BOOL ok=A23ClaimBurstReceipt(@(argv[2]),@(argv[3]),&e);
            if(!ok)fprintf(stderr,"%s\n",e.localizedDescription.UTF8String);return ok ? 0 : 2;
        }
        assert(argc==2);NSString *root=@(argv[1]);assert([[NSFileManager defaultManager] createDirectoryAtPath:root withIntermediateDirectories:NO attributes:nil error:NULL]);
        NSArray *names=@[@"clean",@"no-match",@"ambiguous",@"interrupted-before",@"open-failed",@"interrupted-after-open",
            @"missing-capability",@"journal-exists",@"control-pending",@"iso-pending",@"detach-pending",@"foreign-pointer"];
        dispatch_queue_t q=dispatch_queue_create("a23.entry.injected",DISPATCH_QUEUE_SERIAL);
        for(NSString *name in names){
            NSString *dir=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:dir withIntermediateDirectories:NO attributes:nil error:NULL]);
            SDKFixtureClock *clock=[SDKFixtureClock new];SDKFixtureOperations *ops=[SDKFixtureOperations new];ops.interface=[SDKFixtureInterface new];
            CoordinatorPipe *pipe=[CoordinatorPipe new];pipe.abortAllowed=YES;ops.interface.pipe=pipe;ops.interface.reply=status(NO,NO);
            __block A23BurstEntry *entry=nil;__block BOOL interrupted=[name isEqual:@"interrupted-before"];
            if([name isEqual:@"journal-exists"])assert([@"existing\n" writeToFile:[dir stringByAppendingPathComponent:@"session.jsonl"] atomically:NO encoding:NSUTF8StringEncoding error:NULL]);
            dispatch_sync(q,^{
                entry=[[A23BurstEntry alloc] initWithDirectory:dir queue:q clock:clock];entry.interruptionRequested=^BOOL{return interrupted;};
                EntryProvider *provider=[EntryProvider new];provider.fault=name;
                provider.provider=[[A23AdapterSDKProvider alloc] initWithOperations:ops queue:q interest:^(uint32_t m){(void)m;assert(!"No registry callback");}];
                if([name isEqual:@"interrupted-after-open"])provider.afterOpen=^{interrupted=YES;};
                NSArray *candidates=[name isEqual:@"no-match"] ? @[] : [name isEqual:@"ambiguous"] ? @[candidate(),candidate()] : @[candidate()];
                [entry poll];assert(ops.opens==0);[entry startCandidates:candidates provider:provider];assert(![entry startCandidates:candidates provider:provider]);
                if([name isEqual:@"missing-capability"])assert(provider.missing.closes==1);
            });
            BOOL preflight=[@[@"no-match",@"ambiguous",@"interrupted-before",@"open-failed",@"interrupted-after-open",@"missing-capability",@"journal-exists"] containsObject:name];
            if(!preflight){
                if(![name isEqual:@"iso-pending"] && ![name isEqual:@"detach-pending"]){finishISO(pipe,[name isEqual:@"foreign-pointer"]);dispatch_sync(q,^{});}
                if(![name isEqual:@"control-pending"]){ops.interface.completion(0,0);dispatch_sync(q,^{});}
                ops.interface.reply=status(YES,NO);
                dispatch_sync(q,^{
                    if([name isEqual:@"detach-pending"]){[entry detachedRegistryID:999];[entry detachedRegistryID:102];}
                    if(![name isEqual:@"clean"]){[clock advance:2001000000];[entry poll];[clock advance:1001000000];}
                    [entry poll];[clock advance:250100000];[entry poll];
                });
            }
            dispatch_sync(q,^{
                NSDictionary *r=entry.result;
                for(NSString *key in @[@"attempted",@"preflight_failed",@"finished",@"unresolved",@"hardware_verified",@"usb_strict_pass",
                    @"baseline_accepted",@"allow_next_burst",@"callback_drain_verified"])
                    assert(CFGetTypeID((__bridge CFTypeRef)r[key])==CFBooleanGetTypeID());
                assert(A23SaveBurstEntryResult(dir,@"entry-result.json",r));assert(!A23SaveBurstEntryResult(dir,@"entry-result.json",r));
                assert([r[@"preflight_failed"] boolValue]==preflight);
                if([name isEqual:@"clean"]){assert([r[@"finished"] boolValue] && [r[@"exit_code"] intValue]==0 && ops.interface.destroys==1);}
                else if(preflight){assert([r[@"finished"] boolValue] && [r[@"exit_code"] intValue]==1 && pipe.submissions==0 && ops.interface.triggers==0 && ops.interface.reads==0);}
                else{assert([r[@"unresolved"] boolValue] && ![r[@"finished"] boolValue] && ops.interface.destroys==0 && ops.releases==0);}
                NSDictionary *calls=@{@"injected_only":@YES,@"real_sdk_objects":@0,@"registry_calls":@0,@"usb_requests":@0,@"sd_accesses":@0,
                    @"opens":@(ops.opens),@"destroys":@(ops.interface.destroys),@"releases":@(ops.releases),@"iso_submissions":@(pipe.submissions),
                    @"burst_enqueues":@(ops.interface.triggers),@"status_reads":@(ops.interface.reads),@"host_aborts":@(pipe.aborts)};
                assert(A23SaveBurstEntryResult(dir,@"injected-calls.json",calls));
            });
        }
        puts("12 SDK entry injection scenarios passed; SDK/registry/USB/SD 0");return 0;
    }
}
