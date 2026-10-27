"""Disposable guardian-owned worker comparison; no production broker entry."""
from pathlib import Path
import argparse,copy,json,os,select,shutil,subprocess,sys,tempfile,time
import a23_guardian_owned_materials as model
import a23_integrated_fixture_io as io
import audit_a23_parent_crash as previous
import audit_a23_integrated_fixture as legacy
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-parent-crash-closeout-20261021'
PARENT_SUM='cddc0a12809a9cccc33bfc3a89f27d27b292f225cf4fe829cacfc2a74156fb6c'
SOURCE_REVIEW_SUM='366b54ca0fc43065281c17c20026af597ff1d2385e1ed95b71b043ba8eed1ecd'
NEW=('tests/a23_guardian_owned_parent.py','tools/a23_guardian_owned_materials.py','tools/audit_a23_guardian_owned.py','tests/test_a23_guardian_owned.py')
FALSE={**previous.FALSE,**model.FALSE}
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
CODE=('a23_guardian_owned_parent.py','a23_parent_crash_worker.py','a23_integrated_fixture_worker.py',
    'source/'+BASE+'tools/audit_a23_guardian_owned.py','lib/a23_integrated_fixture_io.py','lib/a23_fixture_publication.py')
MUTANTS=('guardian-wait-false','worker-creator','worker-status-bool','worker-status-splice','worker-count','requester-wait-false',
    'requester-status-bool','owner-missing','owner-worker','handoff-nonce','accept-missing','accept-worker','repeat-promoted',
    'request-nonce','accepted-hash','end-reason','end-worker','result-wait-false','result-worker','trace-sync-missing')


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==528,'prior528 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def claim(job,raw,v):
    with (job/'guardian-use.json').open('xb',buffering=0) as stream:
        io.write_all(stream.fileno(),model.encode(model.use_record(raw,v)));os.fsync(stream.fileno())
    io.sync_directory(job);io.sync_directory(job.parent)


