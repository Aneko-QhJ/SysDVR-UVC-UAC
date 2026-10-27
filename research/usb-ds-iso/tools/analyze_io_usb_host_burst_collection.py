#!/usr/bin/env python3
"""Freeze/audit injected burst artifacts and synthetic A23 logs offline only."""
import argparse
import base64
import json
from pathlib import Path
import re

from analyze_io_usb_host_evidence import require, unique_object
from analyze_io_usb_host_collection import read_file, sha, durable_write, sync_dir
from analyze_io_usb_host_burst_executor import analyze as audit_host
from audit_io_usb_host_device import audit as audit_device

LIMITS={
    'host/journal.jsonl':512*1024,'host/result.json':16384,
    'host/transfer/raw.bin':184320,'host/transfer/transactions.bin':26880,
    'host/transfer/metadata.json':16384,'host/transfer/SHA256SUMS':1024,'host/transfer/COMMITTED':65,
    'status-before.bin':2048,'status-after.bin':2048,'device-log.txt':1024*1024,
    'collection.json':4096,'MOCK_ONLY.txt':256,
}
MARKER=b'Injected host and synthetic device artifacts only. No USB/SD access. Not hardware evidence.\n'
PACKET=re.compile(r'EP0\[(\d+)\]: reqType=0x([0-9a-f]+) req=0x([0-9a-f]+) wVal=0x([0-9a-f]+) wIdx=0x([0-9a-f]+) wLen=(\d+)')
IGNORE=re.compile(r'EP0\[(\d+)\]: wIndex mismatch, ignoring')


def control_trace(log):
    """Require the A23 interface-dispatch shape, without dedup or bus inference."""
    require(type(log) is bytes and 0<len(log)<=1024*1024 and log.endswith(b'\n'),'truncated/oversized device log')
    lines=log.decode('utf-8',errors='strict').splitlines()
    packets={};vendor=[];ignores=[];malformed=[]
    for p,line in enumerate(lines):
        if not line.startswith('EP0['):continue
        m=IGNORE.fullmatch(line)
        if m:ignores.append((p,int(m[1])));continue
        m=PACKET.fullmatch(line)
        if not m:malformed.append(line);continue
        entry=[int(m[1])]+[int(m[i],16) for i in range(2,6)]+[int(m[6])]
        packets[p]=entry
        if entry[1]&0x60==0x40:vendor.append((p,entry))
    bound=all(p-1 in packets and packets[p-1][0]==interface and packets[p-1][1]&0x1f==1 and
              packets[p-1][4]&0xff!=interface for p,interface in ignores)
    tuples=[[0xc1,0x51,0,2,168],[0x41,0x54,1,2,0],[0xc1,0x51,0,2,168]]
    good=bool(not malformed and bound and len(vendor)==6)
    groups=[]
    if good:
        for i,expected in enumerate(tuples):
            a,b=vendor[2*i:2*i+2];start=a[0]
            match=bool(a[1]==[0]+expected and b[1]==[1]+expected and b[0]==start+2 and
                       lines[start+1:start+2]==['EP0[0]: wIndex mismatch, ignoring'] and
                       lines[start+3:start+4]==['EP0[1]: wIndex mismatch, ignoring'])
            good=good and match
            groups.append(dict(phase=['before','trigger','after'][i],start_line=start,end_line=start+3,matches=match))
    ordered=False
    if good:
        start,end=groups[0]['start_line'],groups[-1]['end_line']
        vendor_positions={p for p,_ in vendor}
        # Standard/class traffic during the diagnostic sequence is ambiguity,
        # even if all six vendor deliveries can be found elsewhere in the log.
        extra=any(start<=p<=end and p not in vendor_positions for p in packets)
        forbidden=('USB host connected','USB host disconnected','GetSetupPacket failed:',
                   'ISO EP0:', 'ISO rollback', 'ISO runtime target mismatch')
        extra=extra or any(line.startswith(forbidden) for line in lines[start:end+1])
        submits=[p for p,line in enumerate(lines) if line.startswith('ISO submit ')]
        timings=[p for p,line in enumerate(lines) if line.startswith('ISO timing ')]
        completions=[p for p,line in enumerate(lines) if line.startswith('ISO seq=')]
        if len(submits)==len(timings)==len(completions)==1:
            sp,tp,cp=submits[0],timings[0],completions[0]
            ordered=bool(groups[0]['end_line']<groups[1]['start_line'] and
                         groups[1]['end_line']<sp<tp<groups[2]['start_line'] and tp<cp and
                         not any(line.startswith(forbidden) for line in lines[start:max(end,cp)+1]))
        good=bool(good and not extra and ordered)
    return dict(log_format='A23-interface-dispatch',vendor_records=[entry for _,entry in vendor],
                malformed_records=malformed,ignore_markers_bound=bound,groups=groups,
                device_event_order_matches=ordered,matches_fixed_plan=good,
                inferred_request_phases=['before','trigger','after'] if good else None,
                request_count_verified=False,bus_capture_verified=False)


