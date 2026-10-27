#!/usr/bin/env python3
"""Build/freeze receiver and run injected loop only. No capture invocation."""
import argparse
import json
from pathlib import Path
import subprocess

import build_a23_waiting_receiver as builder
import analyze_a23_waiting_entry as waiting
from workflows.artifacts import verify


def run(output,repo=builder.REPO):
    output=Path(output);require=builder.require
    require(output.is_absolute() and output==output.resolve() and not output.exists(),'new canonical review required');output.mkdir(parents=True)
    record=builder.build(output/'receiver-build',repo);builder.write(output/'offline-record.json',record)
    frozen=output/'receiver-build/source/research/usb-ds-iso'
    command=builder.load(output/'receiver-build/build-command.json')['command'];compiler=command[0];sdk=command[2]
    files=[frozen/'host'/('io_usb_host_'+n+'.m') for n in ('transaction_owner','evidence','runtime_guard','session','sdk_adapter','burst_sdk_transport','burst_sdk_driver','burst_entry')]
    files += [frozen/n for n in ('host/a23_passive_wait_adapter.c','host/a23_passive_wait_iokit.c','host/a23_waiting_burst_entry.m','host/a23_waiting_receiver.m','host/a23_waiting_build_guard.m','tests/a23_waiting_receiver_fixture.m')]
    command=[compiler,'-isysroot',sdk,'-std=c11','-fblocks','-fobjc-arc','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I'+str(output/'receiver-build'),
        '-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',*map(str,files),'-o',str(output/'injected-loop')]
    builder.write(output/'native-command.json',command)
    with (output/'native-build.log').open('x') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    with (output/'native.log').open('x') as log:subprocess.run([str(output/'injected-loop'),str(output/'native-fixtures')],check=True,stdout=log,stderr=subprocess.STDOUT)
    cases={}
    for p in sorted((output/'native-fixtures').iterdir()):
        try:analysis=waiting.analyze(p)
        except ValueError as e:
            require(p.name=='signal-before-begin','unexpected incomplete journal: '+p.name)
            analysis=dict(supplied_order_consistent=False,error=str(e),pre_wait_signal_prefix_preserved=True,hardware_verified=False)
        cases[p.name]=analysis;builder.write(p/'loop-analysis.json',analysis)
    builder.verify_build(record,repo)
    previous=builder.load(builder.PARENT/'audit.json')
    for name,digest in previous['tickets_sha256'].items():require(builder.sha(builder.plain(builder.PARENT.parent/name))==digest,'live ticket changed')
    result=dict(schema='A23-waiting-receiver-review-1',offline_record=record,source_hashes=builder.source_hashes(repo),native_loop_cases=cases,
        native_loop_case_count=len(cases),native_sanitizers='address,undefined',prior_seals=[verify(p) for p in (builder.PARENT,builder.PARENT_VALIDATION,builder.DEVICE)],
        tickets_sha256=previous['tickets_sha256'],production_sources_sha256=previous['production_sources_sha256'],
        receiver_capture_invoked=False,attempt_issued=False,remaining=0,native_iokit_calls=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,hardware_verified=False,root_cause_confirmed=False)
    builder.write(output/'audit.json',result);builder.seal(output);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=run(a.output);print(json.dumps({k:v for k,v in r.items() if k not in ('source_hashes','native_loop_cases')},indent=2))
