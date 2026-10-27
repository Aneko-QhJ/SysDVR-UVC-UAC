#define main olderSDKFixtureMain
#include "io_usb_host_burst_sdk_driver_test.m"
#undef main
#import "../host/a23_waiting_receiver.h"
#include <IOKit/IOMessage.h>
typedef struct {unsigned left,refs[8],pumps,destroys;BOOL arrival,allowArrival,active,existing,ambiguous;
    IOServiceMatchingCallback match;void *ref;__unsafe_unretained SDKFixtureOperations *sdk;} LoopFixture;
static uint64_t fakeNow(void *p){(void)p;return mach_absolute_time();}
static IONotificationPortRef fakeCreate(void *p){LoopFixture *f=p;f->active=YES;return (IONotificationPortRef)(uintptr_t)1;}
static kern_return_t fakeMatch(void *p,IONotificationPortRef n,IOServiceMatchingCallback cb,void *ref,io_iterator_t *out)
{LoopFixture *f=p;assert(n && f->active);f->match=cb;f->ref=ref;f->left=f->existing?1:0;f->refs[1]++;*out=1;return 0;}
static bool fakeValid(void *p,io_iterator_t it){(void)p;assert(it==1);return true;}
static io_service_t fakeNext(void *p,io_iterator_t it){LoopFixture *f=p;assert(it==1);if(!f->left)return 0;f->left--;f->refs[7]++;return 7;}
static bool fakeIdentity(void *p,io_service_t s,A23WaitIdentity *out)
{LoopFixture *f=p;assert(s==7 && f->refs[7]);*out=(A23WaitIdentity){.interface_id=102,.device_id=101,.speed=3};return true;}
static kern_return_t fakeInterest(void *p,IONotificationPortRef n,io_service_t s,IOServiceInterestCallback cb,void *ref,io_object_t *out)
{LoopFixture *f=p;(void)cb;(void)ref;assert(n && s==7);f->refs[2]++;*out=2;return 0;}
static int fakePump(void *p,IONotificationPortRef n)
{LoopFixture *f=p;assert(n && f->active && !f->sdk.interface.reads);++f->pumps;
 if(!f->arrival && f->allowArrival){f->arrival=YES;f->left=f->ambiguous?2:1;f->match(f->ref,1);return 1;}return 0;}
