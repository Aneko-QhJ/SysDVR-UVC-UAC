"""Offline explicit status-pipe failure candidate, preserving the guardian-loss baseline."""
from pathlib import Path
import argparse,copy,json,os,shutil,sys,tempfile,subprocess
import a23_status_transport_materials as model
import audit_a23_guardian_failure as previous
f,a,legacy=previous.f,previous.a,previous.legacy
BASE=previous.BASE
PARENT='A23-guardian-failure-closeout-20261021'
PARENT_SUM='bfe6089f73d09d15ab77adb1cfb71def96f57b2fedb45ea0a162ec88bb253a16'
SOURCE_REVIEW_SUM='58a5802c63de29baedb15746e6960d7465c3051abee02743f376208477742457'
NEW=('tests/a23_status_transport_actor.py','tools/a23_status_transport_materials.py','tools/audit_a23_status_transport.py','tests/test_a23_status_transport.py')
FALSE={**previous.FALSE,**model.FALSE}
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
NEW_MUTANTS=('failure-code-promoted','failure-exception-spliced','transport-missing','frame-missing','transport-errno','transport-reason','committed-bool',
    'committed-positive','attempts-retried','delivery-promoted','local-wait-promoted','frame-hash','frame-size-bool','transport-kind','transport-nonce',
    'transport-pin','frame-job-repinned','frame-pid-repinned','frame-kind-repinned','frame-end-code-repinned')
MUTANTS=tuple('baseline/'+n for n in previous.MUTANTS)+NEW_MUTANTS


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==537,'prior537 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def args_at(directory,pin):
    files={n:v for n,v in cache(directory).items() if n not in {'outer.json','checkpoints.json','exit-notes.json','analysis.json','recovery.json'}}
    return [a.read(directory/'transport-plan.json'),pin,files,f.load(directory/'outer.json'),f.load(directory/'checkpoints.json'),f.load(directory/'exit-notes.json')]


def semantic(r):return {k:v for k,v in r.items() if k!='fixture_job_id'}


