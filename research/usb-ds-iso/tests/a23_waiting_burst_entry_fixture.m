// Actual wait adapter + dormant SDK coordinator, all operations injected.
#define main earlierSDKFixtureMain
#include "io_usb_host_burst_sdk_driver_test.m"
#undef main
#import "../host/a23_waiting_burst_entry.h"
#include <IOKit/IOMessage.h>
#include <CommonCrypto/CommonDigest.h>
typedef struct {
    const char *fault;unsigned left,pumps,refs[8],releases,destroys;BOOL active,initial,arrival,extra;
    IOServiceMatchingCallback match;IOServiceInterestCallback interest;void *ref;
    __unsafe_unretained SDKFixtureOperations *sdk;
    __unsafe_unretained NSString *directory;
} WaitingFixture;
static BOOL is(WaitingFixture *f,const char *name){return !strcmp(f->fault,name);}
static uint64_t fixtureNow(void *p){(void)p;return mach_absolute_time();}
static IONotificationPortRef fixtureCreate(void *p){WaitingFixture *f=p;assert(!f->sdk.opens);f->active=YES;return (IONotificationPortRef)(uintptr_t)1;}
static kern_return_t fixtureMatch(void *p,IONotificationPortRef n,IOServiceMatchingCallback cb,void *ref,io_iterator_t *out)
{WaitingFixture *f=p;assert(n && f->active);f->match=cb;f->ref=ref;f->initial=YES;f->left=is(f,"existing")?1:0;f->refs[1]++;*out=1;return 0;}
static bool fixtureValid(void *p,io_iterator_t it){(void)p;assert(it==1);return true;}
static io_service_t fixtureNext(void *p,io_iterator_t it)
{WaitingFixture *f=p;assert(it==1);if(!f->left){f->initial=NO;return 0;}f->left--;f->refs[7]++;return 7;}
static bool fixtureIdentity(void *p,io_service_t s,A23WaitIdentity *out)
{WaitingFixture *f=p;assert(s==7 && f->refs[7]);*out=(A23WaitIdentity){.interface_id=102,.device_id=101,.speed=3};return true;}
static kern_return_t fixtureInterest(void *p,IONotificationPortRef n,io_service_t s,IOServiceInterestCallback cb,void *ref,io_object_t *out)
{WaitingFixture *f=p;assert(n && s==7 && f->refs[7] && ref==f->ref);f->interest=cb;f->refs[2]++;*out=2;return 0;}
static int fixturePump(void *p,IONotificationPortRef n)
{
    WaitingFixture *f=p;assert(n && f->active && !f->sdk.interface.reads);++f->pumps;
    if(f->extra){f->extra=NO;f->left=1;f->match(f->ref,1);return 1;}
    if(!f->arrival){f->arrival=YES;f->left=is(f,"ambiguous")?2:1;f->match(f->ref,1);return 1;}return 0;
}
static kern_return_t fixtureRelease(void *p,io_object_t s)
{
    WaitingFixture *f=p;assert(s<8 && f->refs[s] && !f->sdk.interface.reads);++f->releases;
    if(is(f,"release-failed"))return 91;
    --f->refs[s];return 0;
}
static void fixtureDestroy(void *p,IONotificationPortRef n)
{WaitingFixture *f=p;assert(n && f->active && !f->sdk.interface.reads);f->active=NO;++f->destroys;}
@interface WaitingSDKOps : SDKFixtureOperations
@property WaitingFixture *fixture;
@property NSMutableData *contextStorage;
@property(copy) A23AdapterInterest observer;
@end
@implementation WaitingSDKOps
- (BOOL)retainService:(io_service_t)s error:(NSError **)error
{assert(_fixture->active && _fixture->refs[7]);return [super retainService:s error:error];}
- (id<A23AdapterInterface>)openService:(io_service_t)s queue:(dispatch_queue_t)q interest:(A23AdapterInterest)cb error:(NSError **)error
{assert(cb && _fixture->active);_observer=[cb copy];return [super openService:s queue:q interest:cb error:error];}
@end
@interface WaitingProvider : NSObject <A23SessionProvider>
@property A23AdapterSDKProvider *inner;
@property WaitingFixture *fixture;
@property(copy) void (^afterOpen)(void);
@end
@implementation WaitingProvider
- (id<A23SessionResources>)openCandidate:(NSDictionary *)c error:(NSError **)error
{
    assert(_fixture->active && _fixture->refs[7]);if(is(_fixture,"open-failed")){
        if(error)*error=[NSError errorWithDomain:@"injected-sdk-open" code:9 userInfo:nil];return nil;}
    if(is(_fixture,"file-permit"))assert([[NSFileManager defaultManager] fileExistsAtPath:[_fixture->directory stringByAppendingPathComponent:@"WAIT_RECEIVER_CLAIMED"]]);
    id<A23SessionResources> r=[_inner openCandidate:c error:error];if(_afterOpen)_afterOpen();return r;
}
@end
@interface WaitingPermit : NSObject <A23WaitingPermit>
@property NSUInteger claims;
@property WaitingFixture *fixture;
@property(copy) void (^afterClaim)(void);
@end
@implementation WaitingPermit
- (BOOL)claimForIdentity:(A23WaitIdentity)idn error:(NSError **)error
{
    (void)error;assert(++_claims==1 && !_fixture->sdk.opens && _fixture->active && idn.interface_id==102 && idn.device_id==101);
    if(_afterClaim)_afterClaim();return !is(_fixture,"permit-denied");
}
@end
@interface WaitingJournal : NSObject <A23SessionJournal>
@property A23WaitingJournal *inner;
@property NSString *fault;
@property(copy) void (^observe)(NSDictionary *);
@end
@implementation WaitingJournal
- (BOOL)append:(NSDictionary *)row error:(NSError **)error
{
    BOOL ok=[_inner append:row error:error];if(_observe)_observe(row);
    NSString *name=row[@"event"];
    if([name isEqual:@"adapter"])name=[@"adapter-" stringByAppendingString:[row[@"details"][@"event"] stringValue]];
    return ok && ![_fault isEqual:[@"journal-" stringByAppendingString:name]];
}
@end
int main(int argc,const char *argv[])
{
    @autoreleasepool {
        if(argc==2 && !strcmp(argv[1],"--describe")){
            NSData *raw=[NSJSONSerialization dataWithJSONObject:A23WaitingBurstPlan() options:NSJSONWritingSortedKeys|NSJSONWritingWithoutEscapingSlashes error:NULL];
            fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;
        }
        if(argc==6 && !strcmp(argv[1],"--claim-only")){
            A23WaitingReceiptPermit *p=[[A23WaitingReceiptPermit alloc] initWithDirectory:@(argv[2]) binary:@(argv[3]) buildManifest:@(argv[4]) recipe:@(argv[5])];
            A23WaitIdentity idn={.interface_id=102,.device_id=101,.speed=3};NSError *error=nil;
            BOOL ok=p && [p claimForIdentity:idn error:&error];if(!ok)fprintf(stderr,"%s\n",error.localizedDescription.UTF8String ?: "invalid file context");return ok?0:2;
        }
        assert(argc==2);NSString *root=@(argv[1]);assert([[NSFileManager defaultManager] createDirectoryAtPath:root withIntermediateDirectories:NO attributes:nil error:NULL]);
        NSArray *names=@[@"ok",@"file-permit",@"waiting-only",@"existing",@"ambiguous",@"permit-denied",@"interrupt-claim",@"open-failed",@"interrupt-open",@"extra-open",
            @"release-failed",@"exit-prepared",@"detach-prepared",@"interrupt-start-intent",@"iso-pending",@"control-pending",@"detach-running",@"late-notification",
            @"sdk-journal-exists",@"journal-begin",@"journal-adapter-1",@"journal-adapter-2",@"journal-adapter-3",@"journal-adapter-4",@"journal-adapter-5",@"journal-adapter-6",
            @"journal-claim_intent",@"journal-claim_committed",@"journal-sdk_open_intent",@"journal-waiter_closed",@"journal-prepared",@"journal-start_intent"];
        dispatch_queue_t q=dispatch_queue_create("a23.wait.entry.injected",DISPATCH_QUEUE_SERIAL);
        for(NSString *name in names){
            NSString *dir=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:dir withIntermediateDirectories:NO attributes:nil error:NULL]);
            assert([@"INJECTED ONLY: no native IOKit/SDK/USB/SD. File order is not physical provenance.\n" writeToFile:[dir stringByAppendingPathComponent:@"MOCK_ONLY.txt"] atomically:NO encoding:NSUTF8StringEncoding error:NULL]);
            NSMutableData *context=[NSMutableData dataWithLength:sizeof(WaitingFixture)];WaitingFixture *f=context.mutableBytes;f->fault=name.UTF8String;f->directory=dir;
            WaitingSDKOps *ops=[WaitingSDKOps new];ops.contextStorage=context;f->sdk=ops;ops.fixture=f;
            ops.interface=[SDKFixtureInterface new];CoordinatorPipe *pipe=[CoordinatorPipe new];pipe.abortAllowed=YES;ops.interface.pipe=pipe;ops.interface.reply=status(NO,NO);
            SDKFixtureClock *clock=[SDKFixtureClock new];WaitingJournal *journal=[WaitingJournal new];journal.fault=name;
            journal.inner=[[A23WaitingJournal alloc] initWithPath:[dir stringByAppendingPathComponent:@"wait.jsonl"]];assert(journal.inner);
            __block A23WaitingBurstEntry *entry=nil;__block BOOL interruption=NO;WaitingPermit *permit=[WaitingPermit new];permit.fixture=f;
            __block BOOL prepared=NO,started=NO;
            id<A23WaitingPermit> selectedPermit=permit;
            if(is(f,"file-permit")){
                char *resolved=realpath(argv[0],NULL);assert(resolved);NSString *binary=@(resolved);free(resolved);
                NSData *program=[NSData dataWithContentsOfFile:binary];unsigned char hash[CC_SHA256_DIGEST_LENGTH];CC_SHA256(program.bytes,(CC_LONG)program.length,hash);
                NSMutableString *digest=[NSMutableString string];for(unsigned i=0;i<sizeof(hash);++i)[digest appendFormat:@"%02x",hash[i]];
                NSString *manifest=[@"" stringByPaddingToLength:64 withString:@"0" startingAtIndex:0],*recipe=[@"" stringByPaddingToLength:64 withString:@"3" startingAtIndex:0];
                NSDictionary *receipt=@{@"schema":@"A23-waiting-burst-consumed-receipt-1",@"backend":@"a23-waiting-burst-1",@"attempt_consumed":@YES,
                    @"receiver_sha256":digest,@"build_manifest_sha256":manifest,@"recipe_sha256":recipe,@"plan":A23WaitingBurstPlan(),@"preparation_id":NSUUID.UUID.UUIDString};
                NSMutableData *raw=[[NSJSONSerialization dataWithJSONObject:receipt options:NSJSONWritingSortedKeys|NSJSONWritingWithoutEscapingSlashes error:NULL] mutableCopy];[raw appendBytes:"\n" length:1];
                assert([raw writeToFile:[dir stringByAppendingPathComponent:@"waiting-authorization.json"] options:NSDataWritingWithoutOverwriting error:NULL]);
                selectedPermit=[[A23WaitingReceiptPermit alloc] initWithDirectory:dir binary:binary buildManifest:manifest recipe:recipe];assert(selectedPermit);
            }
            if(is(f,"sdk-journal-exists"))assert([@"preserve\n" writeToFile:[dir stringByAppendingPathComponent:@"session.jsonl"] atomically:NO encoding:NSUTF8StringEncoding error:NULL]);
            dispatch_sync(q,^{
                entry=[[A23WaitingBurstEntry alloc] initWithDirectory:dir queue:q clock:clock journal:journal];assert(entry);
                entry.interruptionRequested=^BOOL{return interruption;};
                journal.observe=^(NSDictionary *row){if(is(f,"interrupt-start-intent") && [row[@"event"] isEqual:@"start_intent"])interruption=YES;};
                A23WaitOps wait={.context=f,.now=fixtureNow,.create=fixtureCreate,.matching=fixtureMatch,.valid=fixtureValid,.next=fixtureNext,
                    .identity=fixtureIdentity,.interest=fixtureInterest,.pump=fixturePump,.release=fixtureRelease,.destroy=fixtureDestroy};
                [entry poll];assert(![entry startPrepared] && !ops.opens);
                BOOL begun=[entry beginWithOps:&wait deadline:mach_absolute_time()+100000000000ULL];assert(![entry beginWithOps:&wait deadline:UINT64_MAX]);
                if(is(f,"waiting-only")){assert(begun && !ops.opens);[entry requestExit];}
                else if(begun){
                    WaitingProvider *provider=[WaitingProvider new];provider.fixture=f;
                    __weak A23WaitingBurstEntry *weak=entry;
                    provider.inner=[[A23AdapterSDKProvider alloc] initWithOperations:ops queue:q interest:^(uint32_t m){(void)m;[weak detachedRegistryID:102];}];
                    permit.afterClaim=^{if(is(f,"interrupt-claim"))interruption=YES;};
                    provider.afterOpen=^{assert(permit.claims==1 || is(f,"file-permit"));if(is(f,"interrupt-open"))interruption=YES;if(is(f,"extra-open"))f->extra=YES;};
                    prepared=[entry prepareWithProvider:provider permit:selectedPermit];assert(![entry prepareWithProvider:provider permit:selectedPermit]);
                    assert(!ops.interface.reads && !pipe.submissions && !ops.interface.triggers);
                    if(prepared){
                        assert(!f->active && f->destroys==1 && !f->refs[1] && !f->refs[2] && !f->refs[7] && ops.retains==1 && !ops.releases && ops.observer);
                        if(is(f,"exit-prepared"))[entry requestExit];
                        if(is(f,"detach-prepared"))ops.observer(kIOMessageServiceIsTerminated);
                        [entry detachedRegistryID:999];unsigned pumps=f->pumps;
                        started=[entry startPrepared];assert(![entry startPrepared] && f->pumps==pumps && ![entry pollWaiting]);
                    }
                }
                if(!started)assert(!ops.interface.reads && !pipe.submissions && !ops.interface.triggers);
                else assert(ops.interface.reads==1 && pipe.submissions==1 && ops.interface.triggers==1 && !f->active);
            });
            if(started){
                if(!is(f,"iso-pending") && !is(f,"detach-running")){finishISO(pipe,NO);dispatch_sync(q,^{});}
                if(!is(f,"control-pending")){ops.interface.completion(0,0);dispatch_sync(q,^{});}
                ops.interface.reply=status(YES,NO);
                dispatch_sync(q,^{
                    unsigned pumps=f->pumps;
                    if(is(f,"late-notification")){f->interest(f->ref,7,kIOMessageServiceIsTerminated,NULL);assert(![entry.result[@"preflight_failed"] boolValue]);}
                    if(is(f,"detach-running"))ops.observer(kIOMessageServiceIsTerminated);
                    if(is(f,"iso-pending") || is(f,"control-pending") || is(f,"detach-running")){[clock advance:2001000000];[entry poll];[clock advance:1001000000];}
                    [entry poll];[clock advance:250100000];[entry poll];assert(pumps==f->pumps);
                });
            }
            dispatch_sync(q,^{
                NSDictionary *r=entry.result;assert(A23SaveBurstEntryResult(dir,@"waiting-entry-result.json",r));
                for(NSString *key in @[@"begun",@"prepare_attempted",@"permit_claimed",@"prepared",@"started",@"waiter_closed",@"wait_journal_failed",@"preflight_failed",@"finished",@"unresolved",@"hardware_verified",@"usb_strict_pass",@"allow_next_burst"])
                    assert(CFGetTypeID((__bridge CFTypeRef)r[key])==CFBooleanGetTypeID());
                BOOL pending=is(f,"iso-pending") || is(f,"control-pending") || is(f,"detach-running");
                if(started && !pending)assert([r[@"finished"] boolValue] && ![r[@"unresolved"] boolValue] && ops.interface.destroys==1);
                if(pending)assert([r[@"unresolved"] boolValue] && ![r[@"finished"] boolValue] && !ops.interface.destroys && !ops.releases);
                if(!started)assert([r[@"preflight_failed"] boolValue] && [r[@"finished"] boolValue]);
                if(is(f,"release-failed"))assert([r[@"failed_releases"] unsignedIntValue]==3 && [r[@"unreleased_tokens"] count]==3);
                assert(permit.claims<=1 && ops.opens<=1 && pipe.submissions<=1 && ops.interface.triggers<=1 && pipe.aborts<=1);
                NSDictionary *calls=@{@"injected_only":@YES,@"native_iokit_calls":@0,@"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0,
                    @"claims":@(permit.claims),@"sdk_opens":@(ops.opens),@"sdk_retains":@(ops.retains),@"sdk_releases":@(ops.releases),@"sdk_destroys":@(ops.interface.destroys),
                    @"wait_destroys":@(f->destroys),@"wait_pumps":@(f->pumps),@"status_reads":@(ops.interface.reads),@"iso_submissions":@(pipe.submissions),@"burst_enqueues":@(ops.interface.triggers),@"aborts":@(pipe.aborts)};
                assert(A23SaveBurstEntryResult(dir,@"injected-calls.json",calls));
            });
        }
        printf("%lu injected waiting entry cases passed; native IOKit/SDK/USB/SD 0\n",(unsigned long)names.count);return 0;
    }
}
