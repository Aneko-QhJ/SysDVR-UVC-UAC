#!/usr/bin/env python3
"""Build an isolated lead32 receiver, retaining the path-span device materials. Always returns zero uses."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid

import a23_lead32_binding as device
import build_a23_waiting_receiver as old
from workflows.artifacts import verify

ROOT=old.ROOT;REPO=old.REPO;PARENT=ROOT/'private/analysis/A23-iso-retention-window-validation-20261017';DEVICE=device.DEVICE
plain=old.plain;sha=old.sha;canonical=old.canonical;write=old.write
load=device.load;require=old.require;WAIT_PLAN=device.WAIT_PLAN;POLICY=old.POLICY
DESCRIPTION={**old.DESCRIPTION,'schema':'A23-waiting-receiver-description-6',
    'device_binding_schema':'A23-path-span-host-device-binding-1','device_configuration':'path-span-window-30s','host_configuration':'host-lead32-window-1','entry_plan':WAIT_PLAN}
NEW=('host/a23_lead32_policy.h','tools/a23_lead32_binding.py','tools/build_a23_lead32_receiver.py',
     'tools/audit_a23_lead32_receiver.py','tests/a23_lead32_policy_fixture.c','tests/test_a23_lead32_receiver.py')

TOP=old.TOP|{'device-binding.json'}


def description(bound):
    return {**DESCRIPTION,'parent_input_digest':bound['parent_input_digest'],'runtime_recipe_sha256':bound['runtime_recipe_sha256'],
        'device_elf_sha256':bound['device_elf_sha256'],**{n:bound[n] for n in device.EXTRA},'device_binding_sha256':device.binding_hash(bound)}


def seal(root):
    # Sort relative path strings, including '-' versus '/' across directories.
    root=Path(root);files={p.relative_to(root).as_posix():p for p in root.rglob('*')
        if p.is_file() and p not in (root/'SHA256SUMS',root/'COMMITTED')}
    for p in files.values():
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW);os.fsync(fd);os.close(fd)
    sums=''.join(sha(plain(files[n]))+'  '+n+'\n' for n in sorted(files)).encode()
    old.durable_write(root/'SHA256SUMS',sums)
    for p in sorted((p for p in root.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):old.sync_dir(p)
    old.sync_dir(root);old.durable_write(root/'COMMITTED',(sha(sums)+'\n').encode());old.sync_dir(root);old.sync_dir(root.parent)


def source_hashes(repo=REPO):
    repo=Path(repo);require(repo.is_absolute() and repo==repo.resolve(),'canonical source root required')
    previous=load(PARENT/'validation.json');result=dict(previous['source_hashes'])
    for n,h in result.items():require(sha(plain(repo/n,2*1024*1024))==h,'parent source drift: '+n)
    for n in NEW:
        name='research/usb-ds-iso/'+n;require(name not in result,'new source overlaps parent')
        result[name]=sha(plain(repo/name,2*1024*1024))
    return dict(sorted(result.items()))


def metadata(repo=REPO,device_root=DEVICE/'candidate'):
    bound=device.identity(device_root);hashes=source_hashes(repo)
    raws={n:plain(Path(repo)/n,2*1024*1024) for n in hashes}
    generated=device.generated(raws,bound)
    return dict(schema='A23-waiting-receiver-build-6',backend='a23-waiting-burst-1',source_root=str(repo),source_hashes=hashes,
        device_binding=bound,device_binding_sha256=device.binding_hash(bound),recipe_sha256=bound['runtime_recipe_sha256'],
        generated_hashes={n:sha(raw) for n,raw in generated.items()},description=description(bound),acquisition_enabled=False,attempt_issued=False)


def binding_header(meta):return old.binding_header(meta)


def verify_build(record,repo=REPO):
    require(type(record) is dict and record.get('schema')=='A23-waiting-receiver-record-6' and
        record.get('backend')=='a23-waiting-burst-1' and all(record.get(k) is False for k in POLICY),'invalid bound receiver record')
    require(type(record.get('preparation_id')) is str and str(uuid.UUID(record['preparation_id']))==record['preparation_id'],'invalid preparation UUID')
    bound=record.get('device_binding');require(type(bound) is dict and type(bound.get('device_source_root')) is str,'missing device identity')
    build=Path(record['build']);require(build.is_absolute() and build==build.resolve() and build.is_dir(),'invalid bound build path')
    meta=metadata(Path(repo),Path(bound['device_source_root']))
    require(old.typed(load(build/'manifest.json'),meta),'current/frozen device or build metadata mismatch')
    require(old.typed(bound,meta['device_binding']) and record.get('device_binding_sha256')==meta['device_binding_sha256'] and
        record.get('recipe_sha256')==meta['recipe_sha256'] and old.typed(record.get('plan'),WAIT_PLAN),'record/device/plan mismatch')
    require(plain(build/'a23_waiting_build_binding.h')==binding_header(meta),'embedded header changed')
    require(plain(build/'device-binding.json')==canonical(bound) and plain(build/'describe.json')==canonical(description(bound)),'description/device binding changed')
    sources={n:plain(build/'source'/n,2*1024*1024) for n in meta['source_hashes']}
    require(all(sha(raw)==meta['source_hashes'][n] for n,raw in sources.items()),'frozen source drift')
    generated=device.generated(sources,bound)
    require(all(plain(build/'generated'/n)==raw for n,raw in generated.items()),'generated native source drift')
    require(all(sha(plain(build/'device'/n))==h for n,h in bound['artifact_hashes'].items()),'frozen device drift')
    expected=TOP|{'source/'+n for n in sources}|{'generated/'+n for n in generated}|{'device/'+n for n in device.FILES}
    entries=list(build.rglob('*'));require(len(entries)<=768 and all(not p.is_symlink() and (p.is_file() or p.is_dir()) for p in entries),'invalid bound build tree')
    actual={p.relative_to(build).as_posix() for p in entries if p.is_file() and p not in (build/'SHA256SUMS',build/'COMMITTED')}
    require(actual==expected and len(actual)<=320,'bound build inventory mismatch')
    sums=plain(build/'SHA256SUMS',1024*1024)
    require(sha(sums)==record['build_manifest_sha256'] and plain(build/'COMMITTED',65)==(sha(sums)+'\n').encode(),'bound build seal mismatch')
    require(sums==''.join(sha(plain(build/n))+'  '+n+'\n' for n in sorted(expected)).encode(),'bound manifest entries changed')
    require(sha(plain(build/'receiver'))==record['receiver_sha256'],'receiver changed')
    require(metadata(Path(repo),Path(bound['device_source_root']))==meta,'source/device changed during verification')
    return build


def native_inputs(build,fixture=False):
    build=Path(build);frozen=build/'source/research/usb-ds-iso'
    inputs=[(build/'generated' if n in ('runtime_guard','burst_sdk_transport','burst_sdk_driver') else frozen/'host')/('io_usb_host_'+n+'.m') for n in
        ('transaction_owner','evidence','runtime_guard','session','sdk_adapter','burst_sdk_transport','burst_sdk_driver','burst_entry')]
    inputs += [frozen/'host'/n for n in ('a23_passive_wait_adapter.c','a23_passive_wait_iokit.c')]
    inputs += [build/'generated'/n for n in ('a23_waiting_burst_entry.m','a23_waiting_receiver.m','a23_waiting_build_guard.m')]
    inputs += [build/'generated/lead32_loop_fixture.m' if fixture else frozen/'host/a23_waiting_receiver_main.m']
    return inputs


def compile_command(build,binary,fixture=False):
    compiler=subprocess.check_output(['xcrun','-f','clang'],text=True).strip()
    sdk=subprocess.check_output(['xcrun','--show-sdk-path'],text=True).strip();build=Path(build)
    return [compiler,'-isysroot',sdk,'-std=c11','-fblocks','-fobjc-arc','-Wall','-Wextra','-Werror',
        *(['-fsanitize=address,undefined'] if fixture else ['-O2']),'-I'+str(build),'-I'+str(build/'generated'),
        '-I'+str(build/'source/research/usb-ds-iso/host'),'-I'+str(build/'source/source/uvc'),'-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',
        *map(str,native_inputs(build,fixture)),'-o',str(binary)]


def build(output,repo=REPO,device_root=DEVICE/'candidate'):
    output=Path(output);repo=Path(repo)
    require(output.is_absolute() and output==output.resolve() and not output.exists(),'new canonical output required')
    for p in (PARENT,PARENT.parent/'A23-path-span-device-validation-20261016',DEVICE):verify(p)
    meta=metadata(repo,device_root);output.mkdir(parents=True,mode=0o700)
    raws={n:plain(repo/n,2*1024*1024) for n in meta['source_hashes']}
    for n,raw in raws.items():
        require(sha(raw)==meta['source_hashes'][n],'source changed before copy')
        target=output/'source'/n;target.parent.mkdir(parents=True,exist_ok=True);old.durable_write(target,raw)
    for n,raw in device.generated(raws,meta['device_binding']).items():
        target=output/'generated'/n;target.parent.mkdir(exist_ok=True);old.durable_write(target,raw)
    for n,h in meta['device_binding']['artifact_hashes'].items():
        raw=plain(Path(device_root)/n);require(sha(raw)==h,'device changed before copy')
        target=output/'device'/n;target.parent.mkdir(parents=True,exist_ok=True);old.durable_write(target,raw)
    old.durable_write(output/'a23_waiting_build_binding.h',binding_header(meta));write(output/'manifest.json',meta)
    write(output/'device-binding.json',meta['device_binding']);command=compile_command(output,output/'receiver')
    compiler_hash=old.compiler_sha(command[0]);write(output/'build-command.json',dict(command=command,compiler_sha256=compiler_hash,sdk=command[2]))
    with (output/'build.log').open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    described=subprocess.check_output([str(output/'receiver'),'--describe']);require(described==canonical(description(meta['device_binding'])),'bound native description mismatch')
    old.durable_write(output/'describe.json',described)
    require(metadata(repo,device_root)==meta and old.compiler_sha(command[0])==compiler_hash,'build inputs/compiler changed')
    seal(output)
    record=dict(schema='A23-waiting-receiver-record-6',backend='a23-waiting-burst-1',stage='offline_build_ready',remaining=0,acquisition_enabled=False,
        preparation_id=str(uuid.uuid4()),build=str(output),receiver_sha256=sha(plain(output/'receiver')),build_manifest_sha256=sha(plain(output/'SHA256SUMS')),
        recipe_sha256=meta['recipe_sha256'],device_binding=meta['device_binding'],device_binding_sha256=meta['device_binding_sha256'],plan=WAIT_PLAN,
        **{k:False for k in POLICY})
    verify_build(record,repo)
    checked=json.loads(subprocess.check_output([str(output/'receiver'),'--check-build',str(output)]))
    require(checked['recipe_sha256']==meta['recipe_sha256'] and checked['device_binding_sha256']==meta['device_binding_sha256'],'native device guard mismatch')
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(build(a.output),indent=2))