def replies(journal):
    result={}
    for line in journal.splitlines():
        row=json.loads(line,object_pairs_hook=unique_object)
        if row['event'] in ('status_before','status_after'):
            phase=row['event'].split('_')[1]
            require(phase not in result,'duplicate STATUS phase')
            raw=base64.b64decode(row['details']['raw_base64'],validate=True)
            require(len(raw)<=2048 and sha(raw)==row['details']['sha256'],'STATUS journal binding mismatch')
            result[phase]=raw
    require(set(result)=={'before','after'},'missing raw STATUS; incomplete host cannot acquire a collection')
    return result


def metadata(files):
    return dict(schema='A23-burst-simulation-collection-1',execution_mode='simulation',
                status_source='journal_raw_mock_reply',device_log_source='supplied_synthetic_A23_log',
                log_format='A23-interface-dispatch',scenario=dict(kind='single_burst',first_sequence=1),
                journal_sha256=sha(files['host/journal.jsonl']),result_sha256=sha(files['host/result.json']),
                transfer_manifest_sha256=sha(files['host/transfer/SHA256SUMS']),
                device_log_sha256=sha(files['device-log.txt']),hardware_entry_enabled=False,
                hardware_verified=False,baseline_accepted=False,allow_next_burst=False)


def analyze(root):
    root=Path(root);require(root.is_dir() and not root.is_symlink(),'not a plain collection directory')
    expected={k.split('/')[0] for k in LIMITS}|{'SHA256SUMS','COMMITTED'}
    require({p.name for p in root.iterdir()}==expected,'missing/extra collection files')
    host=root/'host';transfer=host/'transfer'
    for directory,names in [(host,{'journal.jsonl','result.json','transfer'}),
                            (transfer,{k.rsplit('/',1)[1] for k in LIMITS if k.startswith('host/transfer/')})]:
        require(directory.is_dir() and not directory.is_symlink() and {p.name for p in directory.iterdir()}==names,
                'missing/extra or symlinked host files')
    files={name:read_file(root/name,limit) for name,limit in LIMITS.items()}
    manifest=read_file(root/'SHA256SUMS',4096)
    require(manifest==''.join(f'{sha(files[k])}  {k}\n' for k in sorted(files)).encode() and
            read_file(root/'COMMITTED',65)==(sha(manifest)+'\n').encode(),'collection manifest/commit mismatch')
    meta=json.loads(files['collection.json'],object_pairs_hook=unique_object)
    require(json.dumps(meta,sort_keys=True)==json.dumps(metadata(files),sort_keys=True) and files['MOCK_ONLY.txt']==MARKER,
            'collection simulation mode/source/hash mismatch')
    host_result=audit_host(host)
    native=json.loads(files['host/transfer/metadata.json'],object_pairs_hook=unique_object)
    require(native['scenario']==meta['scenario'],'collection/native scenario mismatch')
    original=replies(files['host/journal.jsonl'])
    require(original['before']==files['status-before.bin'] and original['after']==files['status-after.bin'],
            'STATUS differs from original journal bytes')
    device=device_error=trace=None
    try:
        device=audit_device(original['before'],original['after'],files['device-log.txt'],'single_burst',1)
        trace=control_trace(files['device-log.txt'])
    except (ValueError,UnicodeError) as error:device_error=str(error)
    related=bool(device and trace and device['device_status_and_log_relation_matches'] and
                 trace['matches_fixed_plan'] and device['after_status']['report_count'] in (0,1))
    passed=bool(host_result['simulation_execution_complete'] and related)
    failures=[]
    if not host_result['simulation_execution_complete']:failures.append('host_model_failed')
    if not device or not device['device_status_and_log_relation_matches']:failures.append('device_relation_failed')
    if not trace or not trace['matches_fixed_plan']:failures.append('control_dispatch_failed')
    if device and device['after_status']['report_count'] not in (0,1):failures.append('ambiguous_report_count')
    return dict(schema='A23-burst-simulation-collection-analysis-1',execution_mode='simulation',
                collection_integrity_verified=True,collection_manifest_sha256=sha(manifest),
                simulation_status_byte_binding_verified=True,simulation_device_log_byte_binding_verified=True,
                simulation_device_relation_matches=related,simulation_collection_pass=passed,failure_reasons=failures,
                host=host_result,device=device,device_error=device_error,control_trace=trace,
                device_log_bound=False,hardware_trigger_binding_verified=False,hardware_entry_enabled=False,
                hardware_verified=False,usb_strict_pass=False,baseline_accepted=False,allow_next_burst=False,
                callback_drain_verified=False,firmware_bytes_verified=False,bus_phase_verified=False,
                cross_clock_alignment_verified=False)


