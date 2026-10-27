"""Require a bound completion fact in addition to all earlier offline checks."""
import json
import types
from pathlib import Path
import build_a23_live132_completion as b
import a23_terminal_observation_consumer as typed

# The original consumer stays immutable. Rebind only its builder in a separate
# module, retaining its SDK, export, service-window and source-time checks.
_path=Path(__file__).with_name('a23_live132_terminal_consumer.py')
_source=_path.read_text().replace('import build_a23_live132_terminal as b','import build_a23_live132_completion as b')
_old=types.ModuleType('a23_completion_previous_consumer');_old.__file__=str(_path)
exec(compile(_source,str(_path),'exec'),_old.__dict__)
module=_old.module

def validate_fact(fact,binding):
    flags=dict(accepted=True,disk_equal=True,sampled_healthy=True,snapshots_equal=True,
        current_entry_complete=True,current_entry_stopped=False,operator_off_acknowledged=False,
        historical_cut_only=True,queue_prefix_only=True,producer_history_authenticated=False,
        file_freshness_after_last_full_check_verified=False,future_events_excluded=False,
        callback_drain_verified=False,buffer_reuse_verified=False,hardware_entry_enabled=False)
    keys=set(flags)|{'schema','binding','clock','queue_requested_ns','continuation_entered_ns','sample_begin_ns','sample_end_ns',
        'queue_handoffs','continuations','exit_requests','sampled_entry_sha256','sampled_final_status_sha256'}
    b.require(type(fact) is dict and set(fact)==keys and fact['schema']=='A23-owner-queue-completion-1','completion shape/schema')
    b.require(json.dumps(fact['binding'],sort_keys=True)==json.dumps(binding,sort_keys=True),'completion binding')
    for key,value in flags.items():b.require(fact[key] is value,'completion boolean '+key)
    for key,value in dict(queue_handoffs=1,continuations=1,exit_requests=0).items():
        b.require(typed.integer(fact[key])==value,'completion count '+key)
    b.require(fact['clock']=='CLOCK_MONOTONIC_RAW_ns','completion clock')
    times=[typed.integer(fact[k],1) for k in ('queue_requested_ns','continuation_entered_ns','sample_begin_ns','sample_end_ns')]
    b.require(times==sorted(times),'completion queue/sample order')
    b.require(fact['sampled_entry_sha256']==binding['entry_snapshot_sha256'] and
        fact['sampled_final_status_sha256']==binding['final_status_sha256'],'completion sampled snapshots')
    return dict(schema='A23-completion-cut-analysis-1',local_completion_cut_accepted=True,
        owner_queue_handoffs=1,sample_begin_ns=times[2],sample_end_ns=times[3],historical_cut_only=True,
        queue_prefix_only=True,future_events_excluded=False,callback_drain_verified=False,
        buffer_reuse_verified=False,producer_history_authenticated=False,hardware_entry_enabled=False)

def analyze(host,build,*,job,simulation):
    b.require(simulation is True,'completion adapter is offline only')
    b.verify(build,current=False);host=Path(host)
    completion=b.w.card.seal_verify(host/'live-completion')
    b.require(set(completion)=={'completion.json'},'completion file inventory')
    fact=json.loads(completion['completion.json'],object_pairs_hook=typed.unique_object)
    final=b.w.card.seal_verify(host/'live-final');accepted=b.w.card.seal_verify(host/'live-acceptance')
    entry=typed.load(host/'live-final/entry-current.json')
    binding=dict(candidate_binding_sha256=b.sha(final['candidate-binding.json']),entry_binding=entry['binding'],
        payload_manifest_sha256=b.sha(b.w.plain(host/'live-final/SHA256SUMS')),
        acceptance_manifest_sha256=b.sha(b.w.plain(host/'live-acceptance/SHA256SUMS')),
        acceptance_receipt_sha256=b.sha(accepted['receipt.json']),entry_snapshot_sha256=b.sha(final['entry-current.json']),
        final_status_sha256=b.sha(final['entry-final-status.json']))
    proof=validate_fact(fact,binding)
    original=_old.analyze(host,build,job=job,simulation=True)
    return dict(original,schema='A23-live132-completion-offline-analysis-1',completion=proof,
        current_state_after_sample_verified=False,overall_hardware_success=False)
