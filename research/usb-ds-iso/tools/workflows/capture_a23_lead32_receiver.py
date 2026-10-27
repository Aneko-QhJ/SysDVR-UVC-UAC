"""Bound-device receiver gate. No issuer, default ticket, retry or process kill."""
import argparse
from datetime import datetime,timezone
import os
import re
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_a23_lead32_receiver as build
import build_a23_path_span_deployment as package
import analyze_a23_lead32_entry as waiting
from analyze_io_usb_host_lead32 import checkpoint
from analyze_io_usb_host_evidence import require
from analyze_io_usb_host_collection import sync_dir


def replace(path,value):
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');build.write(tmp,value);os.replace(tmp,path);sync_dir(path.parent)


def verify_validation(record):
    import path_span_card_workflow as card
    directory=Path(record['validation_directory']);card.seal_verify(directory)
    require(build.sha(build.plain(directory/'SHA256SUMS'))==record['validation_manifest_sha256'],'validation seal changed')
    v=build.load(directory/'validation.json')
    require(v.get('schema')=='A23-lead32-validation-1' and v.get('passed') is True and
        type(v.get('tests')) is int and v['tests']>0 and
        all(type(v.get(k)) is int and v[k]==0 for k in ('failures','errors','skipped','usb_requests','sd_accesses','remaining')) and
        v.get('receiver_sha256')==record['receiver_sha256'] and v.get('attempt_issued') is False and
        v.get('receiver_acquire_invoked') is False and build.old.typed(v.get('source_hashes'),build.source_hashes()),
        'validation does not bind lead32 receiver')
    review=directory.parent/'A23-lead32-receiver-review-20261017-r4'
    card.seal_verify(review)
    require(v.get('review_manifest_sha256')==build.sha(build.plain(review/'SHA256SUMS')) and
        v.get('offline_record_sha256')==build.sha(build.plain(review/'offline-record.json')) and
        build.load(review/'offline-record.json')['build_manifest_sha256']==record['build_manifest_sha256'],
        'validation/review/build mismatch')


SD_UUID='37614F76-3E12-3470-B5C8-52B5A449C213'
WORKFLOW_FILES=('tools/io_usb_host_lead32_policy.py','tools/analyze_io_usb_host_lead32.py',
    'tools/analyze_a23_lead32_entry.py','tools/collect_a23_lead32_envelope.py','tools/collect_a23_lead32_waiting.py',
    'tools/collect_a23_lead32_execution.py','tools/workflows/capture_a23_lead32_receiver.py',
    'tools/prepare_a23_lead32_once.py','tools/audit_a23_lead32_workflow.py','tests/test_a23_lead32_workflow.py')


def workflow_hashes():return {n:build.sha(build.plain(build.ROOT/n)) for n in WORKFLOW_FILES}


def verify_workflow_review(directory):
    import path_span_card_workflow as card
    directory=Path(directory);card.seal_verify(directory);value=build.load(directory/'audit.json')
    expected={**build.source_hashes(),**{'research/usb-ds-iso/'+n:h for n,h in workflow_hashes().items()}}
    require(value.get('schema')=='A23-lead32-workflow-review-1' and value.get('passed') is True and
        value.get('remaining')==0 and type(value.get('remaining')) is int and value.get('attempt_issued') is False and
        value.get('receiver_acquire_invoked') is False and value.get('usb_requests')==value.get('sd_accesses')==0 and
        build.old.typed(value.get('source_hashes'),expected),'workflow review changed/unverified')
    return dict(directory=str(directory),manifest_sha256=build.sha(build.plain(directory/'SHA256SUMS')))


def verify_recovery(directory,scope):
    import path_span_card_workflow as card
    directory=Path(directory);files=card.verify_snapshot(directory)
    value=build.load(directory/'snapshot.json');eject=build.load(directory/'eject.json')
    require(value['mode']=='recovery' and value['simulation'] is False and
        value['read_only_mount_verified'] is True and value['identity']['VolumeUUID']==SD_UUID and
        value['expected_recipe_sha256']==scope['runtime_recipe_sha256'] and value['deployment_files_match'] is True and
        eject['ejected'] is True and eject['mount_absent'] is True,'read-only recovery/safe-eject required')
    seen={row['path']:dict(bytes=row['size'],sha256=row['sha256']) for row in value['deployment_files']}
    require(build.old.typed(seen,scope['deployment_files']),'recovered package does not match device materials')
    return dict(directory=str(directory),manifest_sha256=build.sha(files and build.plain(directory/'SHA256SUMS')))


