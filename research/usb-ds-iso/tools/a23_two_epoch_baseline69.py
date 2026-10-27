"""Read-only adoption of the exact saved69 recovery; no card or issuance writer."""
from pathlib import Path
import json
import build_a23_two_epoch_entry as entry
import context65_once_reservation as legacy
from a23_sequence32_model import encode,sha,parse,require,integer
w=entry.w
PARENT=w.A/'A23-sdk-entry-closeout-20261019'
PARENT_SUM='b9738b92e44a5d5d50ea2a8bc9b70f1371330ee4359a37575cc995756a62b5ae'
LIVE=w.A/'A23-context65-first-live-closeout-20261018'
LIVE_SUM='986c331bbc9c67ad653e02b68e9591081e0de4919530c9152f8cb004bd8e77ec'
ANCHOR=w.ROOT/'private/card-cycles/20261018-context65-first-live-read'
ANCHOR_SUM='2e5e4375acb822927e71c46e5bf6eb3618047064972c307268aef34670860205'
NEW=('tools/a23_two_epoch_baseline69.py','tools/a23_sequence32_model.py','tools/analyze_a23_sequence32.py',
     'tools/prepare_a23_two_epoch.py','tools/audit_a23_two_epoch_workflow.py','tests/test_a23_two_epoch_workflow.py')
PACKAGE={
'atmosphere/contents/00FF0000A53BB666/exefs.nsp':dict(bytes=117024,sha256='b54747adb8e824bb0a08709868335a06c1aca53c6b1e4e8ce6a1d2e761b8deb8'),
'atmosphere/contents/00FF0000A53BB666/flags/boot2.flag':dict(bytes=0,sha256=sha(b'')),
'atmosphere/contents/00FF0000A53BB666/toolbox.json':dict(bytes=90,sha256='c5d8c15172dc275b02f7084b187d9ceed6f9fe600467fb3320209274d9684c52'),
'atmosphere/exefs_patches/SysDVR-ISO/AD8D36F2029822A4C498F055ADBDAA789EB913C6000000000000000000000000.ips':dict(bytes=905,sha256='80991e082dda79da38f016b635715cec0bae4ec7c4963820a769cde17280416f')}

def sources():
    w.card.seal_verify(PARENT);require(sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'parent closeout differs')
    old=w.load(PARENT/'closeout.json');out=entry.sources();require(out==old['source_hashes'] and len(out)==345,'prior345 drift')
    for n,h in old['protected_sha256'].items():require(sha(w.plain(Path(n)))==h,'protected drift')
    for n in NEW:
        key='research/usb-ds-iso/'+n;require(key not in out,'new source overlap');out[key]=sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))

def inventory(files):return {n.removeprefix('card/'):dict(bytes=len(raw),sha256=sha(raw)) for n,raw in files.items() if n.startswith('card/')}

def validate_saved69(files):
    require(type(files) is dict and set(files)=={'snapshot.json','eject.json'}|{n for n in files if n.startswith('card/')},'snapshot inventory differs')
    m=parse(files['snapshot.json']);e=parse(files['eject.json']);inv=inventory(files)
    require(len(inv)==69 and encode(m.get('raw_files'))==encode(inv),'exact69 raw inventory differs')
    require(m.get('schema')=='A23-path-span-card-snapshot-1' and m.get('mode')=='recovery' and m.get('simulation') is False and m.get('read_only_mount_verified') is True and m.get('deployment_files_match') is True,'saved69 recovery mode differs')
    require(e.get('simulation') is False and e.get('ejected') is True and e.get('mount_absent') is True,'saved69 eject differs')
    require(m.get('identity',{}).get('VolumeUUID')=='37614F76-3E12-3470-B5C8-52B5A449C213' and m['identity'].get('WritableVolume') is False,'saved69 card identity differs')
    require(m.get('device_binding_sha256')=='a10e3750ed104576c05b205145e8a8efefe8811d20dec0d1e1debc8c368c61cf' and m.get('expected_recipe_sha256')=='37269528ee3baa2941e1cb9268ccd4702d9db5b0fec87e913d3111c99b6e894f','saved69 device binding differs')
    require(encode(m.get('expected_deployment_files'))==encode(PACKAGE),'saved69 expected package differs')
    rows=m.get('deployment_files');require(type(rows) is list and len(rows)==4 and all(type(r) is dict and set(r)=={'path','size','sha256'} for r in rows),'saved69 deployment list differs')
    observed={r['path']:dict(bytes=r['size'],sha256=r['sha256']) for r in rows};require(encode(observed)==encode(PACKAGE) and all(encode(inv.get(n))==encode(v) for n,v in PACKAGE.items()),'saved69 deployed bytes differ')
    for k in ('hardware_verified','physical_run_authenticated','root_cause_confirmed','card_files_written','attempt_issued'):require(m.get(k) is False,'saved69 unsupported claim: '+k)
    require(integer(m.get('remaining'),0,0) and integer(m.get('usb_requests'),0,0),'saved69 observation count differs')
    w.timestamp(m['collected_at']);w.timestamp(e['ejected_at'])
    return dict(schema='A23-two-epoch-baseline69-validation-1',raw_files=69,current_inventory=inv,inventory_sha256=sha(encode(inv)),deployment_files=PACKAGE,
        read_only_recovery_and_eject=True,physical_run_authenticated=False,hardware_verified=False,device_dual_epoch_reuse_established=False)

