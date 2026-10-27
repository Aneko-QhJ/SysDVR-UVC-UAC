"""Replay fixed pipe/exit cleanup schedules without production/native execution."""
from pathlib import Path
import argparse,json,subprocess
import a23_supervisor_cleanup as supervisor
import a23_supervisor_cleanup_materials as materials
import audit_a23_supervisor_candidate as previous
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-supervisor-candidate-closeout-20261020'
PARENT_SUM='18bcf0c77ff28514aadf979c01292ae1eaa8006b12d85207a0e9e79231bb6062'
SOURCE_REVIEW_SUM='0d79d13386e5d5e8b25b9944f05371ce245ccfbbbc6b98f943adba36c6a5e24d'
NEW=('tests/a23_supervisor_cleanup_fixture.py','tools/a23_supervisor_cleanup.py','tools/a23_supervisor_cleanup_materials.py','tools/audit_a23_supervisor_cleanup.py','tests/test_a23_supervisor_cleanup.py')
FALSE={**previous.FALSE,'descendant_reaping_verified':False,'external_harness_cleanup_upgrades_admission':False}
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
GOOD={'normal','read-interrupted'}
WAIT_FAILURES={'wait-error','wait-timeout','cleanup-multiple-errors'}


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==493,'prior493 drift')
    for name in NEW:
        key=BASE+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def analyze_case(directory,name):
    o=f.load(directory/'observation.json');stdout=a.read(directory/'stdout.bin');stderr=a.read(directory/'stderr.bin')
    result=materials.assess(name,o,stdout,stderr,cache(directory/'materials'));h=f.load(directory/'harness.json')
    f.require(result['completion_admitted'] is (name in GOOD) and result['materials_valid'],'cleanup disposition/materials differ '+name)
    f.require(o['reaped'] is (name not in WAIT_FAILURES) and o['group_kill_attempted'] is (name not in GOOD),'cleanup reap/signal differs '+name)
    f.require(o['reader_error'] is (name=='read-error') and o['selector_error'] is (name=='selector-error'),'cleanup read failure differs')
    f.require(o['read_interrupts']==int(name=='read-interrupted'),'cleanup interrupt differs')
    f.require(o['timed_out'] is (name not in GOOD and name not in ('read-error','selector-error')),'cleanup timeout differs')
    f.require(o['wait_error'] is (name in WAIT_FAILURES) and o['wait_timed_out'] is (name in ('wait-timeout','cleanup-multiple-errors')),'cleanup wait failure differs')
    group='error' if name in ('group-kill-error','cleanup-multiple-errors') else 'not_found' if name=='group-kill-not-found' else 'none' if name in GOOD else 'sent'
    fallback='error' if name=='cleanup-multiple-errors' else 'sent' if name in ('group-kill-error','group-kill-not-found') else 'none'
    f.require(o['group_kill_outcome']==group and o['fallback_kill_outcome']==fallback,'cleanup signal status differs')
    exitcode=0 if name in GOOD or name.startswith('leader-') else -9
    f.require(o['returncode']==(None if name in WAIT_FAILURES else exitcode),'cleanup candidate exit differs')
    expected_h=dict(rescue_used=name in WAIT_FAILURES,direct_child_reaped=True,returncode=exitcode,admission_upgraded=False,descendant_reaping_verified=False)
    f.require(f.encode(h)==f.encode(expected_h),'harness cleanup differs')
    if name.startswith('leader-'):
        f.require(a.read(directory/'control/leader-exiting')==b'after holder ready\n','holder handshake differs')
        holder=f.load(directory/'control/holder.json');f.require(set(holder)=={'holder_pid','group','ttl_seconds'} and type(holder['holder_pid']) is int and holder['holder_pid']>0 and type(holder['group']) is int and holder['group']>0 and holder['ttl_seconds']==2,'holder metadata differs')
        eof={'leader-both-held':(False,False),'leader-stdout-held':(False,True),'leader-stderr-held':(True,False)}[name]
        f.require((o['stdout_eof'],o['stderr_eof'])==eof,'inherited pipe EOF differs')
    if name in ('eof-worker-alive','wait-error','wait-timeout'):f.require(o['stdout_eof'] and o['stderr_eof'],'EOF before exit not observed')
    return {**result,'harness':h,'read_interrupts':o['read_interrupts']}


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);previous.seed_check(inputs);script=source/BASE/'tests/a23_supervisor_cleanup_fixture.py';pin=f.sha(a.read(script));semantic={};observations={}
    for name in materials.CASES:
        directory=output/name;directory.mkdir(mode=0o700)
        o,stdout,stderr,child=supervisor.run_fixture(script,pin,name,inputs/'normal',directory/'materials')
        h=supervisor.harness_reap(child,o)
        for file,value in (('observation.json',o),('harness.json',h)):a.put(directory,file,f.encode(value))
        a.put(directory,'stdout.bin',stdout);a.put(directory,'stderr.bin',stderr)
        semantic[name]=analyze_case(directory,name);a.put(directory,'analysis.json',f.encode(semantic[name]));observations[name]=o
    return dict(passed=True,model_cases=15,semantic=semantic,observations=observations,fixture_sha256=pin,
                python_fixture_direct_children=15,forked_pipe_holders=3,candidate_direct_reaps=12,harness_rescue_reaps=3,
                native_compiler_jobs=0,isolated_native_model_executions=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,production_receiver_executions=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');report=f.load(root/'results.json');f.require(audit['source_count']==498 and audit['prior_sources_unchanged']==493 and len(audit['source_hashes'])==498,'cleanup source inventory differs')
    for name,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/name))==h,'frozen cleanup source differs')
    previous.seed_check(root/'inputs');f.require(report['model_cases']==15 and set(report['semantic'])==set(materials.CASES),'cleanup case inventory differs')
    f.require(report['fixture_sha256']==f.sha(a.read(root/'source'/BASE/'tests/a23_supervisor_cleanup_fixture.py')),'cleanup fixture differs')
    for name in materials.CASES:
        checked=analyze_case(root/'work'/name,name)
        f.require(f.encode(checked)==f.encode(report['semantic'][name]) and f.encode(checked)==a.read(root/'work'/name/'analysis.json'),'saved cleanup disposition differs')
        f.require(f.encode(f.load(root/'work'/name/'observation.json'))==f.encode(report['observations'][name]),'saved cleanup observation differs')
    f.require(all(report[k] is False for k in FALSE),'cleanup claims authority');return report


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new cleanup review required');frozen=sources();output.mkdir(mode=0o700)
    for name,h in frozen.items():
        raw=w.plain(w.b.REPO/name);f.require(f.sha(raw)==h,'cleanup source drift');a.put(output,'source/'+name,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM)
    for n,raw in cache(review/'inputs').items():a.put(output,'inputs/'+n,raw)
    try:result=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='fixed-python-cleanup-fixture-only')));seal(output);raise
    f.require(sources()==frozen,'cleanup source drift after exercise')
    a.put(output,'results.json',f.encode(result));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=498,prior_sources_unchanged=493,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=15)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
