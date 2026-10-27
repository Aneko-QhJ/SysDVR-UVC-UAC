"""Adopt one reviewed saved63 snapshot. All operations here are file-only.

The saved59 workflow remains immutable and rejects this snapshot. This version
binds both log versions and the exact reviewed delta; it never ignores log drift.
"""
from pathlib import Path
import context65_workflow as old

ROOT=old.ROOT; A=old.A; LEDGER=old.LEDGER; b=old.b; card=old.card
OFFLINE=old.OFFLINE; PACKAGE=old.PACKAGE; previous=old.previous
canonical=old.canonical; require=old.require; plain=old.plain; sha=old.sha; load=old.load
write=old.write; replace=old.replace; timestamp=old.timestamp; commitment=old.commitment
verify_build=old.verify_build; latest_snapshot=old.latest_snapshot
ANCHOR=ROOT/'private/card-cycles/20261018-context65-flag-drift-read'
PARENT=A/'A23-context65-flag-card-live-closeout-20261018'
PARENT_SUM='be6c2c5198203d33f1f22de98270b88ef29893c3755f2235e1b1dfcd16f676cd'
PROOF=A/'A23-context65-baseline63-proof.json'
FILES=('tools/context65_baseline63.py','tools/prepare_a23_context65_baseline63.py',
    'tools/workflows/capture_a23_context65_baseline63.py','tools/context65_baseline63_recovery.py',
    'tools/collect_a23_context65_baseline63.py','tools/audit_a23_context65_baseline63.py',
    'tests/test_a23_context65_baseline63.py')
OWNER=A/'A23-context65-flag-card-volume-owner.json'


