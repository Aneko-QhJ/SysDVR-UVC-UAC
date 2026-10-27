#!/usr/bin/env python3
"""Preserve supplied lifecycle/optional EXE3 files. Never authenticate a physical run."""
import argparse
import json
from pathlib import Path
import re
import uuid

import a23_lifecycle_device_binding as device
import build_a23_lifecycle_receiver as builder
import a23_lifecycle_capsule as capsule
import collect_a23_waiting_execution as waiting
from collect_a23_quiet_execution import tree,inputs as old_inputs
from analyze_io_usb_host_evidence import require,unique_object

POLICY=(*waiting.POLICY,'lifecycle_own_commit_authenticated','lifecycle_join_results_authenticated',
        'last_stage_is_latest_execution_proof','lifecycle_physical_run_authenticated')
CLAIMS=('waiting-authorization.json','WAIT_PROCESS_CLAIMED','WAIT_RECEIVER_CLAIMED')

def parse(raw):return json.loads(raw,object_pairs_hook=unique_object)


def binding_analysis(folder):
    folder=Path(folder);result=dict(supplied_binding_consistent=False,errors=[],**{k:False for k in POLICY})
    try:
        record=builder.load(folder/'record.json');meta=builder.load(folder/'manifest.json');bound=builder.load(folder/'device-binding.json')
        require(type(record) is dict and record.get('schema')=='A23-waiting-receiver-record-4' and
            record.get('backend')=='a23-waiting-burst-1' and device.old.typed(record.get('plan'),builder.WAIT_PLAN) and
            record.get('stage') in ('consumed','captured_logs_pending','failed_no_retry','unresolved_no_retry') and
            type(record.get('remaining')) is int and record['remaining']==0 and record.get('acquisition_enabled') is False and
            all(record.get(k) is False for k in builder.POLICY),'missing consumed bound record')
        require(type(record.get('preparation_id')) is str and str(uuid.UUID(record['preparation_id']))==record['preparation_id'],'invalid consumed preparation UUID')
        require(type(meta) is dict and meta.get('schema')=='A23-waiting-receiver-build-4' and
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
        require(type(meta.get('source_hashes')) is dict and 0<len(meta['source_hashes'])<=224 and
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
            **{n:bound[n] for n in device.EXTRA},device_binding_sha256=record['device_binding_sha256'],receipt_sha256=builder.sha(receipt_raw))
        process=builder.load(folder/'WAIT_PROCESS_CLAIMED')
        require(device.old.typed(process,dict(schema='A23-waiting-process-claim-1',checked=checked)),'process claim/build receipt mismatch')
        claim=builder.load(folder/'WAIT_RECEIVER_CLAIMED');identity=waiting.waiting.lines(folder.parent/'host/session.jsonl')[0]['details']['binding']['identity']
        expected=dict(schema='A23-waiting-burst-claim-1',receipt_sha256=builder.sha(receipt_raw),interface_id=identity['interface_id'],device_id=identity['device_id'],speed=3,
            build_manifest_sha256=record['build_manifest_sha256'],recipe_sha256=record['recipe_sha256'],
            parent_input_digest=bound['parent_input_digest'],device_elf_sha256=bound['device_elf_sha256'],**{n:bound[n] for n in device.EXTRA},device_binding_sha256=record['device_binding_sha256'])
        require(device.old.typed(claim,expected),'selected SDK claim/device receipt mismatch')
        result.update(supplied_binding_consistent=True,runtime_recipe_sha256=bound['runtime_recipe_sha256'],parent_input_digest=bound['parent_input_digest'],
            device_elf_sha256=bound['device_elf_sha256'],**{n:bound[n] for n in device.EXTRA},device_binding_sha256=record['device_binding_sha256'])
    except waiting.ERRORS as error:result['errors'].append(str(error).replace(str(folder),'<binding>'))
    return result


def lifecycle_analysis(root,recipe,execution):
    rows=[]
    for path in sorted((Path(root)/'lifecycle').iterdir()):
        raw=builder.plain(path,65536)
        row=dict(name=path.name,bytes=len(raw),full_sized=len(raw)==capsule.MAX,sha256=builder.sha(raw),header_valid=False,
                 filename_matches_nonce=False,context_matches_execution=None,clock_and_writer_match=None,errors=[])
        try:
            decoded=capsule.decode(raw,recipe);row.update(header_valid=True,prefix=decoded)
            row['filename_matches_nonce']=path.name=='ep0-life-'+decoded['main_nonce_hex']+'.bin'
            contexts=[r for r in decoded['records'] if r['stage']=='joined_context']
            row['context_records']=len(contexts)
            if execution is not None and contexts:
                row['context_matches_execution']=all(r['boot_id_hex']==execution['boot_id_hex'] and
                    r['session_id_hex']==execution['session_id_hex'] for r in contexts)
                row['clock_and_writer_match']=bool(decoded['writer']==execution['exporter'] and
                    decoded['frequency']==execution['window']['frequency'] and
                    decoded['start_tick']<=execution['window']['start_tick'] and
                    all(r['tick']>=execution['window']['stop_tick'] for r in contexts))
        except waiting.ERRORS as e:row['errors'].append(str(e))
        rows.append(row)
    single=rows[0] if len(rows)==1 else None
    associated=bool(single and single['header_valid'] and single['filename_matches_nonce'] and
        single['context_matches_execution'] is True and single['clock_and_writer_match'] is True)
    clean=bool(associated and single['full_sized'] and single['prefix']['error'] is None and single['prefix']['tail'] in ('zero_tail','capacity_end'))
    return dict(files=rows,file_count=len(rows),selection_ambiguous=len(rows)>1,
        supplied_context_associated=associated,associated_prefix_has_clean_tail=clean,
        own_commit_authenticated=False,physical_run_authenticated=False,join_results_authenticated=False,
        cleanup_authorized=False,last_stage_is_latest_execution_proof=False)


def analyze_inputs(root,recipe):
    root=Path(root);binding=binding_analysis(root/'binding');has_execution=(root/'execution.bin').exists()
    has_primary=(root/'primary.bin').exists();execution=None
    if binding['supplied_binding_consistent'] and binding['runtime_recipe_sha256']!=recipe:
        binding['supplied_binding_consistent']=False;binding['errors'].append('expected recipe differs from bound device')
    if has_execution:
        checked=waiting.analyze_inputs(root,recipe,has_primary)
        ex=checked['execution']
        if ex.get('execution_valid'):execution=ex['execution']
    else:
        checked=dict(schema='A23-lifecycle-missing-execution-1',expected_recipe=recipe,
            execution_present=False,external_primary_supplied=has_primary,waiting=waiting.analyze_waiting(root/'host'),
            supplied_chain_consistent=False,supplied_chain_complete=False,errors=[dict(component='execution',detail='not supplied')],
            **{k:False for k in POLICY})
    life=lifecycle_analysis(root,recipe,execution)
    consistent=bool(binding['supplied_binding_consistent'] and checked['supplied_chain_consistent'])
    complete=bool(consistent and checked['supplied_chain_complete'] and life['associated_prefix_has_clean_tail'])
    return dict(schema='A23-lifecycle-execution-analysis-1',expected_recipe=recipe,binding=binding,execution=checked,lifecycle=life,
        execution_present=has_execution,external_primary_supplied=has_primary,
        bound_execution_chain_consistent=consistent,bound_execution_chain_complete=bool(consistent and checked['supplied_chain_complete']),
        supplied_chain_complete=complete,**{k:False for k in POLICY})


def metadata(files,recipe):
    return dict(schema='A23-lifecycle-execution-collection-1',expected_recipe=recipe,
        artifact_origin='supplied_static_files_unverified',failed_bytes_preserved=True,
        raw_files=waiting.core.inventory(files),**{k:False for k in POLICY})


def analyze(root):
    root=Path(root);snapshot=tree(root);files=dict(snapshot)
    expected={'host','binding','lifecycle','analysis.json','collection.json','SHA256SUMS','COMMITTED'}|{n for n in ('execution.bin','primary.bin') if n in files}
    require({p.name for p in root.iterdir()}==expected,'unexpected lifecycle root inventory')
    sums=files.pop('SHA256SUMS');commit=files.pop('COMMITTED')
    require(commit==(builder.sha(sums)+'\n').encode() and sums==''.join(builder.sha(raw)+'  '+n+'\n' for n,raw in sorted(files.items())).encode(),'lifecycle collection seal mismatch')
    meta=parse(files.pop('collection.json'));saved=parse(files.pop('analysis.json'));recipe=meta.get('expected_recipe')
    waiting.core.recipe_valid(recipe)
    require((root/'host').is_dir() and (root/'binding').is_dir() and (root/'lifecycle').is_dir(),'missing lifecycle collection directory')
    binding_required={'record.json','manifest.json','device-binding.json','build-SHA256SUMS','receiver'}|{'device/'+n for n in device.FILES}
    binding_present={n.removeprefix('binding/') for n in files if n.startswith('binding/')}
    require(binding_required<=binding_present<=binding_required|set(CLAIMS),'unexpected or missing binding input')
    life=[n for n in files if n.startswith('lifecycle/')]
    require(len(life)<=16 and all(re.fullmatch(r'lifecycle/[A-Za-z0-9_.-]+',n) and len(files[n])<=65536 for n in life),'invalid lifecycle inventory')
    require(all(n in ('execution.bin','primary.bin') or n.startswith(('host/','binding/','lifecycle/')) for n in files),'unexpected lifecycle collection file')
    require(builder.canonical(meta)==builder.canonical(metadata(files,recipe)),'lifecycle inventory metadata mismatch')
    result=analyze_inputs(root,recipe)
    require(builder.canonical(saved)==builder.canonical(result),'lifecycle saved analysis differs')
    require(tree(root)==snapshot,'collection changed during reanalysis')
    return dict(schema='A23-lifecycle-execution-collection-analysis-1',collection_integrity_verified=True,
        manifest_sha256=builder.sha(sums),analysis=result,**{k:False for k in POLICY})


def freeze(host,output,record_path,run,lifecycle=(),execution=None,primary=None,repo=builder.REPO):
    host,output,record_path,run=map(Path,(host,output,record_path,run))
    require(output.is_absolute() and output==output.resolve() and not output.exists(),'new canonical collection required')
    record=builder.load(record_path);build=builder.verify_build(record,repo)
    recipe=record['recipe_sha256'];waiting.core.recipe_valid(recipe)
    paths=list(map(Path,lifecycle));require(len(paths)<=16 and len({p.name for p in paths})==len(paths),'too many/duplicate lifecycle filenames')
    require(all(re.fullmatch(r'[A-Za-z0-9_.-]+',p.name) for p in paths),'invalid lifecycle filename')
    raw_host=waiting.core.tree(host);raw_binding=old_inputs(record_path,run,build)
    raw_life={p.name:builder.plain(p,65536) for p in paths}
    optional={n:builder.plain(Path(p),65536) for n,p in [('execution.bin',execution),('primary.bin',primary)] if p is not None}
    for source in [host,run,build,*paths,*[Path(p) for p in (execution,primary) if p is not None]]:
        require(not output.is_relative_to(source),'output overlaps source')
    files={**{'host/'+n:raw for n,raw in raw_host.items()},**{'binding/'+n:raw for n,raw in raw_binding.items()},
           **{'lifecycle/'+n:raw for n,raw in raw_life.items()},**optional}
    output.mkdir(parents=True,mode=0o700)
    for d in ('host','binding','lifecycle'):(output/d).mkdir()
    for n,raw in files.items():
        target=output/n;target.parent.mkdir(parents=True,exist_ok=True);builder.old.durable_write(target,raw)
    result=analyze_inputs(output,recipe)
    require(waiting.core.tree(host)==raw_host and old_inputs(record_path,run,build)==raw_binding and
        {p.name:builder.plain(p,65536) for p in paths}==raw_life,'collection source changed')
    for n,p in [('execution.bin',execution),('primary.bin',primary)]:
        if p is not None:require(builder.plain(Path(p),65536)==optional[n],'optional source changed')
    require(tree(output)==files,'frozen raw files differ')
    builder.write(output/'analysis.json',result);builder.write(output/'collection.json',metadata(files,recipe));builder.seal(output)
    return analyze(output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    sub.add_parser('analyze').add_argument('collection',type=Path)
    f=sub.add_parser('freeze')
    for n in ('host','output','record','run'):f.add_argument('--'+n,type=Path,required=True)
    for n in ('execution','primary'):f.add_argument('--'+n,type=Path)
    f.add_argument('--lifecycle',type=Path,action='append',default=[]);a=p.parse_args()
    result=analyze(a.collection) if a.mode=='analyze' else freeze(a.host,a.output,a.record,a.run,a.lifecycle,a.execution,a.primary)
    print(json.dumps(result,indent=2))
