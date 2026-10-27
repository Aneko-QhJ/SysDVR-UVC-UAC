#!/usr/bin/env python3
"""Audit static waiting/SDK/EXE3 collections using explicitly generated models."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import build_a23_waiting_receiver as builder
import collect_a23_waiting_execution as collection
from workflows.artifacts import verify

ROOT=builder.ROOT;REPO=builder.REPO
PARENT=ROOT/'private/analysis/A23-waiting-receiver-review-20261015'
VALIDATED=PARENT.parent/'A23-waiting-receiver-validation-20261015'
DEVICE=builder.DEVICE
HISTORICAL=ROOT/'private/runs/A-A23-HS-IOUSBHost-burst-20261013-090224-3c3789da'
NEW=('tools/collect_a23_waiting_execution.py','tests/a23_waiting_execution_fixture.c',
     'tools/audit_a23_waiting_collection.py','tests/test_a23_waiting_collection.py')
RECIPE='03'+'00'*31
MODES=('matching','sequence-mismatch','shape-mismatch','primary-receipt-failure','large-clock')


def header_closure(root):
    result={};pending=['ep0_execution_v3.h']
    while pending:
        name=pending.pop()
        if name in result:continue
        if not re.fullmatch(r'[a-z0-9_]+\.h',name) or len(result)>=64:raise ValueError('Unexpected serializer header')
        raw=builder.plain(root/name,65536);result[name]=collection.core.sha(raw)
        pending.extend(re.findall(r'#include\s+"([^"]+)"',raw.decode()))
    return dict(sorted(result.items()))


def run(output):
    output=Path(output)
    if not output.is_absolute() or output!=output.resolve() or output.exists():raise ValueError('new canonical output required')
    seals=[verify(p) for p in (PARENT,VALIDATED,DEVICE,HISTORICAL)]
    old=builder.load(PARENT/'audit.json');sources=builder.source_hashes()
    if sources!=old['source_hashes']:raise ValueError('Parent source drift')
    sources.update({'research/usb-ds-iso/'+n:builder.sha(builder.plain(ROOT/n)) for n in NEW})
    tickets={n:builder.sha(builder.plain(PARENT.parent/n)) for n in old['tickets_sha256']}
    if tickets!=old['tickets_sha256']:raise ValueError('Ticket drift')
    headers=header_closure(DEVICE/'window-30s/source/uvc');output.mkdir(parents=True)
    for n,h in sources.items():
        dst=output/'source'/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/n,dst)
        if builder.sha(builder.plain(dst))!=h:raise ValueError('Source changed while copying')
    for n,h in headers.items():
        dst=output/'serializer-headers'/n;dst.parent.mkdir(exist_ok=True);shutil.copyfile(DEVICE/'window-30s/source/uvc'/n,dst)
        if builder.sha(builder.plain(dst))!=h:raise ValueError('Serializer header changed')
    compiler=subprocess.run(['xcrun','-f','clang'],capture_output=True,text=True,check=True).stdout.strip()
    compiler_hash=builder.compiler_sha(compiler)
    command=[compiler,'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I'+str(output/'serializer-headers'),str(output/'source/research/usb-ds-iso/tests/a23_waiting_execution_fixture.c'),'-o',str(output/'serializer-model')]
    builder.write(output/'native-command.json',command)
    with (output/'native-build.log').open('x') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    models=output/'models';models.mkdir();native={}
    for name in MODES:
        p=subprocess.run([str(output/'serializer-model'),name,str(models/name)],check=True,capture_output=True,text=True)
        native[name]=json.loads(p.stdout);builder.write(models/(name+'.json'),native[name])
    (models/'MOCK_ONLY.txt').write_text('New bytes from injected requests, terminal reports and receipts; no original capture is edited.\n')
    supplied=output/'supplied';supplied.mkdir();normal=PARENT/'native-fixtures/normal'
    def host_variant(name,change):
        p=supplied/name;shutil.copytree(normal,p);change(p);return p
    def json_change(path,change):
        d=json.loads(path.read_bytes());change(d);path.write_bytes(collection.core.canonical(d))
    def wait_binding(p):
        rows=collection.waiting.lines(p/'wait.jsonl')
        for r in rows:
            if r['event']=='prepared':r['details']['binding']['session_id']='00000000-0000-4000-8000-000000000000'
        (p/'wait.jsonl').write_bytes(b''.join(collection.core.canonical(r) for r in rows))
    variants={
        'missing-wait':host_variant('missing-wait',lambda p:(p/'wait.jsonl').unlink()),
        'missing-entry':host_variant('missing-entry',lambda p:(p/'waiting-entry-result.json').unlink()),
        'partial-wait':host_variant('partial-wait',lambda p:(p/'wait.jsonl').write_bytes((p/'wait.jsonl').read_bytes()[:90])),
        'malformed-wait':host_variant('malformed-wait',lambda p:(p/'wait.jsonl').write_bytes(b'[]\n')),
        'partial-sdk':host_variant('partial-sdk',lambda p:(p/'session.jsonl').write_bytes((p/'session.jsonl').read_bytes()[:120])),
        'malformed-sdk':host_variant('malformed-sdk',lambda p:(p/'session.jsonl').write_bytes(b'[]\n')),
        'waiting-binding':host_variant('waiting-binding',wait_binding),
        'result-contradiction':host_variant('result-contradiction',lambda p:json_change(p/'waiting-entry-result.json',lambda d:d['host_result'].update(exit_code=1))),
        'outer-lifecycle':host_variant('outer-lifecycle',lambda p:json_change(p/'waiting-entry-result.json',lambda d:d.update(finished=False))),
    }
    partial=output/'partial-execution.bin';partial.write_bytes((models/'matching.execution.bin').read_bytes()[:160])
    different=output/'different-primary.bin';different.write_bytes(b'failed/partial original bytes\x00\xff')
    receipt_partial=output/'receipt-failure-partial-primary.bin';receipt_partial.write_bytes((models/'primary-receipt-failure.primary.bin').read_bytes()[:60])
    dest=output/'collections';dest.mkdir();cases={}
    def collect(name,host=normal,mode='matching',execution=None,recipe=RECIPE,primary=True):
        e=execution or models/(mode+'.execution.bin')
        p=models/(mode+'.primary.bin') if primary is True else primary if primary else None
        cases[name]=collection.freeze(host,e,dest/name,recipe,p)
    for name in MODES:collect(name,mode=name)
    for name,p in variants.items():collect(name,host=p)
    collect('missing-primary',primary=False);collect('different-primary',primary=different)
    collect('receipt-failure-partial-primary',mode='primary-receipt-failure',primary=receipt_partial)
    collect('wrong-recipe',recipe='04'+'00'*31);collect('partial-execution',execution=partial)
    collect('retained-iso',host=PARENT/'native-fixtures/iso-pending')
    collect('preflight',host=PARENT/'native-fixtures/signal-between-turns')
    collect('pre-wait-signal',host=PARENT/'native-fixtures/signal-before-begin')
    collect('failed-journal-ack',host=builder.PARENT/'fixtures/journal-adapter-6')
    collect('historical-failure',host=HISTORICAL/'host')
    if sources!={n:builder.sha(builder.plain(REPO/n)) for n in sources} or headers!=header_closure(DEVICE/'window-30s/source/uvc'):
        raise ValueError('Input changed during collection audit')
    if builder.compiler_sha(compiler)!=compiler_hash:raise ValueError('Compiler changed')
    for n,h in tickets.items():
        if builder.sha(builder.plain(PARENT.parent/n))!=h:raise ValueError('Ticket changed')
    for p in (PARENT,VALIDATED,DEVICE,HISTORICAL):verify(p)
    result=dict(schema='A23-waiting-collection-review-1',source_hashes=sources,serializer_headers_sha256=headers,
        compiler=compiler,compiler_sha256=compiler_hash,native_models=native,native_execution_count=len(native),
        native_sanitizers='address,undefined',collection_cases=cases,collection_count=len(cases),
        sealed_inputs=seals,tickets_sha256=tickets,production_sources_sha256=old['production_sources_sha256'],
        parent_receiver_record_unchanged=True,new_matching_models_not_physical_captures=True,
        receiver_capture_invoked=False,native_iokit_calls=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,
        attempt_issued=False,hardware_verified=False,root_cause_confirmed=False)
    builder.write(output/'audit.json',result);builder.seal(output);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    r=run(a.output);print(json.dumps({k:v for k,v in r.items() if k not in ('source_hashes','collection_cases')},indent=2))