def predecessor():
    card.seal_verify(PARENT)
    require(sha(plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'saved live closeout changed')
    value=load(PARENT/'closeout.json')
    require(len(value['source_hashes'])==303,'unexpected predecessor source count')
    for name,digest in value['source_hashes'].items():
        require(sha(plain(b.REPO/name,2*1024*1024))==digest,'old303 source changed: '+name)
    for name,digest in value['protected_sha256'].items():
        require(sha(plain(Path(name)))==digest,'protected record/source changed: '+name)
    return value


def hashes():
    result=dict(predecessor()['source_hashes'])
    for name in FILES:
        key='research/usb-ds-iso/'+name;require(key not in result,'new source overlaps old303')
        result[key]=sha(plain(ROOT/name,2*1024*1024))
    return dict(sorted(result.items()))


def reference(directory):
    directory=canonical(directory);saved=card.seal_verify(directory)
    return dict(directory=str(directory),manifest_sha256=sha(plain(directory/'SHA256SUMS')),entries=len(saved))


def raw_inventory(files):
    return card.inventory({n.removeprefix('card/'):v for n,v in files.items() if n.startswith('card/')})


def adoption(scope):
    """Reproduce the exact sealed delta; preserve the failed job and its owner."""
    parent=predecessor();refs=parent['references']
    for key in ('current_card_snapshot','current_card_analysis','readonly_drift_triage','actual_failed_card_job'):
        require(reference(refs[key]['directory'])==refs[key],'saved live reference changed: '+key)
    require(refs['current_card_snapshot']['directory']==str(ANCHOR),'wrong adopted snapshot')
    files=card.verify_snapshot(ANCHOR);before=card.verify_snapshot(old.ANCHOR)
    current=raw_inventory(files);original=raw_inventory(before)
    report=load(Path(refs['current_card_analysis']['directory'])/'report.json')
    delta=load(Path(refs['readonly_drift_triage']['directory'])/'delta.json')
    added=sorted(set(current)-set(original));removed=sorted(set(original)-set(current))
    changed=sorted(n for n in set(current)&set(original) if current[n]!=original[n])
    require(len(original)==59 and len(current)==63 and added==delta['added']==report['added'] and
        removed==delta['removed']==report['removed']==[] and changed==delta['changed']==report['changed']==['logfile.txt'],
        'reviewed59-to63 delta differs')
    require({n:current[n] for n in added}==delta['added_inventory'] and
        {n:original[n] for n in changed}==delta['changed_before'] and
        {n:current[n] for n in changed}==delta['changed_after'],'reviewed delta bytes differ')
    meta=load(ANCHOR/'snapshot.json');eject=load(ANCHOR/'eject.json')
    require(meta['simulation'] is False and meta['mode']=='recovery' and meta['read_only_mount_verified'] is True and
        meta['identity']['VolumeUUID']==card.UUID and meta['deployment_files_match'] is True and
        meta['device_binding_sha256']==scope['device_binding_sha256'] and
        meta['expected_recipe_sha256']==scope['runtime_recipe_sha256'] and
        eject['ejected'] is True and eject['mount_absent'] is True and
        timestamp(meta['collected_at'])>timestamp(load(old.ANCHOR/'snapshot.json')['collected_at']),
        'adopted snapshot identity/mode/deployment/eject differs')
    require(b.old.typed(meta['expected_deployment_files'],scope['deployment_files']),'adopted package differs')
    state=Path(refs['actual_failed_card_job']['directory'])/'state.json'
    require(sha(plain(state))==parent['actual_failed_job_state_sha256'] and
        load(state)['stage']=='failed_no_retry' and sha(plain(OWNER))==parent['owner_retained_sha256'],
        'failed card job or retained owner changed; manual review required')
    require(report['preserved_old_files']==58 and report['requests']==[] and report['trace_record_count']==0 and
        report['host_session_uniquely_bound'] is False and report['physical_run_authenticated'] is False and
        report['actual_card_repaired_by_agent'] is False,'saved analysis facts changed')
    return dict(schema='A23-context65-baseline63-adoption-1',snapshot=refs['current_card_snapshot'],
        prior_snapshot=reference(old.ANCHOR),analysis=refs['current_card_analysis'],triage=refs['readonly_drift_triage'],
        failed_card_job=refs['actual_failed_card_job'],failed_job_state_sha256=parent['actual_failed_job_state_sha256'],
        retained_owner_sha256=parent['owner_retained_sha256'],raw_files=63,preserved_old_files=58,
        added={n:current[n] for n in added},removed=[],changed_before=delta['changed_before'],changed_after=delta['changed_after'],
        current_inventory=current,both_log_versions_preserved=True,old59_guard_unchanged=True,
        flag_origin_or_restore_time_established=False,physical_run_authenticated=False,test_authorized=False)


def proof():
    if not PROOF.exists():return None
    value=load(PROOF);require(value.get('schema')=='A23-context65-baseline63-proof-1','invalid baseline63 proof')
    expected=hashes()
    for key,filename in [('review','audit.json'),('validation','validation.json')]:
        row=value[key];directory=canonical(row['directory']);card.seal_verify(directory)
        require(sha(plain(directory/'SHA256SUMS'))==row['manifest_sha256'],'baseline63 proof seal differs')
        data=load(directory/filename)
        require(data.get('passed') is True and data.get('source_hashes')==expected and
            all(type(data.get(k)) is int and data[k]==0 for k in
                ('usb_requests','sd_accesses','formal_reservations','formal_records','real_sdk_objects')),
            'baseline63 proof scope differs')
        if key=='validation':require(data['tests_run']>0 and data['failures']==data['errors']==data['skipped']==0,'baseline63 tests incomplete')
    return value


def materials():
    source,scope=old.materials()
    scope.update(schema='A23-context65-baseline63-scope-1',prior_workflow_proof=scope['workflow_proof'],
        source_hashes=hashes(),workflow_proof=proof(),
        baseline_anchor=dict(directory=str(ANCHOR),manifest_sha256=sha(plain(ANCHOR/'SHA256SUMS'))))
    scope['baseline_adoption']=adoption(scope)
    return source,scope


def verify_recovery(directory,scope,*,simulation=False,require_latest=True):
    require(type(simulation) is bool and type(require_latest) is bool,'boolean recovery mode required')
    directory=canonical(directory);files=card.verify_snapshot(directory)
    meta=load(directory/'snapshot.json');eject=load(directory/'eject.json')
    require(meta['simulation'] is simulation and eject.get('simulation',False) is simulation and
        meta['mode']=='recovery' and meta['read_only_mount_verified'] is True and meta['identity']['VolumeUUID']==card.UUID and
        meta['device_binding_sha256']==scope['device_binding_sha256'] and meta['deployment_files_match'] is True and
        meta['expected_recipe_sha256']==scope['runtime_recipe_sha256'] and eject['ejected'] is True and eject['mount_absent'] is True,
        'matching read-only recovery/eject required')
    require(b.old.typed(meta['expected_deployment_files'],scope['deployment_files']),'all four deployment files must match')
    require(scope['baseline_adoption']==adoption(scope),'adoption scope changed')
    require(raw_inventory(files)==scope['baseline_adoption']['current_inventory'],
        'saved63 inventory changed; independent re-review required')
    require(timestamp(meta['collected_at'])>=timestamp(load(ANCHOR/'snapshot.json')['collected_at']),
        'recovery predates saved63 adoption')
    if not simulation and require_latest:require(directory==latest_snapshot(),'latest saved recovery required; older success is not a fallback')
    return dict(directory=str(directory),manifest_sha256=sha(plain(directory/'SHA256SUMS')),simulation=simulation)


def transition(record=None,record_path=None,*,runs_root=None,ledger=None):
    return old.transition(record,record_path,runs_root=runs_root,ledger=ledger)


def verify_scope(record,path):
    import context65_once_reservation as reservations
    path=canonical(path);require(record.get('record_path')==str(path),'record path differs')
    issued=record['issuance'];require(issued.get('schema')=='A23-context65-baseline63-issuance-1' and
        type(issued['maximum_invocations']) is int and issued['maximum_invocations']==1 and issued['automatic_retry'] is False,'invalid issuance')
    source,scope=materials();require(b.old.typed(issued['scope'],scope),'issuance baseline63/source scope changed')
    require(all(record[k]==source[k] for k in ('build','receiver_sha256','build_manifest_sha256','recipe_sha256','device_binding_sha256','device_binding','plan')),'issued candidate changed')
    receipt=issued['reservation'];reservations.verify(receipt,path,record)
    require(previous.verify_deployment(issued['deployment']['directory'],scope)==issued['deployment'],'deployment receipt changed')
    require(verify_recovery(issued['recovery']['directory'],scope,simulation=receipt['simulation'],require_latest=record['stage']=='prepared')==issued['recovery'],'recovery receipt changed')
    if not receipt['simulation']:require(scope['workflow_proof'] is not None,'formal baseline63 proof required')
    transition(record,path)
    return verify_build(record)
