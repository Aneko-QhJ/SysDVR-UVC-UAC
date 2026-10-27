"""Derive a model-only explicit-check candidate from the sealed live75 build."""
from pathlib import Path
import build_a23_live75_two_epoch as parent

w=parent.w
PARENT=w.A/'A23-live75-first-live-closeout-20261022'
PARENT_SUM='c0bd59ccc0c5f892a3b80eddf922a5d1ad43b60abfcd3383b0214f27dd40e04e'
NEW=('host/a23_guard_cadence_api.h','tools/a23_guard_cadence_revision.py',
     'tools/audit_a23_guard_cadence.py','tests/test_a23_guard_cadence.py')


def once(raw,before,after):
    w.require(raw.count(before)==1,'cadence anchor differs: '+before[:90])
    return raw.replace(before,after)


def inputs():
    w.card.seal_verify(PARENT)
    w.require(parent.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'live75 result closeout drift')
    old=w.load(PARENT/'source-hashes.json')
    w.require(parent.sources()==old and len(old)==597,'original597 changed')
    out=dict(old)
    for name in NEW:out['research/usb-ds-iso/'+name]=parent.sha(w.plain(w.ROOT/name))
    w.require(len(out)==601,'cadence source closure differs')
    return dict(sorted(out.items()))


def guards():
    hashes=inputs()
    for p,h in w.load(PARENT/'protected-hashes.json').items():
        w.require(parent.sha(w.plain(Path(p)))==h,'old protected file changed')
    for name,root in [('predecessor-shared32-hashes.json',parent.PREDECESSOR),
                      ('successor-namespace-hashes.json',parent.FORMAL_ROOT)]:
        w.require(all(not p.is_symlink() and (p.is_file() or p.is_dir()) for p in root.rglob('*')),'unsafe ledger node')
        actual={p.relative_to(root).as_posix():parent.sha(w.plain(p)) for p in sorted(root.rglob('*')) if p.is_file()}
        w.require(actual==w.load(PARENT/name),'spent namespace changed')
    w.require(w.plain(Path(w.load(PARENT/'once-record.json')['result_closeout'])/'once-record.json')==
              w.plain(w.A/'A23-live75-two-epoch-once-20261022-r1.json'),'actual113 record drift')
    parent.predecessor()
    return hashes


def instrument(raw):
    raw='#import "a23_guard_cadence_api.h"\n#include <time.h>\n'+raw
    raw=once(raw,'BOOL _failed,_model;NSUInteger _checks;',
        'BOOL _failed,_model,_coreValidated;NSUInteger _checks,_liveJobChecks;NSMutableArray *_coreTimings;NSString *_checkPhase;')
    raw=once(raw,'- (BOOL)verifyCore {','''- (void)setCheckPhase:(NSString *)phase {_checkPhase=[phase copy];}
- (NSDictionary *)cadenceMetrics {
    return @{ @"schema":@"A23-guard-cadence-metrics-1",@"full_invocations":@(_coreTimings.count),
        @"live_job_checks":@(_liveJobChecks),@"full_checks":_coreTimings ? [_coreTimings copy] : @[],
        @"clock_domain":@"host_CLOCK_MONOTONIC_RAW",@"sdk_clock_is_synthetic":@YES };
}
- (BOOL)verifyCore {
    struct timespec begin,end;
    if(clock_gettime(CLOCK_MONOTONIC_RAW,&begin)){_failed=YES;return NO;}
    BOOL ok=[self checkCoreFiles];if(ok && !_failed)_coreValidated=YES;
    if(clock_gettime(CLOCK_MONOTONIC_RAW,&end)){_failed=YES;return NO;}
    uint64_t a=(uint64_t)begin.tv_sec*1000000000ULL+(uint64_t)begin.tv_nsec;
    uint64_t z=(uint64_t)end.tv_sec*1000000000ULL+(uint64_t)end.tv_nsec;
    if(z<a || _coreTimings.count>=1024){_failed=YES;return NO;}
    if(!_coreTimings)_coreTimings=[NSMutableArray new];
    [_coreTimings addObject:@{@"index":@(_coreTimings.count+1),@"phase":_checkPhase?:@"initial",
        @"begin_ns":@(a),@"end_ns":@(z),@"elapsed_ns":@(z-a),@"passed":@(ok)}];return ok;
}
- (BOOL)checkCoreFiles {''')
    return raw


def render_scope(raw,*,candidate):
    raw=instrument(raw)
    if not candidate:return raw
    raw=once(raw,'''- (BOOL)verifyScope:(NSDictionary *)scope job:(NSString *)job {
    if(![self verifyCore] || !equal(scope,_scope) || !canonical(job)){_failed=YES;return NO;}''',
        '''- (BOOL)verifyScope:(NSDictionary *)scope job:(NSString *)job {
    return [self verifyCore] && [self verifyLiveJob:scope job:job];
}
- (BOOL)verifyLiveJob:(NSDictionary *)scope job:(NSString *)job {
    ++_liveJobChecks;
    if(_failed || !_coreValidated || !equal(scope,_scope) || !canonical(job)){_failed=YES;return NO;}''')
    # Keep namespace witnesses and permit bytes live. Only the caller's explicit
    # full boundary certifies archive/source/baseline/history at this instant.
    start=raw.index('- (BOOL)guard {if(![_verifier verifyScope:')
    end=raw.index('\n@end',start)
    raw=raw[:start]+'''- (BOOL)guard:(NSString *)phase {
    [_verifier setCheckPhase:phase];
    if(![_verifier verifyScope:_scope job:_job] || [_permit.result[@"stale"] boolValue]){[_entry requestExit];return NO;}return YES;
}
- (BOOL)begin {return [self guard:@"before_begin"] && [_entry begin];}
- (void)tick {if(![self inflight] && ![self guard:@"before_tick"])return;[_entry tick];}
- (BOOL)finalizeOnce {
    if([self inflight] || ![self guard:@"before_finalize"])return NO;
    BOOL ok=[_entry finalizeOnce];return [self guard:@"after_finalize"] && ok;
}
- (BOOL)validateFinalExport {
    if([self inflight] || ![self guard:@"export_boundary"])return NO;
    NSDictionary *r=_entry.result,*s=_entry.finalStatus;
    return [r[@"complete"] boolValue] && [s[@"saved"] boolValue] && ![s[@"stale"] boolValue];
}
- (NSDictionary *)result {return _entry.result;}
- (NSDictionary *)finalStatus {return _entry.finalStatus;}'''+raw[end:]
    return raw


