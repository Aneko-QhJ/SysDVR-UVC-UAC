#!/usr/bin/env python3
"""Separate deployment variant for one observed Mac companion template.

Existing originals are never ignored. Only this operation's exact temporary
companion name may be added, with bytes equal to the sealed observed template.
No automatic retry, deletion, rollback or issuance; directory models remain ineligible.
"""
import argparse,json,os,uuid,subprocess
from pathlib import Path
import lifecycle_card_workflow as original
from lifecycle_card_workflow import (b,pkg,once,require,new_output,seal_verify,verify_snapshot,read_file,
    selected,expected,inventory,four,put,now,MAX_FILE,MacCard,DirectoryCard)

COMPANION_SHA256='e9dac11f8802bc0233801ba37c5535540210093a39588eda555d5380810cb9ae'
EVIDENCE=b.ROOT/'private/analysis/A23-lifecycle-deployment-failure-20261016-141004'
TEMPLATE_NAME='atmosphere/contents/00FF0000A53BB666/._.a23-lifecycle-602e6e64bf384060bc981b1b0613428b.tmp'


def companion_name(temporary):
    path=Path(temporary);return (path.parent/('._'+path.name)).as_posix()


def check_companion(files,name):
    raw=files.get(name)
    if raw is None:return None
    require(len(raw)==4096 and b.sha(raw)==COMPANION_SHA256,'unrecognized temporary companion')
    original.seal_verify(EVIDENCE)
    template=read_file(EVIDENCE/'observed-card'/TEMPLATE_NAME,4096)
    require(raw==template,'temporary companion differs from sealed observation')
    return raw


