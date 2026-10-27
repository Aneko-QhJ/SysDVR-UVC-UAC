#!/usr/bin/env python3
"""Freeze supplied build/device/receipt/EXE3 agreement. No physical provenance."""
import argparse
import json
from pathlib import Path
import re
import uuid

import a23_device_binding as device
import build_a23_bound_receiver as builder
import collect_a23_waiting_execution as waiting
from analyze_io_usb_host_evidence import require,unique_object

POLICY=waiting.POLICY
CLAIMS=('waiting-authorization.json','WAIT_PROCESS_CLAIMED','WAIT_RECEIVER_CLAIMED')


def tree(root):
    root=Path(root);require(root.is_dir() and root.absolute()==root.resolve(),'canonical bound collection required')
    out={};total=0
    for p in sorted(root.rglob('*')):
        name=p.relative_to(root).as_posix()
        require(not p.is_symlink() and re.fullmatch('[A-Za-z0-9_.\-/]+',name) and len(p.relative_to(root).parts)<=8,'invalid bound packet path')
        if p.is_dir():continue
        require(len(out)<512,'too many bound files');raw=builder.plain(p);total+=len(raw)
        require(total<=32*1024*1024,'oversized bound packet');out[name]=raw
    return out


def parse(raw):return json.loads(raw,object_pairs_hook=unique_object)


def binding_analysis(folder):
    folder=Path(folder);result=dict(supplied_binding_consistent=False,errors=[],**{k:False for k in POLICY})
    try:
        record=builder.load(folder/'record.json');meta=builder.load(folder/'manifest.json');bound=builder.load(folder/'device-binding.json')
        require(type(record) is dict and record.get('schema')=='A23-waiting-receiver-record-2' and
            record.get('backend')=='a23-waiting-burst-1' and device.old.typed(record.get('plan'),builder.WAIT_PLAN) and
            record.get('stage') in ('consumed','captured_logs_pending','failed_no_retry','unresolved_no_retry') and
            type(record.get('remaining')) is int and record['remaining']==0 and record.get('acquisition_enabled') is False and
            all(record.get(k) is False for k in builder.POLICY),'missing consumed bound record')
        require(type(record.get('preparation_id')) is str and str(uuid.UUID(record['preparation_id']))==record['preparation_id'],'invalid consumed preparation UUID')
        require(type(meta) is dict and meta.get('schema')=='A23-waiting-receiver-build-2' and
            meta.get('backend')=='a23-waiting-burst-1' and meta.get('acquisition_enabled') is False and meta.get('attempt_issued') is False and
            device.old.typed(meta.get('device_binding'),bound) and device.old.typed(record.get('device_binding'),bound) and
            device.old.typed(meta.get('description'),builder.description(bound)) and
            record.get('recipe_sha256')==meta.get('recipe_sha256')==bound['runtime_recipe_sha256'] and
            record.get('device_binding_sha256')==meta.get('device_binding_sha256')==device.binding_hash(bound),'record/metadata/device identity mismatch')
        device.supplied_material(bound,folder/'device')
        sums=builder.plain(folder/'build-SHA256SUMS',1024*1024)
        require(builder.sha(sums)==record.get('build_manifest_sha256') and
            builder.sha(builder.plain(folder/'receiver'))==record.get('receiver_sha256'),'supplied receiver/build bytes mismatch')
        entries={}
        for line in sums.decode().splitlines():
            h,name=line.split('  ',1)
            require(name not in entries and re.fullmatch('[0-9a-f]{64}',h) and re.fullmatch('[A-Za-z0-9_.\-/]+',name) and
                not Path(name).is_absolute() and all(part not in ('','.','..') for part in name.split('/')),'invalid build sum row');entries[name]=h
        require(type(meta.get('source_hashes')) is dict and 0<len(meta['source_hashes'])<=200 and
            type(meta.get('generated_hashes')) is dict and len(meta['generated_hashes'])==4,'invalid supplied build closure')
        expected_names=builder.TOP|{'source/'+n for n in meta['source_hashes']}|{'generated/'+n for n in meta['generated_hashes']}|{'device/'+n for n in device.FILES}
        require(set(entries)==expected_names and sums==''.join(entries[n]+'  '+n+'\n' for n in sorted(entries)).encode(),'supplied build inventory shape mismatch')
        require(entries.get('manifest.json')==builder.sha(builder.plain(folder/'manifest.json')) and
            entries.get('device-binding.json')==builder.sha(builder.plain(folder/'device-binding.json')) and
            entries.get('receiver')==record['receiver_sha256'] and
            all(entries.get('device/'+n)==h for n,h in bound['artifact_hashes'].items()),'supplied build inventory does not bind identity')
        receipt_raw=builder.plain(folder/'waiting-authorization.json',16384);receipt=parse(receipt_raw)
        require(device.old.typed(receipt,device.receipt(record)) and receipt_raw==builder.canonical(receipt),'consumed receipt/device mismatch')
        checked=dict(build_manifest_sha256=record['build_manifest_sha256'],recipe_sha256=record['recipe_sha256'],receiver_sha256=record['receiver_sha256'],
            source_closure_checked=True,parent_input_digest=bound['parent_input_digest'],device_elf_sha256=bound['device_elf_sha256'],
            device_binding_sha256=record['device_binding_sha256'],receipt_sha256=builder.sha(receipt_raw))
        process=builder.load(folder/'WAIT_PROCESS_CLAIMED')
        require(device.old.typed(process,dict(schema='A23-waiting-process-claim-1',checked=checked)),'process claim/build receipt mismatch')
        claim=builder.load(folder/'WAIT_RECEIVER_CLAIMED');identity=waiting.waiting.lines(folder.parent/'waiting/host/session.jsonl')[0]['details']['binding']['identity']
        expected=dict(schema='A23-waiting-burst-claim-1',receipt_sha256=builder.sha(receipt_raw),interface_id=identity['interface_id'],device_id=identity['device_id'],speed=3,
            build_manifest_sha256=record['build_manifest_sha256'],recipe_sha256=record['recipe_sha256'],
            parent_input_digest=bound['parent_input_digest'],device_elf_sha256=bound['device_elf_sha256'],device_binding_sha256=record['device_binding_sha256'])
        require(device.old.typed(claim,expected),'selected SDK claim/device receipt mismatch')
        result.update(supplied_binding_consistent=True,runtime_recipe_sha256=bound['runtime_recipe_sha256'],parent_input_digest=bound['parent_input_digest'],
            device_elf_sha256=bound['device_elf_sha256'],device_binding_sha256=record['device_binding_sha256'])
    except waiting.ERRORS as error:result['errors'].append(str(error).replace(str(folder),'<binding>'))
    return result


