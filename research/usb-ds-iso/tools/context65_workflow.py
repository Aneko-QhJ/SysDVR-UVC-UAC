"""File-only workflow binding for the immutable context65 receiver.

The old builder deliberately compares the whole live history before a burn.
This verifier retains all build checks, then separately admits only the exact
reservation/record/run belonging to this invocation. It never edits old tools.
"""
from pathlib import Path
from datetime import datetime
import json
import os
import uuid

import build_a23_context65_receiver as b
import path_span_card_workflow as card
import build_a23_path_span_deployment as package
from workflows import capture_a23_sequence_receiver as previous

ROOT=b.ROOT;A=ROOT/'private/analysis';LEDGER=ROOT/'private/sequence-reservations'
OFFLINE=A/'A23-context65-receiver-review-20261017-r3/offline-record.json'
VALIDATION=A/'A23-context65-receiver-validation-20261017-r2'
PACKAGE=A/'A23-path-span-deployment-review-20261016'
ANCHOR=ROOT/'private/card-cycles/20261017-154709-sequence-first-live-read'
PROOF=A/'A23-context65-workflow-proof.json'
FILES=('tools/context65_workflow.py','tools/context65_once_reservation.py','tools/prepare_a23_context65_once.py',
    'tools/workflows/capture_a23_context65_receiver.py','tools/context65_recovery.py',
    'tools/collect_a23_context65_once.py','tools/audit_a23_context65_workflow.py','tests/test_a23_context65_workflow.py')
require=b.require;plain=b.plain;sha=b.sha;load=b.load;write=b.write

def canonical(path):
    path=Path(path);require(path.is_absolute() and path==path.resolve(),'canonical path required');return path

def replace(path,value):
    path=canonical(path);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    write(tmp,value);os.replace(tmp,path);b.old.sync_dir(path.parent)

def hashes():
    result=b.source_hashes()
    for n in FILES:result['research/usb-ds-iso/'+n]=sha(plain(ROOT/n,2*1024*1024))
    return dict(sorted(result.items()))

def verify_build(record):
    """Same byte/identity/inventory checks as build8, with frozen history only."""
    require(type(record) is dict and record.get('schema')=='A23-waiting-receiver-record-8' and
        record.get('backend')=='a23-waiting-burst-1' and all(record.get(k) is False for k in b.POLICY),'invalid build8 record')
    require(str(uuid.UUID(record['preparation_id']))==record['preparation_id'],'invalid preparation UUID')
    b.device.history.verify_scope(live=False)
    folder=canonical(record['build']);bound=b.device.identity(Path(record['device_binding']['device_source_root']))
    source=b.source_hashes();raws={n:plain(b.REPO/n,2*1024*1024) for n in source};generated=b.device.generated(raws,bound)
    meta=dict(schema='A23-waiting-receiver-build-8',backend='a23-waiting-burst-1',source_root=str(b.REPO),source_hashes=source,
        device_binding=bound,device_binding_sha256=b.device.binding_hash(bound),recipe_sha256=bound['runtime_recipe_sha256'],
        generated_hashes={n:sha(v) for n,v in generated.items()},description=b.description(bound),acquisition_enabled=False,attempt_issued=False)
    require(b.old.typed(load(folder/'manifest.json'),meta),'current/frozen metadata mismatch')
    require(b.old.typed(record['device_binding'],bound) and record['device_binding_sha256']==meta['device_binding_sha256'] and
        record['recipe_sha256']==meta['recipe_sha256'] and b.old.typed(record['plan'],b.WAIT_PLAN),'record identity/plan differs')
    expected=b.TOP|{'source/'+n for n in source}|{'generated/'+n for n in generated}|{'device/'+n for n in b.device.FILES}
    saved=card.seal_verify(folder);require(set(saved)==expected and len(saved)<=352,'build8 inventory differs')
    require(sha(plain(folder/'SHA256SUMS'))==record['build_manifest_sha256'] and sha(saved['receiver'])==record['receiver_sha256'],'build/receiver digest differs')
    require(saved['a23_waiting_build_binding.h']==b.binding_header(meta) and saved['describe.json']==b.canonical(b.description(bound)) and
        saved['device-binding.json']==b.canonical(bound),'embedded binding differs')
    require(all(sha(saved['source/'+n])==h for n,h in source.items()) and
        all(saved['generated/'+n]==raw for n,raw in generated.items()) and
        all(sha(saved['device/'+n])==h for n,h in bound['artifact_hashes'].items()),'frozen source/device differs')
    require(b.source_hashes()==source and b.device.identity(Path(bound['device_source_root']))==bound,'inputs changed during verification')
    return folder

