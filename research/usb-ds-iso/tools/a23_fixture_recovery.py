"""Pure interpretation of interrupted fixture publication; never authorizes reuse."""
import a23_fixture_job_binding as binding
from a23_fixture_publication import EVENTS,FAILURES
require,encode,parse,sha=binding.require,binding.encode,binding.parse,binding.sha
FALSE={**binding.FALSE,'restart_allowed':False,'automatic_repair_allowed':False,
    'global_replay_prevention_verified':False,'crash_durability_verified':False,
    'power_loss_recovery_verified':False,'atomic_exec_input_binding_authenticated':False}


def plan(launch_raw,module_sha,cut=None,fail=None):
    return dict(schema='A23-fixture-publication-plan-1',launch_sha256=sha(launch_raw),
        publication_module_sha256=module_sha,cut_after=cut,fail_before=fail,model_only=True,
        production_execution_authorized=False)


def check_plan(raw,pin,launch_raw):
    require(type(raw) is bytes and binding.digest(pin) and sha(raw)==pin,'external publication plan pin differs')
    v=parse(raw)
    require(type(v) is dict and binding.digest(v.get('publication_module_sha256')),'publication module digest differs')
    require(v.get('cut_after') in (None,*EVENTS) and v.get('fail_before') in (None,*FAILURES) and
        not(v.get('cut_after') and v.get('fail_before')),'publication fault declaration differs')
    binding.same(v,plan(launch_raw,v['publication_module_sha256'],v['cut_after'],v['fail_before']),'publication plan differs')
    launch=binding.check_launch(launch_raw,v['launch_sha256'])
    require(launch['fixture_mode']=='normal','publication fixture launch mode differs')
    return v,launch


def expected_trace(v):
    rows=[]
    for event in EVENTS:
        if v['fail_before']==event:return rows+[dict(event=event,outcome='injected_error')]
        rows.append(dict(event=event,outcome='completed'))
        if v['cut_after']==event:return rows
    return rows


def observation(returncode,out,err):
    return dict(schema='A23-publication-fixture-exit-1',spawned=True,reaped=True,returncode=returncode,
        stdout_bytes=len(out),stderr_bytes=len(err),timed_out=False,provenance_authenticated=False)


def assess(plan_raw,pin,files,out,err,observed):
    require(type(files) is dict and all(type(k) is str and type(v) is bytes for k,v in files.items()),'publication byte cache required')
    launch_raw=files['launch.json'];v,launch=check_plan(plan_raw,pin,launch_raw)
    errors=[];trace=[];trace_ok=False;attempt_ok=False;receipt_ok=False;materials_ok=False;process_ok=False
    try:
        require(files['publication-plan.json']==plan_raw,'cached publication plan bytes differ')
        trace=[parse(line) for line in files.get('trace.jsonl',b'').splitlines()]
        binding.same(trace,expected_trace(v),'publication trace prefix differs');trace_ok=True
    except (ValueError,TypeError,KeyError,UnicodeError):errors.append('trace')
    try:
        require(type(out) is bytes and type(err) is bytes and len(out)<=65536 and len(err)<=8192,'publication output bound differs')
        require(type(observed) is dict and type(observed.get('returncode')) is int,'publication returncode type differs')
        binding.same(observed,observation(observed['returncode'],out,err),'publication observation differs')
        process_ok=observed['returncode']==0 and not err
    except (ValueError,TypeError,KeyError):errors.append('observation')
    try:
        binding.same(parse(files['launch-attempt.json']),binding.attempt(launch_raw),'publication attempt differs');attempt_ok=True
    except (ValueError,TypeError,KeyError,UnicodeError):errors.append('attempt')
    materials={n.removeprefix('result/materials/'):raw for n,raw in files.items() if n.startswith('result/materials/')}
    try:
        binding.same(binding.inventory(materials),launch['seed_files'],'publication material inventory differs')
        # Apply the pre-existing semantic cache validation, separately from IO.
        s=binding.supervisor;cached=encode(s.old.stdout_report('normal','normal',materials))
        # This synthetic healthy observation only validates historical SDK data.
        # It never stands in for the actual publication child exit above.
        o=dict(schema='A23-supervisor-unified-observation-1',case='normal',material_case='normal',spawned=True,spawn_error=False,reaped=True,returncode=0,
            timed_out=False,stdout_eof=True,stderr_eof=True,reader_error=False,selector_error=False,read_interrupts=0,wait_error=False,wait_timed_out=False,
            group_kill_attempted=False,group_kill_outcome='none',fallback_kill_attempted=False,fallback_kill_outcome='none',limit_exceeded=None,
            stdout_bytes=len(cached),stderr_bytes=0,launches=1,retries=0,leader_reaped_before_signal=False,provenance_authenticated=False,native_context_refreshed=False,
            clock_domain='supervisor_monotonic',close_attempts=s.CLOSE_ORDER.copy(),close_completed=s.CLOSE_ORDER.copy(),close_errors=[],completion_wait_attempted=True,cleanup_wait_attempted=False)
        require(s.assess('normal',o,cached,b'',materials)['completion_admitted'],'cached historical SDK data invalid');materials_ok=True
    except (ValueError,KeyError,TypeError,UnicodeError,IndexError):errors.append('materials')
    try:
        receipt=files['result/receipt.json'];part=files['result/receipt.json.part'];attempt=files['launch-attempt.json']
        require(receipt==part,'published receipt/staging bytes differ')
        binding.same(parse(receipt),binding.receipt(launch_raw,attempt,out,materials),'published receipt binding differs')
        binding.same(parse(out),binding.report(launch_raw,attempt,materials),'publication stdout binding differs');receipt_ok=True
    except (ValueError,TypeError,KeyError,UnicodeError):errors.append('receipt_or_stdout')
    complete=bool(trace_ok and process_ok and attempt_ok and materials_ok and receipt_ok and not v['cut_after'] and not v['fail_before'] and not errors)
    return dict(schema='A23-fixture-publication-recovery-1',model_only=True,fixture_job_id=launch['fixture_job_id'],
        trace_prefix_valid=trace_ok,process_healthy=process_ok,attempt_present='launch-attempt.json' in files,
        attempt_valid=attempt_ok,receipt_visible='result/receipt.json' in files,receipt_binding_valid=receipt_ok,
        cached_materials_valid=materials_ok,payload_barrier_recorded=dict(event='payload.begin',outcome='completed') in trace,
        publication_model_complete=complete,errors=errors,consumer_filesystem_calls=0,**FALSE)
