"""Independent single-burst gate. Offline build records have zero invocations."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from analyze_io_usb_host_evidence import require,unique_object
from analyze_io_usb_host_collection import durable_write,sync_dir
from analyze_io_usb_host_burst_sdk import analyze as audit_host
from io_usb_host_burst_entry_plan import PLAN,SCOPE,canonical,validate_plan,validate_scope
TICKET=ROOT/'private/analysis/A23-IOUSBHost-burst-next-test.json'
POLICY=('hardware_verified','usb_strict_pass','baseline_accepted','allow_next_burst','callback_drain_verified')

def source_paths(root=ROOT):
    paths=set(root.glob('host/io_usb_host*.[hm]'))|set(root.glob('tests/io_usb_host*.[hm]'))|set(root.glob('tests/test_io_usb_host*.py'))|set(root.glob('tools/*io_usb_host*.py'))
    paths.add(root/'tools/workflows/capture_io_usb_host_burst.py')
    paths.add(root.parents[1]/'source/uvc/iso_probe_protocol.h')
    return sorted(paths)

def plain(path,maximum=32*1024*1024):
    path=Path(path)
    require(path.is_file() and not path.is_symlink() and path.absolute()==path.resolve() and path.stat().st_size<=maximum,'invalid/oversized prepared file')
    return path.read_bytes()
def digest(path):return hashlib.sha256(plain(path)).hexdigest()
def load(path):return json.loads(plain(path,131072),object_pairs_hook=unique_object)
def write_new(path,value):durable_write(path,canonical(value));sync_dir(path.parent)
def replace_state(path,value):
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');write_new(temp,value);os.replace(temp,path);sync_dir(path.parent)
def source_hashes(root=ROOT):
    repo=root.parents[1];return {p.relative_to(repo).as_posix():digest(p) for p in source_paths(root)}

def verify_build(ticket,root=ROOT):
    require(type(ticket) is dict and ticket.get('schema')=='A23-burst-sdk-preparation-1' and
            ticket.get('backend')=='iousbhost-single-burst-1' and all(ticket.get(k) is False for k in POLICY),'invalid independent burst preparation')
    validate_plan(ticket.get('plan'));validate_scope(ticket.get('diagnostic_scope'))
    require(type(ticket.get('preparation_id')) is str and str(uuid.UUID(ticket['preparation_id']))==ticket['preparation_id'],'invalid preparation ID')
    build=Path(ticket['build']);require(build.is_absolute() and build.is_dir() and not build.is_symlink() and build==build.resolve(),'invalid build directory')
    require(not any(p.is_symlink() for p in build.rglob('*')),'symlink in prepared build')
    manifest=plain(build/'SHA256SUMS',1024*1024)
    require(hashlib.sha256(manifest).hexdigest()==ticket['build_manifest_sha256'] and
            plain(build/'COMMITTED',65)==(ticket['build_manifest_sha256']+'\n').encode(),'prepared build manifest changed')
    expected=[]
    for line in manifest.decode().splitlines():
        sha,name=line.split('  ',1);relative=Path(name)
        require(name==relative.as_posix() and not relative.is_absolute() and '..' not in relative.parts and name not in expected,'invalid/duplicate manifest path')
        require(digest(build/relative)==sha,'prepared file changed');expected.append(name)
    # Nested evidence hashes would be real files too; only outer seals excluded.
    actual=sorted(p.relative_to(build).as_posix() for p in build.rglob('*') if p.is_file() and p not in (build/'SHA256SUMS',build/'COMMITTED'))
    require(expected==sorted(expected) and actual==expected,'extra/missing prepared files')
    meta=load(build/'manifest.json');validate_plan(meta.get('plan'));validate_scope(meta.get('diagnostic_scope'))
    require(meta.get('schema')=='A23-burst-sdk-build-1' and meta.get('backend')=='iousbhost-single-burst-1' and
            meta.get('validation_passed') is True and meta.get('acquisition_enabled') is False and
            type(meta.get('usb_requests_during_preparation')) is int and meta['usb_requests_during_preparation']==0,'invalid build validation')
    require(meta.get('source_hashes')==source_hashes(root),'prepared sources changed; rebuild before issuance')
    for name,sha in meta['source_hashes'].items():require(digest(build/'source'/name)==sha,'frozen source differs from validated source')
    validate_plan(load(build/'describe.json'))
    require(digest(build/'receiver')==ticket['receiver_sha256'],'prepared receiver changed')
    return build

def verify_prepared(ticket,root=ROOT):
    require(ticket.get('stage')=='prepared' and type(ticket.get('remaining')) is int and ticket['remaining']==1 and
            ticket.get('acquisition_enabled') is True,'No single SDK burst invocation issued; no USB accessed')
    return verify_build(ticket,root)

def capture(ticket_path=TICKET,*,dry_run=False,root=ROOT):
    if dry_run:
        ticket=load(ticket_path);build=verify_build(ticket,root)
        require(ticket.get('stage') in ('offline_build_ready','prepared') and type(ticket.get('remaining')) is int and
                ((ticket['stage']=='offline_build_ready' and ticket['remaining']==0 and ticket.get('acquisition_enabled') is False) or
                 (ticket['stage']=='prepared' and ticket['remaining']==1 and ticket.get('acquisition_enabled') is True)),'not a ready offline/issued preparation')
        return dict(stage=ticket['stage'],remaining=ticket['remaining'],build=str(build),acquisition_enabled=ticket['acquisition_enabled'],usb_accessed=False,sd_copy_needed=False)
    # Check the zero-use/offline gate before even creating a lock or output.
    verify_prepared(load(ticket_path),root)
    lock=ticket_path.with_suffix('.lock');fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
    try:
        os.fsync(fd);ticket=load(ticket_path);build=verify_prepared(ticket,root)
        run=root/'private/runs'/('A-A23-HS-IOUSBHost-burst-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
        run.mkdir(mode=0o700);sync_dir(run.parent)
        ticket.update(stage='consumed',remaining=0,acquisition_enabled=False,run=str(run),consumed_at=datetime.now(timezone.utc).isoformat())
        replace_state(ticket_path,ticket)
        receipt=dict(schema='A23-burst-sdk-consumed-receipt-1',backend='iousbhost-single-burst-1',attempt_consumed=True,
            plan=ticket['plan'],diagnostic_scope=ticket['diagnostic_scope'],receiver_sha256=ticket['receiver_sha256'],
            build_manifest_sha256=ticket['build_manifest_sha256'],preparation_id=ticket['preparation_id'])
        write_new(run/'authorization.json',receipt);command=[str(build/'receiver'),'--acquire-once',str(run)];write_new(run/'command.json',command)
        with (run/'stdout.txt').open('x') as out,(run/'stderr.txt').open('x') as err:
            try:process=subprocess.Popen(command,stdout=out,stderr=err,start_new_session=True)
            except OSError as error:
                ticket.update(stage='failed_no_retry');replace_state(ticket_path,ticket)
                result=dict(error=str(error),host_observation_complete=False,receiver_launched=False,remaining=0,**{k:False for k in POLICY})
                write_new(run/'workflow-result.json',result);return result
            try:code=process.wait(timeout=20)
            except (subprocess.TimeoutExpired,OSError) as error:
                ticket.update(stage='unresolved_no_retry',receiver_pid=process.pid);replace_state(ticket_path,ticket)
                result=dict(stage=ticket['stage'],run=str(run),receiver_pid=process.pid,remaining=0,receiver_left_running=True,
                    forced_exit=False,error=str(error),host_observation_complete=False,**{k:False for k in POLICY})
                write_new(run/'workflow-result.json',result);return result
        try:
            result=audit_host(run/'host');entry=load(run/'entry-result.json')
            require(entry.get('schema')=='A23-burst-sdk-entry-result-1' and entry.get('backend')=='iousbhost-single-burst-1' and
                    entry.get('finished') is True and entry.get('unresolved') is False and entry.get('preflight_failed') is False and
                    type(entry.get('exit_code')) is int and entry['exit_code']==code and all(entry.get(k) is False for k in POLICY),'entry result contradicts process/host')
            from analyze_io_usb_host_burst_sdk import checkpoint
            final=checkpoint(run/'host/final');reported=entry.get('host_result')
            require(type(reported) is dict and set(reported)==set(final) and reported.get('final_checkpoint_saved') is True and
                    reported.get('exit_code')==code and type(reported.get('exit_code')) is int and
                    type(reported.get('ticks')) is int and reported['ticks']>=final['ticks'] and
                    all(canonical(reported[k])==canonical(final[k]) for k in final if k not in ('ticks','final_checkpoint_saved')),
                    'entry/coordinator result mismatch')
        except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:
            result=dict(host_observation_complete=False,error=str(error),**{k:False for k in POLICY})
        result.update(run=str(run),receiver_exit_code=code,remaining=0)
        write_new(run/'workflow-result.json',result)
        ticket.update(stage='captured_logs_pending' if code==0 and result['host_observation_complete'] else 'failed_no_retry');replace_state(ticket_path,ticket)
        manifest=''.join(f'{digest(p)}  {p.relative_to(run).as_posix()}\n' for p in sorted(run.rglob('*')) if p.is_file())
        durable_write(run/'SHA256SUMS',manifest.encode());sync_dir(run)
        durable_write(run/'COMMITTED',(hashlib.sha256(manifest.encode()).hexdigest()+'\n').encode());sync_dir(run)
        return result
    finally:os.close(fd);lock.unlink();sync_dir(lock.parent)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    try:
        result=capture(dry_run=args.dry_run);print(json.dumps(result,indent=2));return 0 if args.dry_run or result.get('host_observation_complete') else 1
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:print(str(error),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
