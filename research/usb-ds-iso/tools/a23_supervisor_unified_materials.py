"""One pure byte admission policy for unified offline supervisor observations."""
import a23_supervisor_materials as old
import a23_supervisor_cleanup_materials as cleanup
require,encode,parse,sha=old.require,old.encode,old.parse,old.sha
CLOSE_CASES=('stdout-close-error','stderr-close-error','both-close-error','selector-close-error','close-and-wait-error')
CASES=old.CASES+tuple(n for n in cleanup.CASES if n not in old.CASES)+CLOSE_CASES
GOOD={'normal','read-interrupted'}
LIMITS={'stdout':65536,'stderr':8192}
CLOSE_ORDER=['selector','stdout','stderr']
BOOLS=cleanup.BOOLS|{'spawn_error','completion_wait_attempted','cleanup_wait_attempted'}
KEYS=cleanup.KEYS|{'material_case','spawn_error','limit_exceeded','close_attempts','close_completed','close_errors','completion_wait_attempted','cleanup_wait_attempted'}
def material_case(n):return 'capture-worker-unfinished-return' if n=='driver-failure' else 'capture-worker-error' if n=='worker-failure' else 'normal'
def close_errors(n):return ['stdout','stderr'] if n=='both-close-error' else ['stdout'] if n in ('stdout-close-error','close-and-wait-error') else ['stderr'] if n=='stderr-close-error' else ['selector'] if n=='selector-close-error' else []


def check(name,o,stdout,stderr):
    require(type(o) is dict and set(o)==KEYS and o['schema']=='A23-supervisor-unified-observation-1' and o['case']==name and o['material_case']==material_case(name),'unified observation binding differs')
    require(all(type(o[k]) is bool for k in BOOLS),'unified boolean required')
    require(not o['leader_reaped_before_signal'] and not o['provenance_authenticated'] and not o['native_context_refreshed'] and o['clock_domain']=='supervisor_monotonic','unified authority/ownership differs')
    require(type(stdout) is bytes and type(stderr) is bytes and len(stdout)<=LIMITS['stdout']+1 and len(stderr)<=LIMITS['stderr']+1,'unified output cap differs')
    for k,v in (('stdout_bytes',len(stdout)),('stderr_bytes',len(stderr)),('launches',int(o['spawned'])),('retries',0)):require(type(o[k]) is int and o[k]==v,'unified count differs '+k)
    require(type(o['read_interrupts']) is int and 0<=o['read_interrupts']<=1,'unified EINTR count differs')
    require(o['returncode'] is None or type(o['returncode']) is int and -255<=o['returncode']<=255,'unified returncode differs')
    require(o['reaped']==(o['spawned'] and o['returncode'] is not None) and o['spawn_error']==(not o['spawned']),'unified spawn/reap relation differs')
    for p in ('group','fallback'):
        require(o[p+'_kill_outcome'] in ('none','sent','not_found','error') and o[p+'_kill_attempted']==(o[p+'_kill_outcome']!='none'),'unified signal attempt/outcome differs')
    require(o['fallback_kill_attempted']==(o['group_kill_outcome'] in ('not_found','error')),'unified fallback relation differs')
    require(not o['timed_out'] or o['group_kill_attempted'],'unified timeout without termination attempt')
    require(not o['wait_timed_out'] or o['wait_error'],'unified wait timeout relation differs')
    require(o['limit_exceeded'] in (None,'stdout','stderr'),'unified output label differs')
    require((o['limit_exceeded']=='stdout')==(len(stdout)>LIMITS['stdout']) and (o['limit_exceeded']=='stderr')==(len(stderr)>LIMITS['stderr']),'unified output count/limit differs')
    for k in ('close_attempts','close_completed','close_errors'):
        v=o[k];require(type(v) is list and all(type(x) is str for x in v) and v==[x for x in CLOSE_ORDER if x in v],'unified close labels/order differ')
    require(o['close_attempts']==(CLOSE_ORDER if o['spawned'] else []) and o['close_completed']==[x for x in o['close_attempts'] if x not in o['close_errors']] and set(o['close_errors'])<=set(o['close_attempts']),'unified close attempt/outcome differs')
    if not o['spawned']:
        require(not stdout and not stderr and not any(o[k] for k in ('timed_out','stdout_eof','stderr_eof','group_kill_attempted','completion_wait_attempted','cleanup_wait_attempted')),'unspawned job claims execution')


