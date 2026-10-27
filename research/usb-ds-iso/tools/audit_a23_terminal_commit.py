"""Offline local commit marker and directory-sync protocol; no production entry."""
from pathlib import Path
import argparse,copy,errno,json,os,select,shutil,subprocess,sys,tempfile,time
import a23_terminal_commit_materials as model
import audit_a23_terminal_publication as previous
f,a,legacy,owned=previous.f,previous.a,previous.legacy,previous.owned
BASE=previous.BASE
PARENT='A23-terminal-publication-closeout-20261021'
PARENT_SUM='4472e379838500173277b5cca168375f5519851dbbe00cbc6235120e3b041256'
SOURCE_REVIEW_SUM='6f275dbd024dc8ff30c9c070919d9683b6c968f37e5375070253d02c04ad4ad5'
NEW=('tools/a23_terminal_commit_io.py','tests/a23_terminal_commit_actor.py','tools/a23_terminal_commit_materials.py','tools/audit_a23_terminal_commit.py','tests/test_a23_terminal_commit.py')
ALIASES={'a23_guardian_failure_actor.py':'a23_terminal_commit_actor.py','a23_guardian_failure_guardian.py':'a23_terminal_publication_guardian.py'}
FALSE={**previous.FALSE,**model.FALSE}
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
MUTANTS=('guardian-wait','creator-wait','witness-wait','event-tail','event-missing','event-pin','event-bool-size','event-cut-code','event-cut-missing','event-dir-sync-missing',
    'commit-missing','commit-half','commit-part-spliced','commit-role','commit-record-hash','commit-wait-promoted','use-missing','use-promoted','artifact-missing','artifact-half','artifact-part-spliced','other-commit-missing','event-content-missing','event-job')


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==546,'prior546 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def run_case(stage,job,pin,terminal_pin):
    case=f.load(job/'failure-plan.json')['scenario'];command_r,command_w=os.pipe();status_r,status_w=os.pipe();trace_r,trace_w=os.pipe()
    guardian=None;checkpoints=[];watches={};buffer=bytearray();trace=bytearray();trace_eof=False
    def read_trace():
        nonlocal trace_eof
        chunk=os.read(trace_r,4096)
        if not chunk:trace_eof=True
        else:trace.extend(chunk);f.require(len(trace)<=65536,'commit trace limit')
    def receive():
        deadline=time.monotonic()+4
        while b'\n' not in buffer:
            remaining=deadline-time.monotonic();f.require(remaining>0,'commit checkpoint deadline')
            ready,_,_=select.select([status_r]+([] if trace_eof else [trace_r]),[],[],remaining);f.require(ready,'commit checkpoint timeout')
            if trace_r in ready:read_trace()
            if status_r in ready:
                chunk=os.read(status_r,4096);f.require(bool(chunk),'guardian ended before checkpoint');buffer.extend(chunk);f.require(len(buffer)<=8192,'commit checkpoint limit')
        line,_,tail=buffer.partition(b'\n');buffer[:]=tail;return model.parse(bytes(line))
    try:
        guardian=subprocess.Popen([sys.executable,'-I','-B',str(stage/'a23_guardian_failure_guardian.py'),str(job),pin,str(command_r),str(status_w),str(trace_w),terminal_pin],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(command_r,status_w,trace_w),env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        os.close(command_r);command_r=None;os.close(status_w);status_w=None;os.close(trace_w);trace_w=None
        for expected in ('watch-requester','watch-worker','finished' if case=='normal' else 'before-worker-release'):
            msg=receive();checkpoints.append(msg);f.require(msg['event']==expected and msg['guardian_pid']==guardian.pid and msg['failure_plan_sha256']==pin,'unexpected commit checkpoint')
            if expected.startswith('watch-'):
                role=expected.removeprefix('watch-');pid=next(r['pid'] for r in msg['actors'] if r['role']==role)
                watch=select.kqueue();watch.control([select.kevent(pid,filter=select.KQ_FILTER_PROC,flags=select.KQ_EV_ADD|select.KQ_EV_ONESHOT,fflags=select.KQ_NOTE_EXIT)],0,0);watches[role]=(pid,watch);os.write(command_w,b'R')
            elif case=='normal':os.write(command_w,b'R')
            else:guardian.kill()
        out,err=guardian.communicate(timeout=4);f.require(not out and not err and guardian.returncode==(0 if case=='normal' else -9),'commit guardian diagnostics/wait differs')
        deadline=time.monotonic()+4
        while not trace_eof:
            remaining=deadline-time.monotonic();f.require(remaining>0,'commit trace deadline');ready,_,_=select.select([trace_r],[],[],remaining);f.require(ready,'commit trace timeout');read_trace()
        f.require(trace.endswith(b'\n'),'partial commit trace');publication_events=[model.parse(bytes(line)) for line in trace.splitlines()];f.require(len(publication_events)<=30,'commit event limit')
        notes=[]
        for role,(pid,watch) in watches.items():
            exits=watch.control(None,1,4);f.require(len(exits)==1 and exits[0].ident==pid and exits[0].fflags&select.KQ_NOTE_EXIT,'commit actor exit note missing')
            try:os.waitpid(pid,os.WNOHANG)
            except ChildProcessError as exc:f.require(exc.errno==errno.ECHILD,'unexpected commit actor wait error')
            else:raise ValueError('commit witness unexpectedly owns actor')
            notes.append(dict(role=role,actor_pid=pid,watch_registered=True,proc_exit_observed=True,proc_exit_ident=pid,witness_waited_actor=False,waitpid_errno=errno.ECHILD))
        outer=dict(schema='A23-guardian-failure-witness-1',guardian_pid=guardian.pid,guardian_waited=True,guardian_returncode=guardian.returncode,actor_pid_signals=0,provenance_authenticated=False)
        return outer,checkpoints,notes,publication_events
    finally:
        if guardian is not None:
            if guardian.poll() is None:guardian.kill()
            guardian.communicate(timeout=4)
        for fd in (command_r,command_w,status_r,status_w,trace_r,trace_w):
            if fd is not None:os.close(fd)
        for _,watch in watches.values():watch.close()


def args_at(directory,pin):
    files={n:v for n,v in cache(directory).items() if n not in {'outer.json','checkpoints.json','exit-notes.json','publication-events.json','analysis.json','recovery.json'}}
    return [a.read(directory/'commit-plan.json'),pin,files,f.load(directory/'outer.json'),f.load(directory/'checkpoints.json'),f.load(directory/'exit-notes.json'),f.load(directory/'publication-events.json')]


def semantic(r):return {k:v for k,v in r.items() if k!='fixture_job_id'}


def mutation(name,args):
    args=copy.deepcopy(args);files=args[2];events=args[6]
    def change(path,fn):v=model.parse(files[path]);fn(v);files[path]=model.encode(v)
    if name=='guardian-wait':args[3]['guardian_waited']=False
    if name=='creator-wait':args[4][-1]['actors'][0].update(waited=True,returncode=0)
    if name=='witness-wait':args[5][0]['witness_waited_actor']=True
    if name=='event-tail':events.append(dict(events[-1]))
    if name=='event-missing':events.pop(0)
    if name=='event-pin':events[0]['terminal_plan_sha256']='0'*64
    if name=='event-bool-size':events[0]['content_size']=True
    if name=='event-cut-code':events[-1]['exit_requested']=91
    if name=='event-cut-missing':events[-1]['exit_requested']=None
    if name=='event-dir-sync-missing':events.pop(next(i for i,e in enumerate(events) if e['kind']=='exit' and e['phase']=='dir_sync'))
    if name=='commit-missing':files.pop('worker-terminal-commit.json')
    if name=='commit-half':files['worker-terminal-commit.json']=files['worker-terminal-commit.json'][:len(files['worker-terminal-commit.json'])//2]
    if name=='commit-part-spliced':files['worker-terminal-commit.json.part']+=b' '
    if name=='commit-role':change('worker-terminal-commit.json',lambda v:v.update(role='requester'))
    if name=='commit-record-hash':change('worker-terminal-commit.json',lambda v:v['records']['worker-exit.json'].update(sha256='0'*64))
    if name=='commit-wait-promoted':change('worker-terminal-commit.json',lambda v:v.update(process_wait_verified=True))
    if name=='use-missing':files.pop('worker-terminal-use.json')
    if name=='use-promoted':change('worker-terminal-use.json',lambda v:v.update(maximum_publications=2))
    if name=='artifact-missing':files.pop('worker-exit.json')
    if name=='artifact-half':files['worker-exit.json']=files['worker-exit.json'][:len(files['worker-exit.json'])//2]
    if name=='artifact-part-spliced':files['worker-exit.json.part']+=b' '
    if name=='other-commit-missing':files.pop('requester-terminal-commit.json')
    if name=='event-content-missing':events[0].pop('content_hex')
    if name=='event-job':events[0]['fixture_job_id']='00000000-0000-0000-0000-000000000001'
    return args


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);stage=Path(tempfile.mkdtemp(prefix='a23-terminal-commit-',dir='/private/tmp'));shutil.copytree(source,stage/'source')
    for n in ('a23_guardian_owned_parent.py','a23_parent_crash_worker.py','a23_integrated_fixture_worker.py'):a.put(stage,n,a.read(source/BASE/'tests'/n))
    for alias,name in ALIASES.items():a.put(stage,alias,a.read(source/BASE/'tests'/name))
    for n in legacy.model.LIBRARIES:a.put(stage,'lib/'+n,a.read(source/BASE/'tools'/n))
    a.put(stage,'lib/a23_terminal_commit_io.py',a.read(source/BASE/'tools/a23_terminal_commit_io.py'))
    code={n:f.sha(a.read(stage/n)) for n in owned.CODE};instrumentation={n:f.sha(a.read(stage/n)) for n in ALIASES};library=f.sha(a.read(stage/'lib/a23_terminal_commit_io.py'))
    baseline=f.sha(a.read(source/BASE/'tests/a23_guardian_failure_actor.py'));seed=cache(inputs/'seed');rows={};pins={};observations={}
    for case in model.CASES:
        job=stage/case;legacy.prepare(job,stage/'a23_integrated_fixture_worker.py',seed,{})
        ownedraw=owned.model.encode(owned.model.plan('normal',cache(job),code,SOURCE_REVIEW_SUM));a.put(job,'owned-plan.json',ownedraw);a.put(job,'crash-plan.json',ownedraw)
        inner=model.configuration(case)[3];failure_model=previous.previous.previous.model;failraw=failure_model.encode(failure_model.plan(inner,cache(job),instrumentation,SOURCE_REVIEW_SUM));failpin=f.sha(failraw);a.put(job,'failure-plan.json',failraw)
        transport_model=previous.previous.model;traw=transport_model.encode(transport_model.plan(inner,cache(job),instrumentation['a23_guardian_failure_actor.py'],baseline,SOURCE_REVIEW_SUM));a.put(job,'transport-plan.json',traw)
        raw=model.encode(model.plan(case,cache(job),instrumentation['a23_guardian_failure_actor.py'],instrumentation['a23_guardian_failure_guardian.py'],library,SOURCE_REVIEW_SUM));pin=f.sha(raw);pins[case]=pin;a.put(job,'commit-plan.json',raw);a.put(job,'terminal-plan.json',raw)
        outer,checkpoints,notes,events=run_case(stage,job,failpin,pin);before=cache(job)
        try:owned.claim(job,ownedraw,owned.model.parse(ownedraw))
        except FileExistsError:pass
        else:raise ValueError('terminal commit guardian use repeated')
        for role in ('requester','worker'):
            try:model.publication.publish(job,role,{}, {},lambda *_:None)
            except ValueError:pass
            else:raise ValueError('invalid retry accepted')
            # Valid records force the exclusive use check; every runtime cut retains its local use marker.
            try:model.publication.publish(job,role,{role+'-exit.json':b'no retry'}, {},lambda *_:None)
            except FileExistsError:pass
            else:raise ValueError('local commit use repeated')
            try:model.publication.recover(job,role)
            except ValueError:pass
            else:raise ValueError('local commit recovery restarted')
        try:legacy.publication.recover(job)
        except ValueError:pass
        else:raise ValueError('guardian recovery restarted')
        f.require(cache(job)==before,'terminal commit evidence changed')
        directory=output/'cases'/case;shutil.copytree(job,directory)
        for n,value in (('outer.json',outer),('checkpoints.json',checkpoints),('exit-notes.json',notes),('publication-events.json',events)):a.put(directory,n,f.encode(value))
        checked=model.assess(*args_at(directory,pin));f.require(not checked['errors'] and checked['publication_evidence_valid'] and checked['terminal_commit_model_complete'] is (case=='normal'),'terminal commit verdict differs '+case+': '+str(checked))
        rows[case]=semantic(checked);observations[case]=outer;a.put(directory,'analysis.json',f.encode(checked));a.put(directory,'recovery.json',f.encode(dict(guardian_retry_refused=True,guardian_recovery_refused=True,local_retry_refusals=2,local_recovery_refusals=2,evidence_unchanged=True)))
    args=args_at(output/'cases/worker-commit-dir_sync',pins['worker-commit-dir_sync']);mutants={}
    for name in MUTANTS:
        r=model.assess(*mutation(name,args));f.require(not r['publication_evidence_valid'] and bool(r['errors']),'terminal commit mutation accepted '+name);mutants[name]=semantic(r)
    return dict(passed=True,model_cases=82,guardian_cases=58,semantic=rows,mutations=mutants,plan_pins=pins,observations=observations,
        code_sha256=code,instrumentation_sha256=instrumentation,publication_io_sha256=library,staging_directory=str(stage),
        python_fixture_guardian_processes=58,python_fixture_requester_processes=58,python_fixture_worker_processes=58,witness_guardian_waits=58,
        actor_exit_notes=116,actor_creator_waits=2,terminated_actors_without_verified_wait=114,publication_interruptions=56,
        committed_then_interrupted=2,witness_actor_waits=0,actor_pid_signals=0,fixture_jobs_created=58,
        native_compiler_jobs=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,
        authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json');f.require(audit['source_count']==551 and audit['prior_sources_unchanged']==546 and len(audit['source_hashes'])==551,'commit source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen commit source differs')
    for n,h in r['code_sha256'].items():
        name=n.removeprefix('source/') if n.startswith('source/') else BASE+('tools/' if n.startswith('lib/') else 'tests/')+n.removeprefix('lib/');f.require(h==f.sha(a.read(root/'source'/name)),'commit runtime source differs')
    for alias,name in ALIASES.items():f.require(r['instrumentation_sha256'][alias]==f.sha(a.read(root/'source'/BASE/'tests'/name)),'commit instrumentation alias differs')
    f.require(r['publication_io_sha256']==f.sha(a.read(root/'source'/BASE/'tools/a23_terminal_commit_io.py')),'commit library differs')
    f.require(set(r['semantic'])==set(model.CASES) and set(r['mutations'])==set(MUTANTS),'commit cases differ')
    for case in model.CASES:
        directory=root/'work/cases'/case;args=args_at(directory,r['plan_pins'][case]);checked=model.assess(*args);v=model.parse(args[0])
        f.require(v['actor_source_sha256']==r['instrumentation_sha256']['a23_guardian_failure_actor.py'] and v['guardian_source_sha256']==r['instrumentation_sha256']['a23_guardian_failure_guardian.py'] and v['publication_io_sha256']==r['publication_io_sha256'],'commit source aliases differ')
        f.require(semantic(checked)==r['semantic'][case] and f.encode(checked)==a.read(directory/'analysis.json') and args[3]==r['observations'][case],'saved commit verdict differs')
    args=args_at(root/'work/cases/worker-commit-dir_sync',r['plan_pins']['worker-commit-dir_sync'])
    for name in MUTANTS:f.require(semantic(model.assess(*mutation(name,args)))==r['mutations'][name],'commit mutation differs')
    f.require(sum(v['actor_exit_notes_valid'] for v in r['semantic'].values())==116 and sum(v['actors_waited_by_creator'] for v in r['semantic'].values())==2 and sum(v['terminated_actors_without_verified_wait'] for v in r['semantic'].values())==114 and sum(v['committed_then_interrupted'] for v in r['semantic'].values())==2,'commit aggregate differs')
    f.require(all(r[k] is False for k in FALSE),'terminal commit grants authority');return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new commit review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'commit source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM)
    for n,v in cache(review/'inputs/seed').items():a.put(output,'inputs/seed/'+n,v)
    a.put(output,'inputs/provenance.json',f.encode(dict(source_review=parent['references']['review'],cached_sdk_materials=True,new_sdk_execution=False)))
    try:r=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='fixed-terminal-commit-fixture-only')));seal(output);raise
    f.require(sources()==frozen,'commit source drift after exercise');a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=551,prior_sources_unchanged=546,source_hashes=frozen)));seal(output)
    return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=82)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
