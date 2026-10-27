"""Read-only declared cross-model job/SDK correspondence; never a permit."""
from pathlib import PurePosixPath
import uuid
import a23_supervisor_unified_materials as supervisor
import a23_shared_sequence32 as shared
from a23_execution_context import validate as context_validate
require,encode,parse,sha=supervisor.require,supervisor.encode,supervisor.parse,supervisor.sha
JOB_FILES={'scope.json','history.json','namespace.json','job.json','authorization.json','reservation.json','issue.json','issue-commit',
    'consumed.json','consume-attempt','consume-commit','native-context.json','native-process-claim.json','native-sdk-claim.json',
    'native-process-attempt','native-selection-attempt','entry-binding.json','native-permit.json'}
FALSE={k:False for k in ('same_physical_run_verified','process_origin_authenticated','job_launch_binding_authenticated','actual_sdk_runtime_verified',
    'clock_domain_mapping_verified','callback_drain_verified','device_trace_verified','production_execution_authorized','acquisition_permitted',
    'formal_issuance_available','sequences_allocated','allow_retry','cleanup_authorized','hardware_entry_enabled')}
RELATION='declared_cross_model_correspondence'
def inventory(c):return supervisor.old.inventory(c)
def equal(a,b,message):require(encode(a)==encode(b),message)
def object_at(c,n):return parse(c[n])


def job_view(c):
    require(type(c) is dict and set(c)==JOB_FILES and all(type(v) is bytes for v in c.values()),'job byte inventory differs')
    scope=shared.scope(object_at(c,'scope.json'));require(all(scope[k] is False for k in shared.SCOPE_FLAGS),'model scope grants authority')
    ns=object_at(c,'namespace.json');root=PurePosixPath(ns['root']);require(type(ns['root']) is str and root.is_absolute() and root.is_relative_to('/private/tmp') and str(root)==ns['root'] and '..' not in root.parts,'model job logical root differs')
    require(type(ns['id']) is str and str(uuid.UUID(ns['id']))==ns['id'],'namespace UUID differs')
    sh=sha(c['scope.json']);hh=sha(c['history.json']);shared.f.history(object_at(c,'history.json'))
    equal(ns,dict(schema='A23-shared32-namespace-1',id=ns['id'],root=str(root),scope_sha256=sh,history_sha256=hh,simulation=True),'namespace model commitment differs')
    require(scope['history_sha256']==hh,'history digest differs')
    job=object_at(c,'job.json');jid=shared.job_id(job['job_id']);path=str(root/'jobs'/jid)
    equal(job,dict(schema='A23-shared32-job-1',job_id=jid,job_path=path,namespace_id=ns['id'],scope_sha256=sh),'job commitment differs')
    auth=dict(schema='A23-shared32-authorization-1',job_id=jid,scope_sha256=sh,maximum_invocations=1,simulation=True,hardware_test_authorized=False)
    equal(object_at(c,'authorization.json'),auth,'model authorization differs')
    reservation=dict(schema='A23-shared32-reservation-1',namespace_id=ns['id'],job_id=jid,job_path=path,first=81,last=112,count=32,
        scope_sha256=sh,job_sha256=sha(c['job.json']),authorization_sha256=sha(c['authorization.json']),simulation=True)
    equal(object_at(c,'reservation.json'),reservation,'model reservation commitment differs')
    issue=dict(schema='A23-shared32-issue-1',namespace_id=ns['id'],job_id=jid,job_path=path,scope_sha256=sh,
        reservation_sha256=sha(c['reservation.json']),authorization_sha256=sha(c['authorization.json']),remaining=1,simulation=True)
    equal(object_at(c,'issue.json'),issue,'model issue commitment differs')
    consumed=dict(schema='A23-shared32-consumed-1',namespace_id=ns['id'],job_id=jid,job_path=path,scope_sha256=sh,
        reservation_sha256=sha(c['reservation.json']),issue_sha256=sha(c['issue.json']),authorization_sha256=sha(c['authorization.json']),remaining=0,receiver_launched=False,simulation=True)
    equal(object_at(c,'consumed.json'),consumed,'model consumption commitment differs')
    for n,v in (('issue-commit',b'issue durable\n'),('consume-attempt',b'one attempt\n'),('consume-commit',b'consumption durable\n'),('native-process-attempt',b'one attempt\n'),('native-selection-attempt',b'one attempt\n')):require(c[n]==v,'model marker differs '+n)
    binding=dict(schema='A23-two-epoch-entry-binding-1',build_manifest_sha256=scope['build_manifest_sha256'],receiver_sha256=scope['receiver_sha256'],authorization_receipt_sha256=sha(c['consumed.json']),first_sequence=81,last_sequence=112)
    equal(object_at(c,'entry-binding.json'),binding,'entry binding differs')
    context=object_at(c,'native-context.json');context_validate(context,scope['receiver_sha256'])
    process=dict(schema='A23-shared32-native-process-1',job_id=jid,consumed_sha256=sha(c['consumed.json']),context_sha256=sha(c['native-context.json']),pid=context['pid'],scope_sha256=sh,simulation=True,hardware_verified=False)
    equal(object_at(c,'native-process-claim.json'),process,'native model process commitment differs')
    selected=object_at(c,'native-sdk-claim.json');identity=selected['identity']
    require(type(identity) is dict and set(identity)=={'device_id','interface_id','speed'} and all(type(identity[k]) is int and identity[k]>0 for k in identity) and identity['device_id']!=identity['interface_id'] and identity['speed']==3,'model selection identity differs')
    equal(selected,dict(schema='A23-shared32-native-selection-1',job_id=jid,process_sha256=sha(c['native-process-claim.json']),context_sha256=sha(c['native-context.json']),pid=context['pid'],identity=identity,simulation=True,hardware_verified=False),'native model selection commitment differs')
    permit=dict(schema='A23-shared32-native-permit-result-1',simulation=True,process_attempted=True,process_claimed=True,selection_attempted=True,selection_claimed=True,stale=False,hardware_verified=False,hardware_entry_enabled=False,process_origin_authenticated=False)
    equal(object_at(c,'native-permit.json'),permit,'native model permit declaration differs')
    return dict(job_id=jid,namespace_id=ns['id'],entry_binding=binding,identity=identity,consumed_sha256=sha(c['consumed.json']))