def assess(name,o,stdout,stderr,cache):
    require(name in CASES,'unknown unified case');check(name,o,stdout,stderr);reasons=[]
    for code,bad in (('spawn_failure',o['spawn_error']),('termination_attempt',o['group_kill_attempted']),('worker_timeout',o['timed_out']),('output_limit',o['limit_exceeded'] is not None),
        ('reader_error',o['reader_error']),('selector_error',o['selector_error']),('wait_error',o['wait_error']),
        ('worker_not_reaped',o['spawned'] and not o['reaped']),('worker_exit',o['reaped'] and o['returncode']!=0),
        ('group_signal_unconfirmed',o['group_kill_outcome'] in ('error','not_found')),('fallback_signal_unconfirmed',o['fallback_kill_outcome'] in ('error','not_found')),
        ('close_error',bool(o['close_errors'])),('incomplete_streams',o['spawned'] and not(o['stdout_eof'] and o['stderr_eof'])),
        ('stderr_not_empty',bool(stderr)),('missing_stdout',not stdout)):
        if bad:reasons.append(code)
    report=None
    if stdout and o['limit_exceeded']!='stdout':
        try:report=parse(stdout);require(type(report) is dict,'unified stdout object required')
        except (ValueError,TypeError,UnicodeError):reasons.append('malformed_stdout')
    checked=None;driver=None;healthy=None;source=material_case(name)
    try:
        require(type(cache) is dict and all(type(k) is str and type(v) is bytes for k,v in cache.items()),'unified byte materials required')
        expected=old.worker.inventory()|{'worker-materials.json'} if source!='normal' else old.worker.inventory()-{'worker-failure.json'}
        require(set(cache)==expected,'unified material inventory differs')
        row={k:parse(cache[v]) for k,v in (('result','result.json'),('receipt_status','receipt-status.json'),('facts','fault-facts.json'),('version','version-profile.json'))}
        if source=='normal':
            verified=old.d.validate(source,row,cache)
            for k,v in dict(complete=True,stopped=False,epochs_saved_complete=True,observation_complete=True,saved_epochs=2,iso_attempts=2,trigger_attempts=2,aborts=0,quiet_start_ticks=100,quiet_end_ticks=250000100,failure_reasons=[],journal_failed=False).items():require(encode(row['result'][k])==encode(v),'unified normal terminal state differs')
            old.d.sdk.sdk_lease(row['result']['lease']);checked=verified;driver=True;healthy=True
        else:
            row['worker_failure']=parse(cache['worker-failure.json']);checked=old.worker.validate(source,row,cache);driver=checked['driver_complete'];healthy=checked['worker_success']
        if report is not None:require(encode(report)==encode(old.stdout_report(name,source,cache)),'unified stdout binding differs')
    except (ValueError,KeyError,TypeError,UnicodeError,IndexError,StopIteration):reasons.append('stdout_binding' if checked is not None else 'invalid_materials')
    if checked is not None:
        if not healthy:reasons.append('worker_health')
        if not driver:reasons.append('driver_incomplete')
    return dict(passed=True,case=name,completion_admitted=not reasons,reasons=reasons,materials_valid=checked is not None,driver_complete=driver,
                worker_healthy=healthy,candidate_reaped=o['reaped'],close_errors=o['close_errors'],consumer_filesystem_calls=0,
                provenance_authenticated=False,process_tree_reclamation_verified=False,production_integrated=False)
