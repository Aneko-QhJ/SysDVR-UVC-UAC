// Actual derived controller + verifier/permit, frozen fake SDK and fake clock.
#import "../host/a23_checked_export.h"
static NSDictionary *exportConfig;
static A23VerifiedEntryCoordinator *exportCoordinator;
static A23ReadOnlyScopeVerifier *exportVerifier;
static BOOL staleGetterSeen=NO,gettersHadNoChecks=NO;
void A23ExportModelCheckpoint(NSString *stage){
    NSString *name=exportConfig[@"case"],*repo=exportConfig[@"repository"],*host=exportConfig[@"host"];
    BOOL source=([stage isEqual:@"before_precheck"] && [name isEqual:@"before-pre-source"]) ||
        ([stage isEqual:@"mid_payload"] && [name isEqual:@"mid-payload-source"]) ||
        ([stage isEqual:@"after_payload"] && [@[@"after-payload-source",@"stale-getters"] containsObject:name]) ||
        ([stage isEqual:@"after_postcheck"] && [name isEqual:@"after-post-source"]);
    if(source)change([repo stringByAppendingPathComponent:@"research/usb-ds-iso/host/a23_scope_verifier.m"]);
    if([stage isEqual:@"after_payload"] && [name isEqual:@"after-payload-baseline"])
        change([[exportConfig[@"cards"] stringByAppendingPathComponent:@"20261022-live-two-epoch-first-read"] stringByAppendingPathComponent:@"card/logfile.txt"]);
    if([stage isEqual:@"after_payload"] && [name isEqual:@"after-payload-context"])
        change([exportConfig[@"job"] stringByAppendingPathComponent:@"native-context.json"]);
    if(([stage isEqual:@"after_payload"] && [name isEqual:@"after-payload-bytes"]) ||
        ([stage isEqual:@"after_receipt"] && [name isEqual:@"after-receipt-bytes"]))
        change([[host stringByAppendingPathComponent:@"live-final"] stringByAppendingPathComponent:@"entry-current.json"]);
    if([stage isEqual:@"after_payload"] && [name isEqual:@"stale-getters"]){
        NSDictionary *before=exportVerifier.cadenceMetrics;
        staleGetterSeen=[exportCoordinator.result[@"complete"] boolValue];
        for(unsigned i=0;i<16;++i){(void)exportCoordinator.result;(void)exportCoordinator.finalStatus;}
        gettersHadNoChecks=[before isEqual:exportVerifier.cadenceMetrics];assert(staleGetterSeen && gettersHadNoChecks);
    }
}
int main(int argc,const char *argv[]){@autoreleasepool {
    assert(argc==2);NSDictionary *c=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:@(argv[1])] options:0 error:NULL];assert(c);
    exportConfig=c;NSString *name=c[@"case"],*host=c[@"host"];
    A23ModelScopeVerifier *v=[[A23ModelScopeVerifier alloc] initWithBuild:c[@"build"] repository:c[@"repository"] cards:c[@"cards"] ledger:c[@"ledger"] records:c[@"records"]];assert(v && [v verifyCore]);exportVerifier=v;
    PairOperations *op=pairOperations(name,NO);Live75Status *r=[Live75Status new];r.fault=name;r.clock=[VerifiedClock new];op.interface=r;
    assert([pairCandidate()[@"service_token"] intValue]==7 && !pairZero(r.dataStores[0]));
    dispatch_queue_t q=dispatch_queue_create("a23.checked.export",DISPATCH_QUEUE_SERIAL);
    NSMutableData *storage=[NSMutableData dataWithLength:sizeof(EntryFixture)];EntryFixture *f=storage.mutableBytes;f->interface=r;
    A23WaitOps ops={.context=f,.create=efCreate,.matching=efMatching,.valid=efValid,.next=efNext,.identity=efIdentity,.interest=efInterest,.pump=efPump,.release=efRelease,.destroy=efDestroy};
    __block A23TwoEpochEntry *entry=nil;__block A23CheckedTwoEpochRun *loop=nil;
    __block BOOL pendingSkipped=NO;
    dispatch_sync(q,^{
        A23SharedSequenceModelPermit *permit=[[A23SharedSequenceModelPermit alloc] initWithJob:c[@"job"] expectedScope:v.scope verifier:^BOOL(NSDictionary *s){return [v verifyLiveJob:s job:c[@"job"]];}];assert(permit);
        A23PairedSimulationProvider *provider=pairProvider(op,q,YES,^(uint32_t m){(void)m;[entry detachedRegistryID:102];});
        entry=[[A23TwoEpochEntry alloc] initWithDirectory:host queue:q clock:r.clock ops:&ops provider:provider permit:permit context:efContext(v.scope[@"receiver_sha256"]) binding:c[@"binding"]];assert(entry);
        exportCoordinator=[[A23VerifiedEntryCoordinator alloc] initWithEntry:entry verifier:v permit:permit scope:v.scope job:c[@"job"]];
        loop=[[A23CheckedTwoEpochRun alloc] initWithTarget:(id<A23CheckedEntryTarget>)exportCoordinator directory:host stop:^{[entry requestExit];}];assert(loop && [loop begin] && ![loop begin]);[loop tick];[loop tick];assert(r.submissions==1);
    });
    if([name isEqual:@"exit-running"]){
        dispatch_sync(q,^{NSDictionary *before=v.cadenceMetrics;change([c[@"repository"] stringByAppendingPathComponent:@"research/usb-ds-iso/host/a23_scope_verifier.m"]);[loop requestExit];[loop tick];pendingSkipped=[before isEqual:v.cadenceMetrics];assert(pendingSkipped);});
    }else{
        for(NSUInteger n=0;n<2;++n){
            __block BOOL stopped;dispatch_sync(q,^{stopped=[entry.result[@"stopped"] boolValue];});if(stopped)break;
            if([name isEqual:@"queued-delay"])dispatch_sync(q,^{[r deliver:n];[r.clock advanceNS:25000000];});else [r deliver:n];
            dispatch_sync(q,^{[loop tick];});if(!n)dispatch_sync(q,^{[loop tick];});
        }
        if([@[@"payload-collision",@"acceptance-collision"] containsObject:name]){
            NSString *folder=[name isEqual:@"payload-collision"]?@"live-final":@"live-acceptance";
            assert([[NSFileManager defaultManager] createDirectoryAtPath:[host stringByAppendingPathComponent:folder] withIntermediateDirectories:NO attributes:nil error:NULL]);
        }
        [r.clock advanceNS:250000001];dispatch_sync(q,^{[loop tick];});
    }
    __block NSDictionary *row;
    dispatch_sync(q,^{
        NSDictionary *before=v.cadenceMetrics;NSUInteger submissions=r.submissions;
        BOOL finished=[loop.status[@"finished"] boolValue];if(finished){[loop tick];assert([before isEqual:v.cadenceMetrics] && r.submissions==submissions);}
        row=@{@"schema":@"A23-checked-export-fixture-1",@"case":name,@"loop":loop.status,@"entry":entry.result,@"cadence":v.cadenceMetrics,
            @"stale_getter_seen":@(staleGetterSeen),@"getters_had_no_checks":@(gettersHadNoChecks),@"pending_full_checks_skipped":@(pendingSkipped),
            @"calls":@{@"iso_submissions":@(r.submissions),@"burst_triggers":@(r.triggers),@"aborts":@(r.aborts),@"sdk_destroys":@(r.destroys),@"opens":@(op.opens)},
            @"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0};
        BOOL complete=[@[@"normal",@"queued-delay",@"after-post-source",@"after-receipt-bytes"] containsObject:name];
        assert([loop.status[@"success"] boolValue]==complete);assert(r.submissions<=2 && r.triggers<=2 && !r.destroys);
        efExport(host,@"controller-observation.json",row);
    });
    NSData *raw=[NSJSONSerialization dataWithJSONObject:row options:NSJSONWritingSortedKeys error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;
}}