def adoption():
    hashes=sources();w.card.seal_verify(LIVE);require(sha(w.plain(LIVE/'SHA256SUMS'))==LIVE_SUM,'saved live closeout differs')
    c=w.load(LIVE/'closeout.json');files=w.card.verify_snapshot(ANCHOR);require(sha(w.plain(ANCHOR/'SHA256SUMS'))==ANCHOR_SUM and w.latest_snapshot()==ANCHOR,'latest saved recovery differs; no fallback')
    result=validate_saved69(files);report_ref=c['references']['analysis'];report_root=Path(report_ref['directory']);w.card.seal_verify(report_root)
    require(w.reference(report_root)==report_ref,'saved analysis differs');report=w.load(report_root/'report.json')
    previous=w.ROOT/'private/card-cycles/20261018-context65-flag-drift-read';old=w.card.verify_snapshot(previous);require(w.reference(previous)==report['baseline'],'prior63 reference differs');before=inventory(old);now=result['current_inventory']
    added=sorted(set(now)-set(before));removed=sorted(set(before)-set(now));changed=sorted(n for n in set(before)&set(now) if before[n]!=now[n])
    require(len(before)==63 and len(added)==6 and added==report['added'] and removed==report['removed']==[] and changed==report['changed']==['logfile.txt'] and report['preserved_old_files']==62,'reviewed63-to69 delta differs')
    require(report['raw_files']==69 and report['existing_erpt_unchanged']==8 and report['new_erpt']==0 and report['same_physical_run_verified'] is False and report['hardware_verified'] is False,'saved report facts differ')
    parent=w.load(PARENT/'closeout.json');owner=w.A/'A23-context65-flag-card-volume-owner.json';failed=w.A/'A23-context65-flag-card-ready-20261018/state.json'
    require(sha(w.plain(owner))==parent['failed_owner_sha256'] and sha(w.plain(failed))==parent['failed_job_state_sha256'],'failed repair owner/state differs')
    p=w.load(w.A/'A23-context65-pending.json');require(p['stage']=='sequence65_recovered' and p['remaining']==0 and p['recovered'] is True and p['device_log_pending'] is False and p['ejected'] is True and p['next_sequence_reserved'] is False,'live ticket is not recovered/unreserved')
    history=[]
    for first,row in legacy.entries(w.LEDGER).items():
        v=row['value'];require(v['simulation'] is False,'model in actual ledger');target=Path(v['record']);history.append(dict(first=first,last=v['last'],reservation_sha256=row['sha256'],record_sha256=sha(w.plain(target))))
    require(sorted((r['first'],r['last']) for r in history)==[(49,64),(65,80)],'actual ledger interval drift')
    build=Path(parent['references']['build']['directory']);entry.verify_build(build);require(w.reference(build)==parent['references']['build'],'entry build reference differs')
    return dict(**result,snapshot=w.reference(ANCHOR),prior_snapshot=w.reference(previous),live_closeout=w.reference(LIVE),analysis=report_ref,
        added=added,removed=removed,changed=changed,preserved_old_files=62,history=history,source_hashes=hashes,
        build=w.reference(build),receiver_sha256=w.load(build/'binary.json')['receiver_sha256'],failed_owner_sha256=parent['failed_owner_sha256'],failed_job_state_sha256=parent['failed_job_state_sha256'])
