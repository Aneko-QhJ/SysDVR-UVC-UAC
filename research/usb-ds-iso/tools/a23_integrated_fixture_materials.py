"""Pure synchronized-launch/result/cleanup admission for disposable fixtures."""
import a23_fixture_job_binding as binding
import a23_integrated_fixture_io as io
from a23_fixture_recovery import FALSE
require,encode,parse,sha=binding.require,binding.encode,binding.parse,binding.sha
supervisor=binding.supervisor
MODES=('normal','exit-seven','timeout-after-output','no-stdout','stderr-output')
PARENT_FAULTS=(None,'spawn-error','read-error','stdout-close-error','selector-close-error','wait-error')
LIBRARIES={'a23_integrated_fixture_io.py','a23_fixture_publication.py'}


def plan(launch_raw,libraries,pre=None,cut=None,fail=None,mode='normal',parent=None):
    return dict(schema='A23-integrated-fixture-plan-1',launch_sha256=sha(launch_raw),library_sha256=libraries,
        prelaunch_fail_before=pre,child_cut_after=cut,child_fail_before=fail,worker_mode=mode,
        parent_fault=parent,model_only=True,production_execution_authorized=False)


def check_plan(raw,pin,launch_raw):
    require(type(raw) is bytes and binding.digest(pin) and sha(raw)==pin,'external integrated plan pin differs')
    v=parse(raw);require(type(v) is dict,'integrated plan object required')
    libs=v['library_sha256'];require(type(libs) is dict and set(libs)==LIBRARIES and all(binding.digest(x) for x in libs.values()),'integrated library pins differ')
    require(v['prelaunch_fail_before'] in (None,*io.PRE_FAILURES) and v['child_cut_after'] in (None,*io.CHILD_EVENTS) and
        v['child_fail_before'] in (None,*io.CHILD_FAILURES) and v['worker_mode'] in MODES and v['parent_fault'] in PARENT_FAULTS,'integrated fault labels differ')
    require(not(v['child_cut_after'] and v['child_fail_before']),'conflicting child publication faults')
    binding.same(v,plan(launch_raw,libs,v['prelaunch_fail_before'],v['child_cut_after'],v['child_fail_before'],v['worker_mode'],v['parent_fault']),'integrated plan schema/authority differs')
    launch=binding.check_launch(launch_raw,v['launch_sha256']);require(launch['fixture_mode']=='normal','integrated fixture launch differs')
    return v,launch


def planned_trace(v):
    rows=[]
    for event in io.PRE_EVENTS:
        if event==v['prelaunch_fail_before']:return rows+[dict(event=event,outcome='injected_error')]
        rows.append(dict(event=event,outcome='completed'))
    rows.append(dict(event='launch.ready',outcome='completed'))
    if v['parent_fault']=='spawn-error':return rows
    for event in io.CHILD_EVENTS:
        if event==v['child_fail_before']:return rows+[dict(event=event,outcome='injected_error')]
        rows.append(dict(event=event,outcome='completed'))
        if event==v['child_cut_after']:return rows
    return rows


def observe(launch_raw,plan_raw,attempt_raw,o,prelaunch_error=None):
    return dict(schema='A23-integrated-fixture-observation-1',launch_sha256=sha(launch_raw),plan_sha256=sha(plan_raw),
        attempt_sha256=sha(attempt_raw),prelaunch_error=prelaunch_error,supervisor=o)


def use_record(launch_raw,plan_raw):
    return dict(schema='A23-integrated-fixture-launcher-use-1',launch_sha256=sha(launch_raw),
        plan_sha256=sha(plan_raw),maximum_calls=1,model_only=True)


def empty_observation():
    return dict(schema='A23-supervisor-unified-observation-1',case='normal',material_case='normal',spawned=False,spawn_error=True,reaped=False,returncode=None,
        timed_out=False,stdout_eof=False,stderr_eof=False,reader_error=False,selector_error=False,read_interrupts=0,wait_error=False,wait_timed_out=False,
        group_kill_attempted=False,group_kill_outcome='none',fallback_kill_attempted=False,fallback_kill_outcome='none',limit_exceeded=None,
        stdout_bytes=0,stderr_bytes=0,launches=0,retries=0,leader_reaped_before_signal=False,provenance_authenticated=False,native_context_refreshed=False,
        clock_domain='supervisor_monotonic',close_attempts=[],close_completed=[],close_errors=[],completion_wait_attempted=False,cleanup_wait_attempted=False)


def assess(plan_raw,pin,files,out,err,observed):
    require(type(files) is dict and all(type(k) is str and type(v) is bytes for k,v in files.items()),'integrated byte cache required')
    raw=files['launch.json'];v,launch=check_plan(plan_raw,pin,raw);errors=[];trace=[];prefix=False;full=False;checked=None;ready=False;sync=False;part=False
    attempted=files.get('launch-attempt.json',b'')
    try:
        binding.same(parse(files['launcher-use.json']),use_record(raw,plan_raw),'integrated exclusive launcher use differs')
        require(files['integrated-plan.json']==plan_raw,'cached integrated plan differs')
        trace=[parse(line) for line in files.get('trace.jsonl',b'').splitlines()];expected=planned_trace(v)
        require(bool(trace) and len(trace)<=len(expected),'integrated trace length differs')
        binding.same(trace,expected[:len(trace)],'integrated publication trace prefix differs');prefix=True;full=trace==expected
        ready=dict(event='launch.ready',outcome='completed') in trace
        sync=dict(event='attempt.parent_directory_sync',outcome='completed') in trace
    except (ValueError,KeyError,TypeError,UnicodeError):errors.append('publication_trace')
    try:
        require(observed['prelaunch_error'] in (None,'prelaunch_io_error'),'integrated prelaunch error differs')
        binding.same(observed,observe(raw,plan_raw,attempted,observed['supervisor'],observed['prelaunch_error']),'integrated observation binding differs')
        o=observed['supervisor'];supervisor.check('normal',o,out,err)
        require(not o['spawned'] or prefix and ready and sync and observed['prelaunch_error'] is None,'child launched without synchronized attempt')
        if observed['prelaunch_error'] is not None:errors.append('prelaunch_sync_failure')
        materials={n.removeprefix('result/materials/'):x for n,x in files.items() if n.startswith('result/materials/')}
        old_observed=binding.observation(raw,attempted,o)
        receipt=files.get('result/receipt.json',b'')
        checked=binding.assess(raw,v['launch_sha256'],attempted,old_observed,out,err,materials,receipt)
        part=bool(receipt and receipt==files.get('result/receipt.json.part'))
        if not part:errors.append('receipt_staging')
        if not checked['fixture_completion']:errors.append('child_or_supervisor_failure')
    except (ValueError,KeyError,TypeError,UnicodeError,IndexError):errors.append('launch_or_result')
    no_fault=not any(v[k] for k in ('prelaunch_fail_before','child_cut_after','child_fail_before','parent_fault')) and v['worker_mode']=='normal'
    complete=bool(prefix and full and ready and sync and part and checked and checked['fixture_completion'] and no_fault and not errors)
    return dict(schema='A23-integrated-fixture-result-1',fixture_job_id=launch['fixture_job_id'],model_only=True,
        publication_prefix_valid=prefix,publication_trace_complete=full,attempt_sync_recorded=sync,launch_ready_recorded=ready,
        receipt_staging_matches=part,receipt_binding_valid=checked['receipt_binding_valid'] if checked else False,
        child_model_completion=checked['fixture_completion'] if checked else False,
        integrated_model_complete=complete,errors=errors,consumer_filesystem_calls=0,**FALSE)
