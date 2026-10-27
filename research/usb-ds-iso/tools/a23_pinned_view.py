"""Materialize separate byte copies; consumers cache verified immutable bytes.

This pins a caller-declared byte contract, not current physical/OS provenance.
"""
from pathlib import Path
from dataclasses import dataclass
from types import MappingProxyType
import os
import a23_pinned_view_archive as ar
a=ar.a;f=a.f

def materialize(source,expected,output,checkpoint=None):
    source=a.canonical(source);output=a.canonical(output);expected=ar.contract(expected);f.require(source.is_relative_to('/private/tmp') and output.is_relative_to('/private/tmp') and not output.exists() and not source.is_relative_to(output) and not output.is_relative_to(source),'new separate temporary byte view required');output.mkdir(mode=0o700);a.put(output,'ATTEMPT',b'one detached byte view attempt\n')
    if checkpoint:checkpoint('reserved')
    raw,dirs=ar.snapshot(source,set(expected['files']),set(expected['directories']),lambda stage:checkpoint('source.'+stage) if checkpoint else None);f.require(f.encode(a.inventory(raw))==f.encode(expected['files']),'source differs from declared byte contract')
    if checkpoint:checkpoint('snapshotted')
    (output/'data').mkdir()
    for n in dirs:(output/'data'/n).mkdir(parents=True,exist_ok=True)
    for n,value in raw.items():a.put(output,'data/'+n,value)
    if checkpoint:checkpoint('copied')
    a.put(output,'contract.json',f.encode(expected));a.put(output,'view.json',f.encode(dict(schema='A23-detached-byte-view-1',contract_sha256=f.sha(f.encode(expected)),copy_method='new_exclusive_files_from_captured_bytes',files=len(raw),**ar.FALSE)))
    if checkpoint:checkpoint('before_commit')
    files,directories=ar.layout(expected,sealed=False);written,_=ar.snapshot(output,files,directories);f.require(f.encode(a.inventory({n[5:]:v for n,v in written.items() if n.startswith('data/')}))==f.encode(expected['files']),'detached data changed before commit');a.seal(output);return ar.verify(output,expected)

@dataclass(frozen=True,slots=True)
class PinnedBytes:
    _data:object
    contract_sha256:str
    @classmethod
    def load(cls,root,expected,checkpoint=None):
        data,result=ar.read_verified(root,expected,checkpoint);return cls(MappingProxyType(dict(data)),result['contract_sha256'])
    @property
    def files(self):return tuple(sorted(self._data))
    def read(self,name):return self._data[name]

if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--expected',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fault',choices=('none','reserved','copied','before_commit'),default='none');v=p.parse_args()
    def stop(stage):
        if stage==v.fault:os._exit(75)
    try:r=materialize(v.source,f.load(v.expected),v.output,stop)
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(archive_integrity_valid=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(r,indent=2))
