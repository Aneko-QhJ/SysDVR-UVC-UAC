#!/usr/bin/env python3
"""Build a dormant receiver and return a zero-use record; never issue or launch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

from analyze_a23_waiting_entry import WAIT_PLAN,typed
from analyze_io_usb_host_evidence import require,unique_object
from analyze_io_usb_host_collection import durable_write,sync_dir
from workflows.artifacts import verify

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
PARENT=ROOT/'private/analysis/A23-waiting-entry-review-20261015'
PARENT_VALIDATION=PARENT.parent/'A23-waiting-entry-validation-20261015'
DEVICE=PARENT.parent/'A23-execution-v3-candidate-review-20261015'
NEW=('host/a23_waiting_receiver.h','host/a23_waiting_receiver.m','host/a23_waiting_build_guard.m',
    'host/a23_waiting_receiver_main.m','tools/build_a23_waiting_receiver.py',
    'tools/workflows/capture_a23_waiting_receiver.py','tools/audit_a23_waiting_receiver.py',
    'tests/a23_waiting_receiver_fixture.m','tests/test_a23_waiting_receiver.py')
DESCRIPTION=dict(schema='A23-waiting-receiver-description-1',backend='a23-waiting-burst-1',entry_plan=WAIT_PLAN,
    wait_budget_ns=120000000000,poll_period_ns=10000000,prepare_and_start_separate_turns=True,
    unresolved_process_policy='retain_no_kill_no_retry',hardware_verified=False,allow_next_burst=False)
POLICY=('hardware_verified','usb_strict_pass','allow_next_burst','baseline_accepted')
TOP={'manifest.json','describe.json','build-command.json','build.log','receiver','a23_waiting_build_binding.h'}


def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()


def compiler_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def plain(path,limit=32*1024*1024):
    path=Path(path);require(path.is_absolute() and path==path.resolve() and path.is_file() and not path.is_symlink(),'invalid file path')
    require(path.stat().st_size<=limit,'oversized file');raw=path.read_bytes();require(len(raw)<=limit,'file grew');return raw


def load(path):return json.loads(plain(path,131072),object_pairs_hook=unique_object)


def source_hashes(repo=REPO):
    repo=Path(repo);require(repo.is_absolute() and repo==repo.resolve(),'invalid source root')
    old=load(PARENT/'audit.json');names={'research/usb-ds-iso/'+n for n in set(old['source_hashes'])|set(NEW)}|set(old['production_sources_sha256'])
    result={n:sha(plain(repo/n,2*1024*1024)) for n in sorted(names)}
    for name,digest in old['source_hashes'].items():require(result['research/usb-ds-iso/'+name]==digest,'parent source drift')
    for name,digest in old['production_sources_sha256'].items():require(result[name]==digest,'production source drift')
    return result


def metadata(repo):
    return dict(schema='A23-waiting-receiver-build-1',backend='a23-waiting-burst-1',source_root=str(repo),
        source_hashes=source_hashes(repo),recipe_sha256=json.loads(plain(DEVICE/'audit.json',4*1024*1024),object_pairs_hook=unique_object)['recipe_digest'],
        description=DESCRIPTION,acquisition_enabled=False,attempt_issued=False)


def binding_header(meta):
    raw=canonical(meta)
    return ('/* Generated frozen binding; byte length excludes a NUL terminator. */\n'
        'static const unsigned char A23WaitingBuildBinding[] = {'+','.join(str(n) for n in raw)+'};\n').encode()


def write(path,value):durable_write(path,canonical(value));sync_dir(path.parent)


def seal(root):
    files=sorted(p for p in root.rglob('*') if p.is_file() and p not in (root/'SHA256SUMS',root/'COMMITTED'))
    for p in files:
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW);os.fsync(fd);os.close(fd)
    sums=''.join(sha(plain(p))+'  '+p.relative_to(root).as_posix()+'\n' for p in files).encode()
    durable_write(root/'SHA256SUMS',sums)
    for p in sorted((p for p in root.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):sync_dir(p)
    sync_dir(root);durable_write(root/'COMMITTED',(sha(sums)+'\n').encode());sync_dir(root);sync_dir(root.parent)


def verify_build(record,repo=REPO):
    require(type(record) is dict and record.get('schema')=='A23-waiting-receiver-record-1' and
        record.get('backend')=='a23-waiting-burst-1' and all(record.get(k) is False for k in POLICY),'invalid independent waiting record')
    require(type(record.get('preparation_id')) is str and str(uuid.UUID(record['preparation_id']))==record['preparation_id'],'invalid preparation UUID')
    build=Path(record['build']);require(build.is_absolute() and build==build.resolve() and build.is_dir(),'invalid build root')
    meta=metadata(Path(repo));require(typed(load(build/'manifest.json'),meta),'current build/source binding changed')
    require(typed(record.get('plan'),WAIT_PLAN) and record.get('recipe_sha256')==meta['recipe_sha256'],'record plan/recipe mismatch')
    require(plain(build/'a23_waiting_build_binding.h')==binding_header(meta),'generated binding changed')
    require(plain(build/'describe.json',16384)==canonical(DESCRIPTION),'description changed')
    require(all(sha(plain(build/'source'/n,2*1024*1024))==h for n,h in meta['source_hashes'].items()),'frozen source drift')
    sums=plain(build/'SHA256SUMS',1024*1024)
    require(sha(sums)==record['build_manifest_sha256'] and plain(build/'COMMITTED',65)==(sha(sums)+'\n').encode(),'build seal mismatch')
    expected=TOP|{'source/'+n for n in meta['source_hashes']};actual=set();entries=0
    for p in build.rglob('*'):
        entries+=1;require(entries<=512 and not p.is_symlink() and (p.is_file() or p.is_dir()),'invalid build tree')
        if p.is_file() and p not in (build/'SHA256SUMS',build/'COMMITTED'):actual.add(p.relative_to(build).as_posix())
    require(actual==expected and len(actual)<=256,'build inventory mismatch')
    required=''.join(sha(plain(build/n))+'  '+n+'\n' for n in sorted(expected)).encode()
    require(required==sums,'changed/partial/extra build manifest')
    require(sha(plain(build/'receiver'))==record['receiver_sha256'],'receiver changed')
    require(metadata(Path(repo))==meta,'source changed during verification')
    return build


def build(output,repo=REPO):
    repo=Path(repo);output=Path(output)
    require(output.is_absolute() and output==output.resolve() and not output.exists(),'new canonical output required')
    for p in (PARENT,PARENT_VALIDATION,DEVICE):verify(p)
    meta=metadata(repo);output.mkdir(mode=0o700,parents=True)
    for name,digest in meta['source_hashes'].items():
        raw=plain(repo/name,2*1024*1024);require(sha(raw)==digest,'source changed before copy')
        dst=output/'source'/name;dst.parent.mkdir(parents=True,exist_ok=True);durable_write(dst,raw)
    durable_write(output/'a23_waiting_build_binding.h',binding_header(meta));write(output/'manifest.json',meta)
    compiler=subprocess.run(['xcrun','-f','clang'],capture_output=True,text=True,check=True).stdout.strip()
    sdk=subprocess.run(['xcrun','--show-sdk-path'],capture_output=True,text=True,check=True).stdout.strip();compiler_hash=compiler_sha(compiler)
    frozen=output/'source/research/usb-ds-iso';inputs=[frozen/'host'/('io_usb_host_'+n+'.m') for n in
        ('transaction_owner','evidence','runtime_guard','session','sdk_adapter','burst_sdk_transport','burst_sdk_driver','burst_entry')]
    inputs += [frozen/n for n in ('host/a23_passive_wait_adapter.c','host/a23_passive_wait_iokit.c','host/a23_waiting_burst_entry.m',
        'host/a23_waiting_receiver.m','host/a23_waiting_build_guard.m','host/a23_waiting_receiver_main.m')]
    command=[compiler,'-isysroot',sdk,'-std=c11','-O2','-fblocks','-fobjc-arc','-Wall','-Wextra','-Werror','-I'+str(output),
        '-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',*map(str,inputs),'-o',str(output/'receiver')]
    write(output/'build-command.json',dict(command=command,compiler_sha256=compiler_hash,sdk=sdk))
    with (output/'build.log').open('x') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    described=subprocess.run([str(output/'receiver'),'--describe'],check=True,capture_output=True).stdout
    require(described==canonical(DESCRIPTION),'native description differs');durable_write(output/'describe.json',described)
    require(metadata(repo)==meta and compiler_sha(compiler)==compiler_hash,'source/compiler changed during build')
    seal(output)
    record=dict(schema='A23-waiting-receiver-record-1',backend='a23-waiting-burst-1',stage='offline_build_ready',remaining=0,acquisition_enabled=False,
        preparation_id=str(uuid.uuid4()),build=str(output),receiver_sha256=sha(plain(output/'receiver')),
        build_manifest_sha256=sha(plain(output/'SHA256SUMS')),recipe_sha256=meta['recipe_sha256'],plan=WAIT_PLAN,**{k:False for k in POLICY})
    verify_build(record,repo)
    check=subprocess.run([str(output/'receiver'),'--check-build',str(output)],capture_output=True,text=True,check=True)
    require(json.loads(check.stdout)['source_closure_checked'] is True,'native source guard failed')
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);args=p.parse_args()
    print(json.dumps(build(args.output),indent=2))
