#!/usr/bin/env python3
"""Exercise temporary cards and seal copied evidence; never instantiate MacCard."""
import argparse,json,shutil,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import lifecycle_card_workflow as w
sys.path.insert(0,str(w.b.ROOT/'tests'))
from test_lifecycle_card_workflow import model_card

b=w.b;ANALYSIS=w.once.ANALYSIS
PARENT=ANALYSIS/'A23-lifecycle-preparation-final-20261016'
NEW=('tools/lifecycle_card_workflow.py','tools/audit_lifecycle_card_workflow.py','tests/test_lifecycle_card_workflow.py')
CASES=('success','wrong-uuid','old-baseline','changed-after-backup','partial-write','temporary-readback',
       'replace-error','sync-error','preserved-file-change','eject-error','recovery-missing','recovery-partial',
       'recovery-multiple','recovery-eject-error','computer-copy-error','computer-backup-error')


def exercise(case,root,destination):
    root.mkdir();card=model_card(root/'card');snapshot=root/'snapshot';deployment=root/'deployment'
    before=w.selected(card.root);failure=None;result=None
    try:
        if case.startswith('recovery-'):
            card.info['WritableVolume']=False
            if case=='recovery-partial':
                (card.root/'ep0-life-short.bin').write_bytes(b'EP0LCP1\0short')
                (card.root/'ep0-short.execution.bin').write_bytes(b'partial EXE3')
                (card.root/w.pkg.PATHS[0]).write_bytes(b'partial NSP')
            if case=='recovery-multiple':
                host=b.ROOT/'private/analysis/A23-lifecycle-receiver-review-20261016/collections/matching/lifecycle'
                raw=next(host.iterdir()).read_bytes()
                for name in ('ep0-life-first.bin','ep0-life-second.bin'):(card.root/name).write_bytes(raw)
            if case=='recovery-eject-error':
                with patch.object(card,'eject',side_effect=OSError('injected ejection failure')):result=w.recover(card,snapshot,eject_after=True)
            else:result=w.recover(card,snapshot)
        elif case=='computer-copy-error':
            original=w.put
            def corrupt(out,name,raw):return original(out,name,raw+b'x' if name=='card/logfile.txt' else raw)
            with patch.object(w,'put',side_effect=corrupt):result=w.snapshot(card,snapshot)
        else:
            if case=='wrong-uuid':card.info['VolumeUUID']='wrong'
            if case=='old-baseline':(card.root/w.pkg.PATHS[0]).write_bytes(b'old A23')
            w.snapshot(card,snapshot)
            if case=='changed-after-backup':(card.root/'logfile.txt').write_bytes(b'changed after backup')
            if case=='partial-write':
                original=b.old.durable_write
                def partial(path,raw):
                    if '.a23-lifecycle-' in str(path) and card.root in path.parents:
                        path.write_bytes(raw[:37]);raise OSError('injected partial temporary write')
                    return original(path,raw)
                with patch.object(b.old,'durable_write',side_effect=partial):result=w.deploy(card,snapshot,deployment)
            elif case=='temporary-readback':
                original=w.read_file
                def corrupt(path,*args):
                    raw=original(path,*args)
                    return raw[:-1] if '.a23-lifecycle-' in str(path) and card.root in Path(path).parents else raw
                with patch.object(w,'read_file',side_effect=corrupt):result=w.deploy(card,snapshot,deployment)
            elif case=='replace-error':
                with patch.object(w.os,'replace',side_effect=OSError('injected replace failure')):result=w.deploy(card,snapshot,deployment)
            elif case=='sync-error':
                with patch.object(card,'sync',side_effect=OSError('injected sync failure')):result=w.deploy(card,snapshot,deployment)
            elif case=='preserved-file-change':
                def changed():(card.root/'logfile.txt').write_bytes(b'changed during deployment')
                with patch.object(card,'sync',side_effect=changed):result=w.deploy(card,snapshot,deployment)
            elif case=='eject-error':
                with patch.object(card,'eject',return_value=dict(ejected=True,mount_absent=True,device='disk43')):result=w.deploy(card,snapshot,deployment)
            elif case=='computer-backup-error':
                original=w.put
                def corrupt(out,name,raw):return original(out,name,raw+b'x' if name=='backup/'+w.pkg.PATHS[0] else raw)
                with patch.object(w,'put',side_effect=corrupt):result=w.deploy(card,snapshot,deployment)
            else:result=w.deploy(card,snapshot,deployment)
    except (ValueError,OSError) as error:failure=dict(kind=type(error).__name__,detail=str(error).replace(str(root),'<model>'))
    expected_success=case in ('success','recovery-missing','recovery-partial','recovery-multiple')
    b.require((failure is None)==expected_success,'unexpected model outcome: '+case)
    destination.mkdir(parents=True)
    for name in ('snapshot','deployment'):
        source=root/name
        if source.exists():shutil.copytree(source,destination/name)
    after=w.selected(card.root)
    for name,raw in after.items():w.put(destination,'card-after/'+name,raw)
    if case=='success':
        b.require(after=={**before,w.pkg.PATHS[0]:b.plain(w.once.PACKAGE/'exefs.nsp')},'success changed unrelated files')
        b.require(result['schema']=='A23-lifecycle-card-deployment-model-1','model produced real deployment schema')
        try:w.once.gate.verify_deployment(deployment,w.once.materials()[1])
        except ValueError:model_rejected=True
        else:model_rejected=False
        b.require(model_rejected,'model receipt admitted by issuer')
    row=dict(simulation=True,success=expected_success,result=result,error=failure,model_attached_after=card.attached,
        original_inventory=w.inventory(before),after_inventory=w.inventory(after),
        snapshot_sealed=(snapshot/'COMMITTED').exists(),deployment_sealed=(deployment/'COMMITTED').exists(),
        real_card_accesses=0,real_diskutil_calls=0,receiver_launched=False,attempt_issued=False,remaining=0,hardware_verified=False)
    b.write(destination/'case.json',row);return row


