"""Saved A23 history inventory and a temporary-only durable reservation model.

No production issuer or hardware entry. The inventory has an explicit local
scope and cannot authenticate unrecorded history or malicious file replacement.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import struct
import uuid

import a23_sequence_witness_model as model
import prepare_a23_lead32_once as once
import path_span_card_workflow as card

b=once.build;A=once.ANALYSIS;SCOPE=A/'A23-sequence-history-20261017'


def inventory(root):
    root=Path(root);files={};observed=set();errors=[]
    def walk(value):
        if type(value) is dict:
            for key,item in value.items():
                if key in ('sequence','first_sequence') and type(item) is int and 0<=item<=65535:observed.add(item)
                if key=='value' and value.get('request') in (80,84) and value.get('index')==2 and type(item) is int and 0<=item<=65535:observed.add(item)
                walk(item)
        elif type(value) is list:
            for item in value:walk(item)
    for folder in sorted(root.glob('A-A23-*')):
        b.require(folder.is_dir() and not folder.is_symlink(),'unexpected run entry')
        for path in sorted(folder.rglob('*')):
            b.require(not path.is_symlink(),'symlink in history')
            if not path.is_file():continue
            raw=b.plain(path,32*1024*1024);name=path.relative_to(root).as_posix();files[name]=raw
            if path.suffix in ('.json','.jsonl'):
                try:
                    for line in raw.splitlines() if path.suffix=='.jsonl' else [raw]:walk(json.loads(line))
                except (ValueError,UnicodeError):errors.append(name)
            if path.suffix=='.bin':
                for match in re.finditer(b'ISO1',raw):
                    offset=match.start()
                    if offset+192>len(raw):continue
                    value=struct.unpack_from('<H',raw,offset+4)[0]
                    if raw[offset:offset+192]==model.expected_payload(value)[:192]:observed.add(value)
    b.require(0<len(files)<=2048 and sum(map(len,files.values()))<=256*1024*1024,'history size limit')
    return files,sorted(observed),errors


def create_scope(output=SCOPE):
    output=Path(output);b.require(output.is_absolute() and output==output.resolve() and not output.exists(),'new scope required')
    root=b.ROOT/'private/runs';files,values,errors=inventory(root);b.require(not errors,'unparsed history JSON requires review')
    output.mkdir(mode=0o700)
    for name,raw in files.items():card.pkg.put(output,'runs/'+name,raw)
    value=dict(schema='A23-local-sequence-history-1',root=str(root),files={n:b.sha(v) for n,v in files.items()},
        observed_values=values,conservative_quarantine='Each observed value excludes a16-packet range, including metadata sequence counters.',
        proposed=model.propose_block(values),reserved=False,global_history_authenticated=False,unparsed=[])
    b.write(output/'scope.json',value);b.seal(output);return value


def verify_scope(path=SCOPE,*,live=True):
    path=Path(path);card.seal_verify(path);value=b.load(path/'scope.json')
    b.require(value['schema']=='A23-local-sequence-history-1' and not value['reserved'] and not value['unparsed'],'invalid history scope')
    b.require(value['proposed']==model.propose_block(value['observed_values']),'history proposal differs')
    for name,h in value['files'].items():b.require(b.sha(b.plain(path/'runs'/name))==h,'frozen history changed')
    if live:
        files,values,errors=inventory(Path(value['root']))
        b.require(not errors and values==value['observed_values'] and {n:b.sha(v) for n,v in files.items()}==value['files'],'live history changed')
    return value,b.sha(b.plain(path/'SHA256SUMS'))


def reserve_model(directory,scope_digest,observed,expected_head):
    """Durably burn a block in /private/tmp only. Failure never rolls it back."""
    directory=Path(directory)
    b.require(directory.is_dir() and directory==directory.resolve() and Path('/private/tmp') in directory.parents,'temporary model ledger only')
    b.require(type(scope_digest) is str and re.fullmatch('[0-9a-f]{64}',scope_digest),'scope digest required')
    fd=os.open(directory/'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        paths=sorted(directory.glob('burn-*.json'));entries=[];head=None
        b.require(set(p.name for p in directory.iterdir())<=set(p.name for p in paths)|{'.lock','HEAD'},'unknown ledger artifact')
        for i,path in enumerate(paths):
            entry=b.load(path);b.require(path.name==f'burn-{i:04d}.json' and set(entry)=={'schema','scope','previous','first','id'},'bad reservation record')
            b.require(entry['schema']=='A23-sequence-burn-model-1' and entry['scope']==scope_digest and entry['previous']==head,'reservation chain differs')
            b.require(entry['first']==model.propose_block([*observed,*[v['first'] for v in entries]]),'reused or overlapping sequence')
            b.require(str(uuid.UUID(entry['id']))==entry['id'],'reservation UUID differs')
            head=b.sha(b.plain(path));entries.append(entry)
        saved=(directory/'HEAD').read_text().strip() if (directory/'HEAD').exists() else None
        b.require(saved==head==expected_head,'stale, partial or rolled-back ledger')
        first=model.propose_block([*observed,*[v['first'] for v in entries]])
        entry=dict(schema='A23-sequence-burn-model-1',scope=scope_digest,previous=head,first=first,id=str(uuid.uuid4()))
        path=directory/f'burn-{len(entries):04d}.json';b.write(path,entry)
        # The burn is already durable before the replace. On failure it stays.
        head=b.sha(b.plain(path));temporary=directory/('head-'+uuid.uuid4().hex)
        b.old.durable_write(temporary,(head+'\n').encode());os.replace(temporary,directory/'HEAD');b.old.sync_dir(directory)
        return dict(first=first,head=head,reservation=entry,model_only=True,remaining=0,acquisition_enabled=False)
    finally:os.close(fd)
