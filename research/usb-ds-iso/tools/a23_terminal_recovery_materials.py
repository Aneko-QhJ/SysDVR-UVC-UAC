"""Disk-byte-only local terminal classification; no lifecycle history is inferred."""
import uuid
import a23_terminal_commit_materials as prior
require,encode,parse,sha=prior.require,prior.encode,prior.parse,prior.sha
FALSE=prior.FALSE
same=prior.prior.prior.prior.owned.integrated.binding.same
digest=prior.prior.prior.prior.owned.integrated.binding.digest
ROLES=('requester','worker')
SUFFIXES=('terminal-use.json','failed-status.bin','failed-status.bin.part','transport.json','transport.json.part','exit.json','exit.json.part','terminal-commit.json','terminal-commit.json.part')
ALLOWED={role+'-'+suffix for role in ROLES for suffix in SUFFIXES}


def anchor(launch,terminal_pin,failure_pin,owned_pin,actors):
    return dict(schema='A23-terminal-recovery-anchor-1',fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],
        terminal_plan_sha256=terminal_pin,failure_plan_sha256=failure_pin,owned_plan_sha256=owned_pin,actors=actors,
        model_only=True,production_execution_authorized=False)


def check(raw,pin,files):
    require(type(raw) is bytes and digest(pin) and sha(raw)==pin,'external terminal recovery anchor pin differs')
    v=parse(raw);require(type(v) is dict and type(v['actors']) is dict and set(v['actors'])==set(ROLES),'recovery actor declarations differ')
    require(all(type(p) is int and p>0 for p in v['actors'].values()) and len(set(v['actors'].values()))==2,'recovery actor PID declarations differ')
    require(type(v['fixture_job_id']) is str,'recovery job declaration differs');job=uuid.UUID(v['fixture_job_id'])
    require(str(job)==v['fixture_job_id'] and job.version==4,'recovery job declaration differs')
    for name in ('launch_nonce','terminal_plan_sha256','failure_plan_sha256','owned_plan_sha256'):require(digest(v[name]),'recovery digest declaration differs')
    same(v,anchor(v,v['terminal_plan_sha256'],v['failure_plan_sha256'],v['owned_plan_sha256'],v['actors']),'recovery anchor schema differs')
    require(type(files) is dict and set(files)<=ALLOWED and all(type(k) is str and type(x) is bytes and len(x)<=8192 for k,x in files.items()) and sum(map(len,files.values()))<=131072,'bounded local byte cache required')
    return v


def metadata(v,role):return dict(role=role,actor_pid=v['actors'][role],fixture_job_id=v['fixture_job_id'],launch_nonce=v['launch_nonce'],terminal_plan_sha256=v['terminal_plan_sha256'],failure_plan_sha256=v['failure_plan_sha256'])


def terminal(v,role,code):
    return encode(dict(schema='A23-guardian-failure-actor-exit-1',role=role,actor_pid=v['actors'][role],failure_plan_sha256=v['failure_plan_sha256'],
        fixture_job_id=v['fixture_job_id'],launch_nonce=v['launch_nonce'],reported_exit_code=code,exception_type=None if code==0 else 'StatusTransportFailure',model_only=True))


def frame(v,role,raw):
    require(type(raw) is bytes and raw.endswith(b'\n'),'recovery frame terminator differs');message=parse(raw)
    base=dict(schema='A23-guardian-requester-message-1' if role=='requester' else 'A23-parent-crash-worker-message-1',kind='rejected' if role=='requester' else 'end',fixture_job_id=v['fixture_job_id'],launch_nonce=v['launch_nonce'],model_only=True)
    if role=='requester':
        require(type(message['guardian_pid']) is int and message['guardian_pid']>0,'recovery frame guardian declaration differs')
        base.update(requester_pid=v['actors'][role],guardian_pid=message['guardian_pid'],owned_plan_sha256=v['owned_plan_sha256'],reason='control_failure')
    else:base.update(worker_pid=v['actors'][role],parent_pid=v['actors']['requester'],crash_plan_sha256=v['owned_plan_sha256'],exit_code=87,reason='guardian_closed')
    require(raw==encode(base)+b'\n','recovery frame binding differs');return raw


def transport(v,role,raw):
    return encode(dict(schema='A23-status-transport-failure-1',role=role,actor_pid=v['actors'][role],failure_plan_sha256=v['failure_plan_sha256'],fixture_job_id=v['fixture_job_id'],launch_nonce=v['launch_nonce'],failed_frame_sha256=sha(raw),failed_frame_size=len(raw),message_kind='rejected' if role=='requester' else 'end',delivery_confirmed=False,creator_wait_observed=False,model_only=True,reason='epipe',errno=32,bytes_committed=0,write_attempts=1))


