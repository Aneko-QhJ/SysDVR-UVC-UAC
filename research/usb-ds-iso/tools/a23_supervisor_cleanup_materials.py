"""Pure cached cleanup dispositions. No process or filesystem operations."""
import a23_supervisor_materials as old
require,encode,parse,sha=old.require,old.encode,old.parse,old.sha
CASES=('normal','leader-both-held','leader-stdout-held','leader-stderr-held','eof-worker-alive','stdout-eof-worker-alive','stderr-eof-worker-alive',
       'read-interrupted','read-error','selector-error','group-kill-error','group-kill-not-found','wait-error','wait-timeout','cleanup-multiple-errors')
LIMIT=65536
BOOLS={'spawned','reaped','timed_out','stdout_eof','stderr_eof','reader_error','selector_error','wait_error','wait_timed_out',
       'group_kill_attempted','fallback_kill_attempted','leader_reaped_before_signal','provenance_authenticated','native_context_refreshed'}
KEYS=BOOLS|{'schema','case','returncode','read_interrupts','group_kill_outcome','fallback_kill_outcome','stdout_bytes','stderr_bytes','launches','retries','clock_domain'}


def check(name,o,stdout,stderr):
    require(type(o) is dict and set(o)==KEYS and o['schema']=='A23-supervisor-cleanup-observation-1' and o['case']==name,'cleanup observation binding differs')
    require(all(type(o[k]) is bool for k in BOOLS),'cleanup boolean required')
    require(o['spawned'] and not o['leader_reaped_before_signal'] and not o['provenance_authenticated'] and not o['native_context_refreshed'] and o['clock_domain']=='supervisor_monotonic','cleanup ownership/authority differs')
    require(type(stdout) is bytes and type(stderr) is bytes and len(stdout)<=LIMIT+1 and len(stderr)<=LIMIT+1,'cleanup capture bytes differ')
    for key,value in (('stdout_bytes',len(stdout)),('stderr_bytes',len(stderr)),('launches',1),('retries',0)):
        require(type(o[key]) is int and o[key]==value,'cleanup count differs '+key)
    require(type(o['read_interrupts']) is int and 0<=o['read_interrupts']<=1,'cleanup interrupt count differs')
    require(o['returncode'] is None or type(o['returncode']) is int and -255<=o['returncode']<=255,'cleanup returncode differs')
    require(o['reaped']==(o['returncode'] is not None),'cleanup reap/exit relation differs')
    for prefix in ('group','fallback'):
        require(o[prefix+'_kill_outcome'] in ('none','sent','not_found','error'),'cleanup signal outcome differs')
        require(o[prefix+'_kill_attempted']==(o[prefix+'_kill_outcome']!='none'),'cleanup signal attempt/outcome differs')
    require(o['fallback_kill_attempted']==(o['group_kill_outcome'] in ('not_found','error')),'cleanup fallback relation differs')
    require(not o['timed_out'] or o['group_kill_attempted'],'cleanup timeout without termination attempt')
    require(not o['wait_timed_out'] or o['wait_error'],'cleanup wait timeout without error')


def assess(name,o,stdout,stderr,cache):
    require(name in CASES,'unknown cleanup case');check(name,o,stdout,stderr)
    reasons=[]
    for code,bad in (('worker_timeout',o['timed_out']),('reader_error',o['reader_error']),('selector_error',o['selector_error']),
                     ('wait_error',o['wait_error']),('worker_not_reaped',not o['reaped']),('worker_exit',o['reaped'] and o['returncode']!=0),
                     ('group_signal_unconfirmed',o['group_kill_outcome'] in ('error','not_found')),('fallback_signal_unconfirmed',o['fallback_kill_outcome'] in ('error','not_found')),
                     ('incomplete_streams',not(o['stdout_eof'] and o['stderr_eof'])),('stderr_not_empty',bool(stderr)),('missing_stdout',not stdout)):
        if bad:reasons.append(code)
    valid=False
    try:
        require(type(cache) is dict and all(type(k) is str and type(v) is bytes for k,v in cache.items()),'cleanup byte materials required')
        require(set(cache)==old.worker.inventory()-{'worker-failure.json'},'cleanup material inventory differs')
        row={k:parse(cache[v]) for k,v in (('result','result.json'),('receipt_status','receipt-status.json'),('facts','fault-facts.json'),('version','version-profile.json'))}
        old.d.validate('normal',row,cache)
        for key,value in dict(complete=True,stopped=False,epochs_saved_complete=True,observation_complete=True,saved_epochs=2,iso_attempts=2,trigger_attempts=2,aborts=0,quiet_start_ticks=100,quiet_end_ticks=250000100,failure_reasons=[],journal_failed=False).items():require(encode(row['result'][key])==encode(value),'cleanup driver terminal state differs')
        old.d.sdk.sdk_lease(row['result']['lease']);valid=True
        require(encode(parse(stdout))==encode(old.stdout_report(name,'normal',cache)),'cleanup stdout binding differs')
    except (ValueError,KeyError,TypeError,UnicodeError,IndexError,StopIteration):reasons.append('stdout_binding' if valid else 'invalid_materials')
    return dict(passed=True,case=name,completion_admitted=not reasons,reasons=reasons,materials_valid=valid,driver_complete=True if valid else None,
                candidate_reaped=o['reaped'],group_kill_outcome=o['group_kill_outcome'],fallback_kill_outcome=o['fallback_kill_outcome'],
                consumer_filesystem_calls=0,provenance_authenticated=False,process_tree_reclamation_verified=False,production_integrated=False)
