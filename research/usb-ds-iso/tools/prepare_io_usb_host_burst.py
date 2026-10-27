#!/usr/bin/env python3
"""Build/freeze a dormant SDK burst receiver. Issues no usable capture count."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import uuid
from analyze_io_usb_host_evidence import require
from analyze_io_usb_host_collection import durable_write,sync_dir
from io_usb_host_burst_entry_plan import PLAN,SCOPE,validate_plan
from workflows.capture_io_usb_host_burst import ROOT,TICKET,POLICY,load,write_new,verify_build,source_hashes

def prepare(output,validation,*,ticket_path=TICKET,root=ROOT):
    require(not ticket_path.exists() and not ticket_path.is_symlink(),'independent burst record already exists; no renewal')
    report=load(validation);hashes=source_hashes(root)
    require(report.get('passed') is True and report.get('native_entry_passed') is True and report.get('receiver_guards_passed') is True and
            report.get('native_sanitizers')=='address,undefined' and type(report.get('python_skipped')) is int and report['python_skipped']==0 and
            all(type(report.get(k)) is int and report[k]==0 for k in ('usb_requests','registry_calls','real_sdk_objects','sd_accesses')) and
            report.get('source_hashes')==hashes,'offline validation missing or sources changed')
    output=Path(output)
    require(output.is_absolute() and output==output.resolve(),'output must be a canonical new directory')
    output.mkdir(mode=0o700);repo=root.parents[1]
    for name,sha in hashes.items():
        raw=(repo/name).read_bytes();require(hashlib.sha256(raw).hexdigest()==sha,'source changed during freeze')
        destination=output/'source'/name;destination.parent.mkdir(parents=True,exist_ok=True);durable_write(destination,raw)
    durable_write(output/'validation.json',Path(validation).read_bytes())
    inputs=[output/'source/research/usb-ds-iso/host'/f'io_usb_host_{name}.m' for name in
            ('transaction_owner','evidence','runtime_guard','session','sdk_adapter','burst_sdk_transport','burst_sdk_driver','burst_entry','burst_main')]
    command=['/usr/bin/clang','-std=c11','-O2','-fblocks','-fobjc-arc','-Wall','-Wextra','-Werror',
             '-framework','Foundation','-framework','IOUSBHost','-framework','IOKit']+[str(p) for p in inputs]+['-o',str(output/'receiver')]
    write_new(output/'build-command.json',command)
    with (output/'build.log').open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    described=subprocess.run([str(output/'receiver'),'--describe'],capture_output=True,check=True);validate_plan(json.loads(described.stdout))
    durable_write(output/'describe.json',described.stdout)
    require(source_hashes(root)==hashes,'source changed before build seal')
    metadata=dict(schema='A23-burst-sdk-build-1',backend='iousbhost-single-burst-1',validation_passed=True,
        acquisition_enabled=False,usb_requests_during_preparation=0,sd_copy_needed=False,device_revision='A23',
        plan=PLAN,diagnostic_scope=SCOPE,source_hashes=hashes,build_command=command)
    write_new(output/'manifest.json',metadata)
    sums=''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(output).as_posix()}\n' for p in sorted(output.rglob('*')) if p.is_file()).encode()
    for directory in sorted((p for p in output.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):sync_dir(directory)
    durable_write(output/'SHA256SUMS',sums);sync_dir(output)
    durable_write(output/'COMMITTED',(hashlib.sha256(sums).hexdigest()+'\n').encode());sync_dir(output);sync_dir(output.parent)
    ticket=dict(schema='A23-burst-sdk-preparation-1',backend='iousbhost-single-burst-1',stage='offline_build_ready',remaining=0,
        acquisition_enabled=False,preparation_id=str(uuid.uuid4()),build=str(output),plan=PLAN,diagnostic_scope=SCOPE,
        build_manifest_sha256=hashlib.sha256(sums).hexdigest(),receiver_sha256=hashlib.sha256((output/'receiver').read_bytes()).hexdigest(),
        **{k:False for k in POLICY})
    verify_build(ticket,root);write_new(ticket_path,ticket)
    return dict(stage=ticket['stage'],remaining=0,acquisition_enabled=False,build=str(output),ticket=str(ticket_path),usb_accessed=False,sd_copy_needed=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);parser.add_argument('validation',type=Path);args=parser.parse_args()
    try:print(json.dumps(prepare(args.output,args.validation),indent=2));return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,subprocess.CalledProcessError) as error:print(str(error));return 2
if __name__=='__main__':raise SystemExit(main())
