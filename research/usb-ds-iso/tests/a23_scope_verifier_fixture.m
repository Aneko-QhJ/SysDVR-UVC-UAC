// Appended after frozen entry fixture prefixes. Synthetic clock + fake IOKit /
// SDK operations only; real verifier, permit and complete entry pipeline execute.
#import "../host/a23_scope_verifier.h"
@interface VerifiedClock : TwoClock
@end
@implementation VerifiedClock {atomic_uint_fast64_t _value;}
- (instancetype)init {if((self=[super init]))atomic_init(&_value,1000000);return self;}
- (uint64_t)nowTicks{return atomic_fetch_add(&_value,100);}
- (uint32_t)numerator{return 1;}
- (uint32_t)denominator{return 1;}
- (void)advanceNS:(uint64_t)n{atomic_fetch_add(&_value,n);}
@end
static void change(NSString *path){assert([[@"changed\n" dataUsingEncoding:NSUTF8StringEncoding] writeToFile:path options:0 error:NULL]);}
static void mutation(NSDictionary *c){
    NSString *name=c[@"case"],*repo=c[@"repository"],*cards=c[@"cards"];
    if([name containsString:@"source"] || [name isEqual:@"restored-after-observed"])change([repo stringByAppendingPathComponent:@"research/usb-ds-iso/host/a23_scope_verifier.m"]);
    else if([name isEqual:@"new-recovery"]){NSString *p=[cards stringByAppendingPathComponent:@"new-recovery"];assert([[NSFileManager defaultManager] createDirectoryAtPath:p withIntermediateDirectories:NO attributes:nil error:NULL]);assert([[@"{}" dataUsingEncoding:NSUTF8StringEncoding] writeToFile:[p stringByAppendingPathComponent:@"snapshot.json"] options:0 error:NULL]);}
    else if([name isEqual:@"baseline-drift"])change([[cards stringByAppendingPathComponent:@"20261018-context65-first-live-read"] stringByAppendingPathComponent:@"card/logfile.txt"]);
    else if([name isEqual:@"legacy-drift"])change([c[@"ledger"] stringByAppendingPathComponent:@"block-00049.json"]);
    else if([name isEqual:@"foreign-job"])change(c[@"foreign_job"]);
    else if([name isEqual:@"own-native-context"])change([c[@"job"] stringByAppendingPathComponent:@"native-context.json"]);
    else if([name isEqual:@"new-empty-job"]){NSString *p=[[[c[@"job"] stringByDeletingLastPathComponent] stringByAppendingPathComponent:@"11111111-1111-4111-8111-111111111111"] copy];assert([[NSFileManager defaultManager] createDirectoryAtPath:p withIntermediateDirectories:NO attributes:nil error:NULL]);}
    else if([name isEqual:@"unknown-shared-file"]){NSString *p=[[c[@"job"] stringByDeletingLastPathComponent] stringByDeletingLastPathComponent];assert([[@"unexpected" dataUsingEncoding:NSUTF8StringEncoding] writeToFile:[p stringByAppendingPathComponent:@"unexpected"] options:NSDataWritingWithoutOverwriting error:NULL]);}
}
int main(int argc,const char *argv[]){@autoreleasepool {
    assert(argc==2);NSDictionary *c=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:@(argv[1])] options:0 error:NULL];assert(c);
    NSString *name=c[@"case"],*host=c[@"host"];A23ModelScopeVerifier *v=[[A23ModelScopeVerifier alloc] initWithBuild:c[@"build"] repository:c[@"repository"] cards:c[@"cards"] ledger:c[@"ledger"] records:c[@"records"]];assert(v);
    BOOL initial=[v verifyCore];NSDictionary *scope=v.scope;__block A23SharedSequenceModelPermit *permit=nil;__block A23VerifiedEntryCoordinator *coordinator=nil;__block A23TwoEpochEntry *entry=nil;
    PairOperations *op=pairOperations(name,NO);SDKModelInterface *r=[SDKModelInterface new];r.fault=name;r.clock=[VerifiedClock new];op.interface=r;assert([pairCandidate()[@"service_token"] intValue]==7 && !pairZero(r.dataStores[0]));
    dispatch_queue_t q=dispatch_queue_create("a23.verified.entry",DISPATCH_QUEUE_SERIAL);NSMutableData *storage=[NSMutableData dataWithLength:sizeof(EntryFixture)];EntryFixture *f=storage.mutableBytes;f->interface=r;
    A23WaitOps ops={.context=f,.create=efCreate,.matching=efMatching,.valid=efValid,.next=efNext,.identity=efIdentity,.interest=efInterest,.pump=efPump,.release=efRelease,.destroy=efDestroy};
    __block BOOL fullChecksSkipped=NO;
    if(initial)dispatch_sync(q,^{
        permit=[[A23SharedSequenceModelPermit alloc] initWithJob:c[@"job"] expectedScope:scope verifier:^BOOL(NSDictionary *s){return [v verifyScope:s job:c[@"job"]];}];assert(permit);
        A23PairedSimulationProvider *provider=pairProvider(op,q,YES,^(uint32_t m){(void)m;[entry detachedRegistryID:102];});
        entry=[[A23TwoEpochEntry alloc] initWithDirectory:host queue:q clock:r.clock ops:&ops provider:provider permit:permit context:efContext(scope[@"receiver_sha256"]) binding:c[@"binding"]];assert(entry);
        coordinator=[[A23VerifiedEntryCoordinator alloc] initWithEntry:entry verifier:v permit:permit scope:scope job:c[@"job"]];[coordinator begin];[coordinator tick];assert(!r.submissions);
        if(![@[@"normal",@"queued-delay",@"bad-payload",@"during-pending-source",@"stopped-pending-source",@"between-epochs-source",@"before-final-source",@"after-final-source"] containsObject:name]){
            NSString *p=[c[@"repository"] stringByAppendingPathComponent:@"research/usb-ds-iso/host/a23_scope_verifier.m"];NSData *saved=[NSData dataWithContentsOfFile:p];mutation(c);[coordinator tick];
            if([name isEqual:@"restored-after-observed"]){assert([v.result[@"failed"] boolValue]);assert([saved writeToFile:p options:0 error:NULL]);[coordinator tick];}
        }else [coordinator tick];
    });
    __block BOOL started=NO;if(entry)dispatch_sync(q,^{started=[entry.result[@"started"] boolValue];});
    if(started){
        if([name isEqual:@"stopped-pending-source"])dispatch_sync(q,^{mutation(c);NSUInteger count=[v.result[@"checks"] unsignedIntegerValue];[r.clock advanceNS:17000000];[coordinator tick];[coordinator finalizeOnce];(void)coordinator.result;(void)coordinator.finalStatus;fullChecksSkipped=count==[v.result[@"checks"] unsignedIntegerValue];assert(fullChecksSkipped && [entry.result[@"stopped"] boolValue] && r.submissions==1);});
        if([name isEqual:@"during-pending-source"])dispatch_sync(q,^{mutation(c);NSUInteger count=[v.result[@"checks"] unsignedIntegerValue];[coordinator tick];fullChecksSkipped=count==[v.result[@"checks"] unsignedIntegerValue];assert(fullChecksSkipped && r.submissions==1);});
        for(NSUInteger n=0;n<2;++n){__block BOOL stopped;dispatch_sync(q,^{stopped=[entry.result[@"stopped"] boolValue];});if(stopped)break;
            if([name isEqual:@"queued-delay"])dispatch_sync(q,^{[r deliver:n];[r.clock advanceNS:25000000];});else [r deliver:n];
            dispatch_sync(q,^{[coordinator tick];});
            if(n==0)dispatch_sync(q,^{if([name isEqual:@"between-epochs-source"])mutation(c);[coordinator tick];});
        }
        [r.clock advanceNS:250000001];dispatch_sync(q,^{[coordinator tick];});
    }
    if(coordinator)dispatch_sync(q,^{if([name isEqual:@"before-final-source"])mutation(c);[coordinator finalizeOnce];if([name isEqual:@"after-final-source"])mutation(c);});
    __block NSDictionary *result=@{},*final=@{},*native=@{};
    dispatch_sync(q,^{
        if(coordinator){result=coordinator.result;final=coordinator.finalStatus;efExport(host,@"entry-current.json",result);efExport(host,@"entry-final-status.json",final);
            if([result[@"driver"] isKindOfClass:NSDictionary.class]){efExport(host,@"result.json",result[@"driver"]);efExport(host,@"receipt-status.json",result[@"driver_receipt"]);}}
        NSDictionary *pr=permit ? permit.result : @{};BOOL replay=YES;if(permit){replay=![permit claimProcess:c[@"binding"] context:efContext(scope[@"receiver_sha256"])] && ![permit claimSelection:(A23WaitIdentity){.device_id=101,.interface_id=102,.speed=3} binding:c[@"binding"] context:efContext(scope[@"receiver_sha256"])];}
        native=@{@"schema":@"A23-shared32-native-fixture-1",@"case":name,@"init_accepted":@((BOOL)(permit!=nil)),@"process_returned":pr[@"process_claimed"] ?: @NO,@"selection_returned":pr[@"selection_claimed"] ?: @NO,@"replay_blocked":@(replay),@"permit":pr,@"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0};
    });
    BOOL clean=[@[@"normal",@"queued-delay"] containsObject:name];if(clean)assert([result[@"complete"] boolValue] && [final[@"saved"] boolValue]);else assert(![result[@"complete"] boolValue]);
    NSDictionary *summary=@{@"schema":@"A23-verified-scope-fixture-1",@"case":name,@"initial_core":@(initial),@"verifier":v.result,@"native":native,@"entry":result,@"final":final,@"full_checks_skipped_while_pending":@(fullChecksSkipped),
        @"calls":@{@"wait_creates":@(f->creates),@"opens":@(op.opens),@"iso_submissions":@(r.submissions),@"burst_triggers":@(r.triggers),@"aborts":@(r.aborts),@"sdk_destroys":@(r.destroys),@"sdk_live_refs":@(op.liveReferences)},@"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0};
    NSData *raw=[NSJSONSerialization dataWithJSONObject:summary options:NSJSONWritingSortedKeys error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;
}}
