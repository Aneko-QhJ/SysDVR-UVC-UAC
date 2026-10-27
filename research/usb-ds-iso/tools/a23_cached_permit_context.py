"""Cached simulated issuance, native permit and actual/injected context links.

No ledger writer, process query, binary execution or hardware capability is
exposed. Matching declarations do not authenticate a live process or permit.
"""
import copy
import uuid
from pathlib import PurePosixPath
import a23_cached_session_links as session
import a23_shared_sequence32 as shared
import a23_supervisor_archive as supervisor
from a23_execution_context import validate as context_validate

prior = session.prior
view, ar, a, f = session.view, session.ar, session.a, session.f
HOST, INPUTS = prior.HOST, prior.INPUTS
ENV = 'journal/envelope/'
FALSE = dict(session.FALSE)


def obj(raw, name):
    if name == HOST+'context.json' or name.endswith('/native-context.json'):
        value=raw[name]
        f.require(type(value) is bytes and len(value)<=16384,'context JSON byte limit/type differs')
        row=f.parse(value);canonical=f.encode(row);escaped=canonical.replace(b'/',b'\\/')
        f.require(type(row) is dict and value in (canonical,canonical[:-1],escaped,escaped[:-1]),
                  'context JSON encoding differs')
        return row
    return prior.native_metadata(raw[name])
def equal(left, right, message): session.equal(left,right,message)


def shared_records(raw, receiver):
    prefix = INPUTS+'namespace/'
    scope = shared.scope(obj(raw,prefix+'scope.json'))
    f.require(all(scope[k] is False for k in shared.SCOPE_FLAGS), 'model scope grants formal capability')
    ns = obj(raw,prefix+'namespace.json')
    f.require(set(ns) == {'schema','id','root','scope_sha256','history_sha256','simulation'} and
              ns['schema'] == 'A23-shared32-namespace-1' and ns['simulation'] is True and
              type(ns['id']) is str and str(uuid.UUID(ns['id'])) == ns['id'], 'namespace declaration differs')
    root = session.build.logical_path(ns['root'])
    f.require(root.is_relative_to('/private/tmp') and root != PurePosixPath('/private/tmp'), 'model namespace logical root differs')
    info = obj(raw,INPUTS+'case-info.json');job = shared.job_id(info['job_id'])
    job_prefix = prefix+'jobs/'+job+'/'
    logical_job = str(root/'jobs'/job)
    history = f.parse(raw[prefix+'history.json']);used = f.history(history)
    sh = f.sha(raw[prefix+'scope.json']);hh = f.sha(raw[prefix+'history.json'])
    f.require(ns['scope_sha256'] == sh and ns['history_sha256'] == scope['history_sha256'] == hh and
              f.encode(history) == raw[prefix+'history.json'], 'namespace scope/history digest differs')
    expected_files = ({prefix+n for n in ('scope.json','history.json','namespace.json','.lock','block-00081.json')} |
                      {job_prefix+n for n in shared.JOB_FILES})
    f.require({n for n in raw if n.startswith(prefix)} == expected_files and raw[prefix+'.lock'] == b'',
              'shared job file coverage differs')
    f.require([(r['first'],r['last']) for r in history] == [(49,64),(65,80)], 'reviewed history intervals differ')
    for row in history:
        name='history/ledger/block-%05d.json'%row['first']
        reservation=prior.native_metadata(receiver.read_small(name))
        record=reservation.get('record');session.build.logical_path(record)
        f.require(reservation.get('simulation') is False and
                  session.number(reservation.get('first'),row['first'],row['first']) and
                  session.number(reservation.get('last'),row['last'],row['last']) and
                  row['reservation_sha256'] == session.build.digest_file(receiver,name) and
                  row['record_sha256'] == session.build.digest_file(receiver,'history/records/'+PurePosixPath(record).name),
                  'cached history/member link differs')
    expected = dict(schema='A23-shared32-job-1',job_id=job,job_path=logical_job,namespace_id=ns['id'],scope_sha256=sh)
    equal(obj(raw,job_prefix+'job.json'),expected,'job commitment differs')
    authorization = dict(schema='A23-shared32-authorization-1',job_id=job,scope_sha256=sh,maximum_invocations=1,
                         simulation=True,hardware_test_authorized=False)
    equal(obj(raw,job_prefix+'authorization.json'),authorization,'model authorization differs')
    burn = dict(schema='A23-shared32-reservation-1',namespace_id=ns['id'],job_id=job,job_path=logical_job,
                first=81,last=112,count=32,scope_sha256=sh,job_sha256=f.sha(raw[job_prefix+'job.json']),
                authorization_sha256=f.sha(raw[job_prefix+'authorization.json']),simulation=True)
    equal(obj(raw,prefix+'block-00081.json'),burn,'model reservation differs')
    f.require(not used & set(range(81,113)), 'model block overlaps declared history')
    issue = dict(schema='A23-shared32-issue-1',namespace_id=ns['id'],job_id=job,job_path=logical_job,scope_sha256=sh,
                 reservation_sha256=f.sha(raw[prefix+'block-00081.json']),authorization_sha256=burn['authorization_sha256'],
                 remaining=1,simulation=True)
    equal(obj(raw,job_prefix+'issue.json'),issue,'model issue differs')
    consumed = dict(schema='A23-shared32-consumed-1',namespace_id=ns['id'],job_id=job,job_path=logical_job,
                    scope_sha256=sh,reservation_sha256=issue['reservation_sha256'],issue_sha256=f.sha(raw[job_prefix+'issue.json']),
                    authorization_sha256=burn['authorization_sha256'],remaining=0,receiver_launched=False,simulation=True)
    equal(obj(raw,job_prefix+'consumed.json'),consumed,'model consumption differs')
    for name,expected in (('issue-commit',b'issue durable\n'),('consume-attempt',b'one attempt\n'),('consume-commit',b'consumption durable\n')):
        f.require(raw[job_prefix+name] == expected, 'model durable marker differs: '+name)
    return dict(scope=scope,scope_sha256=sh,job=job,job_prefix=job_prefix,logical_job=logical_job,
                consumed_sha256=f.sha(raw[job_prefix+'consumed.json']))