def mutation(name,args):
    if name.startswith('baseline/'):return previous.mutation(name.removeprefix('baseline/'),args)
    args=copy.deepcopy(args);files=args[2]
    def change(path,fn):v=model.parse(files[path]);fn(v);files[path]=model.encode(v)
    record='worker-transport.json';frame='worker-failed-status.bin'
    if name=='failure-code-promoted':change('worker-exit.json',lambda v:v.update(reported_exit_code=0))
    if name=='failure-exception-spliced':change('worker-exit.json',lambda v:v.update(exception_type='BrokenPipeError'))
    if name=='transport-missing':files.pop(record)
    if name=='frame-missing':files.pop(frame)
    if name=='transport-errno':change(record,lambda v:v.update(errno=0))
    if name=='transport-reason':change(record,lambda v:v.update(reason='success'))
    if name=='committed-bool':change(record,lambda v:v.update(bytes_committed=False))
    if name=='committed-positive':change(record,lambda v:v.update(bytes_committed=1))
    if name=='attempts-retried':change(record,lambda v:v.update(write_attempts=2))
    if name=='delivery-promoted':change(record,lambda v:v.update(delivery_confirmed=True))
    if name=='local-wait-promoted':change(record,lambda v:v.update(creator_wait_observed=True))
    if name=='frame-hash':change(record,lambda v:v.update(failed_frame_sha256='0'*64))
    if name=='frame-size-bool':change(record,lambda v:v.update(failed_frame_size=True))
    if name=='transport-kind':change(record,lambda v:v.update(message_kind='ready'))
    if name=='transport-nonce':change(record,lambda v:v.update(launch_nonce='0'*64))
    if name=='transport-pin':change(record,lambda v:v.update(failure_plan_sha256='0'*64))
    if name.startswith('frame-') and name.endswith('-repinned'):
        v=model.parse(files[frame])
        if name=='frame-job-repinned':v['fixture_job_id']='00000000-0000-0000-0000-000000000001'
        if name=='frame-pid-repinned':v['worker_pid']+=1
        if name=='frame-kind-repinned':v['kind']='ready'
        if name=='frame-end-code-repinned':v['exit_code']=0
        files[frame]=model.encode(v)+b'\n';change(record,lambda x:x.update(failed_frame_sha256=f.sha(files[frame]),failed_frame_size=len(files[frame]),message_kind=v['kind']))
    return args


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);stage=Path(tempfile.mkdtemp(prefix='a23-status-transport-',dir='/private/tmp'));shutil.copytree(source,stage/'source')
    for n in ('a23_guardian_owned_parent.py','a23_parent_crash_worker.py','a23_integrated_fixture_worker.py','a23_guardian_failure_guardian.py'):a.put(stage,n,a.read(source/BASE/'tests'/n))
    # Explicit staging alias: the frozen guardian's actor slot receives the new pinned candidate.
    a.put(stage,'a23_guardian_failure_actor.py',a.read(source/BASE/'tests/a23_status_transport_actor.py'))
    for n in legacy.model.LIBRARIES:a.put(stage,'lib/'+n,a.read(source/BASE/'tools'/n))
    code={n:f.sha(a.read(stage/n)) for n in previous.previous.CODE};instrumentation={n:f.sha(a.read(stage/n)) for n in previous.INSTRUMENTATION}
    baseline=f.sha(a.read(source/BASE/'tests/a23_guardian_failure_actor.py'));seed=cache(inputs/'seed');rows={};pins={};observations={}
    for case in model.CASES:
        job=stage/case;legacy.prepare(job,stage/'a23_integrated_fixture_worker.py',seed,{})
        innercase=case if case.startswith('child-') else 'normal';ownedraw=previous.previous.model.encode(previous.previous.model.plan(innercase,cache(job),code,SOURCE_REVIEW_SUM))
        a.put(job,'owned-plan.json',ownedraw);a.put(job,'crash-plan.json',ownedraw)
        failraw=previous.model.encode(previous.model.plan(case,cache(job),instrumentation,SOURCE_REVIEW_SUM));failpin=f.sha(failraw);a.put(job,'failure-plan.json',failraw)
        raw=model.encode(model.plan(case,cache(job),instrumentation['a23_guardian_failure_actor.py'],baseline,SOURCE_REVIEW_SUM));pin=f.sha(raw);pins[case]=pin;a.put(job,'transport-plan.json',raw)
        outer,checkpoints,notes=previous.run_case(stage,job,failpin);before=cache(job)
        try:previous.previous.claim(job,ownedraw,previous.previous.model.parse(ownedraw))
        except FileExistsError:pass
        else:raise ValueError('status transport use repeated')
        try:legacy.publication.recover(job)
        except ValueError:pass
        else:raise ValueError('status transport recovery restarted')
        f.require(cache(job)==before,'status transport evidence changed')
        directory=output/'cases'/case;shutil.copytree(job,directory)
        for n,value in (('outer.json',outer),('checkpoints.json',checkpoints),('exit-notes.json',notes)):a.put(directory,n,f.encode(value))
        checked=model.assess(*args_at(directory,pin));f.require(not checked['errors'] and checked['status_transport_model_complete'] is (case=='normal'),'status transport verdict differs '+case+': '+str(checked))
        rows[case]=semantic(checked);observations[case]=outer;a.put(directory,'analysis.json',f.encode(checked));a.put(directory,'recovery.json',f.encode(dict(retry_refused=True,recovery_refused=True,evidence_unchanged=True)))
    mutants={}
    for name in MUTANTS:
        case='normal' if name.startswith('baseline/') else 'before-worker-release';args=args_at(output/'cases'/case,pins[case])
        r=model.assess(*mutation(name,args));f.require(not r['status_transport_model_complete'] and bool(r['errors']),'status transport mutation accepted '+name);mutants[name]=semantic(r)
    return dict(passed=True,model_cases=53,guardian_cases=13,semantic=rows,mutations=mutants,plan_pins=pins,observations=observations,
        code_sha256=code,instrumentation_sha256=instrumentation,frozen_observer_sha256=baseline,staging_directory=str(stage),python_fixture_guardian_processes=13,
        python_fixture_requester_processes=12,python_fixture_worker_processes=11,witness_guardian_waits=13,actor_exit_notes=23,
        actor_creator_waits=5,terminated_actors_without_verified_wait=18,status_transport_failures=18,failed_status_frames_valid=18,
        unhandled_broken_pipe_reports=0,witness_actor_waits=0,actor_pid_signals=0,fixture_jobs_created=13,
        native_compiler_jobs=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,
        authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json');f.require(audit['source_count']==541 and audit['prior_sources_unchanged']==537 and len(audit['source_hashes'])==541,'status transport source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen status transport source differs')
    for n,h in r['code_sha256'].items():
        name=n.removeprefix('source/') if n.startswith('source/') else BASE+('tools/' if n.startswith('lib/') else 'tests/')+n.removeprefix('lib/')
        f.require(h==f.sha(a.read(root/'source'/name)),'status transport runtime source differs')
    for n,h in r['instrumentation_sha256'].items():
        source_name='a23_status_transport_actor.py' if n=='a23_guardian_failure_actor.py' else n
        f.require(h==f.sha(a.read(root/'source'/BASE/'tests'/source_name)),'status transport instrumentation alias differs')
    f.require(r['frozen_observer_sha256']==f.sha(a.read(root/'source'/BASE/'tests/a23_guardian_failure_actor.py')),'baseline observer changed')
    f.require(set(r['semantic'])==set(model.CASES) and set(r['mutations'])==set(MUTANTS),'status transport cases differ')
    for case in model.CASES:
        directory=root/'work/cases'/case;args=args_at(directory,r['plan_pins'][case]);checked=model.assess(*args)
        f.require(semantic(checked)==r['semantic'][case] and f.encode(checked)==a.read(directory/'analysis.json') and args[3]==r['observations'][case],'saved status transport verdict differs')
        v=model.parse(args[0]);f.require(v['candidate_sha256']==r['instrumentation_sha256']['a23_guardian_failure_actor.py'] and v['frozen_observer_sha256']==r['frozen_observer_sha256'],'candidate plan source differs')
    for name in MUTANTS:
        case='normal' if name.startswith('baseline/') else 'before-worker-release';args=args_at(root/'work/cases'/case,r['plan_pins'][case])
        f.require(semantic(model.assess(*mutation(name,args)))==r['mutations'][name],'status transport mutation differs')
    f.require(sum(v['actor_exit_notes_valid'] for v in r['semantic'].values())==23 and sum(v['actors_waited_by_creator'] for v in r['semantic'].values())==5 and sum(v['terminated_actors_without_verified_wait'] for v in r['semantic'].values())==18 and sum(v['status_transport_failures'] for v in r['semantic'].values())==18,'status transport aggregate differs')
    f.require(all(r[k] is False for k in FALSE),'status transport grants authority');return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new status transport review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'status transport source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);baseline=previous.verify(review,SOURCE_REVIEW_SUM)
    for n,v in cache(review/'inputs/seed').items():a.put(output,'inputs/seed/'+n,v)
    a.put(output,'inputs/provenance.json',f.encode(dict(source_review=parent['references']['review'],cached_sdk_materials=True,new_sdk_execution=False)))
    a.put(output,'inputs/baseline-summary.json',f.encode(dict(semantic=baseline['semantic'],code_sha256=baseline['code_sha256'],unhandled_broken_pipe_reports=18,actor_creator_waits=5,terminated_actors_without_verified_wait=18)))
    try:r=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='fixed-status-transport-fixture-only')));seal(output);raise
    f.require(sources()==frozen,'status transport source drift after exercise')
    a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=541,prior_sources_unchanged=537,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=53)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
