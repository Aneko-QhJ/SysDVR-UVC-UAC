"""Offline paired-resource AND epoch archive check. Never grants SDK permission."""
import argparse
import json
from pathlib import Path
from analyze_a23_two_epoch import analyze as epoch_analyze,read,load,require,integer


def analyze(root):
    root=Path(root);pair=load(read(root/'paired-result.json',16384));result=load(read(root/'result.json',16384))
    require(type(pair) is dict and pair.get('schema')=='A23-paired-offline-chain-1' and
        pair.get('execution_mode')=='offline_simulation','paired receipt mode/schema differs')
    require(json.dumps(pair.get('receiver'),sort_keys=True)==json.dumps(result,sort_keys=True),'receiver/result mismatch')
    lease=pair.get('lease');require(type(lease) is dict and lease.get('schema')=='A23-paired-resource-result-1' and
        lease.get('execution_mode')=='offline_simulation','paired lease mode/schema differs')
    for k in ('ready','runtime_touched','service_retained'):require(lease.get(k) is True,'missing lifetime state: '+k)
    for k in ('closed_unused','poisoned','interest_seen','continuation_save_verified','callback_drain_verified','hardware_entry_enabled','hardware_verified'):
        require(lease.get(k) is False,'uncertain or unsupported claim: '+k)
    for k,v in dict(iso_attempts=2,trigger_attempts=2,status_reads=4,frame_reads=2,aborts=0,store_count=4).items():
        require(integer(lease.get(k),v,v),'paired limit differs: '+k)
    for k in ('iso_callbacks','control_callbacks'):
        row=lease.get(k);require(type(row) is list and len(row)==2 and all(integer(v,1,1) for v in row),'paired callback mismatch')
    for k,v in dict(mapped_calls=4,pipe_copies=1,service_retained=1,destroys=0).items():require(integer(pair.get(k),v,v),'paired preparation/lifetime differs')
    epochs=epoch_analyze(root)
    return dict(schema='A23-paired-offline-analysis-1',offline_chain_complete=True,resource_and_epoch_checks=True,
        epochs=epochs['epochs'],total_bytes=epochs['total_bytes'],hardware_verified=False,hardware_entry_enabled=False,
        actual_sdk_mapping_verified=False,device_trace_verified=False,callback_drain_verified=False,
        physical_run_authenticated=False,sequences_allocated=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    print(json.dumps(analyze(p.parse_args().directory),indent=2))
