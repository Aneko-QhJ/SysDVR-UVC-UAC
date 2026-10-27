"""Bound-device receiver gate. No issuer, default ticket, retry or process kill."""
import argparse
from datetime import datetime,timezone
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_a23_quiet_receiver as build
import analyze_a23_waiting_entry as waiting
from analyze_io_usb_host_burst_sdk import checkpoint
from analyze_io_usb_host_evidence import require
from analyze_io_usb_host_collection import sync_dir


def replace(path,value):
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');build.write(tmp,value);os.replace(tmp,path);sync_dir(path.parent)


def verify_validation(record):
    directory=Path(record['validation_directory']);sums=build.plain(directory/'SHA256SUMS',16384)
    require(build.sha(sums)==record['validation_manifest_sha256'] and build.plain(directory/'COMMITTED',65)==(build.sha(sums)+'\n').encode(),'invalid validation seal')
    entries=list(directory.rglob('*'));require(len(entries)<=32 and all(not p.is_symlink() and (p.is_file() or p.is_dir()) for p in entries),'invalid validation tree')
    files={p.relative_to(directory).as_posix() for p in entries if p.is_file() and p not in (directory/'SHA256SUMS',directory/'COMMITTED')}
    require(0<len(files)<=16,'invalid validation inventory')
    require(sums==''.join(build.sha(build.plain(directory/n))+'  '+n+'\n' for n in sorted(files)).encode(),'validation files changed')
    value=build.load(directory/'validation.json')
    require(type(value) is dict and value.get('schema')=='A23-waiting-receiver-validation-3' and value.get('passed') is True and
        type(value.get('skipped')) is int and value['skipped']==0 and
        all(type(value.get(k)) is int and value[k]==0 for k in ('native_iokit_calls','real_sdk_objects','usb_requests','sd_accesses')) and
        value.get('build_manifest_sha256')==record['build_manifest_sha256'] and value.get('receiver_sha256')==record['receiver_sha256'] and
        value.get('device_binding_sha256')==record['device_binding_sha256'] and value.get('runtime_recipe_sha256')==record['recipe_sha256'] and
        all(build.old.typed(value.get(n),record['device_binding'][n]) for n in build.device.EXTRA),
        'validation does not bind this receiver')


def prepared(record,repo):
    require(type(record) is dict and record.get('stage')=='prepared' and type(record.get('remaining')) is int and record['remaining']==1 and
        record.get('acquisition_enabled') is True,'no new waiting invocation issued')
    result=build.verify_build(record,repo);verify_validation(record);return result


def capture(record_path,*,repo=build.REPO,dry_run=False):
    record_path=Path(record_path);record=build.load(record_path)
    if dry_run:
        folder=build.verify_build(record,repo)
        require((record.get('stage')=='offline_build_ready' and type(record.get('remaining')) is int and record['remaining']==0 and record.get('acquisition_enabled') is False) or
            (record.get('stage')=='prepared' and type(record.get('remaining')) is int and record['remaining']==1 and record.get('acquisition_enabled') is True),'not an offline/issued waiting record')
        if record['stage']=='prepared':verify_validation(record)
        return dict(stage=record['stage'],remaining=record['remaining'],build=str(folder),acquisition_enabled=record['acquisition_enabled'],usb_accessed=False)
    prepared(record,repo) # reject zero/old/failed records BEFORE lock/output
    lock=record_path.with_suffix('.lock');fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
    try:
        os.fsync(fd);sync_dir(lock.parent);record=build.load(record_path);folder=prepared(record,repo)
        parent=Path(repo)/'research/usb-ds-iso/private/runs';require(parent.is_dir() and parent==parent.resolve(),'invalid run parent')
        run=parent/('A-A23-quiet-waiting-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);run.mkdir(mode=0o700);sync_dir(parent)
        record.update(stage='consumed',remaining=0,acquisition_enabled=False,run=str(run));replace(record_path,record)
        receipt=build.device.receipt(record)
        build.write(run/'waiting-authorization.json',receipt)
        command=[str(folder/'receiver'),'--acquire-once',str(run),str(folder)];build.write(run/'command.json',command)
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
