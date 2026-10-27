#!/usr/bin/env python3
"""Freeze and exercise the isolated waiting entry with injected operations only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import analyze_a23_waiting_entry as analysis
from workflows.artifacts import verify

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
PARENT=ROOT/'private/analysis/A23-host-execution-link-final-review-20261015'
VALIDATED=PARENT.parent/'A23-host-execution-link-final-validation-20261015'
ANCESTORS=(PARENT.parent/'A23-execution-v3-candidate-review-20261015',
    PARENT.parent/'A23-execution-v3-candidate-validation-20261015',
    ROOT/'private/runs/A-A23-HS-IOUSBHost-burst-20261013-090224-3c3789da')
NEW=('host/a23_waiting_burst_entry.h','host/a23_waiting_burst_entry.m',
     'tests/a23_waiting_burst_entry_fixture.m','tools/analyze_a23_waiting_entry.py',
     'tools/audit_a23_waiting_entry.py','tests/test_a23_waiting_entry.py')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal(root):
    # Nested transfer manifests must be in the outer inventory too.
    sums=''.join(sha(p)+'  '+p.relative_to(root).as_posix()+'\n' for p in sorted(root.rglob('*'))
                 if p.is_file() and p not in (root/'SHA256SUMS',root/'COMMITTED')).encode()
    (root/'SHA256SUMS').write_bytes(sums)
    (root/'COMMITTED').write_text(hashlib.sha256(sums).hexdigest()+'\n')


def run(output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Refusing existing output')
    parents=[verify(p) for p in (PARENT,VALIDATED,*ANCESTORS)]
    old=json.loads((PARENT/'audit.json').read_text())
    for name,digest in old['source_hashes'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Parent source changed: '+name)
    protected={n:sha(REPO/n) for n in old['production_sources_sha256']}
    tickets={n:sha(PARENT.parent/n) for n in old['tickets_sha256']}
    if protected!=old['production_sources_sha256'] or tickets!=old['tickets_sha256']:raise ValueError('Protected input drift')
    # Explicit inventory includes every compiled native input/header, fixture
    # include, and the wait .c/.h missed by the old capture workflow's glob.
    names=set(old['source_hashes'])|set(NEW)|{'tests/io_usb_host_burst_sdk_driver_test.m','tests/io_usb_host_mock_adapter.h','tools/io_usb_host_burst_entry_plan.py'}
    names.update(p.relative_to(ROOT).as_posix() for pattern in ('host/io_usb_host*.h','host/io_usb_host*.m','tools/analyze_io_usb_host*.py') for p in ROOT.glob(pattern))
    hashes={n:sha(ROOT/n) for n in sorted(names)};output.mkdir(parents=True)
    for name,digest in hashes.items():
        dst=output/'source/research/usb-ds-iso'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst)
        if sha(dst)!=digest:raise ValueError('Source changed while copying')
    for name,digest in protected.items():
        dst=output/'source'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/name,dst)
        if sha(dst)!=digest:raise ValueError('Protected source changed while copying')
    compiler=subprocess.run(['xcrun','-f','clang'],capture_output=True,text=True,check=True).stdout.strip()
    sdk=subprocess.run(['xcrun','--show-sdk-path'],capture_output=True,text=True,check=True).stdout.strip()
    compiler_hash=sha(compiler);frozen=output/'source/research/usb-ds-iso'
    inputs=[frozen/'host'/('io_usb_host_'+n+'.m') for n in ('transaction_owner','evidence','runtime_guard','session','sdk_adapter','burst_sdk_transport','burst_sdk_driver','burst_entry')]
    inputs += [frozen/n for n in ('host/a23_passive_wait_adapter.c','host/a23_passive_wait_iokit.c','host/a23_waiting_burst_entry.m','tests/a23_waiting_burst_entry_fixture.m')]
    command=[compiler,'-isysroot',sdk,'-std=c11','-fblocks','-fobjc-arc','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',*map(str,inputs),'-o',str(output/'injected-entry')]
    (output/'compile-command.json').write_text(json.dumps(command,indent=2)+'\n')
    with (output/'compile.log').open('x') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    with (output/'native.log').open('x') as log:subprocess.run([str(output/'injected-entry'),str(output/'fixtures')],check=True,stdout=log,stderr=subprocess.STDOUT)
    described=subprocess.run([str(output/'injected-entry'),'--describe'],capture_output=True,check=True)
    (output/'describe.json').write_bytes(described.stdout)
    if not analysis.typed(json.loads(described.stdout),analysis.WAIT_PLAN):raise ValueError('Native/Python plan mismatch')
    cases={}
    for directory in sorted((output/'fixtures').iterdir()):
        result=analysis.analyze(directory);cases[directory.name]=result
        (directory/'waiting-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    for base,group in ((ROOT,hashes),(REPO,protected),(PARENT.parent,tickets)):
        if {n:sha(base/n) for n in group}!=group:raise ValueError('Input changed during audit')
    if sha(compiler)!=compiler_hash:raise ValueError('Compiler changed')
    for p in (PARENT,VALIDATED,*ANCESTORS):verify(p)
    result=dict(schema='A23-waiting-entry-review-1',source_hashes=hashes,production_sources_sha256=protected,tickets_sha256=tickets,
        parent_seals=parents,compiler=compiler,compiler_sha256=compiler_hash,sdk=sdk,
        native_case_count=len(cases),native_cases=cases,native_sanitizers='address,undefined',
        compiled_from_frozen_sources=True,native_iokit_bindings_linked=True,native_iokit_bindings_executed=False,
        dormant_entry_component_integrated=True,live_capture_launcher_integrated=False,build_gate_integrated=False,
        permit_issues_attempts=False,real_sdk_objects=0,native_iokit_calls=0,usb_requests=0,sd_accesses=0,
        attempt_issued=False,hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n');seal(output)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    r=run(args.output);print(json.dumps({k:v for k,v in r.items() if k not in ('source_hashes','native_cases')},indent=2))