def commitment(record):
    issued=record['issuance']
    return sha(b.canonical({k:record[k] for k in ('record_path','preparation_id','receiver_sha256','build_manifest_sha256',
        'recipe_sha256','device_binding_sha256','plan')} | {'scope':issued['scope'],'deployment':issued['deployment'],'recovery':issued['recovery']}))

def transition(record=None,record_path=None,*,runs_root=None,ledger=None):
    """Only this reservation's exact new artifacts may differ from history.

    roots are injectable solely for disposable file fixtures. Formal callers
    always use the fixed repository roots; the capture gate binds own run names.
    """
    import context65_once_reservation as reservations
    frozen,digest=b.device.history.verify_scope(live=False);expected=frozen['files']
    runs=canonical(runs_root or ROOT/'private/runs');ledger=canonical(ledger or LEDGER)
    owned=None;owned_run=None
    if record is not None:
        record_path=canonical(record_path);receipt=record['issuance']['reservation'];reservations.verify(receipt,record_path,record)
        if record_path.exists():require(load(record_path)==record,'record changed during verification')
        if record['stage']=='prepared':
            require(type(record['remaining']) is int and record['remaining']==1 and record['acquisition_enabled'] is True and
                record.get('run') is None,'prepared record must not hide a run')
        else:
            require(record['stage'] in ('consumed','captured_logs_pending','failed_no_retry','unresolved_no_retry') and
                type(record['remaining']) is int and record['remaining']==0 and record['acquisition_enabled'] is False,'invalid consumed transition')
        # A model receipt never excludes anything from the production history.
        if not receipt['simulation']:
            require(ledger==LEDGER,'formal transition requires formal ledger');owned=record_path
            if record.get('run') is not None:
                owned_run=canonical(record['run'])
                require(owned_run.parent==runs and owned_run.name=='A-context65-waiting-'+record['preparation_id'],'foreign run exclusion refused')
    current={}
    folders=sorted({p for pattern in b.device.history.PATTERNS for p in runs.glob(pattern)})
    for folder in folders:
        require(folder.is_dir() and not folder.is_symlink(),'invalid history directory')
        if owned_run==folder:continue
        for p in folder.rglob('*'):
            require(not p.is_symlink(),'symlink in history')
            if p.is_file():current['runs/'+p.relative_to(runs).as_posix()]=sha(plain(p,32*1024*1024))
    for first,row in reservations.entries(ledger).items():
        if owned is not None and first==65:continue # receipt checked above, including commitment
        p=Path(row['path']);target=canonical(row['value']['record'])
        current['reservations/'+p.name]=sha(plain(p));current['issued-records/'+target.name]=sha(plain(target))
    require(current==expected,'foreign history/ledger/record drift; no acquisition')
    return dict(history_manifest_sha256=digest,owned_reservation_excluded=owned is not None,
        owned_run_excluded=owned_run is not None,unrelated_history_unchanged=True)

def proof():
    if not PROOF.exists():return None
    value=load(PROOF);require(value.get('schema')=='A23-context65-workflow-proof-1','invalid workflow proof pointer')
    expected=hashes()
    for key,filename in [('review','audit.json'),('validation','validation.json')]:
        row=value[key];path=canonical(row['directory']);card.seal_verify(path)
        require(sha(plain(path/'SHA256SUMS'))==row['manifest_sha256'],'workflow proof seal differs')
        data=load(path/filename)
        require(data.get('passed') is True and data.get('source_hashes')==expected and
            all(type(data.get(k)) is int and data[k]==0 for k in ('usb_requests','sd_accesses','formal_reservations','formal_records','real_sdk_objects')),
            'workflow proof scope differs')
        if key=='validation':require(data['tests_run']>0 and data['failures']==data['errors']==data['skipped']==0,'workflow tests not complete')
    return value

