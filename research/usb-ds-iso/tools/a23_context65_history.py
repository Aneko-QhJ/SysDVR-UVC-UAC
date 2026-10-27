"""Read-only local history scope, including the burned49 block and failed run."""
from pathlib import Path
import json
import struct
import re

import a23_sequence_history as legacy
import sequence_once_reservation as reservation

b=legacy.b;card=legacy.card
SCOPE=b.ROOT/'private/analysis/A23-context65-history-20261017'
PATTERNS=('A-A23-*','A-sequence-waiting-*','A-context*-waiting-*')

def inventory():
    root=b.ROOT/'private/runs';files={};values=set();errors=[]
    def walk(v):
        if type(v) is dict:
            for k,n in v.items():
                if k in ('sequence','first_sequence') and type(n) is int and 0<=n<=65535:values.add(n)
                if k=='value' and v.get('request') in (80,84) and v.get('index')==2 and type(n) is int and 0<=n<=65535:values.add(n)
                walk(n)
        elif type(v) is list:
            for n in v:walk(n)
    folders=sorted({p for pattern in PATTERNS for p in root.glob(pattern)})
    for folder in folders:
        b.require(folder.is_dir() and not folder.is_symlink(),'invalid history directory')
        for p in sorted(folder.rglob('*')):
            b.require(not p.is_symlink(),'symlink in history')
            if not p.is_file():continue
            raw=b.plain(p,32*1024*1024);files['runs/'+p.relative_to(root).as_posix()]=raw
            if p.suffix in ('.json','.jsonl'):
                try:
                    for row in raw.splitlines() if p.suffix=='.jsonl' else [raw]:walk(json.loads(row))
                except (ValueError,UnicodeError):errors.append(str(p))
            elif p.suffix=='.bin':
                for match in re.finditer(b'ISO1',raw):
                    at=match.start()
                    if at+192<=len(raw):
                        n=struct.unpack_from('<H',raw,at+4)[0]
                        if raw[at:at+192]==legacy.model.expected_payload(n)[:192]:values.add(n)
    burns=reservation.entries(reservation.LEDGER)
    for first,row in burns.items():
        value=row['value'];b.require(not value['simulation'],'formal ledger contains simulation')
        files['reservations/'+Path(row['path']).name]=b.plain(Path(row['path']))
        record=Path(value['record']);b.require(record.parent==b.ROOT/'private/analysis','unexpected record path')
        files['issued-records/'+record.name]=b.plain(record);walk(b.load(record))
    b.require(not errors and 0<len(files)<=2304 and sum(map(len,files.values()))<=256*1024*1024,'unparsed or oversized history')
    proposed=legacy.model.propose_block(sorted(values|set(burns)))
    return files,dict(schema='A23-context-sequence-history-1',patterns=list(PATTERNS),observed_values=sorted(values),
        reserved_blocks={str(k):dict(last=v['value']['last'],sha256=v['sha256']) for k,v in burns.items()},
        proposed=proposed,reserved=False,global_history_authenticated=False,unparsed=[])

def create_scope(output=SCOPE):
    output=Path(output);b.require(output.is_absolute() and output==output.resolve() and not output.exists(),'new history output required')
    legacy.verify_scope(live=True)
    files,value=inventory();output.mkdir(mode=0o700)
    for n,raw in files.items():card.pkg.put(output,n,raw)
    value['files']={n:b.sha(v) for n,v in files.items()};b.write(output/'scope.json',value);b.seal(output)
    return value,b.sha(b.plain(output/'SHA256SUMS'))

def verify_scope(path=SCOPE,*,live=True):
    path=Path(path);card.seal_verify(path);value=b.load(path/'scope.json')
    b.require(value['schema']=='A23-context-sequence-history-1' and value['reserved'] is False and not value['unparsed'],'invalid history scope')
    for n,h in value['files'].items():b.require(b.sha(b.plain(path/n))==h,'frozen history changed')
    if live:
        files,current=inventory();current['files']={n:b.sha(v) for n,v in files.items()}
        b.require(current==value,'live history/reservation/record changed')
    return value,b.sha(b.plain(path/'SHA256SUMS'))