def analyze(root):
    root=Path(root);snapshot=tree(root);files=dict(snapshot)
    require({p.name for p in root.iterdir()}=={'waiting','binding','analysis.json','SHA256SUMS','COMMITTED'},'invalid bound root inventory')
    required={'record.json','manifest.json','device-binding.json','build-SHA256SUMS','receiver'}|{'device/'+n for n in device.FILES}
    present={n.removeprefix('binding/') for n in files if n.startswith('binding/')}
    require(required<=present<=required|set(CLAIMS),'unexpected or missing binding file')
    sums=files.pop('SHA256SUMS');commit=files.pop('COMMITTED')
    require(commit==(builder.sha(sums)+'\n').encode() and sums==''.join(builder.sha(raw)+'  '+n+'\n' for n,raw in sorted(files.items())).encode(),'bound packet seal mismatch')
    bound=builder.load(root/'binding/device-binding.json');inner=waiting.analyze_collection(root/'waiting');binding=binding_analysis(root/'binding')
    require(inner['analysis']['expected_recipe']==bound['runtime_recipe_sha256'],'inner expected recipe differs from device binding')
    consistent=bool(binding['supplied_binding_consistent'] and inner['analysis']['supplied_chain_consistent'])
    result=dict(schema='A23-bound-execution-analysis-1',binding=binding,waiting=inner,
        supplied_chain_consistent=consistent,supplied_chain_complete=bool(consistent and inner['analysis']['supplied_chain_complete']),
        **{k:False for k in POLICY})
    require(builder.canonical(parse(files['analysis.json']))==builder.canonical(result),'bound analysis differs from frozen bytes')
    require(tree(root)==snapshot,'bound packet changed during analysis')
    return dict(schema='A23-bound-execution-collection-1',collection_integrity_verified=True,manifest_sha256=builder.sha(sums),analysis=result,**{k:False for k in POLICY})


def inputs(record_path,run,build):
    values={'record.json':builder.plain(record_path),'manifest.json':builder.plain(build/'manifest.json'),
        'device-binding.json':builder.plain(build/'device-binding.json'),'build-SHA256SUMS':builder.plain(build/'SHA256SUMS',1024*1024),
        'receiver':builder.plain(build/'receiver')}
    for n in device.FILES:values['device/'+n]=builder.plain(build/'device'/n)
    for n in CLAIMS:
        p=run/n
        if p.exists():values[n]=builder.plain(p,16384)
    return values


def freeze(host,execution,output,record_path,run,primary=None,repo=builder.REPO):
    host,execution,output,record_path,run=map(lambda p:Path(p).absolute(),(host,execution,output,record_path,run))
    record=builder.load(record_path);build=builder.verify_build(record,repo)
    require(not output.exists() and output==output.resolve() and
        all(not output.is_relative_to(p) and not p.is_relative_to(output) for p in (host,run,build,record_path)),'bound output overlaps source')
    original=inputs(record_path,run,build);output.mkdir(parents=True,mode=0o700);device_root=output/'binding'
    for n,raw in original.items():
        target=device_root/n;target.parent.mkdir(parents=True,exist_ok=True);device.old.durable_write(target,raw)
    inner=waiting.freeze(host,execution,output/'waiting',record['recipe_sha256'],primary)
    binding=binding_analysis(device_root);consistent=bool(binding['supplied_binding_consistent'] and inner['analysis']['supplied_chain_consistent'])
    result=dict(schema='A23-bound-execution-analysis-1',binding=binding,waiting=inner,supplied_chain_consistent=consistent,
        supplied_chain_complete=bool(consistent and inner['analysis']['supplied_chain_complete']),**{k:False for k in POLICY})
    require(inputs(record_path,run,build)==original,'binding/receipt changed during collection')
    require({p.relative_to(device_root).as_posix():builder.plain(p) for p in device_root.rglob('*') if p.is_file()}==original,'frozen binding bytes changed')
    builder.write(output/'analysis.json',result);builder.seal(output);return analyze(output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    sub.add_parser('analyze').add_argument('collection',type=Path)
    f=sub.add_parser('freeze')
    for n in ('host','execution','output','record','run'):f.add_argument('--'+n,type=Path,required=True)
    f.add_argument('--primary',type=Path);a=p.parse_args()
    value=analyze(a.collection) if a.mode=='analyze' else freeze(a.host,a.execution,a.output,a.record,a.run,a.primary)
    print(json.dumps(value,indent=2))
