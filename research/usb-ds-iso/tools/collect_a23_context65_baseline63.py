"""Freeze an owned invocation with the new history transition checks. No USB."""
from pathlib import Path
import argparse
import json
import uuid
import context65_baseline63 as w
import collect_a23_context65_execution as c

BASELINE_FILES=('baseline63-adoption.json','baseline63-current-SHA256SUMS','baseline63-prior-SHA256SUMS',
    'baseline63-current-snapshot.json','baseline63-prior-snapshot.json','baseline63-current-logfile.txt','baseline63-prior-logfile.txt')


def baseline_inputs(record):
    adopted=record['issuance']['scope']['baseline_adoption']
    files={'baseline63-adoption.json':w.b.canonical(adopted)}
    for label,key in [('current','snapshot'),('prior','prior_snapshot')]:
        directory=w.canonical(adopted[key]['directory'])
        for name,suffix in [('SHA256SUMS','SHA256SUMS'),('snapshot.json','snapshot.json'),('card/logfile.txt','logfile.txt')]:
            files['baseline63-'+label+'-'+suffix]=w.plain(directory/name,1024*1024)
    return files


def supplied_baseline(root,record):
    # Supplied bytes only: moved analysis never opens the original SD, ledger,
    # repository, snapshots, proof paths or a saved repair job.
    scope=record['issuance']['scope'];adopted=scope['baseline_adoption'];folder=Path(root)/'binding'
    w.require(scope['schema']=='A23-context65-baseline63-scope-1' and
        adopted.get('schema')=='A23-context65-baseline63-adoption-1' and
        w.plain(folder/'baseline63-adoption.json')==w.b.canonical(adopted) and
        adopted['both_log_versions_preserved'] is True and adopted['old59_guard_unchanged'] is True and
        adopted['test_authorized'] is False and adopted['physical_run_authenticated'] is False and
        adopted['flag_origin_or_restore_time_established'] is False,'supplied baseline adoption differs')
    inventories={}
    for label,key,count in [('current','snapshot',63),('prior','prior_snapshot',59)]:
        sums=w.plain(folder/('baseline63-'+label+'-SHA256SUMS'),1024*1024)
        ref=adopted[key];w.require(w.sha(sums)==ref['manifest_sha256'],'supplied baseline manifest differs')
        entries={}
        for line in sums.decode().splitlines():
            digest,name=line.split('  ',1)
            w.require(name not in entries and c.re.fullmatch('[0-9a-f]{64}',digest) and
                c.re.fullmatch(r'[A-Za-z0-9_.\-/]+',name) and not Path(name).is_absolute() and
                all(part not in ('','.','..') for part in name.split('/')),'invalid supplied baseline manifest')
            entries[name]=digest
        w.require(len(entries)==count+2==ref['entries'] and
            set(entries)=={'snapshot.json','eject.json'}|{n for n in entries if n.startswith('card/')} and
            sums==''.join(entries[n]+'  '+n+'\n' for n in sorted(entries)).encode(),'supplied baseline manifest inventory differs')
        raw=w.plain(folder/('baseline63-'+label+'-snapshot.json'))
        w.require(w.sha(raw)==entries['snapshot.json'],'supplied baseline metadata bytes differ')
        meta=c.parse(raw);inventory=meta['raw_files'];inventories[label]=inventory
        w.require(len(inventory)==count and set(entries)=={'snapshot.json','eject.json'}|{'card/'+n for n in inventory} and
            all(row['sha256']==entries['card/'+n] and type(row['bytes']) is int and row['bytes']>=0 for n,row in inventory.items()) and
            meta['schema']=='A23-path-span-card-snapshot-1' and meta['mode']=='recovery' and meta['simulation'] is False and
            meta['read_only_mount_verified'] is True and meta['expected_recipe_sha256']==record['recipe_sha256'] and
            meta['device_binding_sha256']==record['device_binding_sha256'] and meta['identity']['VolumeUUID']==w.card.UUID,
            'supplied baseline identity/inventory differs')
        log=w.plain(folder/('baseline63-'+label+'-logfile.txt'))
        w.require(dict(bytes=len(log),sha256=w.sha(log))==inventory['logfile.txt'],'supplied baseline log differs')
        if label=='current':
            w.require(meta['deployment_files_match'] is True and w.b.old.typed(meta['expected_deployment_files'],scope['deployment_files']) and
                scope['baseline_anchor']=={k:ref[k] for k in ('directory','manifest_sha256')},'supplied current deployment/anchor differs')
    current=inventories['current'];prior=inventories['prior']
    added={n:current[n] for n in sorted(set(current)-set(prior))}
    changed=sorted(n for n in set(current)&set(prior) if current[n]!=prior[n])
    w.require(current==adopted['current_inventory'] and len(added)==4 and added==adopted['added'] and
        set(prior)<=set(current) and adopted['removed']==[] and changed==['logfile.txt'] and
        adopted['changed_before']=={n:prior[n] for n in changed} and adopted['changed_after']=={n:current[n] for n in changed} and
        adopted['raw_files']==63 and adopted['preserved_old_files']==58,'supplied reviewed59-to63 delta differs')
    return True


