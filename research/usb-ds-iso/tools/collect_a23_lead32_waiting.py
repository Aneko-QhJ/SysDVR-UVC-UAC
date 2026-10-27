#!/usr/bin/env python3
"""Freeze supplied waiting+SDK+EXE3 files; agreement is never provenance."""
import argparse
import json
from pathlib import Path
import re
import struct

import collect_a23_lead32_envelope as core
import analyze_a23_lead32_entry as waiting
from analyze_io_usb_host_lead32 import checkpoint
from analyze_io_usb_host_evidence import require,unique_object
from analyze_io_usb_host_collection import durable_write,sync_dir

POLICY=(*core.POLICY,'root_cause_confirmed','journal_acknowledgement_verified',
        'build_source_closure_verified','envelope_own_commit_authenticated',
        'full_status_payload_binding_verified','trace_window_complete_verified','device_window_budget_verified')
ERRORS=(OSError,ValueError,TypeError,KeyError,IndexError,AttributeError,struct.error,OverflowError)


def packet_tree(root):
    root=Path(root);require(root.is_dir() and root.absolute()==root.resolve(),'invalid packet path')
    files={};total=0
    for p in sorted(root.rglob('*')):
        name=p.relative_to(root).as_posix()
        require(not p.is_symlink() and re.fullmatch(r'[A-Za-z0-9_.\-/]+',name) and len(p.relative_to(root).parts)<=6,'invalid packet entry')
        if p.is_dir():continue
        require(len(files)<256,'packet has too many files');files[name]=core.read(p);total+=len(files[name])
        require(total<=16*1024*1024,'packet too large')
    return files


def analyze_waiting(host):
    host=Path(host)
    result=dict(schema='A23-lead32-waiting-supplied-check-1',audit_valid=False,
        checkpoint_matches_reported=None,recorded_state='invalid_or_missing',errors=[],
        **{k:False for k in POLICY})
    try:
        checked=waiting.analyze(host)
        entry=json.loads(core.read(host/'waiting-entry-result.json',16384),object_pairs_hook=unique_object)
        require(not entry['started'] or entry['failure'] is None and entry['preparation_error'] is None,
                'started entry also reports preflight error')
        if checked['started']:
            reported=entry['host_result'];kind=checked['sdk_analysis']['checkpoint']
            require(kind in ('final','retained'),'unknown SDK checkpoint')
            saved=checkpoint(host/kind);flag=kind+'_checkpoint_saved'
            require(type(reported) is dict and set(reported)==set(saved) and reported.get(flag) is True and
                waiting.uint(reported.get('ticks')) and reported['ticks']>=saved['ticks'] and
                all(waiting.typed(reported[k],saved[k]) for k in saved if k not in ('ticks',flag)),
                'waiting result contradicts SDK checkpoint')
            require(waiting.typed(entry['finished'],reported['finished']) and
                waiting.typed(entry['unresolved'],reported['unresolved']),'entry/SDK lifecycle disagreement')
            result['checkpoint_matches_reported']=True
            result['recorded_state']='started_closed' if entry['finished'] and not entry['unresolved'] else 'started_unresolved'
        else:
            reported=entry['host_result']
            require(reported is None or type(reported) is dict and reported.get('started') is False,
                    'preflight result contains a started SDK coordinator')
            journal=host/'session.jsonl'
            if journal.exists():
                rows=[json.loads(r,object_pairs_hook=unique_object) for r in core.read(journal,128*4096).splitlines()]
                require(all(type(r) is dict and r.get('event')=='prepared' for r in rows),
                        'preflight result contains SDK activity beyond preparation')
            result['recorded_state']='preflight_failure'
        result.update(audit_valid=True,audit=checked,
            wait_journal_failed=entry['wait_journal_failed'],failed_releases=entry['failed_releases'])
    except ERRORS as error:
        result['errors'].append(dict(component='waiting',detail=str(error).replace(str(host),'<host>')))
    return result


def raw_files(root,has_primary):
    root=Path(root)
    files={'host/'+n:b for n,b in core.tree(root/'host').items()}
    files['execution.bin']=core.read(root/'execution.bin',65536)
    if has_primary:files['primary.bin']=core.read(root/'primary.bin',65536)
    return files


def analyze_inputs(root,recipe,has_primary):
    root=Path(root);core.recipe_valid(recipe);before=raw_files(root,has_primary)
    try:
        checked=core.analyze_inputs(root/'host',root/'execution.bin',recipe,root/'primary.bin' if has_primary else None)
    except ERRORS as error:
        # Older decoders need not handle every malformed JSON shape. Preserve
        # their failure without changing the sealed implementations or bytes.
        checked=dict(execution_valid=False,host_audit_valid=False,supplied_comparison_consistent=False,
            external_primary_supplied=has_primary,external_primary_matches_embedded=False,primary_commit_contradiction=False,
            errors=[dict(component='execution_sdk',detail=str(error).replace(str(root),'<inputs>'))])
        # Preserve the independent EXE3 verdict even when a malformed SDK JSON
        # shape prevented the older combined analyzer from returning its work.
        try:
            raw=before['execution.bin'];decoded=core.decode_execution(raw,recipe)
            ini=struct.unpack_from('<I',raw,24)[0];embedded=raw[256+ini:]
            checked.update(execution_valid=True,execution=decoded,execution_sha256=core.sha(raw))
            if has_primary:
                match=before['primary.bin']==embedded
                checked.update(external_primary_matches_embedded=match,
                    primary_commit_contradiction=not match and decoded['primary_receipt']['commit_acknowledged'])
        except ERRORS as error:checked['errors'].append(dict(component='execution',detail=str(error)))
    wait=analyze_waiting(root/'host')
    require(raw_files(root,has_primary)==before,'frozen inputs changed during waiting analysis')
    consistent=bool(wait['audit_valid'] and wait['audit']['started'] and
        wait['checkpoint_matches_reported'] is True and checked['supplied_comparison_consistent'])
    primary_complete=bool(checked.get('execution_valid') and checked.get('external_primary_supplied') is True and
        checked.get('external_primary_matches_embedded') is True and
        checked['execution']['primary_receipt']['commit_acknowledged'] is True)
    complete=bool(consistent and wait['recorded_state']=='started_closed' and
        checked.get('host_observation_complete') is True and primary_complete)
    return dict(schema='A23-lead32-waiting-execution-supplied-analysis-1',offline_only=True,
        expected_recipe=recipe,raw_inventory_sha256=core.sha(core.canonical(core.inventory(before))),
        execution=checked,waiting=wait,errors=checked['errors']+wait['errors'],
        primary_material_complete=primary_complete,
        supplied_chain_consistent=consistent,supplied_chain_complete=complete,
        **{k:False for k in POLICY})