def freeze(host,synthetic_log,output):
    """Trusted quiescent inputs only. Do not overwrite or fabricate missing bytes."""
    host,synthetic_log,output=map(Path,(host,synthetic_log,output))
    checked=audit_host(host)
    require(checked['journal_core_binding_verified'],'host lacks committed own core')
    files={k:read_file(host/k.removeprefix('host/'),v) for k,v in LIMITS.items() if k.startswith('host/')}
    require(sha(files['host/journal.jsonl'])==checked['journal_sha256'],'host journal changed while freezing')
    original=replies(files['host/journal.jsonl'])
    files.update({'status-before.bin':original['before'],'status-after.bin':original['after'],
                  'device-log.txt':read_file(synthetic_log,LIMITS['device-log.txt']),'MOCK_ONLY.txt':MARKER})
    files['collection.json']=(json.dumps(metadata(files),sort_keys=True,indent=2)+'\n').encode()
    output.mkdir(mode=0o700);(output/'host').mkdir(mode=0o700);(output/'host/transfer').mkdir(mode=0o700)
    for name in sorted(files):durable_write(output/name,files[name])
    manifest=''.join(f'{sha(files[k])}  {k}\n' for k in sorted(files)).encode()
    durable_write(output/'SHA256SUMS',manifest)
    for directory in [output/'host/transfer',output/'host',output]:sync_dir(directory)
    durable_write(output/'COMMITTED',(sha(manifest)+'\n').encode());sync_dir(output);sync_dir(output.parent)
    return analyze(output)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    check=sub.add_parser('audit');check.add_argument('collection',type=Path)
    make=sub.add_parser('freeze');make.add_argument('host',type=Path);make.add_argument('synthetic_log',type=Path);make.add_argument('output',type=Path)
    args=parser.parse_args()
    try:result=analyze(args.collection) if args.command=='audit' else freeze(args.host,args.synthetic_log,args.output)
    except (ValueError,OSError,TypeError,KeyError,UnicodeError) as error:
        print(json.dumps(dict(error=str(error),hardware_verified=False,allow_next_burst=False)));return 2
    print(json.dumps(result,indent=2));return 0 if result['simulation_collection_pass'] else 1


if __name__=='__main__':raise SystemExit(main())
