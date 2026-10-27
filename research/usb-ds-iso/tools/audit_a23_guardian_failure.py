"""Offline guardian interruption with a direct-owner witness and read-only exit watches."""
from pathlib import Path
import argparse,copy,errno,json,os,select,shutil,subprocess,sys,tempfile,time
import a23_guardian_failure_materials as model
import audit_a23_guardian_owned as previous
f,a,legacy=previous.f,previous.a,previous.legacy
BASE=previous.BASE
PARENT='A23-guardian-owned-closeout-20261021'
PARENT_SUM='5315a5a3c808ece615cc686bbe213687a2483045b7604af4172cf21e8e7e3ca6'
SOURCE_REVIEW_SUM='d67c52e911ca33b15819e337ad2b3b824f84419cbc581c24a14acb5a5dbeae18'
NEW=('tests/a23_guardian_failure_actor.py','tests/a23_guardian_failure_guardian.py','tools/a23_guardian_failure_materials.py','tools/audit_a23_guardian_failure.py','tests/test_a23_guardian_failure.py')
INSTRUMENTATION=('a23_guardian_failure_actor.py','a23_guardian_failure_guardian.py')
FALSE={**previous.FALSE,**model.FALSE}
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
MUTANTS=('guardian-wait-false','guardian-status-bool','guardian-status-signal','actor-signals','checkpoint-pin','checkpoint-event','checkpoint-pid-bool',
    'actor-pid-bool','actor-pid-changed','creator-wait-promoted','exit-watch-false','exit-note-false','exit-ident','witness-wait-promoted','wait-errno',
    'terminal-pid','terminal-nonce','terminal-pin','terminal-code-bool','inner-missing')


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==532,'prior532 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def run_case(stage,job,pin):
    case=f.load(job/'failure-plan.json')['scenario'];command_r,command_w=os.pipe();status_r,status_w=os.pipe()
    guardian=None;checkpoints=[];watches={};buffer=bytearray()
    def receive():
        deadline=time.monotonic()+4
        while b'\n' not in buffer:
            remaining=deadline-time.monotonic();f.require(remaining>0,'witness checkpoint deadline')
            ready,_,_=select.select([status_r],[],[],remaining);f.require(ready,'witness checkpoint timeout')
            chunk=os.read(status_r,4096);f.require(bool(chunk),'guardian ended before checkpoint')
            buffer.extend(chunk);f.require(len(buffer)<=8192,'witness checkpoint limit')
        line,_,tail=buffer.partition(b'\n');buffer[:]=tail;return model.parse(bytes(line))
    try:
        guardian=subprocess.Popen([sys.executable,'-I','-B',str(stage/'a23_guardian_failure_guardian.py'),str(job),pin,str(command_r),str(status_w)],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(command_r,status_w),env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        os.close(command_r);command_r=None;os.close(status_w);status_w=None
        for expected in [*('watch-'+r for r in model.roles(case)),'finished' if case=='normal' else case]:
            msg=receive();checkpoints.append(msg);f.require(msg['event']==expected and msg['guardian_pid']==guardian.pid and msg['failure_plan_sha256']==pin,'unexpected guardian checkpoint')
            if expected.startswith('watch-'):
                role=expected.removeprefix('watch-');pid=next(r['pid'] for r in msg['actors'] if r['role']==role)
                watch=select.kqueue();watch.control([select.kevent(pid,filter=select.KQ_FILTER_PROC,flags=select.KQ_EV_ADD|select.KQ_EV_ONESHOT,fflags=select.KQ_NOTE_EXIT)],0,0)
                watches[role]=(pid,watch);os.write(command_w,b'R')
            elif case=='normal':os.write(command_w,b'R')
            else:guardian.kill()
        out,err=guardian.communicate(timeout=4)
        f.require(not out and not err,'guardian emitted diagnostics: '+err.decode(errors='replace')[:1200])
        f.require(guardian.returncode==(0 if case=='normal' else -9),'guardian returncode differs')
        notes=[]
        for role,(pid,watch) in watches.items():
            events=watch.control(None,1,4);f.require(len(events)==1 and events[0].ident==pid and events[0].fflags&select.KQ_NOTE_EXIT,'actor exit note missing')
            try:os.waitpid(pid,os.WNOHANG)
            except ChildProcessError as exc:f.require(exc.errno==errno.ECHILD,'unexpected actor wait error')
            else:raise ValueError('witness unexpectedly owns actor')
            notes.append(dict(role=role,actor_pid=pid,watch_registered=True,proc_exit_observed=True,proc_exit_ident=pid,witness_waited_actor=False,waitpid_errno=errno.ECHILD))
        outer=dict(schema='A23-guardian-failure-witness-1',guardian_pid=guardian.pid,guardian_waited=True,guardian_returncode=guardian.returncode,actor_pid_signals=0,provenance_authenticated=False)
        return outer,checkpoints,notes
    finally:
        if guardian is not None:
            if guardian.poll() is None:guardian.kill()
            guardian.communicate(timeout=4)
        for fd in (command_r,command_w,status_r,status_w):
            if fd is not None:os.close(fd)
        for _,watch in watches.values():watch.close()


def args_at(directory,pin):
    files={n:v for n,v in cache(directory).items() if n not in {'outer.json','checkpoints.json','exit-notes.json','analysis.json','recovery.json'}}
    return [a.read(directory/'failure-plan.json'),pin,files,f.load(directory/'outer.json'),f.load(directory/'checkpoints.json'),f.load(directory/'exit-notes.json')]


def semantic(r):return {k:v for k,v in r.items() if k!='fixture_job_id'}


def mutation(name,args):
    args=copy.deepcopy(args);files=args[2]
    def change(path,fn):v=model.parse(files[path]);fn(v);files[path]=model.encode(v)
    if name=='guardian-wait-false':args[3]['guardian_waited']=False
    if name=='guardian-status-bool':args[3]['guardian_returncode']=False
    if name=='guardian-status-signal':args[3]['guardian_returncode']=-9
    if name=='actor-signals':args[3]['actor_pid_signals']=1
    if name=='checkpoint-pin':args[4][0]['failure_plan_sha256']='0'*64
    if name=='checkpoint-event':args[4][-1]['event']='after-requester-wait'
    if name=='checkpoint-pid-bool':args[4][0]['guardian_pid']=True
    if name=='actor-pid-bool':args[4][0]['actors'][0]['pid']=True
    if name=='actor-pid-changed':args[4][-1]['actors'][0]['pid']+=1
    if name=='creator-wait-promoted':args[4][0]['actors'][0].update(waited=True,returncode=0)
    if name=='exit-watch-false':args[5][0]['watch_registered']=False
    if name=='exit-note-false':args[5][0]['proc_exit_observed']=False
    if name=='exit-ident':args[5][0]['proc_exit_ident']+=1
    if name=='witness-wait-promoted':args[5][0]['witness_waited_actor']=True
    if name=='wait-errno':args[5][0]['waitpid_errno']=0
    if name=='terminal-pid':change('requester-exit.json',lambda v:v.update(actor_pid=v['actor_pid']+1))
    if name=='terminal-nonce':change('requester-exit.json',lambda v:v.update(launch_nonce='0'*64))
    if name=='terminal-pin':change('requester-exit.json',lambda v:v.update(failure_plan_sha256='0'*64))
    if name=='terminal-code-bool':change('requester-exit.json',lambda v:v.update(reported_exit_code=False))
    if name=='inner-missing':files.pop('inner-observation.json')
    return args


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);stage=Path(tempfile.mkdtemp(prefix='a23-guardian-failure-',dir='/private/tmp'));shutil.copytree(source,stage/'source')
    for n in ('a23_guardian_owned_parent.py','a23_parent_crash_worker.py','a23_integrated_fixture_worker.py',*INSTRUMENTATION):a.put(stage,n,a.read(source/BASE/'tests'/n))
    for n in legacy.model.LIBRARIES:a.put(stage,'lib/'+n,a.read(source/BASE/'tools'/n))
    code={n:f.sha(a.read(stage/n)) for n in previous.CODE};instrumentation={n:f.sha(a.read(stage/n)) for n in INSTRUMENTATION}
    seed=cache(inputs/'seed');rows={};pins={};observations={}
    for case in model.CASES:
        job=stage/case;legacy.prepare(job,stage/'a23_integrated_fixture_worker.py',seed,{})
        innercase=case if case.startswith('child-') else 'normal';ownedraw=previous.model.encode(previous.model.plan(innercase,cache(job),code,SOURCE_REVIEW_SUM))
        a.put(job,'owned-plan.json',ownedraw);a.put(job,'crash-plan.json',ownedraw)
        raw=model.encode(model.plan(case,cache(job),instrumentation,SOURCE_REVIEW_SUM));pin=f.sha(raw);pins[case]=pin;a.put(job,'failure-plan.json',raw)
        outer,checkpoints,notes=run_case(stage,job,pin);before=cache(job)
        try:previous.claim(job,ownedraw,previous.model.parse(ownedraw))
        except FileExistsError:pass
        else:raise ValueError('guardian failure use repeated')
        try:legacy.publication.recover(job)
        except ValueError:pass
        else:raise ValueError('guardian failure recovery restarted')
        f.require(cache(job)==before,'guardian failure evidence changed')
        directory=output/'cases'/case;shutil.copytree(job,directory)
        for n,value in (('outer.json',outer),('checkpoints.json',checkpoints),('exit-notes.json',notes)):a.put(directory,n,f.encode(value))
        checked=model.assess(*args_at(directory,pin));f.require(not checked['errors'] and checked['guardian_failure_model_complete'] is (case=='normal'),'guardian failure verdict differs '+case+': '+str(checked))
        rows[case]=semantic(checked);observations[case]=outer;a.put(directory,'analysis.json',f.encode(checked));a.put(directory,'recovery.json',f.encode(dict(retry_refused=True,recovery_refused=True,evidence_unchanged=True)))
    args=args_at(output/'cases/normal',pins['normal']);mutants={}
    for name in MUTANTS:
        r=model.assess(*mutation(name,args));f.require(not r['guardian_failure_model_complete'] and bool(r['errors']),'guardian failure mutation accepted '+name);mutants[name]=semantic(r)
    return dict(passed=True,model_cases=33,guardian_cases=13,semantic=rows,mutations=mutants,plan_pins=pins,observations=observations,
        code_sha256=code,instrumentation_sha256=instrumentation,staging_directory=str(stage),python_fixture_guardian_processes=13,
        python_fixture_requester_processes=12,python_fixture_worker_processes=11,witness_guardian_waits=13,actor_exit_notes=23,
        actor_creator_waits=5,terminated_actors_without_verified_wait=18,witness_actor_waits=0,actor_pid_signals=0,fixture_jobs_created=13,
        native_compiler_jobs=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,
        authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json');f.require(audit['source_count']==537 and audit['prior_sources_unchanged']==532 and len(audit['source_hashes'])==537,'guardian failure source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen guardian failure source differs')
    for n,h in r['code_sha256'].items():
        name=n.removeprefix('source/') if n.startswith('source/') else BASE+('tools/' if n.startswith('lib/') else 'tests/')+n.removeprefix('lib/')
        f.require(h==f.sha(a.read(root/'source'/name)),'guardian failure runtime source differs')
    for n,h in r['instrumentation_sha256'].items():f.require(h==f.sha(a.read(root/'source'/BASE/'tests'/n)),'guardian failure instrumentation source differs')
    f.require(set(r['semantic'])==set(model.CASES) and set(r['mutations'])==set(MUTANTS),'guardian failure cases differ')
    for case in model.CASES:
        directory=root/'work/cases'/case;args=args_at(directory,r['plan_pins'][case]);checked=model.assess(*args)
        f.require(semantic(checked)==r['semantic'][case] and f.encode(checked)==a.read(directory/'analysis.json') and args[3]==r['observations'][case],'saved guardian failure verdict differs')
    args=args_at(root/'work/cases/normal',r['plan_pins']['normal'])
    for name in MUTANTS:f.require(semantic(model.assess(*mutation(name,args)))==r['mutations'][name],'guardian failure mutation differs')
    f.require(sum(v['actor_exit_notes_valid'] for v in r['semantic'].values())==23 and sum(v['actors_waited_by_creator'] for v in r['semantic'].values())==5 and sum(v['terminated_actors_without_verified_wait'] for v in r['semantic'].values())==18,'guardian failure aggregate differs')
    f.require(all(r[k] is False for k in FALSE),'guardian failure grants authority');return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new guardian failure review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'guardian failure source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM)
    for n,v in cache(review/'inputs/seed').items():a.put(output,'inputs/seed/'+n,v)
    a.put(output,'inputs/provenance.json',f.encode(dict(source_review=parent['references']['review'],cached_sdk_materials=True,new_sdk_execution=False)))
    try:r=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='fixed-guardian-interruption-fixture-only')));seal(output);raise
    f.require(sources()==frozen,'guardian failure source drift after exercise')
    a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=537,prior_sources_unchanged=532,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=33)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