def metadata(files,recipe):
    return dict(schema='A23-lead32-waiting-execution-collection-1',expected_recipe=recipe,
        artifact_origin='supplied_static_files_unverified',failed_bytes_preserved=True,
        waiting_check_required=True,has_external_primary='primary.bin' in files,raw_files=core.inventory(files),**{k:False for k in POLICY})


def freeze(host,execution,output,recipe,primary=None):
    core.recipe_valid(recipe)
    host,execution,output=map(lambda p:Path(p).absolute(),(host,execution,output))
    require(not output.exists() and output==output.resolve() and not output.is_relative_to(host),
        'output exists, is symlinked or overlaps source')
    original=core.tree(host);raw=core.read(execution,65536)
    primary_raw=core.read(primary,65536) if primary is not None else None
    output.mkdir(parents=True,mode=0o700);sync_dir(output.parent)
    files={'host/'+n:b for n,b in original.items()};files['execution.bin']=raw
    if primary is not None:files['primary.bin']=primary_raw
    for name,data in files.items():
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);durable_write(target,data)
    (output/'host').mkdir(exist_ok=True)
    result=analyze_inputs(output,recipe,primary is not None)
    meta=metadata(files,recipe)
    durable_write(output/'analysis.json',core.canonical(result))
    durable_write(output/'collection.json',core.canonical(meta))
    require(core.tree(host)==original and core.read(execution,65536)==raw,'source changed during outer collection')
    if primary is not None:require(core.read(primary,65536)==primary_raw,'primary changed during outer collection')
    require(raw_files(output,primary is not None)==files,'inputs changed before seal')
    for p in sorted((p for p in output.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):sync_dir(p)
    files.update({'analysis.json':core.canonical(result),'collection.json':core.canonical(meta)})
    sums=''.join(core.sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    durable_write(output/'SHA256SUMS',sums);sync_dir(output)
    durable_write(output/'COMMITTED',(core.sha(sums)+'\n').encode());sync_dir(output)
    return analyze_collection(output)


def analyze_collection(root):
    root=Path(root);snapshot=packet_tree(root)
    names={'host','execution.bin','analysis.json','collection.json','SHA256SUMS','COMMITTED'}
    if 'primary.bin' in snapshot:names.add('primary.bin')
    require({p.name for p in root.iterdir()}==names,'unexpected/missing packet root entry')
    require((root/'host').is_dir(),'missing host directory')
    files=dict(snapshot);require('SHA256SUMS' in files and 'COMMITTED' in files,'uncommitted waiting collection')
    sums=files.pop('SHA256SUMS');commit=files.pop('COMMITTED')
    require(commit==(core.sha(sums)+'\n').encode() and sums==''.join(core.sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode(),
        'waiting collection hash/commit mismatch')
    require('analysis.json' in files and 'collection.json' in files,'missing waiting collection metadata')
    meta=json.loads(files.pop('collection.json'),object_pairs_hook=unique_object)
    saved=json.loads(files.pop('analysis.json'),object_pairs_hook=unique_object)
    require(type(meta) is dict and 'execution.bin' in files and
        all(n in ('execution.bin','primary.bin') or n.startswith('host/') for n in files),'invalid waiting collection layout')
    recipe=meta.get('expected_recipe');core.recipe_valid(recipe)
    require(core.canonical(meta)==core.canonical(metadata(files,recipe)),'waiting inventory/policy mismatch')
    checked=analyze_inputs(root,recipe,'primary.bin' in files)
    require(core.canonical(saved)==core.canonical(checked),'waiting analysis differs from frozen bytes')
    require(packet_tree(root)==snapshot,'collection changed during reanalysis')
    return dict(schema='A23-lead32-waiting-execution-collection-analysis-1',collection_integrity_verified=True,
        manifest_sha256=core.sha(sums),analysis=checked,**{k:False for k in POLICY})


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    f=sub.add_parser('freeze');f.add_argument('--host',type=Path,required=True);f.add_argument('--execution',type=Path,required=True)
    f.add_argument('--primary',type=Path);f.add_argument('--output',type=Path,required=True);f.add_argument('--expected-recipe',required=True)
    a=sub.add_parser('analyze');a.add_argument('collection',type=Path);args=p.parse_args()
    result=analyze_collection(args.collection) if args.mode=='analyze' else freeze(args.host,args.execution,args.output,args.expected_recipe,args.primary)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
