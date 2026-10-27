"""Explicit read-only recovery. Import and job preparation never access a card."""
import argparse
import json
from pathlib import Path
import fcntl
import os
import context65_flag_card as adapter
import subprocess
import context65_baseline63 as w
import path_span_card_workflow as card
b=w.b

class Gate:
    replace=staticmethod(w.replace)
gate=Gate()

def ready(record_path):
    path=w.canonical(record_path);value=w.load(path)
    w.require(value.get('record_path')==str(path) and value.get('stage') in ('captured_logs_pending','failed_no_retry') and
        type(value.get('remaining')) is int and value['remaining']==0 and value.get('acquisition_enabled') is False and
        value.get('device_log_pending') is True and value.get('recovered') is not True,'closed capture with pending logs required')
    w.verify_scope(value,path);run=Path(value['run']);card.seal_verify(run)
    w.require(w.load(run/'workflow-result.json').get('remaining')==0,'run not closed');return value

def recover(record_path,device,output):
    value=ready(record_path);model=value['issuance']['reservation']['simulation']
    w.require(device.simulated is model,'model/formal card mismatch')
    result=card.recover(device,Path(output),eject_after=True);card.verify_snapshot(Path(output));eject=w.load(Path(output)/'eject.json')
    matched=(result['deployment_files_match'] and result['expected_recipe_sha256']==value['recipe_sha256'] and
        result['device_binding_sha256']==value['device_binding_sha256'] and result['identity']['VolumeUUID']==card.UUID)
    value.update(card_snapshot_saved=True,device_log_pending=False,card_snapshot=str(Path(output)),ejected=True,ejected_at=eject['ejected_at'],
        recovered=bool(matched),recovery_receipt_accepted=bool(matched),deployment_files_match=bool(matched),recovery_required=False)
    w.replace(Path(record_path),value)
    return dict(schema='A23-context65-baseline63-recovery-1',snapshot=str(output),manifest_sha256=w.sha(w.plain(Path(output)/'SHA256SUMS')),
        raw_files=len(result['raw_files']),ejected=True,simulation=model,remaining=0,usb_requests=0,card_files_written=False,
        card_snapshot_saved=True,recovery_receipt_accepted=bool(matched),deployment_files_match=bool(matched))

def prepare_job(record_path,job,snapshot):
    value=ready(record_path);job=Path(job);snapshot=Path(snapshot)
    model=value['issuance']['reservation']['simulation']
    b.require(job.is_absolute() and job==job.resolve() and not job.exists() and
        ((model and Path('/private/tmp') in job.parents) or (not model and job.parent==b.ROOT/'private/analysis')),'new recovery job required')
    b.require(snapshot.is_absolute() and snapshot==snapshot.resolve() and not snapshot.exists() and
        ((model and Path('/private/tmp') in snapshot.parents) or (not model and snapshot.parent==b.ROOT/'private/card-cycles')),'new snapshot required')
    job.mkdir(mode=0o700)
    plan=dict(schema='A23-context65-baseline63-recovery-job-1',record=str(Path(record_path)),run=value['run'],snapshot=str(snapshot),
        scripts_prepared_only=True,card_accessed=False,usb_requests=0,remaining=0)
    b.write(job/'plan.json',plan);return plan


def attached(record_path,job,*,shutdown_card_connected=False):
    """Caller must have the user's explicit shutdown/card-connected confirmation."""
    b.require(shutdown_card_connected is True,'explicit shutdown/card-connected confirmation required before disk access')
    value=ready(record_path);b.require(value['issuance']['reservation']['simulation'] is False,'formal record required')
    job=Path(job)
    b.require(job.is_absolute() and job==job.resolve() and job.parent==b.ROOT/'private/analysis' and
        {p.name for p in job.iterdir()}=={'plan.json'},'fresh prepared recovery job required')
    plan=b.load(job/'plan.json')
    target=Path(plan['snapshot'])
    b.require(plan.get('schema')=='A23-context65-baseline63-recovery-job-1' and plan.get('run')==value['run'] and
        target.is_absolute() and target==target.resolve() and target.parent==b.ROOT/'private/card-cycles' and not target.exists(),'recovery plan mismatch')
    b.require(plan['record']==str(Path(record_path)) and plan['scripts_prepared_only'] is True,'job/record mismatch')
    return physical_job(record_path,job,plan)


def physical_job(record_path,job,plan):
    # Called only after the public formal/confirmation/path gates. Serialize
    # with the old repair adapter; retain its reviewed failed owner unchanged.
    # A separate recovery owner blocks all new jobs after an unresolved read.
    fd=os.open(w.A/'A23-context65-flag-card-volume.lock',os.O_RDWR|os.O_NOFOLLOW)
    active=w.A/'A23-context65-baseline63-recovery-owner.json'
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        w.require(not active.exists() and not active.is_symlink(),'pending readonly recovery; manual review required')
        value=ready(record_path);w.adoption(value['issuance']['scope'])
        owner=dict(schema='A23-context65-baseline63-recovery-owner-1',job=str(job),record=str(record_path),
            preparation_id=value['preparation_id'],automatic_release_on_failure=False)
        w.write(active,owner)
        try:
            # One permanent claim before the first disk query; failed or partial
            # jobs never get another attempt, even with a newly named job.
            claim=os.open(job/'.execute.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            try:os.fsync(claim)
            finally:os.close(claim)
            b.old.sync_dir(job)
            backend=adapter.MacBackend();backend.begin(job/'commands')
            part,whole=backend.resolve();device=backend.mounted(part,whole,readonly=True)
            w.write(job/'readonly-identity.json',device.check(readonly=True))
            result=recover(record_path,device,Path(plan['snapshot']))
            w.require(w.load(active)==owner,'readonly recovery owner changed')
            w.adoption(value['issuance']['scope'])
            w.write(job/'result.json',dict(**result,old_repair_owner_retained=True))
            b.seal(job);active.unlink();b.old.sync_dir(w.A);return result
        except (OSError,ValueError,KeyError,TypeError) as error:
            unresolved=isinstance(error,adapter.UnresolvedCommand)
            failure=dict(stage='unresolved_no_retry' if unresolved else 'failed_no_retry',remaining=0,
                automatic_retry=False,forced_exit=False,owner_retained=True,error=str(error))
            if unresolved:failure.update(command_pid=error.pid,command_left_running=True)
            if not (job/'COMMITTED').exists():
                w.write(job/'failure.json',failure)
                if not unresolved:b.seal(job)
            raise
    finally:os.close(fd)



if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('record',type=Path);p.add_argument('--job',type=Path,required=True)
    p.add_argument('--snapshot',type=Path);p.add_argument('--execute',action='store_true');p.add_argument('--confirm-shutdown-card-connected',action='store_true');a=p.parse_args()
    b.require(a.execute or a.snapshot is not None,'snapshot required to prepare')
    print(json.dumps(attached(a.record,a.job,shutdown_card_connected=a.confirm_shutdown_card_connected) if a.execute else prepare_job(a.record,a.job,a.snapshot),indent=2))
