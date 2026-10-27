"""Durable one-block burns for the scoped sequence receiver. No device access.

Independent reservations use fixed block filenames and are never released.
Partial writes block later issuance. This is local file integrity, not a defense
against a privileged actor deleting both reservation and issued record.
"""
import fcntl
import os
from pathlib import Path
import re
import uuid
from datetime import datetime,timezone

import build_a23_sequence_receiver as b
import a23_sequence_witness_model as model

LEDGER=b.ROOT/'private/sequence-reservations'


def canonical(path):
    path=Path(path);b.require(path.is_absolute() and path==path.resolve(),'canonical reservation path required');return path


def location(record,ledger):
    record=canonical(record);ledger=canonical(ledger)
    simulation=Path('/private/tmp') in record.parents
    if simulation:b.require(Path('/private/tmp') in ledger.parents,'model record requires model ledger')
    else:b.require(record.parent==b.ROOT/'private/analysis' and ledger==LEDGER,'formal ledger/record mismatch')
    return record,ledger,simulation


def entries(ledger):
    ledger=canonical(ledger)
    if not ledger.exists():return {}
    b.require(ledger.is_dir(),'ledger is not directory');result={}
    for path in sorted(ledger.iterdir()):
        if path.name=='.lock':
            b.require(path.is_file() and not path.is_symlink(), 'invalid ledger lock');continue
        match=re.fullmatch(r'block-(\d{5})\.json',path.name)
        b.require(match is not None,'unknown ledger artifact')
        value=b.load(path);first=int(match[1])
        b.require(path.name==f'block-{first:05d}.json' and first not in result,'noncanonical or duplicate block filename')
        b.require(set(value)=={'schema','first','last','record','scope','receiver','id','created_at','simulation'} and
            value['schema']=='A23-sequence-reservation-1' and type(value['first']) is int and value['first']==first and
            1<=first<=65505 and (first-1)%16==0 and type(value['last']) is int and value['last']==first+15 and
            type(value['simulation']) is bool and str(uuid.UUID(value['id']))==value['id'],'invalid reservation record')
        for key in ('scope','receiver'):b.require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}',value[key]),'invalid reservation digest')
        canonical(value['record']);b.require(type(value['created_at']) is str,'invalid reservation timestamp')
        result[first]=dict(path=str(path),sha256=b.sha(b.plain(path)),value=value)
    return result


def available(record,ledger,scope):
    record,ledger,simulation=location(record,ledger);seen=entries(ledger);first=b.device.FIRST
    used=set()
    for row in seen.values():used.update(model.packet_sequences(row['value']['first']))
    b.require(not used.intersection(model.packet_sequences(first)),'candidate sequence block already burned')
    b.require(scope['sequence_history_manifest_sha256']==b.device.HISTORY_DIGEST and scope['first_sequence']==first,'candidate/history mismatch')
    return record,ledger,simulation


def burn(record,ledger,scope):
    record,ledger,simulation=available(record,ledger,scope)
    ledger.mkdir(mode=0o700,exist_ok=True);b.old.sync_dir(ledger.parent)
    fd=os.open(ledger/'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        available(record,ledger,scope)
        value=dict(schema='A23-sequence-reservation-1',first=b.device.FIRST,last=b.device.FIRST+15,
            record=str(record),scope=scope['sequence_history_manifest_sha256'],receiver=scope['receiver_sha256'],
            id=str(uuid.uuid4()),created_at=datetime.now(timezone.utc).isoformat(),simulation=simulation)
        path=ledger/f'block-{b.device.FIRST:05d}.json';b.write(path,value)
        result=dict(directory=str(ledger),path=str(path),sha256=b.sha(b.plain(path)),simulation=simulation)
        verify(result,record,scope);return result
    finally:os.close(fd)


def verify(receipt,record,scope):
    b.require(type(receipt) is dict and set(receipt)=={'directory','path','sha256','simulation'},'missing reservation receipt')
    record,ledger,simulation=location(record,receipt['directory']);seen=entries(ledger)
    row=seen.get(b.device.FIRST);b.require(row is not None,'missing burned sequence')
    b.require(type(receipt['simulation']) is bool and receipt['simulation']==simulation and
        receipt['path']==row['path'] and receipt['sha256']==row['sha256'],'reservation receipt differs')
    value=row['value']
    b.require(value['record']==str(record) and value['scope']==scope['sequence_history_manifest_sha256'] and
        value['receiver']==scope['receiver_sha256'] and value['simulation']==simulation,'reservation scope differs')
    return True