static kern_return_t fakeRelease(void *p,io_object_t s){LoopFixture *f=p;assert(s<8 && f->refs[s] && !f->sdk.interface.reads);--f->refs[s];return 0;}
static void fakeDestroy(void *p,IONotificationPortRef n){LoopFixture *f=p;assert(n && f->active && !f->sdk.interface.reads);f->active=NO;f->destroys++;}
@interface LoopSDKOps : SDKFixtureOperations
@property NSMutableData *fixtureStorage;
@property(copy) A23AdapterInterest observer;
@end
@implementation LoopSDKOps
- (id<A23AdapterInterface>)openService:(io_service_t)s queue:(dispatch_queue_t)q interest:(A23AdapterInterest)cb error:(NSError **)error
{_observer=[cb copy];return [super openService:s queue:q interest:cb error:error];}
@end
@interface LoopPermit : NSObject <A23WaitingPermit>
@property NSUInteger calls;
@end
@implementation LoopPermit
- (BOOL)claimForIdentity:(A23WaitIdentity)identity error:(NSError **)error
{(void)error;assert(identity.interface_id==102 && ++_calls==1);return YES;}
@end
int main(int argc,const char *argv[])
{
 @autoreleasepool {
    if(argc==4 && !strcmp(argv[1],"--claim-process-only")){
        NSString *run=@(argv[2]),*build=@(argv[3]);NSError *error=nil;
        NSDictionary *checked=A23CheckWaitingConsumed(run,build,[build stringByAppendingPathComponent:@"receiver"],&error);
        return checked && A23ClaimWaitingProcess(run,checked) ? 0 : 2; // file-only injected binary branch
    }
    if((argc==4 && !strcmp(argv[1],"--claim-sdk-only")) || (argc==5 && !strcmp(argv[1],"--claim-sdk-checked"))){
        NSString *run=@(argv[2]),*build=@(argv[3]),*binary=[build stringByAppendingPathComponent:@"receiver"];NSError *error=nil;
        NSDictionary *checked=argc==5 ? [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:@(argv[4])] options:0 error:NULL] : A23CheckWaitingConsumed(run,build,binary,&error);if(!checked)return 2;
        id<A23WaitingPermit> permit=A23MakeWaitingBoundPermit(run,build,binary,checked);
        A23WaitIdentity identity={.interface_id=102,.device_id=101,.speed=3};
        return [permit claimForIdentity:identity error:&error] ? 0 : 2; // file checks/claim, no SDK operations
    }
    assert(argc==2);NSString *root=@(argv[1]);assert([[NSFileManager defaultManager] createDirectoryAtPath:root withIntermediateDirectories:NO attributes:nil error:NULL]);
    NSArray *names=@[@"normal",@"signal-before-begin",@"signal-waiting",@"signal-between-turns",@"detach-between-turns",@"wait-timeout",@"existing",@"ambiguous",@"iso-pending",@"control-pending",@"signal-running",@"detach-running"];
    dispatch_queue_t q=dispatch_queue_create("a23.wait.loop.fixture",DISPATCH_QUEUE_SERIAL);
    for(NSString *name in names){
        NSString *dir=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:dir withIntermediateDirectories:NO attributes:nil error:NULL]);
        assert([@"Injected loop/SDK ops only; native IOKit/SDK/USB/SD 0.\n" writeToFile:[dir stringByAppendingPathComponent:@"MOCK_ONLY.txt"] atomically:NO encoding:NSUTF8StringEncoding error:NULL]);
        LoopSDKOps *ops=[LoopSDKOps new];ops.fixtureStorage=[NSMutableData dataWithLength:sizeof(LoopFixture)];LoopFixture *f=ops.fixtureStorage.mutableBytes;
        f->sdk=ops;f->allowArrival=![name isEqual:@"wait-timeout"] && ![name isEqual:@"signal-waiting"];f->existing=[name isEqual:@"existing"];f->ambiguous=[name isEqual:@"ambiguous"];
        ops.interface=[SDKFixtureInterface new];CoordinatorPipe *pipe=[CoordinatorPipe new];pipe.abortAllowed=YES;ops.interface.pipe=pipe;ops.interface.reply=status(NO,NO);
        SDKFixtureClock *clock=[SDKFixtureClock new];LoopPermit *permit=[LoopPermit new];__block A23WaitingReceiverLoop *loop=nil;__block BOOL interrupt=[name isEqual:@"signal-before-begin"];
        dispatch_sync(q,^{
            A23WaitOps wait={.context=f,.now=fakeNow,.create=fakeCreate,.matching=fakeMatch,.valid=fakeValid,.next=fakeNext,.identity=fakeIdentity,.interest=fakeInterest,.pump=fakePump,.release=fakeRelease,.destroy=fakeDestroy};
            A23AdapterSDKProvider *provider=[[A23AdapterSDKProvider alloc] initWithOperations:ops queue:q interest:^(uint32_t m){if(m==kIOMessageServiceIsTerminated)[loop detachedRegistryID:loop.selectedInterfaceID];}];
            loop=[[A23WaitingReceiverLoop alloc] initWithHost:dir queue:q clock:clock ops:&wait provider:provider permit:permit];assert(loop);
            loop.interruptionRequested=^BOOL{return interrupt;};[loop tick];assert(!ops.opens);[loop begin];assert(![loop begin]);
            if([name isEqual:@"signal-waiting"])interrupt=YES;
            if([name isEqual:@"wait-timeout"])[clock advance:121000000000ULL];
            [loop tick];assert(!ops.interface.reads && !pipe.submissions && !ops.interface.triggers);
            if([loop.result[@"prepared"] boolValue])assert(!f->active && ops.retains==1 && !ops.releases);
        });
        // These are genuinely separate queue turns; queued SDK interest is
        // allowed to run after preparation and before the start tick.
        if([name isEqual:@"detach-between-turns"])dispatch_async(q,^{assert(ops.observer);ops.observer(kIOMessageServiceIsTerminated);});
        if([name isEqual:@"signal-between-turns"])interrupt=YES;
        dispatch_sync(q,^{[loop tick];});
        __block BOOL started=NO;dispatch_sync(q,^{started=[loop.result[@"started"] boolValue];});
        if(started){
            BOOL isoPending=[@[@"iso-pending",@"signal-running",@"detach-running"] containsObject:name];
            if(!isoPending){finishISO(pipe,NO);dispatch_sync(q,^{});}
            if(![name isEqual:@"control-pending"]){ops.interface.completion(0,0);dispatch_sync(q,^{});}
            ops.interface.reply=status(YES,NO);
            dispatch_sync(q,^{
                unsigned pumps=f->pumps;if([name isEqual:@"signal-running"])interrupt=YES;
                if([name isEqual:@"detach-running"])ops.observer(kIOMessageServiceIsTerminated);
                if(![name isEqual:@"normal"]){[clock advance:2001000000];[loop tick];[clock advance:1001000000];}
                [loop tick];[clock advance:250100000];[loop tick];assert(pumps==f->pumps);
            });
        }
        dispatch_sync(q,^{
            NSDictionary *r=loop.result;assert(A23SaveBurstEntryResult(dir,@"waiting-entry-result.json",r));
            BOOL pending=[@[@"iso-pending",@"control-pending",@"signal-running",@"detach-running"] containsObject:name];
            assert([r[@"unresolved"] boolValue]==pending && [r[@"finished"] boolValue]!=pending);
            if(!started)assert(!ops.interface.reads && !pipe.submissions && !ops.interface.triggers);
            if(pending)assert(!ops.interface.destroys && !ops.releases);
            if([name isEqual:@"normal"])assert(ops.interface.destroys==1 && ops.releases==1);
            NSDictionary *calls=@{@"sdk_opens":@(ops.opens),@"sdk_releases":@(ops.releases),@"sdk_destroys":@(ops.interface.destroys),@"claims":@(permit.calls),
                @"status_reads":@(ops.interface.reads),@"iso_submissions":@(pipe.submissions),@"burst_enqueues":@(ops.interface.triggers),@"aborts":@(pipe.aborts),@"wait_pumps":@(f->pumps),
                @"native_iokit_calls":@0,@"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0};
            assert(A23SaveBurstEntryResult(dir,@"injected-calls.json",calls));
        });
    }
    printf("%lu receiver loop cases passed; native IOKit/SDK/USB/SD 0\n",(unsigned long)names.count);return 0;
 }
}