def classify_role(v,role,files):
    local={name.removeprefix(role+'-'):raw for name,raw in files.items() if name.startswith(role+'-')};errors=[];opaque=[];declared_code=None
    if not local:return dict(classification='absent',commit_associated=False,declared_exit_code=None,opaque_partial_files=[],errors=[])
    def fail(reason):errors.append(reason)
    use=encode(prior.publication.use_record(metadata(v,role)));actual_use=local.get('terminal-use.json')
    if actual_use is None:fail('use_missing')
    elif not use.startswith(actual_use):fail('use_binding_or_prefix')
    if actual_use!=use and set(local)-{'terminal-use.json'}:fail('records_before_complete_use')
    expected={};family=None
    for suffix in ('exit.json','exit.json.part'):
        if suffix in local:
            raw=local[suffix];matches=[code for code in (0,91) if raw==terminal(v,role,code)]
            if matches:
                if declared_code is not None and matches[0]!=declared_code:fail('exit_pair_code_conflict')
                declared_code=matches[0]
            elif suffix=='exit.json' or not any(terminal(v,role,code).startswith(raw) for code in (0,91)):fail('exit_binding_or_prefix')
    if any(name in local for name in ('failed-status.bin','failed-status.bin.part','transport.json','transport.json.part')):family='epipe'
    elif declared_code is not None:family='normal' if declared_code==0 else 'epipe'
    if family=='epipe' and declared_code==0:fail('failure_files_with_success_exit')
    raw_frame=None
    for suffix in ('failed-status.bin','failed-status.bin.part'):
        if suffix not in local:continue
        raw=local[suffix]
        try:parse(raw)
        except (ValueError,UnicodeError):
            if suffix.endswith('.part'):opaque.append(role+'-'+suffix)
            else:fail('final_frame_unparseable')
        else:
            try:raw_frame=frame(v,role,raw)
            except (ValueError,KeyError,TypeError,UnicodeError):fail('frame_binding')
    if raw_frame is not None:expected['failed-status.bin']=raw_frame;expected['transport.json']=transport(v,role,raw_frame)
    if declared_code is not None:expected['exit.json']=terminal(v,role,declared_code)
    elif family=='epipe':expected['exit.json']=terminal(v,role,91)
    for suffix in ('transport.json','transport.json.part'):
        if suffix not in local:continue
        if 'failed-status.bin' not in local:fail('transport_before_frame_final')
        if raw_frame is None:fail('transport_without_valid_frame')
        elif suffix=='transport.json' and local[suffix]!=expected['transport.json']:fail('transport_binding')
        elif suffix.endswith('.part') and not expected['transport.json'].startswith(local[suffix]):fail('transport_prefix')
    if family=='epipe' and any(name in local for name in ('exit.json','exit.json.part')) and 'transport.json' not in local:fail('exit_before_transport_final')
    for suffix in ('failed-status.bin','transport.json','exit.json','terminal-commit.json'):
        final=local.get(suffix);part=local.get(suffix+'.part')
        if final is not None and (part is None or final!=part):fail('final_part_mismatch:'+suffix)
    for suffix in ('failed-status.bin','transport.json','exit.json'):
        if suffix in local and suffix not in expected:fail('unvalidated_final:'+suffix)
    commit_valid=False
    for suffix in ('terminal-commit.json','terminal-commit.json.part'):
        if suffix not in local:continue
        raw=local[suffix]
        try:manifest=parse(raw)
        except (ValueError,UnicodeError):
            if suffix.endswith('.part'):opaque.append(role+'-'+suffix)
            else:fail('final_commit_unparseable')
            continue
        try:
            require(family in ('normal','epipe') and declared_code==(0 if family=='normal' else 91),'commit_exit_family')
            names=('exit.json',) if family=='normal' else ('failed-status.bin','transport.json','exit.json')
            records={role+'-'+name:local[name] for name in names}
            require(all(name in expected and records[role+'-'+name]==expected[name] for name in names),'commit_record_binding')
            wanted=encode(prior.publication.commit_record(metadata(v,role),records));require(raw==wanted,'commit_manifest_binding')
            require(actual_use==use and all(local.get(name+'.part')==local[name] for name in names),'commit_missing_parts_or_use')
            if suffix=='terminal-commit.json':commit_valid=True
        except (ValueError,KeyError,TypeError,UnicodeError):fail('commit_association')
    return dict(classification='conflict' if errors else 'commit_associated' if commit_valid else 'incomplete',commit_associated=bool(commit_valid and not errors),declared_exit_code=declared_code,opaque_partial_files=sorted(set(opaque)),errors=sorted(set(errors)))


def classify(raw,pin,files):
    v=check(raw,pin,files);roles={role:classify_role(v,role,files) for role in ROLES};labels=[r['classification'] for r in roles.values()]
    label='conflict' if 'conflict' in labels else 'absent' if all(x=='absent' for x in labels) else 'commit_associated' if all(x=='commit_associated' for x in labels) else 'incomplete'
    return dict(schema='A23-terminal-recovery-result-1',fixture_job_id=v['fixture_job_id'],model_only=True,classification=label,roles=roles,
        directory_sync_status='unknown',actor_wait_status='unknown',actual_process_exit_status='unknown',hardlink_identity_status='unknown',
        task_complete=False,record_source_authenticated=False,consumer_filesystem_calls=0,consumer_process_calls=0,**FALSE)
