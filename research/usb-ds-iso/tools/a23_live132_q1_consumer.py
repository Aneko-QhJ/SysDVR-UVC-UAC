"""Q1 dual-mode supplied-evidence consumer; modes never authenticate hardware origin."""
import json
import shutil
import tempfile
import types
from pathlib import Path
import build_a23_live132_q1 as b
import a23_terminal_observation_consumer as typed
from a23_live132_completion_consumer import validate_fact
from a23_live126_interepoch_workflow import validate_trace

def module(build,name):
    import sys
    p=Path(build)/'generated'/(name+'.py');m=types.ModuleType(name);m.__file__=str(p);sys.modules[name]=m
    exec(compile(b.w.plain(p),str(p),'exec'),m.__dict__);return m

def _derive_service():
    path=Path(__file__).with_name('a23_terminal_observation_consumer.py');raw=path.read_text()
    raw=b.one(raw,'def validate(row, expected_binding):','def validate(row, expected_binding, *, simulation):\n    require(type(simulation) is bool, "explicit service mode required")')
    raw=b.one(raw,"expected_binding.get('model_only') is True","expected_binding.get('model_only') is simulation")
    m=types.ModuleType('a23_q1_service_consumer');m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m

service=_derive_service()

def analyze_host(host,build,*,job,simulation):
    b.require(type(simulation) is bool,'explicit Q1 model/SDK mode required')
    b.verify(build,current=False);host=Path(host);d=b.w.load(Path(build)/'descriptor.json')
    _,bound=b.generated(Path(build)/'source',{k:v for k,v in d.items() if k!='generated_hashes'})
    completion=b.w.card.seal_verify(host/'live-completion');b.require(set(completion)=={'completion.json'},'completion inventory')
    fact=json.loads(completion['completion.json'],object_pairs_hook=typed.unique_object)
    payload=b.w.card.seal_verify(host/'live-final');acceptance=b.w.card.seal_verify(host/'live-acceptance')
    entry=typed.load(host/'live-final/entry-current.json')
    binding=dict(candidate_binding_sha256=b.sha(payload['candidate-binding.json']),entry_binding=entry['binding'],
        payload_manifest_sha256=b.sha(b.w.plain(host/'live-final/SHA256SUMS')),
        acceptance_manifest_sha256=b.sha(b.w.plain(host/'live-acceptance/SHA256SUMS')),
        acceptance_receipt_sha256=b.sha(acceptance['receipt.json']),entry_snapshot_sha256=b.sha(payload['entry-current.json']),
        final_status_sha256=b.sha(payload['entry-final-status.json']))
    completed=validate_fact(fact,binding)
    with tempfile.TemporaryDirectory(prefix='a23-q1-consume-',dir='/private/tmp') as temp:
        stage=Path(temp)/'host';shutil.copytree(host,stage)
        for n in ('entry-current.json','entry-final-status.json','result.json','receipt-status.json'):shutil.copyfile(host/'live-final'/n,stage/n)
        module(build,'sdk_analysis');checked_entry=module(build,'entry_analysis').analyze(stage)
        export=module(build,'export_analysis').accept(stage,expected_binding=bound,simulation=simulation)
        result=typed.load(stage/'result.json');before=typed.load(stage/'live-final/validation-before.json');after=typed.load(stage/'live-acceptance/validation-after.json')
        record=before['terminal_guard']
        b.require(before['q1_mode_model'] is simulation and after['q1_mode_model'] is simulation and
            before['verifier']['model_roots'] is simulation and after['verifier']['model_roots'] is simulation,'Q1 verifier mode differs')
        b.require(record==after['terminal_guard']==result['terminal_service_window']==typed.load(stage/'terminal-observation.json'),'terminal snapshots differ')
        expected=dict(schema='A23-live132-q1-terminal-binding-1',model_only=simulation,job=str(job),
            scope_sha256=b.sha(b.encode(before['scope'])),session_id=result['session_id'],source_closure_sha256=d['workflow_source_sha256'],
            baseline_manifest_sha256=d['baseline_manifest_sha256'])
        observed=service.validate(record,expected,simulation=simulation)
        b.require(before['scope']==after['scope']==b.scope(build,current=False),'Q1 scope differs')
        rows=before['cadence']['full_checks'];worker=[r for r in rows if r['phase']=='terminal_worker'];finals=[r for r in rows if r['phase']=='terminal_final']
        b.require(len(worker)==len(finals)==1 and len([r for r in rows if r['phase']=='between_epochs'])==2,'terminal guard count')
        b.require(record['worker_begin_ns']<=worker[0]['begin_ns']<=worker[0]['end_ns']<=record['worker_end_ns'],'worker/file guard timing')
        first,last=record['samples_ns'][0],record['samples_ns'][-1]
        b.require(all(r['end_ns']<=first or r['begin_ns']>=last for r in rows),'file guard overlaps service window')
        b.require(finals[0]['begin_ns']>=last and finals[0]['end_ns']<=record['events'][-1]['ns'],'terminal final ordering')
        origin=checked_entry['sdk']['input_origin']
        b.require(origin==('injected_sdk_model' if simulation else 'unverified_sdk_observation'),'Q1 SDK/model origin differs')
        trace=validate_trace(result['lease']['interest_trace'],success=True)
        return dict(schema='A23-live132-q1-analysis-1',entry=checked_entry,checked_export=export,service=observed,completion=completed,
            interest_trace=trace,simulation=simulation,supplied_sdk_mode_not_origin_authentication=not simulation,
            current_state_after_sample_verified=False,hardware_verified=False,physical_run_authenticated=False,
            callback_drain_verified=False,buffer_reuse_verified=False,continuous_streaming_verified=False)