def metadata(files,recipe):
    return {**c.metadata(files,recipe),'schema':'A23-context65-baseline63-collection-1','parent_launch_environment_required':True,'baseline63_adoption_required':True}

def analyze_inputs(root,recipe):
    root=Path(root);result=c.analyze_inputs(root,recipe);valid=False;reserved=False;adopted=False;errors=[];burn_errors=[];baseline_errors=[]
    try:
        record=w.load(root/'binding/record.json');env=w.load(root/'binding/launch-environment.json')
        model=record['issuance']['reservation']['simulation']
        w.require(type(model) is bool and env==record.get('launch_environment') and env.get('schema')=='A23-context65-launch-environment-1' and
            env.get('requested_execution_mode')==('injected_model' if model else 'require_escalated') and
            type(env.get('sandbox_query_result')) is int and env['sandbox_query_result']==0 and
            type(env.get('sandbox_query_errno')) is int and env['sandbox_query_errno']==0 and
            env.get('automatic_privilege_change') is False and env.get('usb_open_permission_proven') is False,'parent launch environment differs')
        valid=True
    except (OSError,ValueError,TypeError,KeyError) as error:errors.append(str(error).replace(str(root),'<collection>'))
    try:
        record=w.load(root/'binding/record.json');receipt=record['issuance']['reservation']
        raw=w.plain(root/'binding/reservation.json');burn=c.parse(raw)
        issued=record['issuance']
        w.require(issued.get('schema')=='A23-context65-baseline63-issuance-1' and type(issued.get('maximum_invocations')) is int and
            issued['maximum_invocations']==1 and issued.get('automatic_retry') is False,'invalid supplied issuance')
        w.require(type(receipt) is dict and set(receipt)=={'directory','path','sha256','simulation'} and
            type(receipt['simulation']) is bool and receipt['sha256']==w.sha(raw) and raw==w.b.canonical(burn),'supplied burn receipt differs')
        w.require(set(burn)=={'schema','first','last','record','scope','receiver','id','created_at','simulation','preparation_id','commitment_sha256'} and
            burn['schema']=='A23-sequence-reservation-2' and type(burn['first']) is int and burn['first']==65 and
            type(burn['last']) is int and burn['last']==80 and burn['simulation'] is receipt['simulation'] and
            burn['record']==record['record_path'] and burn['scope']==w.b.device.HISTORY_DIGEST and
            burn['receiver']==record['receiver_sha256'] and burn['preparation_id']==record['preparation_id'] and
            burn['commitment_sha256']==w.commitment(record),'supplied invocation commitment differs')
        w.require(type(burn['id']) is str and type(burn['preparation_id']) is str and
            w.canonical(receipt['path'])==w.canonical(receipt['directory'])/'block-00065.json' and
            str(uuid.UUID(burn['id']))==burn['id'] and str(uuid.UUID(burn['preparation_id']))==burn['preparation_id'],'supplied burn identity differs')
        w.canonical(burn['record']);w.timestamp(burn['created_at']);reserved=True
    except (OSError,ValueError,TypeError,KeyError) as error:burn_errors.append(str(error).replace(str(root),'<collection>'))
    try:
        adopted=supplied_baseline(root,w.load(root/'binding/record.json'))
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:baseline_errors.append(str(error).replace(str(root),'<collection>'))
    result.update(baseline63_adoption_consistent=adopted,baseline63_adoption_errors=baseline_errors,
        parent_launch_environment_consistent=valid,parent_launch_environment_errors=errors,
        reservation_commitment_consistent=reserved,reservation_commitment_errors=burn_errors)
    for key in ('bound_execution_chain_consistent','bound_execution_chain_complete','supplied_chain_complete'):
        result[key]=bool(result[key] and valid and reserved and adopted)
    return result

