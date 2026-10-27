#import "a23_interepoch_guard.h"
#import "a23_guard_cadence_api.h"
#include <stdatomic.h>
#include <time.h>

// Linked only into the archival file fixture; never a USB receiver.
extern void A23InterepochFileHook(void (^hook)(void));
@interface A23InterepochGuard (FixtureReturn)
- (void)returnedReceipt:(NSDictionary *)receipt;
@end
static NSString *mode;
@interface AlteredGuard : A23InterepochGuard @end
@implementation AlteredGuard
- (void)returnedReceipt:(NSDictionary *)receipt {
    NSMutableDictionary *r=[receipt mutableCopy];
    if([mode isEqual:@"wrong-phase"])r[@"phase"]=@"before_begin";
    if([mode isEqual:@"wrong-request"]){NSMutableDictionary *q=[r[@"request"] mutableCopy];q[@"request_id"]=@99;r[@"request"]=q;}
    [super returnedReceipt:r];
    if([mode isEqual:@"duplicate-receipt"])[super returnedReceipt:r];
}
@end
static uint64_t nowNS(void){struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC_RAW,&t));return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;}
static void change(NSString *p){assert([@"changed" writeToFile:p atomically:NO encoding:NSUTF8StringEncoding error:NULL]);}
int main(int argc,const char *argv[]){@autoreleasepool{
    assert(argc==2);NSDictionary *c=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:@(argv[1])] options:0 error:NULL];assert(c);mode=c[@"case"];
    dispatch_queue_t q=dispatch_queue_create("a23.interepoch.fixture.serial",DISPATCH_QUEUE_SERIAL);
    dispatch_semaphore_t done=dispatch_semaphore_create(0),hookProcessed=dispatch_semaphore_create(0);
    __block A23InterepochGuard *guard;
    __block A23ModelScopeVerifier *v;
    __block A23SharedSequenceModelPermit *permit;
    __block NSUInteger epoch=1,polls=0,checks=0,rechecks=0,notifications=0,finishes=0;
    __block BOOL boundaryStop=NO,workerReturnedBeforeRecheck=NO,expiredWhileOwned=NO;
    __block NSDictionary *scope;
    __block NSDictionary *last;
    __block _Atomic(bool) workerBodyEnded;
    atomic_init(&workerBodyEnded,false);
    dispatch_sync(q,^{
        v=[[A23ModelScopeVerifier alloc] initWithBuild:c[@"build"] repository:c[@"repository"] cards:c[@"cards"] ledger:c[@"ledger"] records:c[@"records"]];assert(v && [v verifyCore]);scope=v.scope;
        permit=[[A23SharedSequenceModelPermit alloc] initWithJob:c[@"job"] expectedScope:scope verifier:^BOOL(NSDictionary *s){return [v verifyLiveJob:s job:c[@"job"]];}];assert(permit && ![permit.result[@"stale"] boolValue]);
        A23InterepochFileHook(^{
            dispatch_async(q,^{
                notifications++;assert([guard.result[@"busy"] boolValue] && ![guard.result[@"verifier_on_serial_queue"] boolValue]);
                assert(![guard requestEpoch:epoch deadlineNS:nowNS()+10000000000ULL]);
                if([mode isEqual:@"early-receipt"])[guard returnedReceipt:@{}];
                if([mode isEqual:@"exit-in-check"])[guard stopWithReason:@"operator_exit"];
                if([mode isEqual:@"boundary-change"])epoch=2;
                if([mode isEqual:@"permit-change"])change([c[@"job"] stringByAppendingPathComponent:@"consumed.json"]);
                if([mode isEqual:@"source-change"])change([c[@"repository"] stringByAppendingPathComponent:@"research/usb-ds-iso/tools/build_a23_live120_lstat.py"]);
                if([mode isEqual:@"deadline"]){struct timespec pause={0,100000000};nanosleep(&pause,NULL);[guard observeDeadline];expiredWhileOwned=[guard.result[@"stopped"] boolValue] && ![guard.result[@"verifier_on_serial_queue"] boolValue];}
                dispatch_semaphore_signal(hookProcessed);
            });
            assert(!dispatch_semaphore_wait(hookProcessed,dispatch_time(DISPATCH_TIME_NOW,3000000000LL)));
        });
        guard=[[AlteredGuard alloc] initWithQueue:q job:c[@"job"] scopeDigest:c[@"scope_digest"] fullCheck:^BOOL{
            checks++;atomic_store(&workerBodyEnded,false);
            [v setCheckPhase:@"between_epochs"];BOOL ok=[v verifyCore];
            atomic_store(&workerBodyEnded,true);return ok;
        } boundary:^NSDictionary *{
            return @{@"saved_epochs":@(epoch),@"iso_attempts":@(epoch),@"durable":@YES,@"pending":@NO,@"stopped":@(boundaryStop)};
        } recheck:^BOOL{
            assert([guard.result[@"verifier_on_serial_queue"] boolValue]);
            workerReturnedBeforeRecheck=atomic_load(&workerBodyEnded);assert(workerReturnedBeforeRecheck);rechecks++;
            BOOL ok=[v verifyLiveJob:scope job:c[@"job"]] && ![permit.result[@"stale"] boolValue];
            if([mode isEqual:@"fault-in-recheck"])[guard stopWithReason:@"ingress_fault"];
            if([mode isEqual:@"boundary-in-recheck"])boundaryStop=YES;
            return ok;
        } poll:^{
            assert([guard.result[@"verifier_on_serial_queue"] boolValue] && !boundaryStop);polls++;
            assert(![guard requestEpoch:2 deadlineNS:nowNS()+10000000000ULL]);
        } stop:^{boundaryStop=YES;} finished:^{finishes++;last=guard.result;dispatch_semaphore_signal(done);}];assert(guard);
        uint64_t deadline=nowNS()+([mode isEqual:@"deadline"]?50000000ULL:10000000000ULL);
        assert([guard requestEpoch:1 deadlineNS:deadline]);
    });
    assert(!dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,15000000000LL)));
    // Drain the enclosing serial completion before inspecting or requesting again.
    dispatch_sync(q,^{});
    BOOL success=[@[@"normal-two",@"early-receipt",@"duplicate-receipt"] containsObject:mode];
    dispatch_sync(q,^{
        assert([guard.result[@"verifier_on_serial_queue"] boolValue]);
        assert(![guard.result[@"busy"] boolValue]);
        if(success){assert(polls==1);assert(![guard requestEpoch:1 deadlineNS:nowNS()+10000000000ULL]);epoch=2;assert([guard requestEpoch:2 deadlineNS:nowNS()+10000000000ULL]);}
        else {assert(!polls && [guard.result[@"stopped"] boolValue]);assert(![guard requestEpoch:1 deadlineNS:nowNS()+10000000000ULL]);}
    });
    if(success){assert(!dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,15000000000LL)));dispatch_sync(q,^{});}
    __block NSDictionary *row;
    dispatch_sync(q,^{
        last=guard.result;assert([last[@"full_checks"] unsignedIntegerValue]==checks && [last[@"worker_returns"] unsignedIntegerValue]==checks);
        assert(polls==(success?2:0) && finishes==(success?2:1));
        if([mode isEqual:@"deadline"])assert(expiredWhileOwned);
        if([mode isEqual:@"early-receipt"] || [mode isEqual:@"duplicate-receipt"])assert([last[@"discarded_receipts"] unsignedIntegerValue]==2);
        assert(![guard requestEpoch:3 deadlineNS:nowNS()+10000000000ULL]);
        row=@{@"case":mode,@"passed":@YES,@"guard":last,@"full_checks":@(checks),@"local_polls":@(polls),@"job_rechecks":@(rechecks),@"notifications":@(notifications),@"worker_body_ended_before_recheck":@(workerReturnedBeforeRecheck),@"deadline_stopped_while_worker_owned":@(expiredWhileOwned),@"native_submissions":@0,@"real_sdk_objects":@0};
    });
    NSData *raw=[NSJSONSerialization dataWithJSONObject:row options:NSJSONWritingSortedKeys error:NULL];assert(raw);fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;
}}
