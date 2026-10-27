"""Read-only shared32/native-permit model chain verification."""
import argparse,json
from pathlib import Path
import a23_shared_sequence32 as s
from a23_execution_context import validate as context_validate
f=s.f

def analyze(root,job,expected_scope,native_result):
    root=Path(root);ns,scope,h,folder,j,a=s.records(root,job);s.check_consumed(root,job)
    f.require(f.encode(scope)==f.encode(expected_scope),'supplied shared scope differs')
    f.require(ns['simulation'] is True and scope['formal_issuance_available'] is False and scope['acquisition_mode_implemented'] is False,'analysis requires injected shared namespace')
    n=native_result;f.require(type(n) is dict and n.get('schema')=='A23-shared32-native-fixture-1' and n.get('init_accepted') is True and n.get('process_returned') is True and n.get('selection_returned') is True and n.get('replay_blocked') is True,'native permit not complete')
    permit=n.get('permit');f.require(type(permit) is dict and permit.get('schema')=='A23-shared32-native-permit-result-1','native result missing')
    for k in ('simulation','process_attempted','process_claimed','selection_attempted','selection_claimed'):f.require(permit.get(k) is True,'native gate missing')
    for k in ('stale','hardware_verified','hardware_entry_enabled','process_origin_authenticated'):f.require(permit.get(k) is False,'native result stale/claim')
    for name in ('native-process-attempt','native-selection-attempt'):f.require(f.read(folder/name)==b'one attempt\n','native attempt differs')
    raw=f.read(folder/'native-context.json');c=f.parse(raw);context_validate(c,scope['receiver_sha256'])
    p=f.load(folder/'native-process-claim.json');expected_p=dict(schema='A23-shared32-native-process-1',job_id=job,consumed_sha256=f.sha(f.read(folder/'consumed.json')),context_sha256=f.sha(raw),pid=c['pid'],scope_sha256=f.sha(f.read(root/'scope.json')),simulation=True,hardware_verified=False)
    f.require(f.encode(p)==f.encode(expected_p),'native process snapshot differs')
    selection=f.load(folder/'native-sdk-claim.json');identity=selection.get('identity')
    f.require(type(identity) is dict and set(identity)=={'device_id','interface_id','speed'} and f.integer(identity['device_id'],1,2**64-1) and f.integer(identity['interface_id'],1,2**64-1) and identity['device_id']!=identity['interface_id'] and f.integer(identity['speed'],3,3),'native selected identity differs')
    expected_s=dict(schema='A23-shared32-native-selection-1',job_id=job,process_sha256=f.sha(f.read(folder/'native-process-claim.json')),context_sha256=f.sha(raw),pid=c['pid'],identity=identity,simulation=True,hardware_verified=False)
    f.require(f.encode(selection)==f.encode(expected_s),'native selection snapshot differs')
    f.require({p.name for p in folder.iterdir()}==s.JOB_FILES and all(p.is_file() and not p.is_symlink() for p in folder.iterdir()),'native job inventory differs')
    for k in ('real_sdk_objects','usb_requests','sd_accesses'):f.require(f.integer(n.get(k),0,0),'unexpected hardware count')
    return dict(schema='A23-shared32-native-analysis-1',supplied_model_chain_complete=True,reserved_sequences=32,shared_reservation_files=1,
        native_process_and_selection_claimed=True,formal_issuance_available=False,hardware_entry_enabled=False,process_origin_authenticated=False,
        hardware_verified=False,receiver_launched=False,remaining=0)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('job');p.add_argument('--scope',type=Path,required=True);p.add_argument('--native',type=Path,required=True);a=p.parse_args();print(json.dumps(analyze(a.root,a.job,f.load(a.scope),f.load(a.native)),indent=2))