def analyze(root):
    root=Path(root);files=c.tree(root);snapshot=dict(files)
    expected={'host','binding','lifecycle','analysis.json','collection.json','SHA256SUMS','COMMITTED'}|{n for n in ('execution.bin','primary.bin') if n in files}
    w.require({p.name for p in root.iterdir()}==expected,'unexpected owned collection inventory')
    sums=files.pop('SHA256SUMS');commit=files.pop('COMMITTED')
    w.require(commit==(w.sha(sums)+'\n').encode() and sums==''.join(w.sha(raw)+'  '+n+'\n' for n,raw in sorted(files.items())).encode(),'owned collection seal differs')
    meta=c.parse(files.pop('collection.json'));saved=c.parse(files.pop('analysis.json'));recipe=meta['expected_recipe'];c.waiting.core.recipe_valid(recipe)
    required={'record.json','manifest.json','device-binding.json','build-SHA256SUMS','receiver'}|{'device/'+n for n in c.device.FILES}
    present={n.removeprefix('binding/') for n in files if n.startswith('binding/')}
    w.require(required<=present<=required|set(c.CLAIMS)|{'launch-environment.json','reservation.json'}|set(BASELINE_FILES),'binding inventory differs')
    life=[n for n in files if n.startswith('lifecycle/')]
    w.require(len(life)<=16 and all(c.re.fullmatch(r'lifecycle/[A-Za-z0-9_.-]+',n) and len(files[n])<=65536 for n in life),'lifecycle inventory differs')
    w.require(all(n in ('execution.bin','primary.bin') or n.startswith(('host/','binding/','lifecycle/')) for n in files),'unknown raw file')
    w.require(w.b.canonical(meta)==w.b.canonical(metadata(files,recipe)),'owned metadata differs')
    result=analyze_inputs(root,recipe);w.require(w.b.canonical(saved)==w.b.canonical(result) and c.tree(root)==snapshot,'owned saved analysis differs')
    return dict(schema='A23-context65-baseline63-collection-analysis-1',collection_integrity_verified=True,
        manifest_sha256=w.sha(sums),analysis=result,**{k:False for k in c.POLICY})

def freeze(host,output,record_path,run,lifecycle=(),execution=None,primary=None):
    host,output,record_path,run=map(w.canonical,(host,output,record_path,run));record=w.load(record_path)
    build=w.verify_scope(record,record_path);w.require(record.get('run')==str(run) and record['remaining']==0 and
        record['stage'] in ('captured_logs_pending','failed_no_retry','unresolved_no_retry'),'owned consumed run required')
    w.require(not output.exists(),'new collection required');paths=list(map(w.canonical,lifecycle))
    w.require(len(paths)<=16 and len({p.name for p in paths})==len(paths) and
        all(c.re.fullmatch(r'[A-Za-z0-9_.-]+',p.name) for p in paths),'duplicate/too many/invalid lifecycle files')
    raw_host=c.waiting.core.tree(host);raw_binding=c.old_inputs(record_path,run,build)
    reservation=w.canonical(record['issuance']['reservation']['path'])
    raw_binding.update(baseline_inputs(record))
    raw_binding['reservation.json']=w.plain(reservation)
    launch=run/'launch-environment.json'
    if launch.exists():raw_binding['launch-environment.json']=w.plain(launch,16384)
    raw_life={p.name:w.plain(p,65536) for p in paths}
    optional={n:w.plain(w.canonical(p),65536) for n,p in [('execution.bin',execution),('primary.bin',primary)] if p is not None}
    for source in [host,run,build,*paths,*[w.canonical(p) for p in (execution,primary) if p is not None]]:
        w.require(not output.is_relative_to(source),'output overlaps input')
    files={**{'host/'+n:raw for n,raw in raw_host.items()},**{'binding/'+n:raw for n,raw in raw_binding.items()},
        **{'lifecycle/'+n:raw for n,raw in raw_life.items()},**optional}
    output.mkdir(parents=True,mode=0o700)
    for n in ('host','binding','lifecycle'):(output/n).mkdir()
    for n,raw in files.items():w.card.pkg.put(output,n,raw)
    result=analyze_inputs(output,record['recipe_sha256'])
    after=c.old_inputs(record_path,run,build)
    after.update(baseline_inputs(w.load(record_path)))
    after['reservation.json']=w.plain(reservation)
    if launch.exists():after['launch-environment.json']=w.plain(launch,16384)
    w.require(c.waiting.core.tree(host)==raw_host and after==raw_binding and
        {p.name:w.plain(p,65536) for p in paths}==raw_life,'source changed during collection')
    for n,p in [('execution.bin',execution),('primary.bin',primary)]:
        if p is not None:w.require(w.plain(w.canonical(p),65536)==optional[n],'optional source changed')
    w.transition(record,record_path);w.write(output/'analysis.json',result);w.write(output/'collection.json',metadata(files,record['recipe_sha256']));w.b.seal(output)
    return analyze(output)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    sub.add_parser('analyze').add_argument('collection',type=Path)
    freeze_parser=sub.add_parser('freeze')
    for name in ('host','output','record','run'):freeze_parser.add_argument('--'+name,type=Path,required=True)
    for name in ('execution','primary'):freeze_parser.add_argument('--'+name,type=Path)
    freeze_parser.add_argument('--lifecycle',type=Path,action='append',default=[]);args=parser.parse_args()
    value=analyze(args.collection) if args.mode=='analyze' else freeze(args.host,args.output,args.record,args.run,args.lifecycle,args.execution,args.primary)
    print(json.dumps(value,indent=2))