def native_links(raw, records):
    p = records['job_prefix'];scope = records['scope']
    for name in ('native-process-attempt','native-selection-attempt'):
        f.require(raw[p+name] == b'one attempt\n', 'native attempt marker differs')
    context = obj(raw,p+'native-context.json')
    context_validate(context,scope['receiver_sha256'])
    host_context = obj(raw,HOST+'context.json')
    equal(context,host_context,'native/entry context differs')
    expected = dict(schema='A23-shared32-native-process-1',job_id=records['job'],consumed_sha256=records['consumed_sha256'],
                    context_sha256=f.sha(raw[p+'native-context.json']),pid=context['pid'],scope_sha256=records['scope_sha256'],
                    simulation=True,hardware_verified=False)
    equal(obj(raw,p+'native-process-claim.json'),expected,'native process claim differs')
    selected = obj(raw,p+'native-sdk-claim.json');identity = selected.get('identity')
    f.require(type(identity) is dict and set(identity) == {'device_id','interface_id','speed'} and
              session.number(identity['device_id'],1) and session.number(identity['interface_id'],1) and
              identity['device_id'] != identity['interface_id'] and session.number(identity['speed'],3,3), 'native SDK identity differs')
    expected = dict(schema='A23-shared32-native-selection-1',job_id=records['job'],
                    process_sha256=f.sha(raw[p+'native-process-claim.json']),context_sha256=f.sha(raw[p+'native-context.json']),
                    pid=context['pid'],identity=identity,simulation=True,hardware_verified=False)
    equal(selected,expected,'native selection claim differs')
    entry = obj(raw,HOST+'entry-current.json');binding = entry['binding']
    f.require(binding['authorization_receipt_sha256'] == records['consumed_sha256'], 'entry consumption receipt differs')
    for name in ('process-claim.json','sdk-claim.json'):
        claim = obj(raw,HOST+name)
        f.require(session.number(claim.get('pid'),context['pid'],context['pid']), 'entry/native PID differs')
        equal(claim['binding'],binding,'entry/native build binding differs')
    claim = obj(raw,HOST+'sdk-claim.json')
    f.require(claim['device_id'] == identity['device_id'] and claim['interface_id'] == identity['interface_id'], 'native/entry selected identity differs')
    report = obj(raw,INPUTS+'report.json')
    f.require(report.get('schema') == 'A23-verified-scope-fixture-1', 'native report schema differs')
    native = report.get('native')
    f.require(type(native) is dict and native.get('schema') == 'A23-shared32-native-fixture-1' and
              all(native.get(k) is True for k in ('init_accepted','process_returned','selection_returned','replay_blocked')), 'native permit declaration incomplete')
    permit = dict(schema='A23-shared32-native-permit-result-1',simulation=True,process_attempted=True,process_claimed=True,
                  selection_attempted=True,selection_claimed=True,stale=False,hardware_verified=False,
                  hardware_entry_enabled=False,process_origin_authenticated=False)
    equal(native.get('permit'),permit,'native permit result differs')
    for row in (native,report):
        f.require(all(session.number(row.get(k),0,0) for k in ('real_sdk_objects','usb_requests','sd_accesses')), 'model report grants hardware count')
    equal(report.get('execution_context'),context,'reported execution context differs')
    equal(report.get('entry'),entry,'reported entry checkpoint differs')
    f.require(raw[ENV+'final/report.json'] == raw[INPUTS+'report.json'], 'raw report copy differs')
    return dict(context=context,report=report,model_pid=context['pid'])