def materials():
    source=load(OFFLINE);verify_build(source)
    require(source['stage']=='offline_build_ready' and source['remaining']==0 and source['acquisition_enabled'] is False,'offline source not dormant')
    card.seal_verify(VALIDATION);v=load(VALIDATION/'validation.json')
    require(v['passed'] is True and v['tests_run']==18 and v['failures']==v['errors']==v['skipped']==0 and
        v['source_hashes']==b.source_hashes() and v['review_manifest_sha256']==sha(plain(OFFLINE.parent/'SHA256SUMS')),'receiver validation changed')
    package.verify_review(PACKAGE);p=load(PACKAGE/'package-report.json')
    require(p['device_binding_sha256']==source['device_binding_sha256'],'package/device differs')
    scope=dict(schema='A23-context65-once-scope-1',first_sequence=65,sequence_history_manifest_sha256=b.device.HISTORY_DIGEST,
        receiver_sha256=source['receiver_sha256'],build_manifest_sha256=source['build_manifest_sha256'],
        device_binding_sha256=source['device_binding_sha256'],runtime_recipe_sha256=source['recipe_sha256'],plan=source['plan'],
        offline_source_sha256=sha(plain(OFFLINE)),package_directory=str(PACKAGE),package_manifest_sha256=sha(plain(PACKAGE/'SHA256SUMS')),
        exefs_nsp_sha256=p['exefs_nsp_sha256'],deployment_files=p['deployment_files'],device_package_reused=True,
        host_configuration='host-sequence65-context-1',source_hashes=hashes(),workflow_proof=proof(),
        baseline_anchor=dict(directory=str(ANCHOR),manifest_sha256=sha(plain(ANCHOR/'SHA256SUMS'))))
    return source,scope

def timestamp(value):
    result=datetime.fromisoformat(value);require(result.tzinfo is not None,'timestamp needs timezone');return result

def latest_snapshot():
    candidates=[]
    for path in (ROOT/'private/card-cycles').glob('*/snapshot.json'):
        value=load(path)
        if value.get('schema')=='A23-path-span-card-snapshot-1' and value.get('mode')=='recovery' and value.get('simulation') is False:
            candidates.append((timestamp(value['collected_at']),path.parent))
    require(candidates,'no saved recovery');candidates.sort()
    require(len(candidates)<2 or candidates[-1][0]!=candidates[-2][0],'ambiguous latest recovery')
    return candidates[-1][1]

def verify_recovery(directory,scope,*,simulation=False,require_latest=True):
    directory=canonical(directory);files=card.verify_snapshot(directory);meta=load(directory/'snapshot.json');eject=load(directory/'eject.json')
    require(meta['simulation'] is simulation and eject.get('simulation',False) is simulation and
        meta['mode']=='recovery' and meta['read_only_mount_verified'] is True and meta['identity']['VolumeUUID']==card.UUID and
        meta['deployment_files_match'] is True and meta['expected_recipe_sha256']==scope['runtime_recipe_sha256'] and
        eject['ejected'] is True and eject['mount_absent'] is True,'matching read-only recovery/eject required')
    seen={r['path']:dict(bytes=r['size'],sha256=r['sha256']) for r in meta['deployment_files']}
    require(b.old.typed(seen,scope['deployment_files']),'all four deployment files must match')
    anchor=canonical(scope['baseline_anchor']['directory']);before=card.verify_snapshot(anchor)
    require(sha(plain(anchor/'SHA256SUMS'))==scope['baseline_anchor']['manifest_sha256'],'anchor changed')
    require(timestamp(meta['collected_at'])>timestamp(load(anchor/'snapshot.json')['collected_at']),'recovery predates the deployment mismatch')
    require(all(files.get(n)==raw for n,raw in before.items() if n.startswith('card/')),'saved59 originals changed or missing after flag repair')
    if not simulation and require_latest:require(directory==latest_snapshot(),'latest saved recovery required; older success is not a fallback')
    return dict(directory=str(directory),manifest_sha256=sha(plain(directory/'SHA256SUMS')),simulation=simulation)

def verify_scope(record,path):
    import context65_once_reservation as reservations
    path=canonical(path);require(record.get('record_path')==str(path),'record path differs')
    issued=record['issuance'];require(issued.get('schema')=='A23-context65-once-issuance-1' and
        type(issued['maximum_invocations']) is int and issued['maximum_invocations']==1 and issued['automatic_retry'] is False,'invalid issuance')
    source,scope=materials();require(b.old.typed(issued['scope'],scope),'issuance workflow/source scope changed')
    require(all(record[k]==source[k] for k in ('build','receiver_sha256','build_manifest_sha256','recipe_sha256','device_binding_sha256','device_binding','plan')),'issued candidate changed')
    receipt=issued['reservation'];reservations.verify(receipt,path,record)
    require(previous.verify_deployment(issued['deployment']['directory'],scope)==issued['deployment'],'deployment receipt changed')
    require(verify_recovery(issued['recovery']['directory'],scope,simulation=receipt['simulation'],require_latest=record['stage']=='prepared')==issued['recovery'],'recovery receipt changed')
    if not receipt['simulation']:require(scope['workflow_proof'] is not None,'formal workflow proof required')
    transition(record,path)
    return verify_build(record)
