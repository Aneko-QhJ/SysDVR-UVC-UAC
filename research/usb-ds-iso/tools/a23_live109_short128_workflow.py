"""Strict success/failure trace consumers and new explicitly authorized workflow."""
import argparse,json,shutil,sys,tempfile,types
from pathlib import Path
import build_a23_live109_short128 as builder
w=builder.w

def module(build,name):
    p=Path(build)/'generated'/(name+'.py');m=types.ModuleType(name);m.__file__=str(p);sys.modules[name]=m;exec(compile(w.plain(p),str(p),'exec'),m.__dict__);return m
def require(v,s):w.require(v,s)
def integer(v,lo=0,hi=2**64-1):return type(v) is int and lo<=v<=hi
def typed(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)

def trace_from_entry(entry,state):
    if type(entry.get('driver')) is dict:
        require(typed(entry['driver'])==typed(state) and state.get('first_sequence')==273,'driver failure snapshot differs')
        return 'driver',state['lease']['interest_trace']
    provider=entry.get('provider_failure')
    require(entry.get('driver') is None and state=={} and type(provider) is dict and provider.get('schema')=='A23-triple-resource-result-1' and provider.get('interest_seen') is True and provider.get('poisoned') is True,'provider preparation failure differs')
    return 'provider_preparation',provider['interest_trace']

def validate_trace(v,*,success=False):
    keys={'schema','capacity','claimed','committed','pending','overflow','complete','latch_observed','latch_without_slot','rows','clock_domain','clock_timebase_in_driver','argument_captured','message_labels_authenticate_origin','atomic_snapshot_verified','future_events_excluded'}
    require(type(v) is dict and set(v)==keys and v['schema']=='A23-provider-interest-trace-1','trace shape differs')
    require(integer(v['capacity'],8,8) and integer(v['claimed'],0,8) and integer(v['committed'],0,v['claimed']) and integer(v['pending'],v['claimed']-v['committed'],v['claimed']-v['committed']),'trace count differs')
    for k in ('overflow','complete','latch_observed','latch_without_slot'):require(type(v[k]) is bool,'trace flag differs '+k)
    require(v['clock_domain']=='mach_absolute_time' and v['clock_timebase_in_driver'] is True,'trace clock differs')
    for k in ('argument_captured','message_labels_authenticate_origin','atomic_snapshot_verified','future_events_excluded'):require(v[k] is False,'unsupported trace claim')
    rows=v['rows'];require(type(rows) is list and len(rows)==v['committed'],'trace row count differs');last=0
    for row in rows:
        require(type(row) is dict and set(row)=={'ordinal','message_u32','provider_ingress_ticks'} and integer(row['ordinal'],last+1,v['claimed']) and integer(row['message_u32'],0,2**32-1) and integer(row['provider_ingress_ticks']),'trace raw row differs');last=row['ordinal']
    gap=v['latch_observed'] and v['claimed']==0
    require(v['latch_without_slot'] is gap and v['complete'] is (not v['overflow'] and not v['pending'] and not gap),'trace completeness differs')
    if success:require(v['complete'] is True and v['latch_observed'] is False and v['claimed']==0 and rows==[],'interest trace incompatible with success')
    return dict(complete_observed_prefix=v['complete'],message_values=[r['message_u32'] for r in rows],pending=v['pending'],overflow=v['overflow'],argument_captured=False,current_or_future_stream_authenticated=False)

def binding(build):
    d=w.load(Path(build)/'descriptor.json');return builder.generated(Path(build)/'source',{k:v for k,v in d.items() if k!='generated_hashes'})[1]
def analyze_entry(root,build,*,simulation=False):
    builder.verify(build,current=False);module(build,'sdk_analysis');entry=module(build,'entry_analysis').analyze(Path(root));proof=module(build,'export_analysis').accept(Path(root),expected_binding=binding(build),simulation=simulation)
    require(proof['entry_binding']==w.load(Path(root)/'entry-current.json')['binding'],'checked/SDK binding differs')
    trace=validate_trace(w.load(Path(root)/'result.json')['lease']['interest_trace'],success=True)
    return dict(entry,checked_export=proof,interest_trace=trace)