def supervision_links(raw, records, native):
    p = ENV+'supervision/'
    handoff = obj(raw,p+'handoff-original.json');observed = obj(raw,p+'result.json')
    f.require(set(handoff) == {'schema','nonce','parent','build','environment_sha256','model_only','inherited_environment',
              'execution_budget_ns','hello_budget_ns'} and handoff['schema'] == 'A23-broker-supervision-handoff-1' and
              handoff['model_only'] is True and handoff['inherited_environment'] is False and
              f.hex64(handoff['nonce']) and f.hex64(handoff['environment_sha256']), 'supervision handoff differs')
    f.require(raw[p+'handoff.json'] == raw[p+'handoff-original.json'] and
              raw[p+'OWNER'] == raw[p+'OWNER-original'] == (handoff['nonce']+'\n').encode() and
              raw[p+'launch-attempt'] == b'one model launch attempt\n', 'supervision owner/handoff changed')
    f.require(type(handoff['parent']) is dict and set(handoff['parent']) == {'pid','ppid','uid','euid','gid','egid'} and
              all(session.number(v) for v in handoff['parent'].values()) and handoff['parent']['pid']>0, 'parent identity type differs')
    f.require(len(raw[p+'stdout.bin'])<=4096 and len(raw[p+'stderr.bin'])<=256 and
              raw[p+'stdout.bin'].endswith(b'\n') and len(raw[p+'stdout.bin'].splitlines()) == 1, 'hello stream differs')
    hello = obj(raw,p+'stdout.bin')
    f.require(session.number(observed.get('child_pid'),native['model_pid'],native['model_pid']) and
              type(observed.get('binary_path')) is str, 'supervised model PID/path differs')
    actual_policy = supervisor.link(hello,handoff,observed['child_pid'],observed['binary_path'])
    f.require(observed.get('schema') == 'A23-broker-supervision-result-1' and
              all(observed.get(k) is False for k in supervisor.FALSE), 'supervision authority differs')
    for key in ('producer_exited','hello_consistent','supervision_complete','stdout_eof','stderr_eof'):
        f.require(observed.get(key) is True, 'supervision declaration incomplete: '+key)
    for key in ('timed_out','hello_timed_out','truncated'):f.require(observed.get(key) is False,'supervision failure: '+key)
    f.require(observed.get('child_execution_policy_pass') is actual_policy and observed.get('failure_reasons') == [] and
              session.number(observed.get('returncode'),0,0), 'supervision saved verdict differs')
    # These are consistency checks within the supervisor's declared ns domain,
    # never comparisons with SDK/owner ticks or live process observations.
    f.require(session.number(handoff['execution_budget_ns'],10000000,30000000000) and
              session.number(handoff['hello_budget_ns'],min(5000000000,handoff['execution_budget_ns']),min(5000000000,handoff['execution_budget_ns'])), 'supervisor declared budget differs')
    for key in ('launch_begin_ns','deadline_ns','hello_deadline_ns','hello_observed_ns','settled_ns'):
        f.require(session.number(observed.get(key),1), 'supervisor ns type differs')
    f.require(observed['deadline_ns']-observed['launch_begin_ns'] == handoff['execution_budget_ns'] and
              observed['hello_deadline_ns']-observed['launch_begin_ns'] == handoff['hello_budget_ns'] and
              observed['launch_begin_ns'] <= observed['hello_observed_ns'] < observed['hello_deadline_ns'] and
              observed['hello_observed_ns'] <= observed['settled_ns'] < observed['deadline_ns'], 'supervisor declared deadline records differ')
    plan = obj(raw,ENV+'plan.json');report = native['report'];actual = hello['context']
    f.require(type(plan.get('inject_policy')) is bool and plan.get('job_id') == records['job'] and
              report.get('execution_context_injected') is plan['inject_policy'], 'policy injection declaration differs')
    expected = copy.deepcopy(actual)
    if plan['inject_policy']:expected.update(sandbox_query_available=True,sandbox_query_result=0,sandbox_query_errno=0)
    equal(report.get('actual_context'),actual,'reported actual context differs')
    equal(native['context'],expected,'actual/injected context transformation differs')
    control = obj(raw,ENV+'control.json')
    f.require(control.get('schema') == 'A23-broker-model-command-1' and control.get('action') == 'execute_model' and
              control.get('nonce') == handoff['nonce'] and control.get('job_path') == records['logical_job'], 'model command link differs')
    equal(control.get('actual_context'),actual,'command actual context differs')
    f.require(report.get('command_valid') is True and report.get('model_execute_admitted') is True, 'reported model command rejected')
    for name in ('source-marker',ENV+'envelope.json'):
        f.require(session.number(obj(raw,name).get('child_pid'),native['model_pid'],native['model_pid']), 'collection model PID differs')
    return dict(actual_context_policy_accepted=actual_policy,injected_policy_declared=plan['inject_policy'],
                actual_sandbox_query_result=actual['sandbox_query_result'],
                supplied_execution_sandbox_query_result=native['context']['sandbox_query_result'])