def analyze_entry(host,build,*,job,simulation=False):
    full=analyze_host(host,build,job=job,simulation=simulation)
    return dict(full['entry'],checked_export=full['checked_export'],service=full['service'],completion=full['completion'],
        q1_contract=True,simulation=simulation,current_state_after_sample_verified=False)

def analyze_failure(host,build,*,job,simulation,require_after_off=False):
    b.require(type(simulation) is bool,'explicit failure mode required');b.verify(build,current=False);host=Path(host)
    d=b.w.load(Path(build)/'descriptor.json');_,expected=b.generated(Path(build)/'source',{k:v for k,v in d.items() if k!='generated_hashes'})
    path=host/('live-failure' if (host/'live-failure').exists() else 'live-final')
    files=b.w.card.seal_verify(path)
    b.require('candidate-binding.json' in files and json.loads(files['candidate-binding.json'])==expected,'failure candidate differs')
    entry=json.loads(files['entry-current.json']);state=json.loads(files['result.json'])
    boundary=json.loads(files['terminal-boundary.json'] if path.name=='live-failure' else files['validation-before.json'])
    b.require(boundary['q1_mode_model'] is simulation,'failure mode differs')
    b.require(entry['binding']['first_sequence']==465 and entry['binding']['last_sequence']==512,'failure range differs')
    if path.name=='live-failure':b.require(entry['stopped'] is True and entry['complete'] is False,'early failure state differs')
    terminal=None
    if (host/'terminal-observation.json').exists():
        terminal=typed.load(host/'terminal-observation.json')
        expected_terminal=dict(schema='A23-live132-q1-terminal-binding-1',model_only=simulation,job=str(job),
            scope_sha256=b.sha(b.encode(b.scope(build,current=False))),session_id=entry['driver']['session_id'],
            source_closure_sha256=d['workflow_source_sha256'],baseline_manifest_sha256=d['baseline_manifest_sha256'])
        b.require(terminal['binding']==expected_terminal and terminal['busy'] is False and terminal['worker_returns']==1 and
            terminal['verifier_on_serial_queue'] is True and terminal['exit_allowed'] is True,'failure verifier return differs')
    completion=None
    if (host/'live-completion/COMMITTED').exists():
        extra=b.w.card.seal_verify(host/'live-completion');b.require(set(extra)=={'completion.json'},'failure completion inventory')
        completion=json.loads(extra['completion.json'],object_pairs_hook=typed.unique_object)
        b.require(completion['accepted'] is False and completion['binding']['entry_binding']==entry['binding'] and
            completion['binding']['candidate_binding_sha256']==b.sha(files['candidate-binding.json']),'failure completion binding/state')
        accepted=b.w.card.seal_verify(host/'live-acceptance')
        expected_completion=dict(candidate_binding_sha256=b.sha(files['candidate-binding.json']),entry_binding=entry['binding'],
            payload_manifest_sha256=b.sha(b.w.plain(path/'SHA256SUMS')),
            acceptance_manifest_sha256=b.sha(b.w.plain(host/'live-acceptance/SHA256SUMS')),
            acceptance_receipt_sha256=b.sha(accepted['receipt.json']),entry_snapshot_sha256=b.sha(files['entry-current.json']),
            final_status_sha256=b.sha(files['entry-final-status.json']))
        b.require(json.dumps(completion['binding'],sort_keys=True)==json.dumps(expected_completion,sort_keys=True),'failure completion full digest binding')
    if path.name=='live-final':
        b.require(completion is not None or not (host/'live-completion/COMMITTED').exists(),'completed payload lacks rejected completion')
    traces=[];initial=None;initial_stage=None
    if type(state) is dict and state.get('lease'):initial=state['lease']['interest_trace'];initial_stage='driver'
    elif type(entry.get('provider_failure')) is dict:initial=entry['provider_failure']['interest_trace'];initial_stage='provider'
    if initial is not None:traces.append(validate_trace(initial))
    if (host/'interest-after-power-off').exists():
        after=b.w.card.seal_verify(host/'interest-after-power-off');latest=json.loads(after['entry-current.json']);rawstate=json.loads(after['result.json'])
        b.require(latest['binding']==entry['binding'] and latest['stopped'] is True and latest['complete'] is False,'after-off failure state')
        boundary=json.loads(after['boundary.json']);b.require(boundary['operator_power_off_confirmed'] is True and
            boundary['device_power_observed_by_software'] is False and boundary['callback_drain_verified'] is False,'after-off claims')
        newer=None;new_stage=None
        if rawstate.get('lease'):newer=rawstate['lease']['interest_trace'];new_stage='driver'
        elif type(latest.get('provider_failure')) is dict:newer=latest['provider_failure']['interest_trace'];new_stage='provider'
        if initial is not None:
            b.require(newer is not None and initial_stage==new_stage,'failure trace stage changed')
            traces.append(validate_trace(newer));rows={r['ordinal']:r for r in newer['rows']}
            b.require(all(rows.get(row['ordinal'])==row for row in initial['rows']) and newer['claimed']>=initial['claimed'] and
                (not initial['overflow'] or newer['overflow']),'failure trace prefix changed')
    else:b.require(not require_after_off or entry.get('resources_retained') is False,'operator-off evidence missing')
    return dict(schema='A23-live132-q1-failure-analysis-1',overall_success=False,failure_preserved=True,
        payload_may_describe_an_earlier_success=path.name=='live-final',terminal_return_record=terminal is not None,
        rejected_completion_record=completion is not None,interest_traces=traces,simulation=simulation,
        hardware_verified=False,physical_run_authenticated=False,callback_drain_verified=False,buffer_reuse_verified=False)

