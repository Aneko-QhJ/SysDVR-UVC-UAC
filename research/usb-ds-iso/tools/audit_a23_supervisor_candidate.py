"""Run a pinned Python-only supervisor against cached driver model materials."""
from pathlib import Path
import argparse,json,subprocess
import a23_supervisor_candidate as supervisor
import a23_supervisor_materials as materials
import audit_a23_driver_worker_failure_model as previous
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-driver-worker-failure-model-closeout-20261020'
PARENT_SUM='e95dc209165541193d5e96c3653aed0125089a9b7a0b9a72c80725bcd2c571ff'
SOURCE_REVIEW_SUM='64e842cd32025f5cf947af2e035ea33885d8ba5fe7075b0698896a95babf0c48'
NEW=('tests/a23_supervised_worker_fixture.py','tools/a23_supervisor_candidate.py','tools/a23_supervisor_materials.py','tools/audit_a23_supervisor_candidate.py','tests/test_a23_supervisor_candidate.py')
SEEDS=('normal','capture-worker-error','capture-worker-unfinished-return')
FALSE={**previous.FALSE,'supervisor_production_integrated':False,'supervisor_observation_provenance_authenticated':False,
       'process_tree_reclamation_verified':False,'spawn_to_exec_atomic_binding_verified':False}
seal,sealed,reference=previous.seal,previous.sealed,previous.reference
cache=previous.cache
EXPECTED={
 'normal':(), 'no-stdout':('missing_stdout',),'malformed-stdout':('malformed_stdout',),'partial-stdout':('malformed_stdout',),
 'empty-materials':('invalid_materials',),'missing-material':('invalid_materials',),'abnormal-exit':('worker_exit',),
 'signal-exit':('worker_exit',),'timeout-before-output':('worker_timeout','worker_exit','incomplete_streams','missing_stdout','invalid_materials'),
 'timeout-after-output':('worker_timeout','worker_exit','incomplete_streams'),
 'oversize-stdout':('output_limit','worker_exit','incomplete_streams'),
 'oversize-stderr':('output_limit','worker_exit','stderr_not_empty','incomplete_streams','missing_stdout'),
 'stderr-output':('stderr_not_empty',),'wrong-case':('stdout_binding',),'wrong-digest':('stdout_binding',),
 'driver-failure':('worker_health','driver_incomplete'),'worker-failure':('worker_health',),
 'spawn-error':('spawn_failure','missing_stdout','invalid_materials')}


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==488,'prior488 drift')
    for name in NEW:
        key=BASE+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def seed_manifest(root):
    return dict(schema='A23-supervisor-seed-bytes-1',source_review_sha256=SOURCE_REVIEW_SUM,
                cases={n:materials.inventory(cache(root/n)) for n in SEEDS},provenance_authenticated=False)


def seed_check(root):
    saved=f.load(root/'manifest.json');f.require(f.encode(saved)==f.encode(seed_manifest(root)),'supervisor seed bytes differ')
    for name in SEEDS:
        c=cache(root/name);row={k:f.parse(c[v]) for k,v in (('result','result.json'),('receipt_status','receipt-status.json'),('facts','fault-facts.json'),('version','version-profile.json'))}
        if name=='normal':materials.d.validate(name,row,c)
        else:row['worker_failure']=f.parse(c['worker-failure.json']);materials.worker.validate(name,row,c)
    return saved


def reject_spawn(*args,**kwargs):raise OSError('injected fixed-fixture spawn failure')


def analyze_case(directory,name):
    observation=f.load(directory/'observation.json');stdout=a.read(directory/'stdout.bin');stderr=a.read(directory/'stderr.bin')
    result=materials.assess(name,observation,stdout,stderr,cache(directory/'materials'))
    f.require(result['completion_admitted'] is (name=='normal') and set(result['reasons'])==set(EXPECTED[name]),'supervisor disposition differs '+name+': '+str(result['reasons']))
    if name!='spawn-error':f.require(observation['spawned'] and observation['reaped'],'child not reaped')
    if name=='abnormal-exit':f.require(observation['returncode']==7,'exit7 not observed')
    if name=='signal-exit':f.require(observation['returncode']==-15,'signal exit not observed')
    if name.startswith('timeout-') or name.startswith('oversize-'):f.require(observation['returncode']==-9 and observation['group_kill_sent'],'bounded child not killed/reaped')
    if name=='spawn-error':f.require(not observation['spawned'],'spawn failure created child')
    return result


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);seed_check(inputs);script=source/BASE/'tests/a23_supervised_worker_fixture.py';pin=f.sha(a.read(script));semantic={};observations={}
    for name in materials.CASES:
        directory=output/name;directory.mkdir(mode=0o700);kwargs={'popen':reject_spawn} if name=='spawn-error' else {}
        observation,stdout,stderr=supervisor.run_fixture(script,pin,name,inputs/materials.material_case(name),directory/'materials',**kwargs)
        a.put(directory,'observation.json',f.encode(observation));a.put(directory,'stdout.bin',stdout);a.put(directory,'stderr.bin',stderr)
        semantic[name]=analyze_case(directory,name);a.put(directory,'analysis.json',f.encode(semantic[name]));observations[name]=observation
    f.require(sum(o['launches'] for o in observations.values())==17 and all(o['retries']==0 for o in observations.values()),'process accounting differs')
    return dict(passed=True,model_cases=18,semantic=semantic,observations=observations,fixture_sha256=pin,python_fixture_process_executions=17,
                simulated_spawn_failures=1,supervisor_monotonic_deadlines_used=True,driver_clock_or_timebase_queries=0,
                native_compiler_jobs=0,isolated_native_model_executions=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,production_receiver_executions=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');report=f.load(root/'results.json');f.require(audit['source_count']==493 and audit['prior_sources_unchanged']==488 and len(audit['source_hashes'])==493,'supervisor source count differs')
    for name,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/name))==h,'frozen supervisor source differs')
    seed_check(root/'inputs');f.require(report['model_cases']==18 and set(report['semantic'])==set(materials.CASES),'supervisor case inventory differs')
    f.require(report['fixture_sha256']==f.sha(a.read(root/'source'/BASE/'tests/a23_supervised_worker_fixture.py')),'supervised fixture differs')
    for name in materials.CASES:
        checked=analyze_case(root/'work'/name,name)
        f.require(f.encode(checked)==f.encode(report['semantic'][name]) and f.encode(checked)==a.read(root/'work'/name/'analysis.json'),'saved supervisor result differs')
        f.require(f.encode(f.load(root/'work'/name/'observation.json'))==f.encode(report['observations'][name]),'saved supervisor observation differs')
    f.require(all(report[k] is False for k in FALSE),'supervisor claims authority');return report


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new supervisor review required');frozen=sources();output.mkdir(mode=0o700)
    for name,h in frozen.items():
        raw=w.plain(w.b.REPO/name);f.require(f.sha(raw)==h,'supervisor source drift');a.put(output,'source/'+name,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM)
    for name in SEEDS:
        for path,raw in cache(review/'work/models-optimized'/name).items():a.put(output,'inputs/'+name+'/'+path,raw)
    a.put(output,'inputs/manifest.json',f.encode(seed_manifest(output/'inputs')))
    try:result=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='fixed-python-fixture-only')));seal(output);raise
    f.require(sources()==frozen,'supervisor source drift after exercise')
    a.put(output,'results.json',f.encode(result));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=493,prior_sources_unchanged=488,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=18)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
