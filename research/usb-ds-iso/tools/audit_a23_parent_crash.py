"""Fixed parent crash windows; observe worker exit without claiming orphan wait."""
from pathlib import Path
import argparse,copy,errno,json,os,select,shutil,subprocess,sys,tempfile,time
import a23_parent_crash_materials as model
import audit_a23_integrated_fixture as previous
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-integrated-fixture-closeout-20261021'
PARENT_SUM='cdb63d3c9fdb053086ce60126a926e58306bfee3a688b6a75df274bd732a1c90'
SOURCE_REVIEW_SUM='6e33161eac73724abbad63c08f67264f30609b052fd07c0343df5bcd2c30d103'
NEW=('tests/a23_parent_crash_parent.py','tests/a23_parent_crash_worker.py','tools/a23_parent_crash_materials.py',
    'tools/audit_a23_parent_crash.py','tests/test_a23_parent_crash.py')
FALSE={**previous.FALSE,**model.FALSE}
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
CODE=('a23_parent_crash_parent.py','a23_parent_crash_worker.py','a23_integrated_fixture_worker.py',
    'source/'+BASE+'tools/a23_integrated_fixture_launcher.py','lib/a23_integrated_fixture_io.py','lib/a23_fixture_publication.py')
MUTANTS=('owner-pid-bool','owner-parent','owner-plan','ready-pid-bool','ready-nonce','ready-plan','end-reason','end-pid',
    'exit-note-missing','exit-note-pid','guardian-wait-promoted','parent-return-bool','parent-wait-false','parent-report-missing','worker-counter','owner-missing')


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==523,'prior523 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def run_case(stage,job):
    plan=f.load(job/'crash-plan.json');case=plan['scenario'];gate_r,gate_w=os.pipe();status_r,status_w=os.pipe()
    parent=None;watch=None;buffer=bytearray();messages=[];worker=None;note=None;wait_errno=None
    def read_message(timeout=3):
        deadline=time.monotonic()+timeout
        while b'\n' not in buffer:
            remaining=deadline-time.monotonic();f.require(remaining>0,'fixed worker status deadline')
            ready,_,_=select.select([status_r],[],[],remaining);f.require(ready,'fixed worker status timeout')
            chunk=os.read(status_r,4096)
            if not chunk:f.require(not buffer,'partial worker status');return None
            buffer.extend(chunk);f.require(len(buffer)<=8192,'worker status limit')
        raw,_,tail=buffer.partition(b'\n');buffer[:]=tail;v=model.parse(bytes(raw));messages.append(v);return v
    try:
        parent=subprocess.Popen([sys.executable,'-I','-B',str(stage/'a23_parent_crash_parent.py'),str(job),str(gate_r),str(status_w)],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(gate_r,status_w),
            env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        os.close(gate_r);gate_r=None;os.close(status_w);status_w=None
        first=read_message()
        if first is not None:
            f.require(first['kind']=='ready' and type(first['worker_pid']) is int and first['worker_pid']>0,'worker readiness differs');worker=first['worker_pid']
            # Read-only watch established while the pipe-gated worker is alive.
            # Never send a signal to a PID obtained from a file or message.
            watch=select.kqueue();watch.control([select.kevent(worker,filter=select.KQ_FILTER_PROC,flags=select.KQ_EV_ADD|select.KQ_EV_ONESHOT,fflags=select.KQ_NOTE_EXIT)],0,0)
            if case in ('after-popen-unrecorded','owner-partial','owner-synced'):parent.wait(timeout=3)
            if case=='gate-closed':os.close(gate_w);gate_w=None
            else:os.write(gate_w,b'R')
            if case.startswith('child-'):
                checkpoint=read_message();f.require(checkpoint and checkpoint['kind']=='checkpoint' and checkpoint['event']==case.removeprefix('child-'),'worker pause checkpoint differs')
                parent.kill();parent.wait(timeout=3);os.write(gate_w,b'R')
            ending=read_message();f.require(ending and ending['kind']=='end','worker ending missing')
            events=watch.control(None,1,3);f.require(len(events)==1,'worker exit note missing');note=events[0]
            f.require(note.ident==worker and note.fflags&select.KQ_NOTE_EXIT,'worker exit note identity differs')
            try:os.waitpid(worker,os.WNOHANG)
            except ChildProcessError as exc:wait_errno=exc.errno
            else:raise ValueError('guardian unexpectedly waited grandchild')
            f.require(wait_errno==errno.ECHILD,'non-child wait boundary differs')
            f.require(read_message() is None,'extra worker status message')
        out,err=parent.communicate(timeout=3)
        f.require(not out and not err,'parent fixture emitted diagnostics')
        expected=79 if case in model.SELF_EXIT else -9 if case.startswith('child-') else 0
        f.require(parent.returncode==expected,'parent fixture exit differs '+case)
        outer=dict(schema='A23-parent-crash-outer-1',parent_pid=parent.pid,returncode=parent.returncode,waited=True,provenance_authenticated=False)
        guard=dict(schema='A23-parent-crash-guard-1',worker_seen=worker is not None,worker_pid=worker,
            proc_watch_registered=watch is not None,proc_exit_observed=note is not None,proc_exit_ident=int(note.ident) if note else None,
            worker_waited_by_guardian=False,waitpid_errno=wait_errno,worker_pid_signals=0)
        return outer,guard,messages
    finally:
        # Owned direct parent only; closing the retained control pipe causes the
        # fixed worker to abort or hit its two-second gate timeout.
        if gate_w is not None:os.close(gate_w)
        if parent is not None:
            if parent.poll() is None:parent.kill()
            parent.communicate(timeout=3)
        for fd in (gate_r,status_r,status_w):
            if fd is not None:os.close(fd)
        if watch is not None:watch.close()


def args_at(directory,pin):
    files={n:v for n,v in cache(directory).items() if n not in {'outer.json','guard.json','messages.json','analysis.json','recovery.json'}}
    return [a.read(directory/'crash-plan.json'),pin,files,f.load(directory/'outer.json'),f.load(directory/'guard.json'),f.load(directory/'messages.json')]


def semantic(r):return {k:v for k,v in r.items() if k!='fixture_job_id'}


def mutation(name,args):
    args=copy.deepcopy(args);files=args[2]
    if name.startswith('owner-') and name!='owner-missing':
        owner=model.parse(files['owner.json'])
        if name=='owner-pid-bool':owner['worker_pid']=True
        if name=='owner-parent':owner['parent_pid']+=1
        if name=='owner-plan':owner['crash_plan_sha256']='0'*64
        files['owner.json']=model.encode(owner)
    if name=='ready-pid-bool':args[5][0]['worker_pid']=True
    if name=='ready-nonce':args[5][0]['launch_nonce']='0'*64
    if name=='ready-plan':args[5][0]['crash_plan_sha256']='0'*64
    if name=='end-reason':args[5][-1]['reason']='guardian_cleanup_authenticated'
    if name=='end-pid':args[5][-1]['worker_pid']+=1
    if name=='exit-note-missing':args[4]['proc_exit_observed']=False
    if name=='exit-note-pid':args[4]['proc_exit_ident']+=1
    if name=='guardian-wait-promoted':args[4]['worker_waited_by_guardian']=True
    if name=='parent-return-bool':args[3]['returncode']=False
    if name=='parent-wait-false':args[3]['waited']=False
    if name=='parent-report-missing':files.pop('parent-observation.json')
    if name=='worker-counter':args[4]['worker_seen']=False
    if name=='owner-missing':files.pop('owner.json')
    return args


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);f.require(hasattr(select,'kqueue'),'macOS proc-exit observer required')
    stage=Path(tempfile.mkdtemp(prefix='a23-parent-crash-',dir='/private/tmp'));shutil.copytree(source,stage/'source')
    for n in ('a23_parent_crash_parent.py','a23_parent_crash_worker.py','a23_integrated_fixture_worker.py'):a.put(stage,n,a.read(source/BASE/'tests'/n))
    for n in previous.model.LIBRARIES:a.put(stage,'lib/'+n,a.read(source/BASE/'tools'/n))
    code={n:f.sha(a.read(stage/n)) for n in CODE};seed=cache(inputs/'seed');rows={};pins={};observations={}
    for case in model.CASES:
        job=stage/case;previous.prepare(job,stage/'a23_integrated_fixture_worker.py',seed,{})
        raw=model.encode(model.plan(case,a.read(job/'launch.json'),a.read(job/'integrated-plan.json'),code,SOURCE_REVIEW_SUM));pin=f.sha(raw);pins[case]=pin;a.put(job,'crash-plan.json',raw)
        outer,guard,messages=run_case(stage,job);before=cache(job)
        # The original launcher-use marker still blocks another invocation.
        try:previous.launcher.run(stage/'a23_integrated_fixture_worker.py',job,f.sha(a.read(job/'integrated-plan.json')),f.sha(a.read(stage/'a23_integrated_fixture_worker.py')))
        except FileExistsError:pass
        else:raise ValueError('interrupted parent ticket reused')
        try:previous.publication.recover(job)
        except ValueError:pass
        else:raise ValueError('parent crash recovery allowed restart')
        f.require(cache(job)==before,'parent crash evidence changed during refusal')
        directory=output/'cases'/case;shutil.copytree(job,directory)
        for n,v in (('outer.json',outer),('guard.json',guard),('messages.json',messages)):a.put(directory,n,f.encode(v))
        checked=model.assess(*args_at(directory,pin));f.require(not checked['errors'] and checked['parent_crash_model_complete'] is (case=='normal'),'parent crash verdict differs '+case)
        rows[case]=semantic(checked);observations[case]=dict(outer=outer,guard=guard)
        a.put(directory,'analysis.json',f.encode(checked));a.put(directory,'recovery.json',f.encode(dict(retry_refused=True,recovery_refused=True,evidence_unchanged=True)))
    args=args_at(output/'cases/normal',pins['normal']);mutants={}
    for name in MUTANTS:
        r=model.assess(*mutation(name,args));f.require(not r['parent_crash_model_complete'] and bool(r['errors']),'parent crash mutation accepted '+name);mutants[name]=semantic(r)
    return dict(passed=True,model_cases=27,parent_cases=11,semantic=rows,mutations=mutants,plan_pins=pins,
        observations=observations,code_sha256=code,staging_directory=str(stage),python_fixture_parent_processes=11,
        python_fixture_worker_processes=10,direct_parent_waits=11,worker_proc_exit_notes=10,
        workers_reaped_by_original_parent=3,interrupted_parent_orphan_workers=7,guardian_worker_waits=0,worker_pid_signals=0,
        fixture_jobs_created=11,native_compiler_jobs=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,
        formal_records=0,formal_reservations=0,authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json');f.require(audit['source_count']==528 and audit['prior_sources_unchanged']==523 and len(audit['source_hashes'])==528,'parent crash source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen parent crash source differs')
    code=dict(r['code_sha256'])
    for n in CODE:
        name=n.removeprefix('source/') if n.startswith('source/') else BASE+('tools/' if n.startswith('lib/') else 'tests/')+n.removeprefix('lib/')
        f.require(code[n]==f.sha(a.read(root/'source'/name)),'parent crash runtime code differs')
    f.require(set(r['semantic'])==set(model.CASES) and set(r['mutations'])==set(MUTANTS),'parent crash cases differ')
    for case in model.CASES:
        directory=root/'work/cases'/case;args=args_at(directory,r['plan_pins'][case]);checked=model.assess(*args)
        f.require(semantic(checked)==r['semantic'][case] and f.encode(checked)==a.read(directory/'analysis.json'),'saved parent crash verdict differs')
        f.require(dict(outer=args[3],guard=args[4])==r['observations'][case],'saved parent crash observations differ')
    args=args_at(root/'work/cases/normal',r['plan_pins']['normal'])
    for name in MUTANTS:f.require(semantic(model.assess(*mutation(name,args)))==r['mutations'][name],'parent crash mutation differs')
    f.require(all(r[k] is False for k in FALSE),'parent crash claims authority');return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new parent crash review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'parent crash source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM)
    for n,v in cache(review/'inputs/seed').items():a.put(output,'inputs/seed/'+n,v)
    a.put(output,'inputs/provenance.json',f.encode(dict(source_review=parent['references']['review'],cached_sdk_materials=True,new_sdk_execution=False)))
    try:r=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='fixed-parent-crash-fixture-only')));seal(output);raise
    f.require(sources()==frozen,'parent crash source drift after exercise')
    a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=528,prior_sources_unchanged=523,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=27)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