def verify_deployment(directory,scope):
    """Check saved readback claims, never a live card or physical provenance."""
    directory=Path(directory)
    require(directory.is_absolute() and directory==directory.resolve() and
        (directory.parent==build.ROOT/'private/deployments' or Path('/private/tmp') in directory.parents),
        'saved deployment must be outside sealed review trees')
    package.verify(directory)
    files={p.relative_to(directory).as_posix():p for p in directory.rglob('*') if p.is_file() and p not in (directory/'SHA256SUMS',directory/'COMMITTED')}
    require(len(files)<=64 and all(not p.is_symlink() and (p.is_file() or p.is_dir()) for p in directory.rglob('*')),'invalid saved deployment tree')
    sums=''.join(build.sha(build.plain(files[n]))+'  '+n+'\n' for n in sorted(files)).encode()
    require(build.plain(directory/'SHA256SUMS')==sums and build.plain(directory/'COMMITTED')==(build.sha(sums)+'\n').encode(),'saved deployment seal mismatch')
    value=build.load(directory/'deployment.json');eject=build.load(directory/'eject.json')
    require(type(value) is dict and value.get('schema')=='A23-path-span-card-deployment-1' and
        value.get('sd_uuid')==SD_UUID and type(value.get('whole_disk')) is str and re.fullmatch(r'disk[0-9]+',value['whole_disk']) and
        value.get('card_write_readback_verified') is True and
        value.get('attempt_issued') is False and type(value.get('remaining')) is int and value['remaining']==0 and
        type(value.get('usb_test_invocations')) is int and value['usb_test_invocations']==0 and
        value.get('package_manifest_sha256')==scope['package_manifest_sha256'] and
        value.get('device_binding_sha256')==scope['device_binding_sha256'] and
        value.get('source_package')==scope['package_directory'],'deployment does not bind new package')
    after=value.get('after');require(type(after) is list and len(after)==4,'four readback entries required')
    seen={}
    for row in after:
        require(type(row) is dict and set(row)=={'path','size','sha256'} and type(row['path']) is str and
            row['path'] not in seen and type(row['size']) is int,'invalid deployment readback entry')
        seen[row['path']]=dict(bytes=row['size'],sha256=row['sha256'])
    require(build.old.typed(seen,scope['deployment_files']) and type(eject) is dict and eject.get('ejected') is True and
        eject.get('mount_absent') is True and eject.get('device')==value['whole_disk'],'new files were not read back and target disk safely ejected')
    return dict(directory=str(directory),manifest_sha256=build.sha(sums))


def verify_scope(record):
    issuance=record.get('issuance')
    require(type(issuance) is dict and issuance.get('schema')=='A23-lead32-once-issuance-1' and
        type(issuance.get('maximum_invocations')) is int and issuance['maximum_invocations']==1 and
        issuance.get('automatic_retry') is False,'missing one-use lifecycle issuance')
    scope=issuance.get('scope');require(type(scope) is dict,'missing lifecycle scope')
    require(build.old.typed(scope.get('workflow_source_hashes'),{n:build.sha(build.plain(build.ROOT/n)) for n in WORKFLOW_FILES}),'workflow changed after issuance')
    checked=package.verify_review(Path(scope['package_directory']));report=build.load(Path(scope['package_directory'])/'package-report.json')
    require(scope['package_manifest_sha256']==checked['manifest_sha256'] and scope['exefs_nsp_sha256']==report['exefs_nsp_sha256'] and
        build.old.typed(scope['deployment_files'],report['deployment_files']) and
        build.old.typed(record['device_binding'],report['device_binding']) and
        all(scope[n]==record[n] for n in ('device_binding_sha256','receiver_sha256','build_manifest_sha256')) and
        scope['runtime_recipe_sha256']==record['recipe_sha256'] and build.old.typed(scope['plan'],record['plan']) and
        scope['validation_directory']==record['validation_directory'] and scope['validation_manifest_sha256']==record['validation_manifest_sha256'],
        'issuance/package/receiver scope mismatch')
    require(scope.get('device_package_reused') is True and scope.get('host_configuration')=='host-lead32-window-1', 'missing explicit host-only scope')
    require(verify_workflow_review(scope['workflow_review']['directory'])==scope['workflow_review'], 'workflow review changed')
    require(verify_recovery(issuance['recovery']['directory'],scope)==issuance['recovery'], 'saved recovery changed')
    deployment=issuance.get('deployment')
    require(type(deployment) is dict and verify_deployment(deployment['directory'],scope)==deployment,'deployment changed after issuance')


