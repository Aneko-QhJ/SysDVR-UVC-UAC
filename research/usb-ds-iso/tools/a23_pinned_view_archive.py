"""Strict file-only byte-contract views; validated bytes returned from one read."""
from pathlib import Path
import os,re,stat
import a23_bootstrap_capture as base
a=base.a;f=a.f
FALSE={**base.ar.FALSE,'atomic_snapshot_verified':False,'source_unchanged_through_commit_proven':False,'post_final_changes_excluded':False,'live_source_authenticated':False,'os_immutability_enforced':False}

def contract(value):
    v=f.parse(f.encode(value));f.require(type(v) is dict and set(v)=={'schema','source_manifest_sha256','source_prefix','files','directories',*FALSE} and v['schema']=='A23-pinned-byte-contract-1' and all(v[k] is False for k in FALSE),'byte contract authority/inventory differs');f.require(f.hex64(v['source_manifest_sha256']) and v['source_prefix']=='raw/' and type(v['files']) is dict and 1<=len(v['files'])<=128 and type(v['directories']) is list and v['directories']==sorted(set(v['directories'])),'byte contract scope differs')
    for n,entry in v['files'].items():
        valid_name(n);f.require(type(entry) is dict and set(entry)=={'bytes','sha256'} and type(entry['bytes']) is int and 0<=entry['bytes']<=1024*1024 and f.hex64(entry['sha256']),'byte contract entry differs')
    for n in v['directories']:valid_name(n)
    f.require(set(a.prefixes(v['files'])).issubset(v['directories']) and len(v['directories'])<=256,'byte contract directory parents differ');return v

def valid_name(name):f.require(type(name) is str and re.fullmatch(r'[A-Za-z0-9_.\-/]+',name) and not name.startswith('/') and all(n not in ('','.','..') for n in name.split('/')) and len(name.split('/'))<=18,'unsafe byte view name')
def stamp(st):return base.identity(st)+[st.st_nlink]

def snapshot(root,allowed_files,allowed_dirs,checkpoint=None):
    root=a.canonical(root);fd=base.pin(root);raw={};dirs=[];nodes=0;total=0;first=stamp(os.fstat(fd))
    def walk(handle,prefix=''):
        nonlocal nodes,total
        initial=stamp(os.fstat(handle));names=[]
        with os.scandir(handle) as iterator:
            for entry in iterator:f.require(nodes+len(names)<512,'view node limit');names.append(entry.name)
        for name in sorted(names):
            nodes+=1;f.require(nodes<=512,'view node limit');n=prefix+name;valid_name(n);st=os.stat(name,dir_fd=handle,follow_symlinks=False);child=None
            if stat.S_ISDIR(st.st_mode):
                f.require(n in allowed_dirs,'unexpected view directory')
                try:child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=handle);f.require(stamp(os.fstat(child))==stamp(st),'view directory replaced');dirs.append(n);walk(child,n+'/');f.require(stamp(os.fstat(child))==stamp(os.stat(name,dir_fd=handle,follow_symlinks=False)),'view directory binding changed')
                finally:
                    if child is not None:os.close(child)
            else:
                f.require(n in allowed_files,'unexpected view file');f.require(stat.S_ISREG(st.st_mode) and st.st_nlink==1,'nonregular or multiply-linked view file');f.require(0<=st.st_size<=1024*1024,'view file size limit')
                try:
                    child=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=handle);f.require(stamp(os.fstat(child))==stamp(st),'view file replaced before read')
                    if checkpoint:checkpoint('file_opened:'+n)
                    value=bytearray()
                    while len(value)<st.st_size:
                        part=os.read(child,min(65536,st.st_size-len(value)));f.require(part,'short view read');value.extend(part)
                    f.require(not os.read(child,1) and os.fstat(child).st_nlink==1 and stamp(os.fstat(child))==stamp(st) and stamp(os.stat(name,dir_fd=handle,follow_symlinks=False))==stamp(st),'view file changed during read');total+=len(value);f.require(total<=16*1024*1024,'view byte limit');raw[n]=bytes(value)
                finally:
                    if child is not None:os.close(child)
        f.require(stamp(os.fstat(handle))==initial,'view directory changed during read')
    try:
        if checkpoint:checkpoint('root_pinned')
        walk(fd);f.require(stamp(os.fstat(fd))==first and base.same_path(root,first[:6]),'view root binding changed')
    finally:os.close(fd)
    f.require(set(raw)==set(allowed_files) and sorted(dirs)==sorted(allowed_dirs),'view inventory incomplete');return dict(sorted(raw.items())),sorted(dirs)

def layout(expected,sealed=True):
    files={'ATTEMPT','contract.json','view.json'}|{'data/'+n for n in expected['files']};dirs=set(a.prefixes(files))|{'data'}|{'data/'+n for n in expected['directories']}
    if sealed:files|={'SHA256SUMS','COMMITTED'}
    return files,dirs

def read_verified(root,expected,checkpoint=None):
    expected=contract(expected);files,dirs=layout(expected);raw,_=snapshot(root,files,dirs,checkpoint);manifest=raw.pop('SHA256SUMS');commit=raw.pop('COMMITTED');f.require(commit==(f.sha(manifest)+'\n').encode() and a.sums(raw)==manifest,'view seal differs');f.require(raw['ATTEMPT']==b'one detached byte view attempt\n' and raw['contract.json']==f.encode(expected),'external byte contract differs');meta=f.parse(raw['view.json']);want=dict(schema='A23-detached-byte-view-1',contract_sha256=f.sha(f.encode(expected)),copy_method='new_exclusive_files_from_captured_bytes',files=len(expected['files']),**FALSE);f.require(f.encode(meta)==f.encode(want),'view metadata/authority differs');data={n[5:]:v for n,v in raw.items() if n.startswith('data/')};f.require(f.encode(a.inventory(data))==f.encode(expected['files']),'view data differs from contract');return data,dict(schema='A23-detached-byte-view-analysis-1',archive_integrity_valid=True,byte_contract_matches=True,contract_sha256=want['contract_sha256'],manifest_sha256=f.sha(manifest),files=len(data),bytes=sum(len(v) for v in data.values()),**FALSE)

def verify(root,expected):return read_verified(root,expected)[1]
if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('view',type=Path);p.add_argument('--expected',type=Path,required=True);v=p.parse_args()
    try:r=verify(v.view,f.load(v.expected))
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(archive_integrity_valid=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(r,indent=2))
