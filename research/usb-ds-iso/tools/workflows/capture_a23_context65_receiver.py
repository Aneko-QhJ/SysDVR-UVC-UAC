"""One consumed invocation. Models require an injected runner; never auto-escalate."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import context65_workflow as w
import analyze_a23_context65_entry as waiting
from analyze_io_usb_host_context65 import checkpoint

def environment(requested):
    result=dict(schema='A23-context65-launch-environment-1',requested_execution_mode=requested,pid=os.getpid(),
        uid=os.getuid(),euid=os.geteuid(),sandbox_query_result=-1,sandbox_query_errno=0,
        automatic_privilege_change=False,usb_open_permission_proven=False)
    try:
        query=ctypes.CDLL(None,use_errno=True).sandbox_check;query.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int];query.restype=ctypes.c_int
        ctypes.set_errno(0);result['sandbox_query_result']=query(os.getpid(),None,0);result['sandbox_query_errno']=ctypes.get_errno()
    except (AttributeError,OSError):result['sandbox_query_errno']=38
    return result

def prepared(path):
    path=w.canonical(path);record=w.load(path)
    w.require(record.get('record_path')==str(path) and record.get('stage')=='prepared' and
        type(record.get('remaining')) is int and record['remaining']==1 and record.get('acquisition_enabled') is True,'no unused context65 invocation')
    return record,w.verify_scope(record,path)

def capture(path,*,dry_run=False,execution_mode=None,_model_runner=None,_model_runs=None):
    path=w.canonical(path);record=w.load(path)
    if dry_run and record.get('stage')=='offline_build_ready':
        w.require(record['remaining']==0 and record['acquisition_enabled'] is False,'invalid offline record')
        w.transition();folder=w.verify_build(record)
        return dict(stage='offline_build_ready',remaining=0,build=str(folder),receiver_launched=False,usb_requests=0,sd_accesses=0)
    record,folder=prepared(path);model=record['issuance']['reservation']['simulation']
    if dry_run:return dict(stage='prepared',remaining=1,receiver_launched=False,simulation=model,usb_requests=0,sd_accesses=0)
    if model:
        w.require(callable(_model_runner) and _model_runs is not None and Path('/private/tmp') in w.canonical(_model_runs).parents,'model requires injected runner and temporary run root')
        parent=w.canonical(_model_runs);env=dict(schema='A23-context65-launch-environment-1',requested_execution_mode='injected_model',
            sandbox_query_result=0,sandbox_query_errno=0,automatic_privilege_change=False,usb_open_permission_proven=False)
    else:
        w.require(_model_runner is None and _model_runs is None and execution_mode=='require_escalated','formal run requires explicit execution-mode record')
        env=environment(execution_mode)
        w.require(type(env['sandbox_query_result']) is int and env['sandbox_query_result']==0 and env['sandbox_query_errno']==0,
            'parent is sandboxed or query unavailable; not consumed, no launch')
        parent=w.ROOT/'private/runs'
    w.require(parent.is_dir(),'run parent missing')
    lock=path.with_suffix('.lock');fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        os.fsync(fd);w.b.old.sync_dir(lock.parent);record,folder=prepared(path)
        run=parent/('A-context65-waiting-'+record['preparation_id']);run.mkdir(mode=0o700);w.b.old.sync_dir(parent)
        record.update(stage='consumed',remaining=0,acquisition_enabled=False,run=str(run),launch_environment=env);w.replace(path,record)
        try:
            w.write(run/'waiting-authorization.json',w.b.device.receipt(record));w.write(run/'launch-environment.json',env)
            command=[str(folder/'receiver'),'--acquire-once',str(run),str(folder)];w.write(run/'command.json',command)
        except (OSError,ValueError):
            record.update(stage='failed_no_retry');w.replace(path,record);raise
        with (run/'stdout.txt').open('x') as out,(run/'stderr.txt').open('x') as err:
            try:
                process=_model_runner(command,run,record) if model else subprocess.Popen(command,stdout=out,stderr=err,start_new_session=True)
            except OSError as error:
                record.update(stage='failed_no_retry',device_log_pending=False,recovered=False);w.replace(path,record)
                result=dict(stage='failed_no_retry',run=str(run),remaining=0,receiver_launched=False,host_observation_complete=False,error=str(error))
                w.write(run/'workflow-result.json',result);w.b.seal(run);return result
            try:code=process.wait(timeout=130)
            except (subprocess.TimeoutExpired,OSError) as error:
                record.update(stage='unresolved_no_retry',receiver_pid=process.pid,device_log_pending=True,recovered=False);w.replace(path,record)
                result=dict(stage='unresolved_no_retry',run=str(run),remaining=0,receiver_pid=process.pid,receiver_left_running=True,
                    forced_exit=False,host_observation_complete=False,error=str(error))
                w.write(run/'workflow-result.json',result);return result # never seal or kill unresolved I/O
        complete=False
        try:
            result=waiting.analyze(run/'host');entry=w.load(run/'host/waiting-entry-result.json')
            w.require(entry['finished'] is True and entry['unresolved'] is False,'unresolved entry at process exit')
            if entry['started']:
                reported=entry['host_result'];saved=checkpoint(run/'host/final')
                w.require(type(reported['exit_code']) is int and reported['exit_code']==code and reported['final_checkpoint_saved'] is True and
                    reported['ticks']>=saved['ticks'] and set(reported)==set(saved) and
                    all(w.b.old.typed(reported[k],saved[k]) for k in saved if k not in ('ticks','final_checkpoint_saved')),'entry/checkpoint/exit disagreement')
                complete=code==0 and result['sdk_analysis']['host_observation_complete']
            else:w.require(code==1,'preflight exit disagreement')
        except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:result=dict(error=str(error))
        stage='captured_logs_pending' if complete else 'failed_no_retry'
        record.update(stage=stage,device_log_pending=True,recovered=False);w.replace(path,record)
        result.update(stage=stage,run=str(run),remaining=0,receiver_launched=True,receiver_exit_code=code,host_observation_complete=complete,
            **{k:False for k in w.b.POLICY})
        w.write(run/'workflow-result.json',result);w.b.seal(run);return result
    finally:os.close(fd) # durable per-record claim is never removed or refilled

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('record',type=Path);p.add_argument('--dry-run',action='store_true')
    p.add_argument('--execution-mode',choices=['require_escalated']);a=p.parse_args()
    print(json.dumps(capture(a.record,dry_run=a.dry_run,execution_mode=a.execution_mode),indent=2))