def fixture(source):
    import audit_a23_live75_two_epoch as old
    raw=old.fixture(source)
    raw='#import "a23_guard_cadence_api.h"\n'+raw
    raw=once(raw,'BOOL initial=[v verifyCore];',
        '''if([name hasPrefix:@"proof-"]){
        BOOL archive=NO;if([name isEqual:@"proof-archive-only"])archive=[v verifyArchive];
        BOOL accepted=[v verifyLiveJob:c[@"scope"] job:c[@"job"]];
        assert(!accepted && [v.result[@"failed"] boolValue]);
        NSDictionary *probe=@{@"schema":@"A23-cadence-proof-probe-1",@"case":name,@"archive_checked":@(archive),
            @"live_job_accepted":@(accepted),@"verifier":v.result,@"cadence":v.cadenceMetrics,
            @"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0};
        NSData *raw=[NSJSONSerialization dataWithJSONObject:probe options:NSJSONWritingSortedKeys error:NULL];
        fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;
    }
    BOOL initial=[v verifyCore];''')
    raw=once(raw,'return [v verifyScope:s job:c[@"job"]];',
        'return [v respondsToSelector:@selector(verifyLiveJob:job:)] ? [v verifyLiveJob:s job:c[@"job"]] : [v verifyScope:s job:c[@"job"]];')
    # A source/body change made after the first save must be caught at the next
    # explicit pre-arm boundary, including native claim and job changes.
    extras='@"between-epochs-baseline",@"between-epochs-legacy",@"between-epochs-predecessor",@"between-epochs-job",@"between-epochs-context",@"after-export-source",'
    raw=once(raw,'@"normal",@"queued-delay",@"bad-payload",',extras+'@"normal",@"queued-delay",@"bad-payload",')
    raw=once(raw,'__block BOOL fullChecksSkipped=NO;',
        '__block BOOL fullChecksSkipped=NO,gettersPure=NO,exportAccepted=NO;__block NSUInteger betweenChecks=0;')
    raw=once(raw,'dispatch_sync(q,^{[coordinator tick];});\n            if(n==0)dispatch_sync(q,^{if([name isEqual:@"between-epochs-source"])mutation(c);[coordinator tick];});',
        '''__block NSUInteger before=0;
            if(n==0)dispatch_sync(q,^{before=[v.cadenceMetrics[@"full_invocations"] unsignedIntegerValue];});
            dispatch_sync(q,^{[coordinator tick];});
            if(n==0)dispatch_sync(q,^{
                // Mirrors the live loop's result observation after the saving tick.
                (void)coordinator.result;
                NSDictionary *aliases=@{@"between-epochs-baseline":@"baseline-drift",@"between-epochs-legacy":@"legacy-drift",
                    @"between-epochs-predecessor":@"predecessor-drift",@"between-epochs-job":@"foreign-job",@"between-epochs-context":@"own-native-context"};
                if([name isEqual:@"between-epochs-source"])mutation(c);
                else if(aliases[name]){NSMutableDictionary *m=[c mutableCopy];m[@"case"]=aliases[name];mutation(m);}
                [coordinator tick];betweenChecks=[v.cadenceMetrics[@"full_invocations"] unsignedIntegerValue]-before;
            });''')
    raw=once(raw,'[coordinator finalizeOnce];if([name isEqual:@"after-final-source"])mutation(c);});',
        '''[coordinator finalizeOnce];if([name isEqual:@"after-final-source"])mutation(c);
        if([coordinator respondsToSelector:@selector(validateFinalExport)])exportAccepted=[coordinator validateFinalExport];
        else exportAccepted=[coordinator.result[@"complete"] boolValue];
        if([coordinator respondsToSelector:@selector(validateFinalExport)]){
            NSDictionary *before=v.cadenceMetrics;NSDictionary *r=coordinator.result,*s=coordinator.finalStatus;
            for(unsigned i=0;i<16;++i){assert([r isEqual:coordinator.result]);assert([s isEqual:coordinator.finalStatus]);}
            gettersPure=[before isEqual:v.cadenceMetrics];assert(gettersPure);
        }});''')
    raw=once(raw,'efExport(host,@"receipt-status.json",result[@"driver_receipt"]);}}',
        '''efExport(host,@"receipt-status.json",result[@"driver_receipt"]);}
            if([name isEqual:@"after-export-source"]){mutation(c);assert([coordinator respondsToSelector:@selector(validateFinalExport)]);
                exportAccepted=[coordinator validateFinalExport];result=coordinator.result;final=coordinator.finalStatus;assert(!exportAccepted);}
        }''')
    raw=once(raw,'@"full_checks_skipped_while_pending":@(fullChecksSkipped),',
        '@"full_checks_skipped_while_pending":@(fullChecksSkipped),@"cadence":v.cadenceMetrics,@"between_epoch_full_checks":@(betweenChecks),@"snapshot_getters_pure":@(gettersPure),@"export_accepted":@(exportAccepted),')
    return raw