def collect_failure(run):
    run=b.w.canonical(run);state=b.w.load(run/'workflow.json')
    b.require(state['stage']=='exited' and state['creator_wait_verified'] is True and type(state['exit_code']) is int and
        state['exit_code']!=0 and state['execution_mode']=='require_escalated' and state['remaining']==0,'actual failed wait missing')
    build=Path(state['build']);b.verify(build,current=False);job=Path(state['job'])
    b.require(job.parent==b.FORMAL_ROOT/'jobs' and run.parent==b.w.ROOT/'private/runs' and
        run.name=='A-q1-three-epoch-'+job.name,'failure workflow paths differ')
    engine=module(build,'fixed48');ns,scope,_,_,_,_=engine.records(b.FORMAL_ROOT,job.name)
    b.require(ns['simulation'] is False and scope==b.scope(build,current=False) and state['scope']==scope,'failure model/scope differs')
    engine.check_consumed(b.FORMAL_ROOT,job.name)
    for name in ('native-process-claim.json','native-sdk-claim.json'):
        path=job/name
        if path.exists():b.require(b.w.load(path)['simulation'] is False,'model claim in failed real workflow')
    if (job/'native-context.json').exists():b.require(b.w.load(job/'native-context.json')['pid']==state['receiver_pid'],'failed child/context PID differs')
    host=run/'host'
    try:result=analyze_failure(host,build,job=job,simulation=False,require_after_off=True)
    except (ValueError,OSError,KeyError,TypeError) as error:
        result=dict(overall_success=False,raw_failure_preserved=True,semantic_failure_chain_complete=False,error=str(error),
            hardware_verified=False,callback_drain_verified=False,resources_released_verified=False)
    return dict(schema='A23-live132-q1-failure-collection-1',creator_wait_verified=True,receiver_exit_code=state['exit_code'],
        result=result,remaining=0,hardware_verified=False,physical_run_authenticated=False)
