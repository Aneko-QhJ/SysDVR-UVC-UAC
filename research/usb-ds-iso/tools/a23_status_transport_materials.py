"""Pure status transport candidate evidence; local failure never proves wait."""
import copy,errno
import a23_guardian_failure_materials as prior
require,encode,parse,sha=prior.require,prior.encode,prior.parse,prior.sha
FALSE=prior.FALSE
CASES=prior.CASES


def plan(case,files,candidate,baseline,source):
    return dict(schema='A23-status-transport-plan-1',scenario=case,failure_plan_sha256=sha(files['failure-plan.json']),
        candidate_sha256=candidate,frozen_observer_sha256=baseline,source_review_sha256=source,
        failure_exit_code=91,epipe_retry_allowed=False,local_terminal_is_wait_evidence=False,model_only=True,production_execution_authorized=False)


def check(raw,pin,files):
    require(type(raw) is bytes and prior.owned.integrated.binding.digest(pin) and sha(raw)==pin,'external status transport pin differs')
    v=parse(raw);require(type(v) is dict and v.get('scenario') in CASES,'status transport case differs')
    for key in ('candidate_sha256','frozen_observer_sha256','source_review_sha256'):require(prior.owned.integrated.binding.digest(v[key]),'status transport source pin differs')
    prior.owned.integrated.binding.same(v,plan(v['scenario'],files,v['candidate_sha256'],v['frozen_observer_sha256'],v['source_review_sha256']),'status transport plan differs')
    require(files['transport-plan.json']==raw,'cached status transport plan differs')
    nested=prior.check(files['failure-plan.json'],v['failure_plan_sha256'],files)
    require(nested['scenario']==v['scenario'] and nested['instrumentation_sha256']['a23_guardian_failure_actor.py']==v['candidate_sha256'],'status transport runtime alias differs')
    owned=parse(files['owned-plan.json']);require(owned['scenario']==(v['scenario'] if v['scenario'].startswith('child-') else 'normal'),'status transport inner scenario differs')
    return v


def assess(raw,pin,files,outer,checkpoints,notes):
    v=check(raw,pin,files);case=v['scenario'];launch=parse(files['launch.json']);projected=dict(files);errors=[];failures=0;frames=0
    try:
        for note in notes:
            role=note['role'];pid=note['actor_pid'];waited=prior.reaped(case,role);terminal=parse(files[role+'-exit.json'])
            prior.owned.integrated.binding.same(terminal,dict(schema='A23-guardian-failure-actor-exit-1',role=role,actor_pid=pid,
                failure_plan_sha256=v['failure_plan_sha256'],fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],
                reported_exit_code=0 if waited else 91,exception_type=None if waited else 'StatusTransportFailure',model_only=True),'candidate local terminal differs')
            report_name=role+'-transport.json';frame_name=role+'-failed-status.bin'
            if waited:require(report_name not in files and frame_name not in files,'successful actor has transport failure')
            else:
                frame=files[frame_name];message=parse(frame);report=parse(files[report_name]);kind=message['kind']
                allowed=('request','rejected') if role=='requester' and case=='after-requester' else ('rejected',) if role=='requester' else ('ready','end') if case=='after-worker-unrecorded' else ('end',)
                require(kind in allowed and frame.endswith(b'\n') and len(frame)<=8192,'failed status frame kind differs')
                base=dict(schema='A23-guardian-requester-message-1' if role=='requester' else 'A23-parent-crash-worker-message-1',
                    kind=kind,fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],model_only=True)
                if role=='requester':
                    require(type(message['guardian_pid']) is int and message['guardian_pid']>0,'frame guardian declaration differs')
                    base.update(requester_pid=pid,guardian_pid=message['guardian_pid'],owned_plan_sha256=sha(files['owned-plan.json']))
                    if kind=='rejected':base['reason']='control_failure'
                else:
                    parent=next(n['actor_pid'] for n in notes if n['role']=='requester');base.update(worker_pid=pid,parent_pid=parent,crash_plan_sha256=sha(files['crash-plan.json']))
                    if kind=='end':base.update(exit_code=87,reason='guardian_closed')
                prior.owned.integrated.binding.same(message,base,'failed status frame binding differs')
                prior.owned.integrated.binding.same(report,dict(schema='A23-status-transport-failure-1',role=role,actor_pid=pid,
                    failure_plan_sha256=v['failure_plan_sha256'],fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],
                    failed_frame_sha256=sha(frame),failed_frame_size=len(frame),message_kind=kind,delivery_confirmed=False,creator_wait_observed=False,
                    model_only=True,reason='epipe',errno=errno.EPIPE,bytes_committed=0,write_attempts=1),'transport failure record differs')
                failures+=1;frames+=1
                # Mechanical compatibility projection only after validating the raw candidate failure.
                translated=dict(terminal,reported_exit_code=1,exception_type='BrokenPipeError');projected[role+'-exit.json']=encode(translated)
    except (ValueError,KeyError,TypeError,UnicodeError,StopIteration):errors.append('status_transport_observation')
    inner=prior.assess(files['failure-plan.json'],v['failure_plan_sha256'],projected,outer,checkpoints,notes)
    errors.extend(inner['errors']);complete=bool(not errors and inner['guardian_failure_model_complete'])
    return dict(schema='A23-status-transport-result-1',scenario=case,fixture_job_id=launch['fixture_job_id'],model_only=True,
        status_transport_model_complete=complete,status_transport_failures=failures,failed_status_frames_valid=frames,
        actor_exit_notes_valid=inner['actor_exit_notes_valid'],actors_waited_by_creator=inner['actors_waited_by_creator'],
        terminated_actors_without_verified_wait=inner['terminated_actors_without_verified_wait'],
        failure_not_upgraded=not complete,errors=errors,consumer_filesystem_calls=0,**FALSE)
