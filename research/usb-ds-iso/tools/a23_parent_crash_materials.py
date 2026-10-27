"""Pure parent-interruption evidence checks; exit observation is not orphan wait."""
import errno
import a23_integrated_fixture_materials as integrated
require,encode,parse,sha=integrated.require,integrated.encode,integrated.parse,integrated.sha
FALSE={**integrated.FALSE,'orphan_reaping_verified':False,'process_tree_reclamation_verified':False,
    'production_launcher_integrated':False,'journal_pid_signal_authorized':False}
CASES=('normal','before-popen','after-popen-unrecorded','owner-partial','owner-synced',
    'child-payload.begin','child-receipt.partial','child-receipt.link','child-stdout.emit','after-parent-report','gate-closed')
SELF_EXIT={'before-popen','after-popen-unrecorded','owner-partial','owner-synced','after-parent-report'}


def plan(scenario,launch_raw,integrated_raw,code,source_pin):
    return dict(schema='A23-parent-crash-plan-1',scenario=scenario,launch_sha256=sha(launch_raw),
        integrated_plan_sha256=sha(integrated_raw),code_sha256=code,source_review_sha256=source_pin,
        guard_channel='retained_pipe_and_proc_exit_note',model_only=True,production_execution_authorized=False)


def check_plan(raw,pin,files):
    require(type(raw) is bytes and integrated.binding.digest(pin) and sha(raw)==pin,'external parent crash plan pin differs')
    v=parse(raw);require(type(v) is dict and v.get('scenario') in CASES,'parent crash scenario differs')
    require(type(v['code_sha256']) is dict and len(v['code_sha256'])==6 and all(type(n) is str and not n.startswith('/') and '..' not in n.split('/') and integrated.binding.digest(h) for n,h in v['code_sha256'].items()),'parent crash code inventory differs')
    require(integrated.binding.digest(v['source_review_sha256']),'parent crash source pin differs')
    integrated.binding.same(v,plan(v['scenario'],files['launch.json'],files['integrated-plan.json'],v['code_sha256'],v['source_review_sha256']),'parent crash plan differs')
    integrated.check_plan(files['integrated-plan.json'],v['integrated_plan_sha256'],files['launch.json'])
    require(files['crash-plan.json']==raw,'cached parent crash plan differs');return v


def message(kind,launch,pin,parent_pid,worker_pid,**extra):
    return dict(schema='A23-parent-crash-worker-message-1',kind=kind,worker_pid=worker_pid,parent_pid=parent_pid,
        fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],crash_plan_sha256=pin,model_only=True,**extra)


def assess(raw,pin,files,outer,guard,messages):
    v=check_plan(raw,pin,files);case=v['scenario'];launch=parse(files['launch.json']);errors=[];owner=False;ready=False;end=False;exit_note=False;checked=None
    parent=outer.get('parent_pid');worker=guard.get('worker_pid')
    try:
        require(type(parent) is int and parent>0 and type(outer['returncode']) is int and type(outer['waited']) is bool and outer['waited'],'parent exit/identity differs')
        expected=79 if case in SELF_EXIT else -9 if case.startswith('child-') else 0
        require(outer['returncode']==expected and outer['schema']=='A23-parent-crash-outer-1' and outer['provenance_authenticated'] is False,'parent interruption observation differs')
    except (ValueError,KeyError,TypeError):errors.append('parent_observation')
    seen=case!='before-popen'
    try:
        require(type(messages) is list and type(guard['worker_seen']) is bool and guard['worker_seen']==seen,'worker visibility differs')
        if seen:
            require(type(worker) is int and worker>0 and worker!=parent,'worker PID type differs')
            expected=[message('ready',launch,pin,parent,worker)]
            if case.startswith('child-'):expected.append(message('checkpoint',launch,pin,parent,worker,event=case.removeprefix('child-')))
            code=87 if case=='gate-closed' else 0 if case in ('normal','after-parent-report') else 86
            reason='guardian_closed' if case=='gate-closed' else 'inner_exit' if code==0 else 'parent_pipe_eof'
            expected.append(message('end',launch,pin,parent,worker,exit_code=code,reason=reason))
            integrated.binding.same(messages,expected,'worker pipe binding/exit reason differs');ready=end=True
            require(guard['proc_watch_registered'] is True and guard['proc_exit_observed'] is True and type(guard['proc_exit_ident']) is int and guard['proc_exit_ident']==worker,'worker proc exit note differs')
            require(guard['worker_waited_by_guardian'] is False and type(guard['waitpid_errno']) is int and guard['waitpid_errno']==errno.ECHILD,'non-child wait boundary differs');exit_note=True
        else:
            require(not messages and worker is None and guard['proc_watch_registered'] is False and guard['proc_exit_observed'] is False and guard['proc_exit_ident'] is None and guard['worker_waited_by_guardian'] is False and guard['waitpid_errno'] is None,'unspawned parent claims worker exit')
        require(guard['schema']=='A23-parent-crash-guard-1' and guard['worker_pid_signals']==0 and type(guard['worker_pid_signals']) is int,'journal PID signal boundary differs')
    except (ValueError,KeyError,TypeError,UnicodeError):errors.append('worker_guard')
    try:
        o=parse(files['owner.json']);require(type(o['parent_pid']) is int and type(o['worker_pid']) is int,'owner PID type differs')
        integrated.binding.same(o,dict(schema='A23-parent-crash-owner-1',parent_pid=parent,worker_pid=worker,crash_plan_sha256=pin,launch_sha256=v['launch_sha256'],model_only=True),'owner journal binding differs');owner=True
    except (ValueError,KeyError,TypeError,UnicodeError):pass
    if case not in ('before-popen','after-popen-unrecorded','owner-partial') and not owner:errors.append('owner')
    present='parent-observation.json' in files
    if present:
        try:
            checked=integrated.assess(files['integrated-plan.json'],v['integrated_plan_sha256'],files,files['parent-stdout.bin'],files['parent-stderr.bin'],parse(files['parent-observation.json']))
        except (ValueError,KeyError,TypeError,UnicodeError):errors.append('parent_report')
    if case in ('normal','after-parent-report','gate-closed') and checked is None:errors.append('missing_parent_report')
    complete=bool(case=='normal' and not errors and owner and ready and end and exit_note and outer['returncode']==0 and checked and checked['integrated_model_complete'])
    return dict(schema='A23-parent-crash-result-1',scenario=case,fixture_job_id=launch['fixture_job_id'],model_only=True,
        parent_wait_observed=not('parent_observation' in errors),worker_handshake_valid=ready,worker_end_binding_valid=end,
        worker_exit_note_valid=exit_note,owner_record_valid=owner,unrecorded_worker_gap_observed=bool(ready and not owner),
        parent_report_present=present,parent_inner_completion=checked['integrated_model_complete'] if checked else False,
        parent_crash_model_complete=complete,errors=errors,consumer_filesystem_calls=0,**FALSE)
