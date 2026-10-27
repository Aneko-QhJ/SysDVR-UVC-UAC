"""Pure commit visibility and observed sync checks; neither proves process wait."""
import a23_terminal_publication_materials as prior
import a23_terminal_commit_io as publication
require,encode,parse,sha=prior.require,prior.encode,prior.parse,prior.sha
FALSE=prior.FALSE
roles=prior.roles
PHASES=('before','created','half','file_sync','link','dir_sync')
USE_PHASES=('created','half','file_sync','dir_sync')
CUTS=(*(('use',p) for p in USE_PHASES),*((kind,p) for kind in ('frame','transport','exit','commit') for p in PHASES))
CASES=('normal','guardian-loss',*(role+'-'+kind+'-'+phase for role in ('requester','worker') for kind,phase in CUTS))


def configuration(case):
    if case in ('normal','guardian-loss'):return 'worker',None,None,'normal' if case=='normal' else 'before-worker-release'
    role,kind,phase=case.split('-');return role,kind,phase,'before-worker-release'


def plan(case,files,actor,guardian,library,source):
    role,kind,phase,inner=configuration(case)
    return dict(schema='A23-terminal-commit-plan-1',scenario=case,role=role,artifact=kind,phase=phase,guardian_case=inner,
        failure_plan_sha256=sha(files['failure-plan.json']),transport_plan_sha256=sha(files['transport-plan.json']),actor_source_sha256=actor,
        guardian_source_sha256=guardian,publication_io_sha256=library,source_review_sha256=source,event_limit=30,
        interruption_exit_requested=73,model_only=True,production_execution_authorized=False)


def check(raw,pin,files):
    require(type(raw) is bytes and prior.prior.prior.owned.integrated.binding.digest(pin) and sha(raw)==pin,'external terminal commit pin differs')
    v=parse(raw);require(type(v) is dict and v.get('scenario') in CASES,'terminal commit case differs');same=prior.prior.prior.owned.integrated.binding.same
    for key in ('actor_source_sha256','guardian_source_sha256','publication_io_sha256','source_review_sha256'):require(prior.prior.prior.owned.integrated.binding.digest(v[key]),'terminal commit source pin differs')
    same(v,plan(v['scenario'],files,v['actor_source_sha256'],v['guardian_source_sha256'],v['publication_io_sha256'],v['source_review_sha256']),'terminal commit plan differs')
    require(files['commit-plan.json']==files['terminal-plan.json']==raw,'terminal commit compatibility alias differs')
    nested=prior.prior.check(files['transport-plan.json'],v['transport_plan_sha256'],files);failure=parse(files['failure-plan.json'])
    require(nested['scenario']==v['guardian_case'] and nested['candidate_sha256']==v['actor_source_sha256'] and failure['instrumentation_sha256']['a23_guardian_failure_guardian.py']==v['guardian_source_sha256'],'terminal commit runtime aliases differ')
    return v


def observe(v,outer,checkpoints,notes):
    normal=v['scenario']=='normal';same=prior.prior.prior.owned.integrated.binding.same
    g=outer['guardian_pid'];require(type(g) is int and g>0,'commit guardian PID differs')
    same(outer,dict(schema='A23-guardian-failure-witness-1',guardian_pid=g,guardian_waited=True,guardian_returncode=0 if normal else -9,actor_pid_signals=0,provenance_authenticated=False),'commit guardian witness differs')
    labels=('watch-requester','watch-worker','finished' if normal else 'before-worker-release');known={}
    require(type(checkpoints) is list and len(checkpoints)==3,'commit guardian checkpoint count differs')
    for checkpoint,label in zip(checkpoints,labels):
        actors=checkpoint['actors'];require(type(actors) is list and [a['role'] for a in actors]==(['requester'] if label=='watch-requester' else ['requester','worker']),'commit checkpoint actor order differs')
        for actor in actors:
            role=actor['role'];pid=actor['pid'];require(type(pid) is int and pid>0 and pid!=g,'commit actor PID differs')
            if role in known:require(known[role]==pid,'commit actor PID changed')
            known[role]=pid;waited=normal and label=='finished';same(actor,dict(role=role,pid=pid,waited=waited,returncode=0 if waited else None),'commit creator wait differs')
        same(checkpoint,dict(schema='A23-guardian-failure-checkpoint-1',event=label,guardian_pid=g,failure_plan_sha256=v['failure_plan_sha256'],actors=actors,model_only=True),'commit checkpoint binding differs')
    require(type(notes) is list and [n['role'] for n in notes]==['requester','worker'] and len(set(known.values()))==2,'commit exit notes differ')
    import errno
    for note in notes:
        role=note['role'];pid=known[role];same(note,dict(role=role,actor_pid=pid,watch_registered=True,proc_exit_observed=True,proc_exit_ident=pid,witness_waited_actor=False,waitpid_errno=errno.ECHILD),'commit NOTE_EXIT/wait differs')
    return known