def deploy(card,snapshot_path,output):
    output=new_output(output,card,'deployments');info=card.check(writable=True)
    pkg.verify_review(once.PACKAGE);report=b.load(once.PACKAGE/'package-report.json');package_hash=b.sha(b.plain(once.PACKAGE/'SHA256SUMS'))
    saved=verify_snapshot(Path(snapshot_path));meta=json.loads(saved['snapshot.json'],object_pairs_hook=b.old.unique_object)
    require(meta['schema']=='A23-lifecycle-card-snapshot-1' and meta['mode']=='predeployment' and meta['simulation'] is card.simulated and
        meta['identity']==info and meta['package_manifest_sha256']==package_hash,'snapshot/identity/package mismatch')
    original={n.removeprefix('card/'):raw for n,raw in saved.items() if n.startswith('card/')}
    require(inventory(original)==meta['raw_files'],'snapshot raw inventory mismatch');expected(original,report['historical_baseline'])
    require(selected(card.root)==original,'card changed since backup')
    raw=b.plain(once.PACKAGE/'sd-review'/pkg.PATHS[0]);require(b.sha(raw)==report['exefs_nsp_sha256'],'new NSP changed')
    output.mkdir(parents=True,mode=0o700)
    for name in pkg.PATHS:put(output,'backup/'+name,original[name])
    require(all(read_file(output/'backup'/name,MAX_FILE)==original[name] for name in pkg.PATHS),'computer backup readback mismatch')
    b.write(output/'intent.json',dict(schema='A23-lifecycle-card-deploy-intent-1',simulation=card.simulated,identity=info,
        source_package=str(once.PACKAGE),package_manifest_sha256=package_hash,device_binding_sha256=report['device_binding_sha256'],
        recovered_snapshot=str(snapshot_path),snapshot_manifest_sha256=b.sha(read_file(Path(snapshot_path)/'SHA256SUMS',1024*1024)),
        changed_files=[pkg.PATHS[0]],automatic_rollback=False,automatic_retry=False,remaining=0))
    temporary=pkg.CONTENT+'.a23-lifecycle-'+uuid.uuid4().hex+'.tmp';target=card.root/pkg.PATHS[0];published=False;phase='prewrite'
    try:
        require(card.check(writable=True)==info and selected(card.root)==original,'card changed before write')
        require(pkg.verify_review(once.PACKAGE)['manifest_sha256']==package_hash,'package changed before write')
        phase='temporary_write';b.old.durable_write(card.root/temporary,raw)
        phase='temporary_readback';require(read_file(card.root/temporary,MAX_FILE)==raw,'temporary readback mismatch')
        before_replace=selected(card.root)
        companion=companion_name(temporary)
        auxiliary=check_companion(before_replace,companion)
        require(card.check(writable=True)==info and {n:data for n,data in before_replace.items() if n not in (temporary,companion)}==original,'card changed before replacement')
        if auxiliary is not None:put(output,'temporary-companion.bin',auxiliary)
        phase='replace';os.replace(card.root/temporary,target);published=True
        phase='sync';card.sync()
        phase='readback';after=selected(card.root);wanted={**original,pkg.PATHS[0]:raw}
        after_auxiliary=check_companion(after,companion)
        require(card.check(writable=True)==info and {n:data for n,data in after.items() if n!=companion}==wanted,'deployment readback or preserved originals mismatch')
        if auxiliary is None and after_auxiliary is not None:put(output,'temporary-companion.bin',after_auxiliary)
        metadata_changes=[companion] if after_auxiliary is not None else []
        b.write(output/'readback.json',dict(verified=True,after=four(after),preserved_inventory_sha256=b.sha(b.canonical(inventory({n:data for n,data in after.items() if n!=pkg.PATHS[0]})))))
        phase='eject';eject=card.eject(info)
        require(eject.get('ejected') is True and eject.get('mount_absent') is True and eject.get('device')==info['ParentWholeDisk'],'target disk ejection not confirmed')
        phase='receipt'
        receipt=dict(schema='A23-lifecycle-card-deployment-model-1' if card.simulated else 'A23-lifecycle-card-deployment-1',
            artifact_origin='temporary_directory_model' if card.simulated else 'saved_card_operation',deployed_at=now(),
            sd_uuid=info['VolumeUUID'],device=info['DeviceIdentifier'],whole_disk=info['ParentWholeDisk'],mount=str(card.root),
            source_package=str(once.PACKAGE),package_manifest_sha256=package_hash,device_binding=report['device_binding'],device_binding_sha256=report['device_binding_sha256'],
            recovered_snapshot=str(snapshot_path),snapshot_manifest_sha256=b.sha(read_file(Path(snapshot_path)/'SHA256SUMS',1024*1024)),
            before=four(original),after=four(after),changed_files=[pkg.PATHS[0]],unchanged_files=list(pkg.PATHS[1:]),
            card_write_readback_verified=True,old_originals_preserved=True,simulation=card.simulated,
            allowed_added_metadata_files=metadata_changes,companion_template_sha256=COMPANION_SHA256,
            companion_observed=auxiliary is not None or after_auxiliary is not None,
            card_tool_sha256=b.sha(read_file(Path(__file__).resolve(),2*1024*1024)),firmware_executed=False,
            hardware_verified=False,physical_run_authenticated=False,usb_test_invocations=0,attempt_issued=False,remaining=0)
        b.write(output/'deployment.json',receipt);b.write(output/'eject.json',eject);b.seal(output);seal_verify(output)
        return receipt
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        failure=dict(schema='A23-lifecycle-card-deploy-failure-1',phase=phase,replacement_return_observed=published,simulation=card.simulated,
            temporary_card_path=temporary,error=str(error),automatic_rollback=False,automatic_retry=False,
            card_state_requires_inspection=True,attempt_issued=False,remaining=0)
        if not (output/'COMMITTED').exists():
            b.write(output/'failure.json',failure)
            # Never make a failed deployment look like a complete receipt.
            b.seal(output)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mount',type=Path,required=True);p.add_argument('--device');p.add_argument('--model',action='store_true')
    p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true')
    args=p.parse_args()
    if not args.execute:p.error('explicit --execute required after authorization and a new snapshot')
    card=DirectoryCard(args.mount) if args.model else MacCard(args.mount,args.device)
    print(json.dumps(deploy(card,args.snapshot,args.output),indent=2))

if __name__=='__main__':main()
