"""Pure byte admission of observed fixture exits and pinned model materials."""
import a23_concurrent_diagnostics as d
import a23_driver_worker_materials as worker
require,encode,parse,sha=d.require,d.encode,d.parse,d.sha
CASES=('normal','no-stdout','malformed-stdout','partial-stdout','empty-materials','missing-material','abnormal-exit','signal-exit',
       'timeout-before-output','timeout-after-output','oversize-stdout','oversize-stderr','stderr-output','wrong-case','wrong-digest',
       'driver-failure','worker-failure','spawn-error')
STDOUT_LIMIT=65536
STDERR_LIMIT=8192
OBS_KEYS={'schema','case','material_case','spawned','reaped','returncode','timed_out','limit_exceeded','group_kill_sent','stdout_eof','stderr_eof',
          'reader_error','spawn_error','cleanup_error','stdout_bytes','stderr_bytes','launches','retries','clock_domain','provenance_authenticated','native_context_refreshed'}


def material_case(name):
    require(name in CASES,'unknown supervisor fixture')
    return 'capture-worker-unfinished-return' if name=='driver-failure' else 'capture-worker-error' if name=='worker-failure' else 'normal'


def inventory(cache):return {n:dict(bytes=len(v),sha256=sha(v)) for n,v in sorted(cache.items())}


def stdout_report(name,source,cache):
    return dict(schema='A23-supervised-worker-report-1',case=name,material_case=source,inventory_sha256=sha(encode(inventory(cache))),
                result_sha256=sha(cache['result.json']),driver_complete=parse(cache['result.json'])['complete'],provenance_authenticated=False)


def observation_check(name,o,stdout,stderr):
    require(type(o) is dict and set(o)==OBS_KEYS and o['schema']=='A23-supervisor-observation-1' and o['case']==name and o['material_case']==material_case(name),'supervisor observation binding differs')
    for key in ('spawned','reaped','timed_out','group_kill_sent','stdout_eof','stderr_eof','reader_error','spawn_error','cleanup_error','provenance_authenticated','native_context_refreshed'):
        require(type(o[key]) is bool,'supervisor boolean required '+key)
    require(o['provenance_authenticated'] is False and o['native_context_refreshed'] is False and o['clock_domain']=='supervisor_monotonic','supervisor authority differs')
    require(type(stdout) is bytes and type(stderr) is bytes and len(stdout)<=STDOUT_LIMIT+1 and len(stderr)<=STDERR_LIMIT+1,'supervisor output bytes exceed capture cap')
    for key,value in (('stdout_bytes',len(stdout)),('stderr_bytes',len(stderr)),('launches',int(o['spawned'])),('retries',0)):
        require(type(o[key]) is int and o[key]==value,'supervisor count differs '+key)
    require(o['returncode'] is None or type(o['returncode']) is int and -255<=o['returncode']<=255,'supervisor exit code differs')
    require(o['reaped']==(o['spawned'] and o['returncode'] is not None),'supervisor reap/exit relation differs')
    require(o['spawn_error']==(not o['spawned']),'supervisor spawn relation differs')
    if not o['spawned']:require(not stdout and not stderr and not o['timed_out'] and not o['group_kill_sent'] and not o['stdout_eof'] and not o['stderr_eof'],'unspawned fixture claims execution')
    require(o['limit_exceeded'] in (None,'stdout','stderr'),'supervisor limit label differs')
    require((o['limit_exceeded']=='stdout')==(len(stdout)>STDOUT_LIMIT) and (o['limit_exceeded']=='stderr')==(len(stderr)>STDERR_LIMIT),'supervisor output limit relation differs')
    require(not o['timed_out'] or o['spawned'] and o['group_kill_sent'],'supervisor timeout cleanup differs')


def assess(name,o,stdout,stderr,cache):
    require(name in CASES,'unknown supervised case');observation_check(name,o,stdout,stderr)
    reasons=[]
    for code,bad in (('spawn_failure',o['spawn_error']),('worker_timeout',o['timed_out']),('output_limit',o['limit_exceeded'] is not None),
                     ('worker_not_reaped',o['spawned'] and not o['reaped']),('worker_exit',o['reaped'] and o['returncode']!=0),
                     ('stderr_not_empty',bool(stderr)),('incomplete_streams',o['spawned'] and not(o['stdout_eof'] and o['stderr_eof'])),
                     ('reader_error',o['reader_error']),('cleanup_error',o['cleanup_error']),('missing_stdout',not stdout)):
        if bad:reasons.append(code)
    report=None
    if stdout and o['limit_exceeded']!='stdout':
        try:
            report=parse(stdout)
            require(type(report) is dict,'worker stdout object required')
        except (ValueError,TypeError,UnicodeError):reasons.append('malformed_stdout')
    checked=None;source=material_case(name);driver=None;healthy=None
    try:
        require(type(cache) is dict and all(type(k) is str and type(v) is bytes for k,v in cache.items()),'supervisor materials must be bytes')
        expected=worker.inventory()|{'worker-materials.json'} if source!='normal' else worker.inventory()-{'worker-failure.json'}
        require(set(cache)==expected,'supervisor material inventory differs')
        row={key:parse(cache[file]) for key,file in (('result','result.json'),('receipt_status','receipt-status.json'),('facts','fault-facts.json'),('version','version-profile.json'))}
        if source=='normal':
            verified=d.validate(source,row,cache);state=row['result'];driver=state['complete']
            for key,value in dict(complete=True,stopped=False,epochs_saved_complete=True,observation_complete=True,saved_epochs=2,iso_attempts=2,trigger_attempts=2,aborts=0,quiet_start_ticks=100,quiet_end_ticks=250000100,failure_reasons=[],journal_failed=False).items():require(encode(state[key])==encode(value),'normal driver terminal state differs')
            d.sdk.sdk_lease(state['lease']);checked=verified;healthy=True
        else:
            row['worker_failure']=parse(cache['worker-failure.json']);checked=worker.validate(source,row,cache);driver=checked['driver_complete'];healthy=checked['worker_success']
        if report is not None:require(encode(report)==encode(stdout_report(name,source,cache)),'worker stdout binding differs')
    except (ValueError,KeyError,TypeError,IndexError,UnicodeError,StopIteration) as exc:
        if checked is not None:reasons.append('stdout_binding')
        else:reasons.append('invalid_materials')
    if checked is not None:
        if healthy is False:reasons.append('worker_health')
        if driver is False:reasons.append('driver_incomplete')
    process_healthy=o['spawned'] and o['reaped'] and o['returncode']==0 and not any(o[k] for k in ('timed_out','reader_error','cleanup_error')) and o['limit_exceeded'] is None and o['stdout_eof'] and o['stderr_eof'] and not stderr
    return dict(passed=True,case=name,material_case=source,process_healthy=process_healthy,completion_admitted=not reasons,driver_complete=driver,worker_healthy=healthy,
                materials_valid=checked is not None,reasons=reasons,consumer_filesystem_calls=0,provenance_authenticated=False,production_integrated=False)
