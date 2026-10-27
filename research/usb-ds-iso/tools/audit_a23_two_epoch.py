"""Build/run a bounded offline receiver with injected resources and archive negatives."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess

import audit_a23_rearm as prior
from analyze_a23_two_epoch import analyze,sha

w=prior.w
PARENT=w.A/'A23-rearm-closeout-20261018'
PARENT_SUM='673d767cf142cc2017692d252ae43e397536bc3525432e7a7b4bc99c5a7058e0'
NEW=('host/a23_two_epoch_receiver.h','host/a23_two_epoch_receiver.m',
     'tests/a23_two_epoch_receiver_test.m','tests/test_a23_two_epoch_receiver.py',
     'tools/analyze_a23_two_epoch.py','tools/audit_a23_two_epoch.py')
NATIVE=('host/io_usb_host_transaction_owner.m','host/io_usb_host_runtime_guard.m',
        'host/io_usb_host_evidence.m','host/io_usb_host_session.m',
        'host/a23_two_epoch_receiver.m','tests/a23_two_epoch_receiver_test.m')


def sources():
    w.card.seal_verify(PARENT);w.require(w.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'parent closeout differs')
    parent=w.load(PARENT/'closeout.json');current=prior.sources()
    w.require(len(current)==317 and current==parent['source_hashes'],'prior317 drift')
    for name in NEW:
        key='research/usb-ds-iso/'+name;w.require(key not in current,'new source overlap');current[key]=w.sha(w.plain(w.ROOT/name))
    return dict(sorted(current.items()))


def compile_command(source,binary):
    return ['clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-g',
        '-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',
        *(str(source/'research/usb-ds-iso'/n) for n in NATIVE),'-o',str(binary)]


def write_json(path,value):path.write_text(json.dumps(value,sort_keys=True,separators=(',',':')))


def negative_cases(normal,root):
    root.mkdir();results={}
    cases=('raw-corrupt','transaction-corrupt','status-sequence','same-urb','iso7-corrupt','before-second',
        'epoch-sequence','binding-swap','claimed-hardware','claimed-trace','bool-result-count','bool-event-epoch',
        'budget-relabel','deadline-relabel','journal-order','journal-partial','extra-epoch-file','missing-commit','raw-short','wrong-mode')
    semantic={'raw-corrupt','transaction-corrupt','status-sequence','same-urb','iso7-corrupt','before-second',
        'epoch-sequence','binding-swap','budget-relabel','deadline-relabel','raw-short'}
    for case in cases:
        folder=root/case;shutil.copytree(normal,folder)
        epoch=folder/'epoch-1';meta=json.loads((epoch/'metadata.json').read_text());result=json.loads((folder/'result.json').read_text())
        rows=[json.loads(s) for s in (folder/'session.jsonl').read_text().splitlines()]
        if case=='raw-corrupt':
            raw=bytearray((epoch/'raw.bin').read_bytes());raw[120*192+6]^=1;(epoch/'raw.bin').write_bytes(raw)
        elif case=='raw-short':(epoch/'raw.bin').write_bytes((epoch/'raw.bin').read_bytes()[:-1])
        elif case=='transaction-corrupt':
            raw=bytearray((epoch/'transactions.bin').read_bytes());struct.pack_into('<i',raw,0,-1);(epoch/'transactions.bin').write_bytes(raw)
        elif case in ('status-sequence','same-urb','iso7-corrupt'):
            raw=bytearray((epoch/'after.bin').read_bytes())
            if case=='status-sequence':struct.pack_into('<I',raw,8,65)
            elif case=='same-urb':struct.pack_into('<II',raw,20,501,501)
            else:struct.pack_into('<I',raw,68,0)
            (epoch/'after.bin').write_bytes(raw)
        elif case=='before-second':(epoch/'before.bin').write_bytes((folder/'epoch-0/before.bin').read_bytes())
        elif case=='epoch-sequence':meta['first_sequence']=81
        elif case=='binding-swap':meta['binding']['session_id']='00000000-0000-0000-0000-000000000000'
        elif case=='claimed-hardware':result['hardware_verified']=True
        elif case=='claimed-trace':result['device_trace_verified']=True
        elif case=='bool-result-count':result['aborts']=False
        elif case=='bool-event-epoch':
            for row in rows:
                if row['event']=='iso_callback' and row['details'].get('epoch')==1:row['details']['epoch']=True
        elif case=='budget-relabel':
            meta['budget']['age_ns']=0
            for row in rows:
                if row['event']=='iso_return' and row['details']['epoch']==1:row['details']['budget']=meta['budget']
        elif case=='deadline-relabel':meta['control_arrival_ticks']=meta['trigger_ticks']+2**40
        elif case=='journal-order':
            # Keep indices monotone while moving second admission before save0.
            i=next(i for i,r in enumerate(rows) if r['event']=='saved' and r['details']['epoch']==0)
            rows[i],rows[i+1]=rows[i+1],rows[i]
            for n,row in enumerate(rows,1):row['index']=n
        elif case=='extra-epoch-file':(epoch/'unlisted.bin').write_bytes(b'x')
        elif case=='missing-commit':(epoch/'COMMITTED').unlink()
        elif case=='wrong-mode':result['execution_mode']='hardware'
        if case in semantic:
            write_json(epoch/'metadata.json',meta)
            names=('after.bin','before.bin','metadata.json','raw.bin','transactions.bin')
            sums=''.join(sha((epoch/n).read_bytes())+'  '+n+'\n' for n in names).encode()
            (epoch/'SHA256SUMS').write_bytes(sums);(epoch/'COMMITTED').write_text(sha(sums)+'\n')
            for row in rows:
                if row['event']=='saved' and row['details']['epoch']==1:row['details']['metadata_sha256']=sha((epoch/'metadata.json').read_bytes())
                if row['event']=='before' and row['details']['epoch']==1:row['details']['sha256']=sha((epoch/'before.bin').read_bytes())
        write_json(folder/'result.json',result)
        journal=''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows)
        (folder/'session.jsonl').write_text(journal[:-1] if case=='journal-partial' else journal)
        try:analyze(folder)
        except (ValueError,KeyError,TypeError,struct.error) as error:results[case]=dict(rejected=True,reason=str(error),integrity_rebound=case in semantic)
        else:raise ValueError('invalid archive accepted: '+case)
    return results


def run(output):
    output=w.canonical(output);w.require(not output.exists(),'new offline review required');before=sources();output.mkdir(mode=0o700)
    for name,digest in before.items():
        raw=w.plain(w.b.REPO/name,2*1024*1024);w.require(w.sha(raw)==digest,'source changed')
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    command=compile_command(output/'source',output/'receiver-test')
    compiled=subprocess.run(command,capture_output=True,text=True);w.card.put(output,'compile.log',(compiled.stdout+compiled.stderr).encode())
    w.require(compiled.returncode==0,'native compile failed');models=output/'models';models.mkdir()
    native=subprocess.run([str(output/'receiver-test'),str(models)],capture_output=True,text=True)
    w.card.put(output,'native.stdout',native.stdout.encode());w.card.put(output,'native.stderr',native.stderr.encode())
    w.require(native.returncode==0,'native scenarios failed');matrix=json.loads(native.stdout);w.require(matrix['case_count']==47,'wrong native matrix')
    accepted={};rejected={}
    for name,result in matrix['cases'].items():
        if result.get('init_rejected'):rejected[name]='capability rejected before any submission';continue
        try:accepted[name]=analyze(models/name)
        except (ValueError,KeyError,TypeError) as error:rejected[name]=str(error)
    w.require(set(accepted)=={'normal'} and len(rejected)==46,'bad native classification')
    negatives=negative_cases(models/'normal',output/'negative-archives');w.require(len(negatives)==20,'negative count differs')
    snapshot=w.ROOT/'private/card-cycles/20261018-context65-first-live-read';saved=w.card.seal_verify(snapshot)
    w.require(w.sha(w.plain(snapshot/'SHA256SUMS'))=='2e5e4375acb822927e71c46e5bf6eb3618047064972c307268aef34670860205','latest69 anchor differs')
    w.card.put(output,'latest69-snapshot.json',saved['snapshot.json'])
    plan=dict(schema='A23-two-epoch-offline-plan-1',first_sequence=81,last_sequence=112,max_iso_attempts=2,max_triggers=2,max_async_aborts=1,
        first_frame_lead=32,sequence_ranges_allocated=False,latest69=w.reference(snapshot),latest69_used_as_new_issuance_baseline=False,
        receipt_and_collector_offline_only=True,device_trace_verified=False,actual_urb_service_generation_verified=False,
        sdk_provider_implemented=False,actual_sdk_mapping_tested=False,device_package_reuse_established=False,
        hardware_entry_enabled=False,formal_records=0,formal_reservations=0,remaining=0,acquisition_enabled=False)
    w.write(output/'offline-plan.json',plan)
    w.require(sources()==before,'source drift after native tests')
    audit=dict(schema='A23-two-epoch-offline-audit-1',passed=True,source_hashes=before,source_count=len(before),prior_sources_unchanged=317,
        native_cases=47,native_matrix=matrix,accepted=accepted,rejected=rejected,negative_archives=negatives,
        sanitizers=['address','undefined'],compiler_command=command,usb_requests=0,sd_accesses=0,real_sdk_objects=0,
        formal_reservations=0,formal_records=0,remaining=0,firmware_built=False,device_package_changed=False,hardware_verified=False)
    w.write(output/'audit.json',audit);w.b.seal(output)
    return dict(reference=w.reference(output),source_count=len(before),native_cases=47,accepted=list(accepted),rejected_native=46,negative_archives=20,passed=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(p.parse_args().output),indent=2))
