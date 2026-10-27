"""Pure interrupted local publication evidence; full local exit files are not wait."""
import errno
import a23_status_transport_materials as prior
require,encode,parse,sha=prior.require,prior.encode,prior.parse,prior.sha
FALSE=prior.FALSE
roles=prior.prior.roles
ARTIFACTS={'frame':'failed-status.bin','transport':'transport.json','exit':'exit.json'}
PHASES=('before','created','half','synced')
CASES=('normal','guardian-loss',*(role+'-'+artifact+'-'+phase for role in ('requester','worker') for artifact in ARTIFACTS for phase in PHASES))


def configuration(case):
    if case in ('normal','guardian-loss'):return 'worker',None,None,'normal' if case=='normal' else 'before-worker-release'
    role,artifact,phase=case.split('-');return role,ARTIFACTS[artifact],phase,'before-worker-release'


def plan(case,files,actor,guardian,source):
    role,artifact,phase,inner=configuration(case)
    return dict(schema='A23-terminal-publication-plan-1',scenario=case,role=role,artifact=artifact,phase=phase,guardian_case=inner,
        failure_plan_sha256=sha(files['failure-plan.json']),transport_plan_sha256=sha(files['transport-plan.json']),
        actor_source_sha256=actor,guardian_source_sha256=guardian,source_review_sha256=source,
        interruption_exit_requested=73,event_limit=12,model_only=True,production_execution_authorized=False)


def check(raw,pin,files):
    require(type(raw) is bytes and prior.prior.owned.integrated.binding.digest(pin) and sha(raw)==pin,'external terminal publication pin differs')
    v=parse(raw);require(type(v) is dict and v.get('scenario') in CASES,'terminal publication case differs')
    for key in ('actor_source_sha256','guardian_source_sha256','source_review_sha256'):require(prior.prior.owned.integrated.binding.digest(v[key]),'terminal source pin differs')
    same=prior.prior.owned.integrated.binding.same
    same(v,plan(v['scenario'],files,v['actor_source_sha256'],v['guardian_source_sha256'],v['source_review_sha256']),'terminal plan differs')
    require(files['terminal-plan.json']==raw,'cached terminal plan differs')
    nested=prior.check(files['transport-plan.json'],v['transport_plan_sha256'],files);failure=parse(files['failure-plan.json'])
    require(nested['scenario']==v['guardian_case'] and nested['candidate_sha256']==v['actor_source_sha256'] and failure['instrumentation_sha256']['a23_guardian_failure_guardian.py']==v['guardian_source_sha256'],'terminal runtime aliases differ')
    return v


def actor_contents(role,pid,notes,launch,files,failure_pin,normal,frame=None):
    terminal=encode(dict(schema='A23-guardian-failure-actor-exit-1',role=role,actor_pid=pid,failure_plan_sha256=failure_pin,
        fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],reported_exit_code=0 if normal else 91,
        exception_type=None if normal else 'StatusTransportFailure',model_only=True))
    if normal:return {'exit.json':terminal}
    require(type(frame) is bytes and frame.endswith(b'\n') and len(frame)<=8192,'terminal failed frame differs');message=parse(frame)
    base=dict(schema='A23-guardian-requester-message-1' if role=='requester' else 'A23-parent-crash-worker-message-1',
        kind='rejected' if role=='requester' else 'end',fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],model_only=True)
    if role=='requester':
        require(type(message['guardian_pid']) is int and message['guardian_pid']>0,'frame guardian declaration differs')
        base.update(requester_pid=pid,guardian_pid=message['guardian_pid'],owned_plan_sha256=sha(files['owned-plan.json']),reason='control_failure')
    else:base.update(worker_pid=pid,parent_pid=next(n['actor_pid'] for n in notes if n['role']=='requester'),crash_plan_sha256=sha(files['crash-plan.json']),exit_code=87,reason='guardian_closed')
    require(frame==encode(base)+b'\n','terminal failed frame binding differs')
    transport=encode(dict(schema='A23-status-transport-failure-1',role=role,actor_pid=pid,failure_plan_sha256=failure_pin,
        fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],failed_frame_sha256=sha(frame),failed_frame_size=len(frame),
        message_kind=base['kind'],delivery_confirmed=False,creator_wait_observed=False,model_only=True,reason='epipe',errno=errno.EPIPE,bytes_committed=0,write_attempts=1))
    return {'failed-status.bin':frame,'transport.json':transport,'exit.json':terminal}


