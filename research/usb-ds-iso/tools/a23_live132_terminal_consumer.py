"""Bound offline receiver evidence: original SDK/export checks plus service ticks."""
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path
import build_a23_live132_terminal as b
import a23_terminal_observation_consumer as service
from a23_live126_interepoch_workflow import validate_trace

def module(build,name):
    p=Path(build)/'generated'/(name+'.py');m=types.ModuleType(name);m.__file__=str(p)
    sys.modules[name]=m;exec(compile(b.w.plain(p),str(p),'exec'),m.__dict__);return m

def analyze(host,build,*,job,simulation):
    b.require(simulation is True,'offline adapter cannot authenticate a physical run')
    b.verify(build,current=False);d=b.w.load(Path(build)/'descriptor.json')
    _,bound=b.generated(Path(build)/'source',{k:v for k,v in d.items() if k!='generated_hashes'})
    with tempfile.TemporaryDirectory(prefix='a23-terminal-consumer-',dir='/private/tmp') as temp:
        stage=Path(temp)/'host';shutil.copytree(host,stage)
        for n in ('entry-current.json','entry-final-status.json','result.json','receipt-status.json'):
            shutil.copyfile(Path(host)/'live-final'/n,stage/n)
        module(build,'sdk_analysis');entry=module(build,'entry_analysis').analyze(stage)
        export=module(build,'export_analysis').accept(stage,expected_binding=bound,simulation=True)
        result=b.w.load(stage/'result.json');before=b.w.load(stage/'live-final/validation-before.json')
        after=b.w.load(stage/'live-acceptance/validation-after.json');record=before['terminal_guard']
        b.require(record==after['terminal_guard']==result['terminal_service_window']==b.w.load(stage/'terminal-observation.json'),'terminal snapshots differ')
        expected=dict(schema='A23-live132-terminal-binding-1',model_only=True,job=str(job),
            scope_sha256=b.sha(b.encode(before['scope'])),session_id=result['session_id'],
            source_closure_sha256=d['workflow_source_sha256'],baseline_manifest_sha256=d['baseline_manifest_sha256'])
        observed=service.validate(record,expected)
        b.require(before['scope']==after['scope'] and before['scope']['workflow_source_sha256']==d['workflow_source_sha256'] and
            before['scope']['baseline_manifest_sha256']==d['baseline_manifest_sha256'],'scope differs')
        rows=before['cadence']['full_checks'];worker=[r for r in rows if r['phase']=='terminal_worker']
        finals=[r for r in rows if r['phase']=='terminal_final']
        b.require(len(worker)==len(finals)==1 and len([r for r in rows if r['phase']=='between_epochs'])==2,'terminal guard count')
        b.require(record['worker_begin_ns']<=worker[0]['begin_ns']<=worker[0]['end_ns']<=record['worker_end_ns'],'worker/file guard timing')
        first,last=record['samples_ns'][0],record['samples_ns'][-1]
        b.require(all(r['end_ns']<=first or r['begin_ns']>=last for r in rows),'full file guard overlaps service window')
        b.require(finals[0]['begin_ns']>=last and finals[0]['end_ns']<=record['events'][-1]['ns'],'terminal final check ordering')
        trace=validate_trace(result['lease']['interest_trace'],success=True)
        return dict(schema='A23-live132-terminal-offline-analysis-1',entry=entry,checked_export=export,
            service=observed,interest_trace=trace,current132_bound=True,simulated_transport=True,
            actual_usb_verified=False,callback_drain_verified=False,buffer_reuse_verified=False,hardware_entry_enabled=False)

def analyze_failure(host,build,*,job):
    b.verify(build,current=False);host=Path(host);files=b.w.card.seal_verify(host/'live-failure')
    b.require(set(files)=={'entry-current.json','entry-final-status.json','result.json','receipt-status.json',
        'candidate-binding.json','live.json','terminal-boundary.json'},'failure inventory')
    d=b.w.load(Path(build)/'descriptor.json');_,bound=b.generated(Path(build)/'source',{k:v for k,v in d.items() if k!='generated_hashes'})
    b.require(json.loads(files['candidate-binding.json'])==bound,'failure candidate pin')
    entry=json.loads(files['entry-current.json']);b.require(entry['stopped'] is True and entry['complete'] is False,'failure entry state')
    settled=service.load(host/'terminal-observation.json');scope=b.scope(build)
    expected=dict(schema='A23-live132-terminal-binding-1',model_only=True,job=str(job),
        scope_sha256=b.sha(b.encode(scope)),session_id=entry['driver']['session_id'],
        source_closure_sha256=d['workflow_source_sha256'],baseline_manifest_sha256=d['baseline_manifest_sha256'])
    b.require(settled['binding']==expected and settled['busy'] is False and settled['worker_returns']==1 and
        settled['verifier_on_serial_queue'] is True and settled['exit_allowed'] is True,'failure worker return')
    boundary=json.loads(files['terminal-boundary.json'])['terminal_guard']
    b.require(boundary['binding']==expected and boundary['full_checks']==1,'failure boundary binding')
    b.require(settled['accepted'] is False or settled['accepted'] is True,'failure acceptance type')
    return dict(overall_success=False,failure_preserved=True,worker_return_record_retained=True,
        boundary_was_pending=boundary['busy'],local_window_passed_before_later_failure=settled['accepted'],
        callback_drain_verified=False,hardware_entry_enabled=False)
