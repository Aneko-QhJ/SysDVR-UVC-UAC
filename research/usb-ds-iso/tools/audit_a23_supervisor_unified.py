"""Audit one supervisor/schema/policy over collection, cleanup and close faults."""
from pathlib import Path
import argparse,json,subprocess
import a23_supervisor_unified as supervisor
import a23_supervisor_unified_materials as materials
import audit_a23_supervisor_cleanup as previous
import audit_a23_supervisor_candidate as collection
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-supervisor-cleanup-closeout-20261020-r2'
PARENT_SUM='0cf14c60634f1ca93895c2b9cdaae441b274b33b43dd14e64d68810343fb213d'
SOURCE_REVIEW_SUM='0dd9603fb5d9b0084c07ca423dc4dac9ffb9925547737fda7f7efee3f5e8054e'
NEW=('tests/a23_supervisor_unified_fixture.py','tools/a23_supervisor_unified.py','tools/a23_supervisor_unified_materials.py','tools/audit_a23_supervisor_unified.py','tests/test_a23_supervisor_unified.py')
FALSE={**previous.FALSE,'stream_close_failure_upgrades_admission':False}
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
GOOD=materials.GOOD
WAIT_FAILURES=previous.WAIT_FAILURES|{'close-and-wait-error'}
CLEANUP_BAD=set(previous.materials.CASES)-GOOD
TIMED=CLEANUP_BAD-{'read-error','selector-error'}|{'timeout-before-output','timeout-after-output','close-and-wait-error'}
SIGNALED=TIMED|{'read-error','selector-error','oversize-stdout','oversize-stderr'}


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==498,'prior498 drift')
    for name in NEW:
        key=BASE+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def analyze_case(directory,name):
    o=f.load(directory/'observation.json');stdout=a.read(directory/'stdout.bin');stderr=a.read(directory/'stderr.bin')
    r=materials.assess(name,o,stdout,stderr,cache(directory/'materials'));h=f.load(directory/'harness.json')
    f.require(r['completion_admitted'] is (name in GOOD),'unified admission differs '+name)
    f.require(o['spawned'] is (name!='spawn-error') and o['reaped'] is (name!='spawn-error' and name not in WAIT_FAILURES),'unified spawn/reap differs')
    f.require(o['timed_out'] is (name in TIMED) and o['group_kill_attempted'] is (name in SIGNALED),'unified deadline/signal differs '+name)
    f.require(o['reader_error'] is (name=='read-error') and o['selector_error'] is (name=='selector-error') and o['read_interrupts']==int(name=='read-interrupted'),'unified read/selector differs')
    f.require(o['wait_error'] is (name in WAIT_FAILURES) and o['wait_timed_out'] is (name in ('wait-timeout','cleanup-multiple-errors')),'unified wait outcome differs')
    f.require(o['close_errors']==materials.close_errors(name) and o['close_attempts']==(materials.CLOSE_ORDER if name!='spawn-error' else []),'unified close outcomes differ')
    f.require(o['cleanup_wait_attempted'] is (name in SIGNALED),'unified cleanup wait bypassed')
    f.require(o['limit_exceeded']==('stdout' if name=='oversize-stdout' else 'stderr' if name=='oversize-stderr' else None),'unified output limit differs')
    group='error' if name in ('group-kill-error','cleanup-multiple-errors') else 'not_found' if name=='group-kill-not-found' else 'sent' if name in SIGNALED else 'none'
    fallback='error' if name=='cleanup-multiple-errors' else 'sent' if name in ('group-kill-error','group-kill-not-found') else 'none'
    f.require(o['group_kill_outcome']==group and o['fallback_kill_outcome']==fallback,'unified signal outcome differs')
    exitcode=None if name=='spawn-error' else 7 if name=='abnormal-exit' else -15 if name=='signal-exit' else -9 if name in SIGNALED and not name.startswith('leader-') else 0
    f.require(o['returncode']==(None if name in WAIT_FAILURES else exitcode),'unified candidate exit differs '+name)
    expected_h=dict(rescue_used=name in WAIT_FAILURES,resource_rescues=materials.close_errors(name),direct_child_reaped=name!='spawn-error',returncode=exitcode,admission_upgraded=False,descendant_reaping_verified=False)
    f.require(f.encode(h)==f.encode(expected_h),'unified harness outcome differs')
    if name in collection.EXPECTED:f.require(set(collection.EXPECTED[name])<=set(r['reasons']),'collection rejection contract lost '+name)
    if name.startswith('leader-'):
        f.require(a.read(directory/'control/leader-exiting')==b'after holder ready\n','unified holder handshake differs')
        holder=f.load(directory/'control/holder.json');f.require(set(holder)=={'holder_pid','group','ttl_seconds'} and type(holder['holder_pid']) is int and holder['holder_pid']>0 and type(holder['group']) is int and holder['group']>0 and holder['ttl_seconds']==2,'unified holder metadata differs')
        eof={'leader-both-held':(False,False),'leader-stdout-held':(False,True),'leader-stderr-held':(True,False)}[name]
        f.require((o['stdout_eof'],o['stderr_eof'])==eof,'unified inherited pipe EOF differs')
    if name in ('eof-worker-alive','wait-error','wait-timeout','close-and-wait-error'):f.require(o['stdout_eof'] and o['stderr_eof'],'unified EOF before exit not observed')
    if name in materials.CLOSE_CASES:f.require('close_error' in r['reasons'],'close failure not denied')
    return {**r,'harness':h,'read_interrupts':o['read_interrupts']}


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);collection.seed_check(inputs);script=source/BASE/'tests/a23_supervisor_unified_fixture.py';pin=f.sha(a.read(script));semantic={};observations={}
    f.require(len(materials.CASES)==37 and set(collection.materials.CASES)|set(previous.materials.CASES)|set(materials.CLOSE_CASES)==set(materials.CASES),'unified coverage differs')
    for name in materials.CASES:
        directory=output/name;directory.mkdir(mode=0o700)
        o,stdout,stderr,owned=supervisor.run_fixture(script,pin,name,inputs/materials.material_case(name),directory/'materials')
        h=supervisor.harness_finish(owned,o)
        for file,value in (('observation.json',o),('harness.json',h)):a.put(directory,file,f.encode(value))
        a.put(directory,'stdout.bin',stdout);a.put(directory,'stderr.bin',stderr)
        semantic[name]=analyze_case(directory,name);a.put(directory,'analysis.json',f.encode(semantic[name]));observations[name]=o
    return dict(passed=True,model_cases=37,semantic=semantic,observations=observations,fixture_sha256=pin,
        python_fixture_direct_children=sum(o['launches'] for o in observations.values()),forked_pipe_holders=3,
        candidate_direct_reaps=sum(o['reaped'] for o in observations.values()),harness_rescue_reaps=sum(r['harness']['rescue_used'] for r in semantic.values()),
        parent_resource_rescues=sum(len(r['harness']['resource_rescues']) for r in semantic.values()),
        native_compiler_jobs=0,isolated_native_model_executions=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,production_receiver_executions=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');report=f.load(root/'results.json');f.require(audit['source_count']==503 and audit['prior_sources_unchanged']==498 and len(audit['source_hashes'])==503,'unified source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen unified source differs')
    collection.seed_check(root/'inputs');f.require(report['model_cases']==37 and set(report['semantic'])==set(materials.CASES),'unified case inventory differs')
    f.require(report['fixture_sha256']==f.sha(a.read(root/'source'/BASE/'tests/a23_supervisor_unified_fixture.py')),'unified fixture differs')
    for name in materials.CASES:
        checked=analyze_case(root/'work'/name,name)
        f.require(f.encode(checked)==f.encode(report['semantic'][name]) and f.encode(checked)==a.read(root/'work'/name/'analysis.json'),'saved unified disposition differs')
        f.require(f.encode(f.load(root/'work'/name/'observation.json'))==f.encode(report['observations'][name]),'saved unified observation differs')
    f.require(all(report[k] is False for k in FALSE),'unified supervisor claims authority');return report


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new unified review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'unified source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM)
    for n,raw in cache(review/'inputs').items():a.put(output,'inputs/'+n,raw)
    try:result=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='fixed-python-unified-fixture-only')));seal(output);raise
    f.require(sources()==frozen,'unified source drift after exercise')
    a.put(output,'results.json',f.encode(result));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=503,prior_sources_unchanged=498,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=37)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