def contents(v,pin,role,pid,notes,launch,files,frame):
    raw=prior.actor_contents(role,pid,notes,launch,files,v['failure_plan_sha256'],v['scenario']=='normal',frame)
    records={role+'-'+name:data for name,data in raw.items()};metadata=dict(role=role,actor_pid=pid,fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],terminal_plan_sha256=pin,failure_plan_sha256=v['failure_plan_sha256'])
    data={'use':encode(publication.use_record(metadata)),**{('frame' if name.endswith('failed-status.bin') else 'transport' if name.endswith('transport.json') else 'exit'):value for name,value in records.items()},'commit':encode(publication.commit_record(metadata,records))}
    return metadata,data


def filename(role,kind):return role+'-'+{'use':'terminal-use.json','frame':'failed-status.bin','transport':'transport.json','exit':'exit.json','commit':'terminal-commit.json'}[kind]


def assess(raw,pin,files,outer,checkpoints,notes,events):
    v=check(raw,pin,files);normal=v['scenario']=='normal';launch=parse(files['launch.json']);same=prior.prior.prior.owned.integrated.binding.same
    errors=[];commit_valid=sync_observed=committed_interrupted=False;notes_valid=0
    try:
        known=observe(v,outer,checkpoints,notes);notes_valid=2;role=v['role'];pid=known[role]
        require(type(events) is list and 1<=len(events)<=30,'commit event count differs')
        frame=None
        if not normal:
            frame_before=next((e for e in events if e['kind']=='frame' and e['phase']=='before'),None)
            # If cut in use, frame data has not been emitted or published; only use is checked.
            frame=bytes.fromhex(frame_before['content_hex']) if frame_before else None
        metadata=dict(role=role,actor_pid=pid,fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],terminal_plan_sha256=pin,failure_plan_sha256=v['failure_plan_sha256'])
        if frame is None and not normal:data={'use':encode(publication.use_record(metadata))}
        else:metadata,data=contents(v,pin,role,pid,notes,launch,files,frame)
        states={filename(role,kind)+(suffix):None for kind in ('use','frame','transport','exit','commit') for suffix in (('',) if kind=='use' else ('','.part'))}
        index=0;stopped=False
        sequence=[(kind,phase,blob) for kind,blob in data.items() for phase in (('before',*USE_PHASES) if kind=='use' else PHASES)]
        sequence.append(('complete','complete',data.get('commit',b'')))
        for kind,phase,blob in sequence:
            written=0 if phase in ('before','created') else len(blob)//2 if phase=='half' else len(blob)
            cut=v['artifact']==kind and v['phase']==phase
            row=dict(schema='A23-terminal-commit-event-1',kind=kind,phase=phase,content_sha256=sha(blob),content_size=len(blob),bytes_written=written,exit_requested=73 if cut else None,model_only=True,**metadata)
            if phase=='before':row['content_hex']=blob.hex()
            require(index<len(events),'commit event missing');same(events[index],row,'commit event order/binding differs');index+=1
            if kind!='complete':
                final=filename(role,kind);part=final if kind=='use' else final+'.part'
                if phase!='before':states[part]=blob[:written]
                if phase in ('link','dir_sync') and kind!='use':states[final]=blob
                if kind=='commit' and phase in ('link','dir_sync'):commit_valid=True
                if kind=='commit' and phase=='dir_sync':sync_observed=True
            if cut:stopped=True;break
        require(index==len(events) and stopped is (v['phase'] is not None),'commit event tail/cut differs')
        for name,value in states.items():
            if value is None:require(name not in files,'commit future file unexpectedly exists')
            else:require(files.get(name)==value,'commit retained bytes differ')
        other='requester' if role=='worker' else 'worker';_,other_data=contents(v,pin,other,known[other],notes,launch,files,files.get(other+'-failed-status.bin'))
        for kind in ('use','frame','transport','exit','commit'):
            name=filename(other,kind)
            for key in ([name] if kind=='use' else [name,name+'.part']):
                if kind not in other_data:require(key not in files,'normal companion has failure file')
                else:require(files.get(key)==other_data[kind],'companion committed bytes differ')
        committed_interrupted=bool(sync_observed and v['phase'] is not None)
    except (ValueError,KeyError,TypeError,IndexError,StopIteration,UnicodeError):errors.append('terminal_commit_observation')
    old=prior.prior.assess(files['transport-plan.json'],v['transport_plan_sha256'],files,outer,checkpoints,notes)
    if normal and not old['status_transport_model_complete']:errors.append('normal_inner_report')
    complete=bool(not errors and normal and old['status_transport_model_complete'])
    return dict(schema='A23-terminal-commit-result-1',scenario=v['scenario'],fixture_job_id=launch['fixture_job_id'],model_only=True,
        terminal_commit_model_complete=complete,publication_evidence_valid=not errors,publication_interrupted=v['phase'] is not None,
        local_commit_file_valid=commit_valid,commit_directory_sync_observed=sync_observed,committed_then_interrupted=committed_interrupted,
        actor_exit_notes_valid=notes_valid,actors_waited_by_creator=2 if normal and not errors else 0,
        terminated_actors_without_verified_wait=0 if normal else notes_valid,consumer_filesystem_calls=0,errors=errors,**FALSE)