def consume(receiver,supervisor_build,journal,link_bytes,link_digest):
    base = session.consume(receiver,supervisor_build,journal,link_bytes,link_digest)
    result = dict(schema='A23-cached-permit-context-1',classification='inconsistent_permit_context_subset',
                  errors=[],reasons={},session_subset_consistent=not base['errors'],shared_model_records_consistent=False,
                  native_claim_links_consistent=False,supervision_context_links_consistent=False,
                  context_observation=None,model_sequences_declared=None, **FALSE)
    if base['errors']:
        result['errors']=['session_subset'];result['reasons']['session_subset']=','.join(base['errors']);return result
    raw = prior.verify_scope(*journal)
    def check(name,action):
        try:return action()
        except (ValueError,KeyError,TypeError,UnicodeError,RecursionError,IndexError) as exc:
            result['errors'].append(name);result['reasons'][name]=str(exc);return None
    receiver_bytes,_ = session.build.grouped.consume(*receiver)
    records = check('shared_records',lambda:shared_records(raw,receiver_bytes))
    if records is not None:
        result['shared_model_records_consistent']=True
        native = check('native_claims',lambda:native_links(raw,records))
        if native is not None:
            result['native_claim_links_consistent']=True
            joined = check('supervision_context',lambda:supervision_links(raw,records,native))
            if joined is not None:
                result['supervision_context_links_consistent']=True;result['context_observation']=joined
                result['model_sequences_declared']=32
    if not result['errors']:result['classification']='consistent_cached_simulated_permit_context_subset'
    return result
