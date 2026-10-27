"""Pure guardian failure evidence: exit notes never stand in for missing wait."""
import errno
import a23_guardian_owned_materials as owned
require,encode,parse,sha=owned.require,owned.encode,owned.parse,owned.sha
FALSE=owned.FALSE
CASES=('normal','before-requester','after-requester','after-worker-unrecorded','owner-partial','owner-synced','before-worker-release',
    'child-payload.begin','child-receipt.partial','child-receipt.link','child-stdout.emit','after-worker-wait','after-requester-wait')


def plan(case,files,instrumentation,source_pin):
    return dict(schema='A23-guardian-failure-plan-1',scenario=case,owned_plan_sha256=sha(files['owned-plan.json']),
        launch_sha256=sha(files['launch.json']),instrumentation_sha256=instrumentation,source_review_sha256=source_pin,
        observe_actor_exit_without_pipe_retention=True,model_only=True,production_execution_authorized=False)


def roles(case):return [] if case=='before-requester' else ['requester'] if case=='after-requester' else ['requester','worker']
def reaped(case,role):return case in ('normal','after-requester-wait') or case=='after-worker-wait' and role=='worker'


def check(raw,pin,files):
    require(type(raw) is bytes and owned.integrated.binding.digest(pin) and sha(raw)==pin,'external guardian failure plan pin differs')
    v=parse(raw);require(type(v) is dict and v.get('scenario') in CASES,'guardian failure case differs')
    require(type(v['instrumentation_sha256']) is dict and set(v['instrumentation_sha256'])=={'a23_guardian_failure_guardian.py','a23_guardian_failure_actor.py'} and all(owned.integrated.binding.digest(x) for x in v['instrumentation_sha256'].values()),'guardian failure instrumentation pins differ')
    require(owned.integrated.binding.digest(v['source_review_sha256']),'guardian failure source pin differs')
    owned.integrated.binding.same(v,plan(v['scenario'],files,v['instrumentation_sha256'],v['source_review_sha256']),'guardian failure plan schema differs')
    require(files['failure-plan.json']==raw,'cached guardian failure plan differs')
    owned.check(files['owned-plan.json'],v['owned_plan_sha256'],files);return v


def assess(raw,pin,files,outer,checkpoints,notes):
    v=check(raw,pin,files);case=v['scenario'];launch=parse(files['launch.json']);errors=[];valid_exit=0;creator_waits=0;unwaited=0;inner=None
    try:
        require(outer['schema']=='A23-guardian-failure-witness-1' and type(outer['guardian_pid']) is int and outer['guardian_pid']>0 and
            outer['guardian_waited'] is True and type(outer['guardian_returncode']) is int and outer['guardian_returncode']==(0 if case=='normal' else -9) and outer['actor_pid_signals']==0 and type(outer['actor_pid_signals']) is int and outer['provenance_authenticated'] is False,'guardian witness wait differs')
        expected_events=[*('watch-'+r for r in roles(case)),'finished' if case=='normal' else case]
        require(type(checkpoints) is list and len(checkpoints)==len(expected_events),'guardian checkpoints length differs')
        known={}
        for checkpoint,event in zip(checkpoints,expected_events):
            require(checkpoint['schema']=='A23-guardian-failure-checkpoint-1' and checkpoint['event']==event and checkpoint['guardian_pid']==outer['guardian_pid'] and type(checkpoint['guardian_pid']) is int and checkpoint['failure_plan_sha256']==pin and checkpoint['model_only'] is True,'guardian checkpoint binding differs')
            actors=checkpoint['actors'];expected_roles=roles(case)[:1] if event=='watch-requester' else roles(case)
            require(type(actors) is list and [a['role'] for a in actors]==expected_roles,'guardian checkpoint actors differ')
            for actor in actors:
                role=actor['role'];require(type(actor['pid']) is int and actor['pid']>0 and actor['pid']!=outer['guardian_pid'],'checkpoint actor PID differs')
                if role in known:require(known[role]==actor['pid'],'checkpoint actor PID changed')
                known[role]=actor['pid'];waited=reaped(case,role) if event==expected_events[-1] else False
                owned.integrated.binding.same(actor,dict(role=role,pid=actor['pid'],waited=waited,returncode=0 if waited else None),'checkpoint creator wait state differs')
        require(type(notes) is list and [n['role'] for n in notes]==roles(case),'actor exit observations differ')
        for note in notes:
            role=note['role'];pid=known[role];waited=reaped(case,role)
            owned.integrated.binding.same(note,dict(role=role,actor_pid=pid,watch_registered=True,proc_exit_observed=True,proc_exit_ident=pid,
                witness_waited_actor=False,waitpid_errno=errno.ECHILD),'actor exit note/wait boundary differs')
            result=parse(files[role+'-exit.json']);code=0 if waited else 1;exception=None if waited else 'BrokenPipeError'
            owned.integrated.binding.same(result,dict(schema='A23-guardian-failure-actor-exit-1',role=role,actor_pid=pid,failure_plan_sha256=pin,
                fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],reported_exit_code=code,exception_type=exception,model_only=True),'actor terminal report differs')
            valid_exit+=1;creator_waits+=int(waited);unwaited+=int(not waited)
    except (ValueError,KeyError,TypeError,UnicodeError,IndexError):errors.append('guardian_or_actor_observation')
    if case=='normal':
        try:
            inner=owned.assess(files['owned-plan.json'],v['owned_plan_sha256'],files,parse(files['inner-observation.json']),parse(files['inner-requester-messages.json']),parse(files['inner-worker-messages.json']))
            require(inner['guardian_owned_model_complete'],'guardian inner normal completion missing')
        except (ValueError,KeyError,TypeError,UnicodeError):errors.append('inner_guardian')
    complete=bool(case=='normal' and not errors and inner and inner['guardian_owned_model_complete'] and valid_exit==2 and creator_waits==2)
    return dict(schema='A23-guardian-failure-result-1',scenario=case,fixture_job_id=launch['fixture_job_id'],model_only=True,
        actor_exit_notes_valid=valid_exit,actors_waited_by_creator=creator_waits,terminated_actors_without_verified_wait=unwaited,
        guardian_failure_model_complete=complete,guardian_loss_broken_pipe_observed=bool(unwaited),errors=errors,consumer_filesystem_calls=0,**FALSE)
