"""Separate consumed-before-launch one-use SDK no-TD gate. Never force-kill DMA."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from analyze_io_usb_host_evidence import require, unique_object
from analyze_io_usb_host_collection import durable_write, sync_dir
from analyze_io_usb_host_hardware import analyze_run
from io_usb_host_probe_plan import validate_hardware_plan
TICKET=ROOT/'private/analysis/A23-IOUSBHost-next-test.json'


def digest(path):
    require(path.is_file() and not path.is_symlink(),'not a regular prepared file')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=131072,'invalid gate file')
    return json.loads(path.read_bytes(),object_pairs_hook=unique_object)


def write_new(path,value):
    durable_write(path,(json.dumps(value,indent=2,sort_keys=True)+'\n').encode());sync_dir(path.parent)


def replace_state(path,value):
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    write_new(temporary,value);os.replace(temporary,path);sync_dir(path.parent)


def verify_prepared(ticket,root=ROOT):
    require(ticket.get('schema')=='A23-IOUSBHost-preparation-1' and ticket.get('backend')=='iousbhost-no-td-1' and
            ticket.get('stage')=='prepared' and type(ticket.get('remaining')) is int and ticket['remaining']==1,
            'No single SDK no-TD invocation prepared; no USB accessed')
    validate_hardware_plan(ticket.get('plan'))
    build=Path(ticket['build']);require(build.is_dir() and not build.is_symlink(),'invalid prepared build')
    require(digest(build/'SHA256SUMS')==ticket['build_manifest_sha256'],'prepared build manifest changed')
    files=set()
    for line in (build/'SHA256SUMS').read_text().splitlines():
        sha,name=line.split('  ',1);relative=Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts and name not in files,'invalid prepared manifest path')
        require(digest(build/relative)==sha,'prepared file changed');files.add(name)
    require({p.relative_to(build).as_posix() for p in build.rglob('*') if p.is_file() and p!=build/'SHA256SUMS'}==files,
            'extra/missing prepared files')
    meta=load(build/'manifest.json')
    require(meta.get('schema')=='A23-IOUSBHost-build-1' and meta.get('backend')=='iousbhost-no-td-1' and meta.get('validation_passed') is True and
            meta.get('usb_requests_during_preparation')==0 and type(meta.get('usb_requests_during_preparation')) is int,
            'build validation missing')
    validate_hardware_plan(meta.get('plan'))
    require(digest(build/'receiver')==ticket['receiver_sha256'],'receiver changed')
    for name,sha in meta['source_hashes'].items():
        relative=Path(name);require(not relative.is_absolute() and '..' not in relative.parts,'invalid source path')
        require(digest(root/relative)==sha,'prepared source changed; rebuild before hardware')
    require(digest(root.parents[1]/'source/uvc/iso_probe_protocol.h')==meta.get('protocol_header_sha256'), 'prepared protocol changed')
    return build


def capture(ticket_path=TICKET, *, dry_run=False, root=ROOT):
    # Dry-run performs only file reads, never claims an attempt or starts a process.
    if dry_run:
        ticket=load(ticket_path);build=verify_prepared(ticket,root)
        return dict(stage='prepared',remaining=1,build=str(build),usb_accessed=False,sd_copy_needed=False)
    lock=ticket_path.with_suffix('.lock')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600)
    try:
        os.fsync(fd);ticket=load(ticket_path);build=verify_prepared(ticket,root)
        run=root/'private/runs'/('A-A23-HS-IOUSBHost-no-td-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
        run.mkdir(mode=0o700)
        sync_dir(run.parent)
        ticket.update(stage='consumed',remaining=0,run=str(run),consumed_at=datetime.now(timezone.utc).isoformat())
        replace_state(ticket_path,ticket) # Must be durable BEFORE launch, including failed launch/preflight.
        receipt=dict(schema='A23-IOUSBHost-consumed-receipt-1',attempt_consumed=True,plan=ticket['plan'],
            receiver_sha256=ticket['receiver_sha256'],preparation_id=ticket['preparation_id'],build_manifest_sha256=ticket['build_manifest_sha256'])
        write_new(run/'authorization.json',receipt)
        command=[str(build/'receiver'),'--acquire-once',str(run)];write_new(run/'command.json',command)
        with (run/'stdout.txt').open('x') as out,(run/'stderr.txt').open('x') as err:
            process=subprocess.Popen(command,stdout=out,stderr=err,start_new_session=True)
            try:code=process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                # Pending I/O or a blocked SDK call: leave the receiver resident.
                # A watchdog is not permission to unmap or destroy outstanding DMA.
                ticket.update(stage='unresolved_no_retry',receiver_pid=process.pid);replace_state(ticket_path,ticket)
                result=dict(stage=ticket['stage'],run=str(run),receiver_pid=process.pid,remaining=0,
                            receiver_left_running=True,forced_exit=False,hardware_verified=False,baseline_accepted=False)
                write_new(run/'workflow-result.json',result);return result
        try:result=analyze_run(run)
        except (OSError,ValueError,TypeError,KeyError) as error:
            result=dict(host_observation_complete=False,error=str(error),hardware_verified=False,baseline_accepted=False)
        result.update(run=str(run),receiver_exit_code=code,remaining=0)
        write_new(run/'workflow-result.json',result)
        ticket.update(stage='captured_logs_pending' if code==0 and result['host_observation_complete'] else 'failed_no_retry')
        replace_state(ticket_path,ticket)
        manifest=''.join(f'{digest(p)}  {p.relative_to(run).as_posix()}\n' for p in sorted(run.rglob('*')) if p.is_file())
        durable_write(run/'SHA256SUMS',manifest.encode());sync_dir(run)
        return result
    finally:
        os.close(fd);lock.unlink();sync_dir(lock.parent)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    try:
        result=capture(dry_run=args.dry_run);print(json.dumps(result,indent=2))
        return 0 if args.dry_run or result.get('host_observation_complete') else 1
    except (OSError,ValueError,TypeError,KeyError) as error:
        print(str(error),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
