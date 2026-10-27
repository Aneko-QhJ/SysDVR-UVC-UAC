#!/usr/bin/env python3
"""Offline build/freeze of the SDK receiver and one-use ticket; never captures."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid
from analyze_io_usb_host_evidence import require
from io_usb_host_probe_plan import HARDWARE_PLAN
from workflows.capture_io_usb_host_no_td import ROOT,TICKET,load,write_new,verify_prepared


def source_paths(root=ROOT):
    result=set(root.glob('host/io_usb_host*.[hm]'))|set(root.glob('tests/io_usb_host*.[hm]'))|set(root.glob('tests/test_io_usb_host*.py'))
    result |= set(root.glob('tools/*io_usb_host*.py'))
    result |= {root/'tools/experiment.py',root/'tools/workflows/capture_io_usb_host_no_td.py',
               root/'tools/audit_host_driver.py',root/'tools/audit_host_driver_dispatch.py',root.parents[1]/'source/uvc/iso_probe_protocol.h'}
    return sorted(result)


def prepare(output,validation):
    require(not TICKET.exists(),'SDK ticket already exists; no duplicate preparation')
    report=load(validation)
    require(report.get('passed') is True and report.get('usb_requests')==0 and type(report.get('usb_requests')) is int and
            report.get('driver_mock_scenarios')==18 and report.get('python_skipped')==0 and
            report.get('native_sanitizers')=='address,undefined','offline validation incomplete')
    repo=ROOT.parents[1]
    hashes={p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths()}
    require(report.get('source_hashes')==hashes,'validated sources changed')
    output=Path(output).resolve();output.mkdir(mode=0o700)
    for name in hashes:
        destination=output/'source'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(repo/name,destination)
    shutil.copy2(validation,output/'validation.json')
    prefix='research/usb-ds-iso/host/'
    inputs=[output/'source'/(prefix+f'io_usb_host_{name}.m') for name in
            ('transaction_owner','evidence','runtime_guard','session','sdk_adapter','no_td_driver','no_td_main')]
    command=['/usr/bin/clang','-std=c11','-O2','-fblocks','-fobjc-arc','-Wall','-Wextra','-Werror',
             '-framework','Foundation','-framework','IOUSBHost','-framework','IOKit']+[str(p) for p in inputs]+['-o',str(output/'receiver')]
    with (output/'build.log').open('x') as log: subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    described=subprocess.run([str(output/'receiver'),'--describe'],capture_output=True,check=True)
    require(json.loads(described.stdout)==HARDWARE_PLAN,'compiled receiver plan differs')
    (output/'describe.json').write_bytes(described.stdout)
    metadata=dict(schema='A23-IOUSBHost-build-1',backend='iousbhost-no-td-1',validation_passed=True,usb_requests_during_preparation=0,
        sd_copy_needed=False,device_revision='A23',plan=HARDWARE_PLAN,build_command=command,
        source_hashes={p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else '../../'+p.relative_to(repo).as_posix():
            hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths()})
    # Repo-level protocol header uses an explicit, separately pinned path.
    metadata['source_hashes'].pop('../../source/uvc/iso_probe_protocol.h')
    metadata['protocol_header_sha256']=hashes['source/uvc/iso_probe_protocol.h']
    write_new(output/'manifest.json',metadata)
    write_new(output/'build-command.json',command)
    # Include the command record too, then seal once.
    sums=''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(output).as_posix()}\n' for p in sorted(output.rglob('*')) if p.is_file())
    from analyze_io_usb_host_collection import durable_write,sync_dir
    durable_write(output/'SHA256SUMS',sums.encode());sync_dir(output)
    ticket=dict(schema='A23-IOUSBHost-preparation-1',backend='iousbhost-no-td-1',stage='prepared',remaining=1,
        preparation_id=uuid.uuid4().hex,build=str(output),plan=HARDWARE_PLAN,
        build_manifest_sha256=hashlib.sha256(sums.encode()).hexdigest(),receiver_sha256=hashlib.sha256((output/'receiver').read_bytes()).hexdigest())
    verify_prepared(ticket);write_new(TICKET,ticket)
    return dict(stage='prepared',remaining=1,build=str(output),ticket=str(TICKET),usb_accessed=False,sd_copy_needed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);parser.add_argument('validation',type=Path);args=parser.parse_args()
    try:print(json.dumps(prepare(args.output,args.validation),indent=2));return 0
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as error:print(str(error));return 2

if __name__=='__main__':raise SystemExit(main())