def run_case(stage,job):
    raw=a.read(job/'owned-plan.json');v=model.check(raw,f.sha(raw),cache(job));case=v['scenario'];launch=f.load(job/'launch.json');g=os.getpid();claim(job,raw,v)
    command_r,command_w=os.pipe();parent_r,parent_w=os.pipe();life_r,life_w=os.pipe();gate_r=gate_w=worker_r=worker_w=None
    parent=worker=None;parent_messages=[];worker_messages=[];buffers={};out=err=b''
    def receive(fd,rows):
        buffer=buffers.setdefault(fd,bytearray());deadline=time.monotonic()+3
        while b'\n' not in buffer:
            remaining=deadline-time.monotonic();f.require(remaining>0,'owned fixture message deadline')
            ready,_,_=select.select([fd],[],[],remaining);f.require(ready,'owned fixture message timeout')
            chunk=os.read(fd,4096)
            if not chunk:f.require(not buffer,'partial owned fixture message');return None
            buffer.extend(chunk);f.require(len(buffer)<=8192,'owned fixture message limit')
        line,_,tail=buffer.partition(b'\n');buffer[:]=tail;msg=model.parse(bytes(line));rows.append(msg);return msg
    def send(h):io.write_all(command_w,model.encode(h)+b'\n')
    def kill_requester():parent.kill();parent.wait(timeout=3)
    def store(name,data):a.put(job,name,data)
    try:
        parent=subprocess.Popen([sys.executable,'-I','-B',str(stage/'a23_guardian_owned_parent.py'),str(job),str(command_r),str(parent_w),str(life_w)],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(command_r,parent_w,life_w),env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        for fd in (command_r,parent_w,life_w):os.close(fd)
        command_r=parent_w=life_w=None
        request=receive(parent_r,parent_messages)
        if case=='before-request':f.require(request is None,'unexpected launch request');parent.wait(timeout=3)
        elif case=='after-request':f.require(request is not None,'launch request missing');parent.wait(timeout=3)
        else:
            f.require(request==model.requester('request',launch,f.sha(raw),g,parent.pid),'bound requester differs')
            with (job/'launcher-use.json').open('xb',buffering=0) as stream:
                io.write_all(stream.fileno(),model.encode(model.integrated.use_record(a.read(job/'launch.json'),a.read(job/'integrated-plan.json'))));os.fsync(stream.fileno())
            io.publish_attempt(job,model.encode(model.integrated.binding.attempt(a.read(job/'launch.json'))),lambda event,phase:io.record(job,event,'completed') if phase=='after' else None)
            io.record(job,'launch.ready','completed')
            gate_r,gate_w=os.pipe();worker_r,worker_w=os.pipe()
            # Retain the actual Popen handle before publishing any owner journal.
            worker=subprocess.Popen([sys.executable,'-I','-B',str(stage/'a23_parent_crash_worker.py'),str(job),str(life_r),str(gate_r),str(worker_w),str(parent.pid)],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(life_r,gate_r,worker_w),start_new_session=True,
                env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
            for fd in (life_r,gate_r,worker_w):os.close(fd)
            life_r=gate_r=worker_w=None
            ready=receive(worker_r,worker_messages);f.require(ready and ready['kind']=='ready' and ready['worker_pid']==worker.pid,'owned worker ready differs')
            h=model.handoff(raw,v,launch,g,parent.pid,worker.pid)
            if case=='worker-unrecorded':kill_requester()
            else:
                if case=='owner-partial':store('guardian-owner.json',model.encode(h)[:len(model.encode(h))//2])
                else:
                    with (job/'guardian-owner.json').open('xb',buffering=0) as stream:io.write_all(stream.fileno(),model.encode(h));os.fsync(stream.fileno())
                if case in model.EARLY_KILL:kill_requester()
            if case not in model.EARLY_KILL:
                sent=dict(h)
                if case=='handoff-job-mismatch':sent['fixture_job_id']='00000000-0000-0000-0000-000000000001'
                if case=='handoff-nonce-mismatch':sent['launch_nonce']='0'*64
                store('handoff-sent.json',model.encode(sent));send(sent)
                ack=receive(parent_r,parent_messages);f.require(ack is not None,'handoff response missing')
                if case in ('handoff-job-mismatch','handoff-nonce-mismatch','after-handoff'):parent.wait(timeout=3)
                elif case=='handoff-repeat':
                    store('handoff-repeat.json',model.encode(h));send(h);f.require(receive(parent_r,parent_messages) is not None,'repeat refusal missing');parent.wait(timeout=3)
            if case=='guardian-gate-closed':os.close(gate_w);gate_w=None
            else:os.write(gate_w,b'R')
            if case.startswith('child-'):
                checkpoint=receive(worker_r,worker_messages);f.require(checkpoint and checkpoint['kind']=='checkpoint','owned worker checkpoint missing')
                kill_requester();os.write(gate_w,b'R')
            ending=receive(worker_r,worker_messages);f.require(ending and ending['kind']=='end','owned worker ending missing')
            out,err=worker.communicate(timeout=3)
            f.require(len(out)<=65536 and len(err)<=8192 and not err and worker.returncode==ending['exit_code'],'owned worker wait/output differs')
            f.require(receive(worker_r,worker_messages) is None,'extra owned worker message')
            if case in ('normal','after-parent-report','guardian-gate-closed'):
                send(model.result(h,worker.returncode));f.require(receive(parent_r,parent_messages) is not None,'requester result report missing')
        pout,perr=parent.communicate(timeout=3);f.require(not pout and not perr,'requester diagnostics emitted')
        f.require(receive(parent_r,parent_messages) is None,'extra requester message')
        observation=dict(schema='A23-guardian-owned-observation-1',guardian_pid=g,requester_pid=parent.pid,requester_waited=True,
            requester_returncode=parent.returncode,worker_seen=worker is not None,worker_pid=worker.pid if worker else None,
            worker_creator_pid=g if worker else None,worker_waited=worker is not None,worker_returncode=worker.returncode if worker else None,
            journal_pid_signals=0,provenance_authenticated=False)
        store('worker-stdout.bin',out);store('worker-stderr.bin',err)
        return observation,parent_messages,worker_messages
    finally:
        if gate_w is not None:os.close(gate_w);gate_w=None
        if command_w is not None:os.close(command_w);command_w=None
        # Cleanup only retained direct-child handles; no recorded PID is signaled.
        for process in (parent,worker):
            if process is not None:
                if process.poll() is None:process.kill()
                process.communicate(timeout=3)
        for fd in (command_r,parent_r,parent_w,life_r,life_w,gate_r,worker_r,worker_w):
            if fd is not None:os.close(fd)


def args_at(directory,pin):
    files={n:v for n,v in cache(directory).items() if n not in {'observation.json','parent-messages.json','worker-messages.json','analysis.json','recovery.json'}}
    return [a.read(directory/'owned-plan.json'),pin,files,f.load(directory/'observation.json'),f.load(directory/'parent-messages.json'),f.load(directory/'worker-messages.json')]


def semantic(r):return {k:v for k,v in r.items() if k!='fixture_job_id'}


def mutation(name,args):
    args=copy.deepcopy(args);files=args[2]
    def change(path,fn):v=model.parse(files[path]);fn(v);files[path]=model.encode(v)
    if name=='guardian-wait-false':args[3]['worker_waited']=False
    if name=='worker-creator':args[3]['worker_creator_pid']+=1
    if name=='worker-status-bool':args[3]['worker_returncode']=False
    if name=='worker-status-splice':args[3]['worker_returncode']=7
    if name=='worker-count':args[3]['worker_seen']=False
    if name=='requester-wait-false':args[3]['requester_waited']=False
    if name=='requester-status-bool':args[3]['requester_returncode']=False
    if name=='owner-missing':files.pop('guardian-owner.json')
    if name=='owner-worker':change('guardian-owner.json',lambda v:v.update(worker_pid=v['worker_pid']+1))
    if name=='handoff-nonce':change('handoff-sent.json',lambda v:v.update(launch_nonce='0'*64))
    if name=='accept-missing':files.pop('parent-accept.json')
    if name=='accept-worker':change('parent-accept.json',lambda v:v.update(worker_pid=v['worker_pid']+1))
    if name=='repeat-promoted':args[4].insert(2,dict(args[4][1]))
    if name=='request-nonce':args[4][0]['launch_nonce']='0'*64
    if name=='accepted-hash':args[4][1]['handoff_sha256']='0'*64
    if name=='end-reason':args[5][-1]['reason']='reaped_by_requester'
    if name=='end-worker':args[5][-1]['worker_pid']+=1
    if name=='result-wait-false':change('parent-result.json',lambda v:v.update(worker_waited=False))
    if name=='result-worker':change('parent-result.json',lambda v:v.update(worker_pid=v['worker_pid']+1))
    if name=='trace-sync-missing':files['trace.jsonl']=b'\n'.join(line for line in files['trace.jsonl'].splitlines() if model.parse(line)['event']!='attempt.parent_directory_sync')+b'\n'
    return args


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);stage=Path(tempfile.mkdtemp(prefix='a23-guardian-owned-',dir='/private/tmp'));shutil.copytree(source,stage/'source')
    for n in ('a23_guardian_owned_parent.py','a23_parent_crash_worker.py','a23_integrated_fixture_worker.py'):a.put(stage,n,a.read(source/BASE/'tests'/n))
    for n in legacy.model.LIBRARIES:a.put(stage,'lib/'+n,a.read(source/BASE/'tools'/n))
    code={n:f.sha(a.read(stage/n)) for n in CODE};seed=cache(inputs/'seed');rows={};pins={};observations={}
    for case in model.CASES:
        job=stage/case;legacy.prepare(job,stage/'a23_integrated_fixture_worker.py',seed,{})
        raw=model.encode(model.plan(case,cache(job),code,SOURCE_REVIEW_SUM));pin=f.sha(raw);pins[case]=pin
        a.put(job,'owned-plan.json',raw);a.put(job,'crash-plan.json',raw)
        observation,pm,wm=run_case(stage,job);before=cache(job);v=model.parse(raw)
        try:claim(job,raw,v)
        except FileExistsError:pass
        else:raise ValueError('guardian-owned use repeated')
        try:legacy.publication.recover(job)
        except ValueError:pass
        else:raise ValueError('guardian-owned recovery restarted')
        f.require(cache(job)==before,'guardian-owned evidence changed')
        directory=output/'cases'/case;shutil.copytree(job,directory)
        for n,value in (('observation.json',observation),('parent-messages.json',pm),('worker-messages.json',wm)):a.put(directory,n,f.encode(value))
        checked=model.assess(*args_at(directory,pin));f.require(not checked['errors'] and checked['guardian_owned_model_complete'] is (case=='normal'),'guardian-owned verdict differs '+case)
        f.require(checked['guardian_worker_wait_model_valid'] is (case not in model.NO_WORKER),'guardian-owned wait missing')
        rows[case]=semantic(checked);observations[case]=observation;a.put(directory,'analysis.json',f.encode(checked));a.put(directory,'recovery.json',f.encode(dict(retry_refused=True,recovery_refused=True,evidence_unchanged=True)))
    args=args_at(output/'cases/normal',pins['normal']);mutants={}
    for name in MUTANTS:
        r=model.assess(*mutation(name,args));f.require(not r['guardian_owned_model_complete'] and bool(r['errors']),'guardian-owned mutation accepted '+name);mutants[name]=semantic(r)
    return dict(passed=True,model_cases=36,requester_cases=16,semantic=rows,mutations=mutants,plan_pins=pins,observations=observations,
        code_sha256=code,staging_directory=str(stage),python_fixture_requester_processes=16,python_fixture_worker_processes=14,
        guardian_requester_waits=16,guardian_worker_waits=14,journal_pid_signals=0,fixture_jobs_created=16,
        native_compiler_jobs=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,
        authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json');f.require(audit['source_count']==532 and audit['prior_sources_unchanged']==528 and len(audit['source_hashes'])==532,'guardian-owned source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen guardian-owned source differs')
    for n,h in r['code_sha256'].items():
        name=n.removeprefix('source/') if n.startswith('source/') else BASE+('tools/' if n.startswith('lib/') else 'tests/')+n.removeprefix('lib/')
        f.require(h==f.sha(a.read(root/'source'/name)),'guardian-owned runtime source differs')
    f.require(set(r['semantic'])==set(model.CASES) and set(r['mutations'])==set(MUTANTS),'guardian-owned cases differ')
    for case in model.CASES:
        directory=root/'work/cases'/case;args=args_at(directory,r['plan_pins'][case]);checked=model.assess(*args)
        f.require(semantic(checked)==r['semantic'][case] and f.encode(checked)==a.read(directory/'analysis.json') and args[3]==r['observations'][case],'saved guardian-owned verdict differs')
    args=args_at(root/'work/cases/normal',r['plan_pins']['normal'])
    for name in MUTANTS:f.require(semantic(model.assess(*mutation(name,args)))==r['mutations'][name],'guardian-owned mutation differs')
    f.require(all(r[k] is False for k in FALSE),'guardian-owned grants authority');return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new guardian-owned review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'guardian-owned source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM)
    for n,v in cache(review/'inputs/seed').items():a.put(output,'inputs/seed/'+n,v)
    a.put(output,'inputs/provenance.json',f.encode(dict(source_review=parent['references']['review'],cached_sdk_materials=True,new_sdk_execution=False)))
    try:r=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='fixed-guardian-owned-fixture-only')));seal(output);raise
    f.require(sources()==frozen,'guardian-owned source drift after exercise')
    a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=532,prior_sources_unchanged=528,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=36)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