def run(output):
    output=w.pkg.output_path(output);parent=b.load(PARENT/'audit.json');hashes=dict(parent['source_hashes']);b.require(len(hashes)==207,'parent source count')
    for name,h in hashes.items():b.require(b.sha(b.plain(b.REPO/name))==h,'parent source drift')
    for name in NEW:hashes['research/usb-ds-iso/'+name]=b.sha(b.plain(b.ROOT/name))
    protected=b.load(PARENT/'protected-inputs.json');live=ANALYSIS/'A23-quiet-once-20261016-interface2.json';before=b.plain(live)
    output.mkdir(mode=0o700,parents=True)
    for name in NEW:w.pkg.put(output,'inputs/'+name,b.plain(b.ROOT/name))
    cases={}
    with tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-card-rehearsal-') as temporary:
        for name in CASES:cases[name]=exercise(name,Path(temporary)/name,output/'cases'/name)
    for name in ('success','recovery-missing','recovery-partial','recovery-multiple'):
        w.verify_snapshot(output/'cases'/name/'snapshot')
    w.seal_verify(output/'cases/success/deployment')
    for name,h in hashes.items():b.require(b.sha(b.plain(b.REPO/name))==h,'source drift')
    for name,h in protected['production'].items():b.require(b.sha(b.plain(b.REPO/name))==h,'production drift')
    for group in ('tickets','offline_records_sha256'):
        for name,h in protected[group].items():b.require(b.sha(b.plain(ANALYSIS/name))==h,'ticket drift')
    b.require(b.plain(live)==before==b.plain(PARENT/'live-record-snapshot.json'),'live record drift')
    result=dict(schema='A23-lifecycle-card-file-review-1',source_hashes=hashes,parent_sources_unchanged=207,new_sources=3,
        model_cases=cases,model_case_count=len(cases),model_receipts_rejected_for_issuance=True,
        protected_originals_selected_only=True,whole_card_backup_claimed=False,actual_card_accesses=0,actual_diskutil_calls=0,
        device_elf_rebuilt=False,receiver_rebuilt=False,new_firmware_packaged=False,deployed=False,
        receiver_launched=False,formal_record_created=False,attempt_issued=False,remaining=0,usb_requests=0,
        actual_fs_service_verified=False,actual_kernel_thread_budget_verified=False,hardware_verified=False,root_cause_confirmed=False)
    b.write(output/'audit.json',result);b.write(output/'protected-inputs.json',protected);w.pkg.put(output,'live-record-snapshot.json',before)
    b.seal(output);w.seal_verify(output);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();r=run(a.output)
    print(json.dumps(dict(source_files=len(r['source_hashes']),cases=r['model_case_count'],remaining=0)))