def prepared(record,repo):
    require(type(record) is dict and record.get('stage')=='prepared' and type(record.get('remaining')) is int and record['remaining']==1 and
        record.get('acquisition_enabled') is True,'no new waiting invocation issued')
    result=build.verify_build(record,repo);verify_validation(record);verify_scope(record);return result


def capture(record_path,*,repo=build.REPO,dry_run=False):
    record_path=Path(record_path);record=build.load(record_path)
    if dry_run:
        folder=build.verify_build(record,repo)
        require((record.get('stage')=='offline_build_ready' and type(record.get('remaining')) is int and record['remaining']==0 and record.get('acquisition_enabled') is False) or
            (record.get('stage')=='prepared' and type(record.get('remaining')) is int and record['remaining']==1 and record.get('acquisition_enabled') is True),'not an offline/issued waiting record')
        if record['stage']=='prepared':
            verify_validation(record);verify_scope(record)
        return dict(stage=record['stage'],remaining=record['remaining'],build=str(folder),acquisition_enabled=record['acquisition_enabled'],usb_accessed=False)
    prepared(record,repo) # reject zero/old/failed records BEFORE lock/output
    lock=record_path.with_suffix('.lock');fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
    try:
        os.fsync(fd);sync_dir(lock.parent);record=build.load(record_path);folder=prepared(record,repo)
        parent=Path(repo)/'research/usb-ds-iso/private/runs';require(parent.is_dir() and parent==parent.resolve(),'invalid run parent')
        run=parent/('A-A23-lead32-waiting-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);run.mkdir(mode=0o700);sync_dir(parent)
        record.update(stage='consumed',remaining=0,acquisition_enabled=False,run=str(run));replace(record_path,record)
        try:
            receipt=build.device.receipt(record)
            build.write(run/'waiting-authorization.json',receipt)
            command=[str(folder/'receiver'),'--acquire-once',str(run),str(folder)];build.write(run/'command.json',command)
        except (OSError,ValueError) as error:
            record.update(stage='failed_no_retry');replace(record_path,record)
            raise error
        with (run/'stdout.txt').open('x') as out,(run/'stderr.txt').open('x') as err:
            try:process=subprocess.Popen(command,stdout=out,stderr=err,start_new_session=True)
            except OSError as error:
                record.update(stage='failed_no_retry');replace(record_path,record)
                result=dict(stage=record['stage'],run=str(run),remaining=0,receiver_launched=False,error=str(error),host_observation_complete=False,**{k:False for k in build.POLICY})
                build.write(run/'workflow-result.json',result);build.seal(run);return result
            try:code=process.wait(timeout=130)
            except (subprocess.TimeoutExpired,OSError) as error:
                record.update(stage='unresolved_no_retry',receiver_pid=process.pid);replace(record_path,record)
                result=dict(stage=record['stage'],run=str(run),remaining=0,receiver_pid=process.pid,receiver_left_running=True,
                    forced_exit=False,error=str(error),host_observation_complete=False,**{k:False for k in build.POLICY})
                build.write(run/'workflow-result.json',result);return result # mutable live host, never seal it
        try:
            result=waiting.analyze(run/'host');entry=build.load(run/'host/waiting-entry-result.json')
            require(entry['finished'] is True and entry['unresolved'] is False,'process exited with unresolved entry')
            complete=False
            if entry['started']:
                reported=entry['host_result'];final=checkpoint(run/'host/final')
                require(type(reported.get('exit_code')) is int and reported['exit_code']==code and reported.get('final_checkpoint_saved') is True and
                    type(reported.get('ticks')) is int and reported['ticks']>=final['ticks'] and set(reported)==set(final) and
                    all(build.canonical(reported[k])==build.canonical(final[k]) for k in final if k not in ('ticks','final_checkpoint_saved')),'entry/final/process mismatch')
                complete=code==0 and result['sdk_analysis']['host_observation_complete']
            else:require(code==1,'preflight failure exit mismatch')
            result.update(host_observation_complete=complete)
        except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:
            result=dict(host_observation_complete=False,error=str(error))
        result.update(run=str(run),receiver_exit_code=code,remaining=0,**{k:False for k in build.POLICY})
        record.update(stage='captured_logs_pending' if result['host_observation_complete'] else 'failed_no_retry');replace(record_path,record)
        build.write(run/'workflow-result.json',result);build.seal(run);return result
    finally:os.close(fd);lock.unlink();sync_dir(lock.parent)


if __name__=='__main__':
    import json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('record',type=Path);p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    print(json.dumps(capture(a.record,dry_run=a.dry_run),indent=2))
