"""Prepare a bounded flag repair and exercise it on temporary directory models.

There is deliberately no physical-card writer in this candidate. Import, plan
preparation and analysis read saved local evidence only; model writes require
the exact DirectoryCard type and canonical /private/tmp paths.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import uuid

import context65_workflow as w

PARENT=w.A/'A23-context65-workflow-closeout-20261018'
FLAG='atmosphere/contents/00FF0000A53BB666/flags/boot2.flag'
NEW=('tools/context65_flag_repair.py','tools/audit_a23_context65_flag_repair.py','tests/test_a23_context65_flag_repair.py')


def source_hashes():
    w.card.seal_verify(PARENT);old=w.load(PARENT/'closeout.json')['source_hashes'];current=w.hashes()
    w.require(old==current and len(old)==295,'parent workflow sources changed')
    for name in NEW:
        name='research/usb-ds-iso/'+name
        w.require(name not in current,'source overlap');current[name]=w.sha(w.plain(w.b.REPO/name,2*1024*1024))
    return dict(sorted(current.items()))


def materials(*,live=True):
    _,scope=w.materials();w.require(scope['workflow_proof'] is not None,'parent workflow proof missing')
    if live:
        w.transition();w.require(w.latest_snapshot()==w.ANCHOR,'latest saved baseline changed; re-review repair')
    saved=w.card.verify_snapshot(w.ANCHOR);meta=w.load(w.ANCHOR/'snapshot.json');eject=w.load(w.ANCHOR/'eject.json')
    raw={n.removeprefix('card/'):v for n,v in saved.items() if n.startswith('card/')}
    w.require(len(raw)==59 and FLAG not in raw and FLAG.rsplit('/',1)[0]+'/._boot2.flag' in raw,'missing-flag anchor differs')
    w.require(meta['simulation'] is False and meta['mode']=='recovery' and meta['read_only_mount_verified'] is True and
        meta['identity']['VolumeUUID']==w.card.UUID and meta['deployment_files_match'] is False and
        eject['ejected'] is True and eject['mount_absent'] is True,'anchor is not the saved real mismatch recovery')
    expected=scope['deployment_files'];w.require(expected[FLAG]==dict(bytes=0,sha256=w.sha(b'')),'flag recipe changed')
    w.require(w.b.old.typed({n:dict(bytes=len(raw[n]),sha256=w.sha(raw[n])) for n in expected if n!=FLAG},
        {n:v for n,v in expected.items() if n!=FLAG}),'another deployment file differs')
    binding=dict(schema='A23-context65-flag-repair-scope-1',sd_uuid=w.card.UUID,
        source_hashes=source_hashes(),parent_workflow_proof=scope['workflow_proof'],
        anchor=dict(directory=str(w.ANCHOR),manifest_sha256=w.sha(w.plain(w.ANCHOR/'SHA256SUMS'))),
        device_binding_sha256=scope['device_binding_sha256'],runtime_recipe_sha256=scope['runtime_recipe_sha256'],
        expected_deployment_files=expected,preserved_files=w.card.inventory(raw),
        target=dict(path=FLAG,bytes=0,sha256=w.sha(b'')),allowed_changed_files=[FLAG],
        create_exclusive=True,overwrite_allowed=False,remove_allowed=False,automatic_retry=False,automatic_rollback=False,
        prewrite_readonly_recovery_and_eject_required=True,prewrite_inventory_must_equal_anchor=True,
        postwrite_readonly_recovery_and_eject_required=True,postwrite_inventory_must_equal_anchor_plus_target=True,
        maximum_model_creates=1,physical_card_execution_supported=False,
        usb_requests=0,sd_accesses=0,formal_reservations=0,formal_records=0,remaining=0)
    return raw,scope,binding


def prepare(output):
    output=w.canonical(output);w.require(not output.exists() and output.parent.is_dir() and
        (output.parent==w.A or Path('/private/tmp') in output.parents),'new local repair-plan directory required')
    _,_,scope=materials();output.mkdir(mode=0o700)
    value=dict(schema='A23-context65-flag-repair-plan-1',preparation_id=str(uuid.uuid4()),prepared_at=w.card.now(),scope=scope,
        simulation_plan=True,actual_card_write_authorized=False,physical_card_execution_supported=False,
        card_accessed=False,card_repaired=False,attempt_issued=False,remaining=0)
    w.write(output/'plan.json',value);w.b.seal(output);verify_plan(output);return value


def verify_plan(folder,*,live=True):
    folder=w.canonical(folder);saved=w.card.seal_verify(folder);w.require(set(saved)=={'plan.json'},'repair plan inventory differs')
    value=w.load(folder/'plan.json');_,_,scope=materials(live=live)
    w.require(type(value) is dict and set(value)=={'schema','preparation_id','prepared_at','scope','simulation_plan',
        'actual_card_write_authorized','physical_card_execution_supported','card_accessed','card_repaired','attempt_issued','remaining'} and
        value['schema']=='A23-context65-flag-repair-plan-1' and type(value['preparation_id']) is str and
        str(uuid.UUID(value['preparation_id']))==value['preparation_id'] and w.b.old.typed(value['scope'],scope) and
        value['simulation_plan'] is True and all(value[k] is False for k in ('actual_card_write_authorized',
        'physical_card_execution_supported','card_accessed','card_repaired','attempt_issued')) and
        type(value['remaining']) is int and value['remaining']==0,'repair plan binding differs')
    w.timestamp(value['prepared_at']);return value


def analyze_model(folder):
    folder=w.canonical(folder);files=w.card.seal_verify(folder)
    w.require({p.name for p in folder.iterdir()}=={'plan','before','after','intent.json','result.json','SHA256SUMS','COMMITTED'},'model success inventory differs')
    plan=verify_plan(folder/'plan',live=False);original,scope,_=materials(live=False)
    before=w.load(folder/'before/snapshot.json');root=Path(before['identity']['MountPoint'])
    w.require(root==root.resolve() and Path('/private/tmp') in root.parents,'model mount identity is not temporary')
    previous=before_repair(folder/'before',root,original)
    recovered=w.verify_recovery(folder/'after',scope,simulation=True,require_latest=False)
    after=w.card.verify_snapshot(folder/'after');post={n.removeprefix('card/'):v for n,v in after.items() if n.startswith('card/')}
    w.require(post=={**original,FLAG:b''},'saved model postimage differs')
    intent=w.load(folder/'intent.json');result=w.load(folder/'result.json')
    w.card.identity(intent['identity'],root,writable=True)
    w.require(all(intent['identity'][k]==v for k,v in before['identity'].items() if k!='WritableVolume') and
        intent['schema']=='A23-context65-flag-model-intent-1' and intent['preparation_id']==plan['preparation_id'] and
        intent['before']['manifest_sha256']==previous['manifest_sha256'] and intent['target']==FLAG and
        intent['allowed_changed_files']==[FLAG] and intent['simulation'] is True and intent['physical_card_execution_supported'] is False,'saved model intent differs')
    w.require(result['schema']=='A23-context65-flag-repair-model-1' and result['passed'] is True and result['simulation'] is True and
        result['preparation_id']==plan['preparation_id'] and result['changed_files']==[FLAG] and
        type(result['preserved_originals']) is int and result['preserved_originals']==59 and
        type(result['post_files']) is int and result['post_files']==60 and type(result['exclusive_creates']) is int and result['exclusive_creates']==1 and
        result['post_recovery']['simulation'] is True and result['post_recovery']['manifest_sha256']==recovered['manifest_sha256'] and
        result['post_deployment_files_match'] is True and result['readonly_recovery_and_eject_verified'] is True and
        all(result[k] is False for k in ('formal_baseline_accepted','physical_card_execution_supported','actual_card_repaired','automatic_retry','automatic_rollback')) and
        all(type(result[k]) is int and result[k]==0 for k in ('usb_requests','sd_accesses','formal_records','formal_reservations','remaining')),'saved model result differs')
    w.require(w.card.seal_verify(folder)==files,'model archive changed during analysis')
    return dict(schema='A23-context65-flag-model-analysis-1',collection_integrity_verified=True,
        supplied_model_consistent=True,manifest_sha256=w.sha(w.plain(folder/'SHA256SUMS')),
        preserved_originals=59,changed_files=[FLAG],physical_card_execution_supported=False,physical_run_authenticated=False,
        actual_card_repaired=False,formal_baseline_accepted=False,remaining=0)


def temporary_output(path,card_root):
    path=w.canonical(path);w.require(Path('/private/tmp') in path.parents and not path.exists() and path.parent.is_dir() and
        not path.is_relative_to(card_root) and not card_root.is_relative_to(path),'new nonoverlapping temporary output required');return path


def before_repair(folder,root,original):
    folder=w.canonical(folder);files=w.card.verify_snapshot(folder);meta=w.load(folder/'snapshot.json');eject=w.load(folder/'eject.json')
    w.require(meta['simulation'] is True and eject.get('simulation') is True and meta['mode']=='recovery' and
        meta['read_only_mount_verified'] is True and meta['deployment_files_match'] is False and
        eject['ejected'] is True and eject['mount_absent'] is True,'fresh model read-only recovery/eject required')
    w.card.identity(meta['identity'],root,readonly=True)
    w.require(w.timestamp(meta['collected_at'])>w.timestamp(w.load(w.ANCHOR/'snapshot.json')['collected_at']) and
        {n.removeprefix('card/'):v for n,v in files.items() if n.startswith('card/')}==original,'prewrite59 originals drifted')
    return dict(directory=str(folder),manifest_sha256=w.sha(w.plain(folder/'SHA256SUMS')))


def model_repair(plan,device,before,output,after):
    # Reject even a MacCard instance before consulting it or resolving a volume.
    w.require(type(device) is w.card.DirectoryCard and device.simulated is True and
        Path('/private/tmp') in device.root.parents,'only an exact temporary DirectoryCard may be written')
    plan=w.canonical(plan);bound=verify_plan(plan);original,scope,_=materials()
    output=temporary_output(output,device.root);after=temporary_output(after,device.root)
    w.require(output!=after and not output.is_relative_to(after) and not after.is_relative_to(output) and
        not output.is_relative_to(plan) and not after.is_relative_to(plan),'outputs overlap plan or each other')
    receipt=before_repair(before,device.root,original)
    w.require(not output.is_relative_to(Path(before)) and not after.is_relative_to(Path(before)),'output overlaps prewrite evidence')
    info=device.check(writable=True)
    w.require(w.card.selected(device.root)==original,'current selected files differ; do not create flag')
    target=device.root/FLAG;parent=target.parent
    w.require(parent.is_dir() and parent==parent.resolve() and not target.exists() and not target.is_symlink(),'flag must be absent under the existing canonical flags directory')
    output.mkdir(mode=0o700);shutil.copytree(plan,output/'plan');shutil.copytree(before,output/'before')
    w.write(output/'intent.json',dict(schema='A23-context65-flag-model-intent-1',preparation_id=bound['preparation_id'],
        before=receipt,identity=info,target=FLAG,allowed_changed_files=[FLAG],simulation=True,physical_card_execution_supported=False))
    phase='recheck_before_create';created=False;parent_fd=flag_fd=None
    try:
        w.require(device.check(writable=True)==info and w.card.selected(device.root)==original,'card changed before exclusive create')
        parent_fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        w.require(os.fstat(parent_fd)==parent.stat(),'flags directory changed before create')
        phase='exclusive_empty_create'
        flag_fd=os.open(target.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent_fd);created=True
        w.require(os.fstat(flag_fd).st_size==0,'new flag not empty');os.fsync(flag_fd);os.close(flag_fd);flag_fd=None
        os.fsync(parent_fd);w.require(os.fstat(parent_fd)==parent.stat(),'flags directory changed during create')
        os.close(parent_fd);parent_fd=None
        phase='sync_and_readback';device.sync()
        expected={**original,FLAG:b''}
        w.require(device.check(writable=True)==info and w.card.selected(device.root)==expected,'readback changed more than the allowed empty flag')
        phase='readonly_recovery_and_eject'
        # DirectoryCard has no mounts. Detaching this writable model and opening
        # a distinct readonly model represents the two required mount phases.
        device.attached=False;readonly=w.card.DirectoryCard(device.root,readonly=True)
        w.card.recover(readonly,after,eject_after=True)
        w.require(w.card.selected(device.root)==expected,'model card changed during recovery')
        recovered=w.verify_recovery(after,scope,simulation=True,require_latest=False)
        shutil.copytree(after,output/'after')
        result=dict(schema='A23-context65-flag-repair-model-1',passed=True,simulation=True,
            preparation_id=bound['preparation_id'],changed_files=[FLAG],preserved_originals=len(original),post_files=len(expected),
            exclusive_creates=1,post_recovery=recovered,post_deployment_files_match=True,readonly_recovery_and_eject_verified=True,
            formal_baseline_accepted=False,physical_card_execution_supported=False,actual_card_repaired=False,
            automatic_retry=False,automatic_rollback=False,usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,remaining=0)
        w.write(output/'result.json',result);w.b.seal(output);w.card.seal_verify(output);return result
    except (OSError,ValueError,TypeError,KeyError) as error:
        for fd in (flag_fd,parent_fd):
            if fd is not None:os.close(fd)
        failure=dict(schema='A23-context65-flag-repair-model-failure-1',passed=False,simulation=True,phase=phase,
            error=str(error),model_flag_created=created,automatic_retry=False,automatic_rollback=False,
            physical_card_execution_supported=False,actual_card_repaired=False,readonly_recovery_and_eject_verified=False,
            usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,remaining=0)
        try:
            observed=w.card.selected(device.root)
            for name,raw in observed.items():w.card.put(output,'observed-card/'+name,raw)
            failure['observed_files']=w.card.inventory(observed)
        except (OSError,ValueError) as observed_error:failure['observation_error']=str(observed_error)
        w.write(output/'failure.json',failure);w.b.seal(output);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    for name in ('prepare','analyze','analyze-model'):sub.add_parser(name).add_argument('directory',type=Path)
    model=sub.add_parser('model')
    for name in ('plan','card','before','output','after'):model.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.mode=='prepare':result=prepare(args.directory)
    elif args.mode=='analyze':result=verify_plan(args.directory)
    elif args.mode=='analyze-model':result=analyze_model(args.directory)
    else:result=model_repair(args.plan,w.card.DirectoryCard(args.card),args.before,args.output,args.after)
    print(json.dumps(result,indent=2))
