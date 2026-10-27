#!/usr/bin/env python3
"""Offline freeze/compare of supplied static files, including partial failures.

No card access, ticket mutation, receiver execution or origin authentication.
Failed/short bytes are preserved in a new collection, never repaired or retried.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct

from analyze_a23_v2_association import compare, setup_hex
from analyze_ep0_execution_v3 import decode_execution
from analyze_io_usb_host_context65 import analyze as audit_host
from analyze_io_usb_host_burst_sdk_collection import replies
from analyze_io_usb_host_collection import durable_write, sync_dir
from analyze_io_usb_host_evidence import require, unique_object
from audit_io_usb_host_device import decode_status

POLICY=('source_authenticated','same_physical_run_verified','cross_clock_alignment_verified',
        'usb_strict_pass','hardware_verified','cleanup_authorized','allow_next_burst')


def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def sha(raw):return hashlib.sha256(raw).hexdigest()


def read(path,limit=2*1024*1024):
    path=Path(path)
    require(path.absolute()==path.resolve(),'symlinked/noncanonical input path')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size<=limit,'nonregular/oversized input')
        raw=b''
        while len(raw)<=limit:
            chunk=os.read(fd,min(65536,limit+1-len(raw)))
            if not chunk:break
            raw+=chunk
        require(len(raw)<=limit,'input grew beyond limit');return raw
    finally:os.close(fd)


def tree(path,*,maximum=128):
    path=Path(path)
    require(path.is_dir() and path.absolute()==path.resolve(),'invalid/symlinked input directory')
    result={};total=0
    for p in sorted(path.rglob('*')):
        require(not p.is_symlink(),'symlink in input tree')
        name=p.relative_to(path).as_posix()
        require(re.fullmatch(r'[A-Za-z0-9_.\-/]+',name) and len(p.relative_to(path).parts)<=5,'invalid/deep input name')
        if p.is_dir():continue
        require(len(result)<maximum,'too many input files')
        result[name]=read(p);total+=len(result[name]);require(total<=8*1024*1024,'input tree too large')
    return result


def recipe_valid(recipe):
    require(type(recipe) is str and re.fullmatch('[0-9a-f]{64}',recipe),'invalid expected recipe')


def analyze_inputs(host,execution,recipe,primary=None):
    recipe_valid(recipe);host,execution=Path(host),Path(execution)
    result=dict(schema='A23-context65-execution-supplied-analysis-1',offline_only=True,errors=[],
        expected_recipe=recipe,execution_valid=False,host_audit_valid=False,
        supplied_comparison_consistent=False,external_primary_supplied=primary is not None,
        external_primary_matches_embedded=False,primary_commit_contradiction=False,
        envelope_own_commit_authenticated=False,**{k:False for k in POLICY})
    def error(component,e):
        detail=str(e).replace(str(host),'<host>').replace(str(execution),'<execution>')
        if primary is not None:detail=detail.replace(str(primary),'<primary>')
        result['errors'].append(dict(component=component,detail=detail))
    decoded=None
    try:
        raw=read(execution,65536);result['execution_sha256']=sha(raw)
        decoded=decode_execution(raw,recipe);result.update(execution_valid=True,execution=decoded)
        ini=struct.unpack_from('<I',raw,24)[0];embedded=raw[256+ini:]
        result['embedded_primary_sha256']=sha(embedded)
        if primary is not None:
            external=read(primary,65536);match=external==embedded
            result.update(external_primary_sha256=sha(external),external_primary_matches_embedded=match,
                primary_commit_contradiction=not match and decoded['primary_receipt']['commit_acknowledged'])
    except (OSError,ValueError,TypeError,KeyError,struct.error) as e:error('execution',e)
    try:
        journal=read(host/'session.jsonl',128*4096)
        checked=audit_host(host)
        require(checked['journal_sha256']==sha(journal) and read(host/'session.jsonl',128*4096)==journal,
                'host journal changed during comparison')
        rows=[json.loads(row,object_pairs_hook=unique_object) for row in journal.splitlines()]
        events={r['details']['event']:r['details']['details'] for r in rows if r['event']=='adapter'}
        requests=[dict(phase=p,setup_hex=setup_hex(events['status_'+p]['observation']['control'])) for p in ('before','after')]
        requests.insert(1,dict(phase='burst',setup_hex=setup_hex(events['trigger_return'])))
        status={k:decode_status(v) for k,v in replies(journal).items()}
        result.update(host_audit_valid=True,host=checked,host_requests=requests,
            host_status=status,host_observation_complete=checked['host_observation_complete'])
        if decoded:
            relation=compare(requests,status,decoded['primary']['trace']);result['comparison']=relation
            result['supplied_comparison_consistent']=bool(not result['errors'] and result['execution_valid'] and
                not result['primary_commit_contradiction'] and relation['exact_target_setup_order_matches'] and
                relation['status_state_sequence_matches'])
    except (OSError,ValueError,TypeError,KeyError,struct.error) as e:error('host',e)
    return result


def inventory(files):return {name:dict(bytes=len(raw),sha256=sha(raw)) for name,raw in sorted(files.items())}


def metadata(files,recipe):
    return dict(schema='A23-context65-execution-collection-1',artifact_origin='supplied_static_files_unverified',
        expected_recipe=recipe,has_external_primary='primary.bin' in files,raw_files=inventory(files),
        failed_bytes_preserved=True,**{k:False for k in POLICY})


def freeze(host,execution,output,recipe,primary=None):
    recipe_valid(recipe)
    host,execution,output=map(lambda p:Path(p).absolute(),(host,execution,output))
    require(not output.exists() and output==output.resolve() and not output.is_relative_to(host),
            'output exists, is symlinked or overlaps host source')
    original=tree(host)
    files={'host/'+name:raw for name,raw in original.items()}
    files['execution.bin']=read(execution,65536)
    if primary is not None:files['primary.bin']=read(primary,65536)
    output.mkdir(parents=True,mode=0o700)
    sync_dir(output.parent)
    # Preserve invalid and incomplete inputs. Decode only the frozen copies.
    for name,raw in files.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);durable_write(path,raw)
    (output/'host').mkdir(exist_ok=True)
    result=analyze_inputs(output/'host',output/'execution.bin',recipe,
                          output/'primary.bin' if primary is not None else None)
    durable_write(output/'analysis.json',canonical(result));durable_write(output/'collection.json',canonical(metadata(files,recipe)))
    require(tree(host)==original and read(execution,65536)==files['execution.bin'],'source changed during collection')
    if primary is not None:require(read(primary,65536)==files['primary.bin'],'primary changed during collection')
    for directory in sorted((p for p in output.rglob('*') if p.is_dir()),reverse=True):sync_dir(directory)
    all_files={**files,'analysis.json':canonical(result),'collection.json':canonical(metadata(files,recipe))}
    sums=''.join(sha(raw)+'  '+name+'\n' for name,raw in sorted(all_files.items())).encode()
    durable_write(output/'SHA256SUMS',sums);sync_dir(output)
    durable_write(output/'COMMITTED',(sha(sums)+'\n').encode());sync_dir(output)
    return analyze_collection(output)


def analyze_collection(root):
    root=Path(root);snapshot=tree(root,maximum=256);all_files=dict(snapshot)
    require((root/'host').is_dir(),'missing host directory')
    require('COMMITTED' in all_files and 'SHA256SUMS' in all_files,'uncommitted collection')
    sums=all_files.pop('SHA256SUMS');commit=all_files.pop('COMMITTED')
    require(commit==(sha(sums)+'\n').encode() and sums==''.join(sha(raw)+'  '+name+'\n'
        for name,raw in sorted(all_files.items())).encode(),'collection hash/commit mismatch')
    require('collection.json' in all_files and 'analysis.json' in all_files,'missing collection metadata')
    meta=json.loads(all_files.pop('collection.json'),object_pairs_hook=unique_object)
    saved=json.loads(all_files.pop('analysis.json'),object_pairs_hook=unique_object)
    require('execution.bin' in all_files and all(name in ('execution.bin','primary.bin') or name.startswith('host/')
        for name in all_files),'unexpected collection file')
    recipe=meta.get('expected_recipe');recipe_valid(recipe)
    require(canonical(meta)==canonical(metadata(all_files,recipe)),'collection inventory/policy mismatch')
    checked=analyze_inputs(root/'host',root/'execution.bin',recipe,root/'primary.bin' if 'primary.bin' in all_files else None)
    require(canonical(saved)==canonical(checked),'saved comparison differs from frozen bytes')
    require(tree(root,maximum=256)==snapshot,'collection changed during analysis')
    return dict(schema='A23-context65-execution-collection-analysis-1',collection_integrity_verified=True,
        manifest_sha256=sha(sums),raw_file_count=len(all_files),analysis=checked,**{k:False for k in POLICY})


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    f=sub.add_parser('freeze');f.add_argument('--host',required=True,type=Path)
    f.add_argument('--execution',required=True,type=Path);f.add_argument('--primary',type=Path)
    f.add_argument('--expected-recipe',required=True);f.add_argument('--output',required=True,type=Path)
    a=sub.add_parser('analyze');a.add_argument('collection',type=Path);args=p.parse_args()
    result=analyze_collection(args.collection) if args.mode=='analyze' else freeze(args.host,args.execution,args.output,args.expected_recipe,args.primary)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