def anchor(name,job,o,out,err,cache,job_review,supervisor_review):
    return dict(schema='A23-supervisor-job-anchor-1',relation_kind=RELATION,supervisor_case=name,job_review_sha256=job_review,
        supervisor_review_sha256=supervisor_review,job_files=inventory(job),observation_sha256=sha(encode(o)),stdout_sha256=sha(out),stderr_sha256=sha(err),material_files=inventory(cache),model_only=True,production_execution_authorized=False)


def declaration(job,o,cache):
    receipt=object_at(cache,'sdk-receipt/receipt.json')
    return dict(schema='A23-supervisor-job-correspondence-1',relation_kind=RELATION,job_id=object_at(job,'job.json')['job_id'],namespace_id=object_at(job,'namespace.json')['id'],
        entry_binding=object_at(job,'entry-binding.json'),consumed_sha256=sha(job['consumed.json']),sdk_binding=receipt['binding'],
        sdk_receipt_sha256=sha(cache['sdk-receipt/receipt.json']),sdk_snapshot_sha256=sha(cache['sdk-receipt/snapshot.json']),supervisor_case=o['case'],observation_sha256=sha(encode(o)))


def assess(expected_raw,expected_sha,job,o,out,err,cache,link_raw):
    require(type(expected_raw) is bytes and type(expected_sha) is str and len(expected_sha)==64 and sha(expected_raw)==expected_sha,'external job anchor pin differs')
    expected=parse(expected_raw);errors=[];view=None;checked=None;linked=False
    try:
        require(type(expected) is dict and expected.get('relation_kind')==RELATION and expected.get('model_only') is True and expected.get('production_execution_authorized') is False,'job anchor authority differs')
        name=expected['supervisor_case'];actual=anchor(name,job,o,out,err,cache,expected['job_review_sha256'],expected['supervisor_review_sha256'])
        for key in ('job_review_sha256','supervisor_review_sha256'):require(type(expected[key]) is str and len(expected[key])==64 and all(x in '0123456789abcdef' for x in expected[key]),'source review digest differs')
        equal(expected,actual,'job/supervisor anchored bytes differ')
    except (ValueError,KeyError,TypeError):errors.append('anchor');name=None
    if name is not None:
        try:view=job_view(job)
        except (ValueError,KeyError,TypeError,UnicodeError,IndexError,AttributeError):errors.append('job')
        try:checked=supervisor.assess(name,o,out,err,cache)
        except (ValueError,KeyError,TypeError,UnicodeError,IndexError):errors.append('supervisor')
        if checked is not None and not checked['materials_valid']:errors.append('supervisor_materials')
        if view is not None and checked is not None and checked['materials_valid']:
            try:
                receipt=object_at(cache,'sdk-receipt/receipt.json');snapshot=object_at(cache,'sdk-receipt/snapshot.json');state=object_at(cache,'result.json');binding=receipt['binding']
                require(binding['session_id']==snapshot['session_id']==state['session_id'] and binding['first_sequence']==view['entry_binding']['first_sequence'] and view['entry_binding']['last_sequence']==binding['first_sequence']+31,'SDK session/range correspondence differs')
                equal(binding['identity'],dict(device_id=view['identity']['device_id'],interface_id=view['identity']['interface_id'],parent_device_id=view['identity']['device_id']),'SDK/job declared identity differs')
                for i in range(2):equal(object_at(cache,'epoch-'+str(i)+'/metadata.json')['binding'],binding,'epoch/receipt SDK binding differs')
                require(receipt['schema']=='A23-two-epoch-sdk-receipt-1' and all(receipt[k] is False for k in ('hardware_entry_enabled','hardware_verified','physical_run_authenticated')),'SDK receipt grants authority')
                equal(parse(link_raw),declaration(job,o,cache),'declared job/SDK correspondence differs');linked=True
            except (ValueError,KeyError,TypeError,UnicodeError,IndexError):errors.append('correspondence')
    return dict(schema='A23-supervisor-job-readonly-result-1',relation_kind=RELATION,model_only=True,job_scope_consistent=view is not None,
        supervisor_checked=checked is not None,correspondence_valid=linked,supervisor_model_completion=checked['completion_admitted'] if checked else False,
        linked_model_completion=bool(linked and checked['completion_admitted']),errors=errors,consumed_remaining=0 if view else None,
        job_id=view['job_id'] if view else None,supervisor_case=name,consumer_filesystem_calls=0,**FALSE)
