"""Read-only OFFLINE presentation of a historical cut and optional later model observation."""
import argparse
import json
from pathlib import Path
import a23_live132_completion_consumer as consumer
import build_a23_live132_completion as b
import a23_terminal_observation_consumer as typed

def present(analysis,binding,observation=None):
    b.require(type(analysis) is dict and analysis.get('schema')=='A23-live132-completion-offline-analysis-1','validated completion analysis required')
    proof=analysis.get('completion',{})
    b.require(proof.get('schema')=='A23-completion-cut-analysis-1' and proof.get('local_completion_cut_accepted') is True and
        proof.get('historical_cut_only') is True and proof.get('queue_prefix_only') is True and
        analysis.get('current_state_after_sample_verified') is False and analysis.get('overall_hardware_success') is False,'historical scope missing')
    for key in ('future_events_excluded','callback_drain_verified','buffer_reuse_verified','producer_history_authenticated','hardware_entry_enabled'):
        b.require(proof.get(key) is False,'unsupported view claim '+key)
    sampled=typed.integer(proof.get('sample_end_ns'),1)
    later=dict(state='not_supplied',is_current=False,hardware_observed=False)
    text='历史终结采样：通过；采样后的模型状态：未提供观察；当前设备状态：未验证。'
    if observation is not None:
        keys={'schema','binding_sha256','clock','observed_ns','model_only','entry_complete','entry_stopped','source'}
        b.require(type(observation) is dict and set(observation)==keys and observation['schema']=='A23-postcut-model-observation-1','observation shape')
        b.require(observation['binding_sha256']==b.sha(b.encode(binding)),'observation bound to another record')
        b.require(observation['clock']=='CLOCK_MONOTONIC_RAW_ns' and observation['model_only'] is True and
            observation['source']=='offline_fixture_entry_result_getter','explicit model observation required')
        at=typed.integer(observation['observed_ns'],1);b.require(at>sampled,'observation is not after sampling')
        b.require(type(observation['entry_complete']) is bool and type(observation['entry_stopped']) is bool and
            not(observation['entry_complete'] and observation['entry_stopped']),'observation flags')
        state='stopped_at_observation' if observation['entry_stopped'] else (
            'complete_at_observation' if observation['entry_complete'] else 'incomplete_at_observation')
        label={'stopped_at_observation':'已停止','complete_at_observation':'完整','incomplete_at_observation':'未完成'}[state]
        later=dict(state=state,observed_ns=at,model_only=True,is_current=False,hardware_observed=False)
        text=f'历史终结采样：通过；随后提供的模型观察：{label}；当前设备状态：未验证。'
    return dict(schema='A23-completion-status-view-1',historical_cut=dict(accepted=True,sample_end_ns=sampled,
        binding_sha256=b.sha(b.encode(binding)),scope='owner_queue_prefix_at_sample'),latest_supplied_model_observation=later,
        current_device_state='unverified',current_live_health_verified=False,overall_hardware_success=False,
        sdk_drain_verified=False,buffer_reuse_authorized=False,producer_history_authenticated=False,
        user_text=text,loop_success_is_not_a_live_health_probe=True)

def from_archive(host,build,*,job,observation=None):
    analysis=consumer.analyze(host,build,job=job,simulation=True)
    raw=b.w.card.seal_verify(Path(host)/'live-completion')['completion.json']
    fact=json.loads(raw,object_pairs_hook=typed.unique_object)
    return present(analysis,fact['binding'],observation)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',required=True,type=Path)
    p.add_argument('--build',required=True,type=Path);p.add_argument('--job',required=True)
    p.add_argument('--model-observation',type=Path);args=p.parse_args()
    o=typed.load(args.model_observation) if args.model_observation else None
    print(json.dumps(from_archive(args.host,args.build,job=args.job,observation=o),ensure_ascii=False,sort_keys=True))