def analyze_host(host,build,*,simulation=False):
    with tempfile.TemporaryDirectory(prefix='a23-interest-host-',dir='/private/tmp') as t:
        stage=Path(t)/'host';shutil.copytree(host,stage)
        for n in ('entry-current.json','entry-final-status.json','result.json','receipt-status.json'):shutil.copyfile(Path(host)/'live-final'/n,stage/n)
        return analyze_entry(stage,build,simulation=simulation)

def analyze_failure(host,build,*,require_after_off=False):
    builder.verify(build,current=False);host=Path(host);files=w.card.seal_verify(host/'live-failure');expected={'entry-current.json','entry-final-status.json','candidate-binding.json','result.json','receipt-status.json','live.json'}
    require(set(files)==expected,'failure inventory differs');require(typed(json.loads(files['candidate-binding.json']))==typed(binding(build)),'failure candidate pin differs')
    entry=json.loads(files['entry-current.json']);result=json.loads(files['result.json']);require(entry['stopped'] is True and entry['complete'] is False,'failure entry snapshot differs')
    require(entry['binding']['first_sequence']==273 and entry['binding']['last_sequence']==320,'failure range differs')
    stage,initial=trace_from_entry(entry,result);proof=validate_trace(initial);supplement=None
    folder=host/'interest-after-power-off'
    if folder.exists():
        extra=w.card.seal_verify(folder);require(set(extra)=={'entry-current.json','result.json','boundary.json'},'after-off shape differs');boundary=json.loads(extra['boundary.json']);latest=json.loads(extra['entry-current.json']);state=json.loads(extra['result.json'])
        require(typed(boundary)==typed(dict(schema='A23-interest-after-off-boundary-1',operator_power_off_confirmed=True,device_power_observed_by_software=False,raw_sdk_buffers_copied=False,callback_drain_verified=False,future_events_excluded=False)),'after-off claims differ')
        require(typed(latest['binding'])==typed(entry['binding']),'after-off entry binding differs');after_stage,new=trace_from_entry(latest,state);require(after_stage==stage,'failure stage changed');supplement=validate_trace(new)
        newer={x['ordinal']:x for x in new['rows']};require(all(newer.get(row['ordinal'])==row for row in initial['rows']) and new['claimed']>=initial['claimed'] and (not initial['overflow'] or new['overflow']),'after-off trace prefix changed')
    require(not require_after_off or supplement is not None,'after-off trace evidence missing')
    return dict(schema='A23-interest-failure-analysis-1',failure_preserved=True,failure_stage=stage,initial_trace=proof,after_operator_off=supplement,overall_success=False,creator_wait_verified=False,physical_run_authenticated=False,callback_drain_verified=False)

def implementation(build):builder.verify(build);return module(build,'workflow')
def preview(build):return implementation(build).preview(build)
def engine_module(build):return implementation(build).engine_module(build)
def issue(build,*,authorized=False):return implementation(build).issue(build,authorized=authorized)
def capture(build,job,*,execution_mode=None):return implementation(build).capture(build,job,execution_mode=execution_mode)
def collect(run):return implementation(Path(w.load(Path(run)/'workflow.json')['build'])).collect(run)
def acknowledge_power_off(run,*,confirmed=False):return implementation(Path(w.load(Path(run)/'workflow.json')['build'])).acknowledge_power_off(run,confirmed=confirmed)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);s=p.add_subparsers(dest='mode',required=True);s.add_parser('preview');q=s.add_parser('issue');q.add_argument('--authorized-three-epoch-test',action='store_true');q=s.add_parser('capture');q.add_argument('job',type=Path);q.add_argument('--execution-mode',choices=['require_escalated'],required=True);a=p.parse_args()
    value=preview(a.build) if a.mode=='preview' else issue(a.build,authorized=a.authorized_three_epoch_test) if a.mode=='issue' else capture(a.build,a.job,execution_mode=a.execution_mode);print(json.dumps(value,indent=2))