def assess(raw,pin,files,outer,checkpoints,notes,events):
    v=check(raw,pin,files);case=v['scenario'];normal=case=='normal';launch=parse(files['launch.json']);same=prior.prior.owned.integrated.binding.same
    errors=[];complete_file=False;notes_valid=0
    try:
        require(type(outer['guardian_pid']) is int and outer['guardian_pid']>0,'guardian PID differs')
        g=outer['guardian_pid'];same(outer,dict(schema='A23-guardian-failure-witness-1',guardian_pid=g,guardian_waited=True,guardian_returncode=0 if normal else -9,actor_pid_signals=0,provenance_authenticated=False),'terminal guardian witness differs')
        labels=('watch-requester','watch-worker','finished' if normal else 'before-worker-release');known={}
        require(type(checkpoints) is list and len(checkpoints)==3,'terminal guardian checkpoint count differs')
        for checkpoint,label in zip(checkpoints,labels):
            actors=checkpoint['actors'];roles=['requester'] if label=='watch-requester' else ['requester','worker']
            require([a['role'] for a in actors]==roles,'terminal actor checkpoint order differs')
            for actor in actors:
                role=actor['role'];pid=actor['pid'];require(type(pid) is int and pid>0 and pid!=g,'terminal actor PID differs')
                if role in known:require(known[role]==pid,'terminal actor PID changed')
                known[role]=pid;waited=normal and label=='finished';same(actor,dict(role=role,pid=pid,waited=waited,returncode=0 if waited else None),'terminal creator wait differs')
            same(checkpoint,dict(schema='A23-guardian-failure-checkpoint-1',event=label,guardian_pid=g,failure_plan_sha256=v['failure_plan_sha256'],actors=actors,model_only=True),'terminal checkpoint binding differs')
        require(type(notes) is list and [n['role'] for n in notes]==['requester','worker'] and len(set(known.values()))==2,'terminal actor notes differ')
        for note in notes:
            role=note['role'];pid=known[role];same(note,dict(role=role,actor_pid=pid,watch_registered=True,proc_exit_observed=True,proc_exit_ident=pid,witness_waited_actor=False,waitpid_errno=errno.ECHILD),'terminal NOTE_EXIT/wait differs')
            notes_valid+=1
        role=v['role'];pid=known[role];require(type(events) is list and 1<=len(events)<=12,'terminal publication event count differs')
        first=events[0];intended=bytes.fromhex(first['content_hex']) if not normal else None
        selected=actor_contents(role,pid,notes,launch,files,v['failure_plan_sha256'],normal,intended)
        expected_state={name:None for name in ARTIFACTS.values()};index=0;stopped=False
        for name,data in selected.items():
            for phase in PHASES:
                written=0 if phase in ('before','created') else len(data)//2 if phase=='half' else len(data)
                cut=v['artifact']==name and v['phase']==phase
                row=dict(schema='A23-terminal-publication-event-1',role=role,actor_pid=pid,filename=role+'-'+name,phase=phase,
                    terminal_plan_sha256=pin,failure_plan_sha256=v['failure_plan_sha256'],fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],
                    content_sha256=sha(data),content_size=len(data),bytes_written=written,exit_requested=73 if cut else None,model_only=True)
                if phase=='before':row['content_hex']=data.hex()
                require(index<len(events),'terminal publication event missing');same(events[index],row,'terminal publication event differs');index+=1
                expected_state[name]=None if phase=='before' else data[:written]
                if cut:stopped=True;break
            if stopped:break
        require(index==len(events) and stopped is (v['phase'] is not None),'terminal event tail/cut differs')
        for name,value in expected_state.items():
            key=role+'-'+name
            if value is None:require(key not in files,'terminal future file unexpectedly exists')
            else:require(files.get(key)==value,'terminal retained prefix differs')
        other='requester' if role=='worker' else 'worker';other_frame=files.get(other+'-failed-status.bin')
        full=actor_contents(other,known[other],notes,launch,files,v['failure_plan_sha256'],normal,other_frame)
        for name in ARTIFACTS.values():
            key=other+'-'+name
            if name not in full:require(key not in files,'normal actor has failure file')
            else:require(files.get(key)==full[name],'non-interrupted actor local record differs')
        complete_file=expected_state['exit.json']==selected['exit.json']
    except (ValueError,KeyError,TypeError,IndexError,StopIteration,UnicodeError):errors.append('terminal_publication_observation')
    old=prior.assess(files['transport-plan.json'],v['transport_plan_sha256'],files,outer,checkpoints,notes)
    complete=bool(not errors and normal and old['status_transport_model_complete'])
    if normal and not old['status_transport_model_complete']:errors.append('normal_inner_report')
    return dict(schema='A23-terminal-publication-result-1',scenario=case,fixture_job_id=launch['fixture_job_id'],model_only=True,
        terminal_publication_model_complete=complete,publication_evidence_valid=not errors,publication_interrupted=v['phase'] is not None,
        selected_terminal_file_complete=complete_file,complete_terminal_then_interrupted=bool(complete_file and v['phase'] is not None),
        prior_actor_metadata_accepted=not old['errors'],actor_exit_notes_valid=notes_valid,actors_waited_by_creator=2 if normal and not errors else 0,
        terminated_actors_without_verified_wait=0 if normal else notes_valid,consumer_filesystem_calls=0,errors=errors,**FALSE)
