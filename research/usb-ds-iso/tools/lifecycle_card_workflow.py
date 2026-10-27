#!/usr/bin/env python3
"""Bounded card files and receipts. Import/--help never probes a card.

DirectoryCard is a disposable model. MacCard uses explicit mount/device inputs;
actual deployment additionally requires CLI --execute and prior authorization.
No receiver launch, device request, ticket change, deletion or automatic rollback.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import uuid
from zoneinfo import ZoneInfo

import prepare_a23_lifecycle_once as once
import a23_lifecycle_capsule as capsule
from collect_a23_execution_v3 import read as read_file

pkg=once.package;b=once.build;require=b.require
UUID=once.gate.SD_UUID
TREES=('atmosphere/contents/'+pkg.TITLE,'atmosphere/exefs_patches/SysDVR-ISO',
       'atmosphere/crash_reports','atmosphere/fatal_reports','atmosphere/erpt_reports')
MAX_FILES=4096;MAX_FILE=32*1024*1024;MAX_TOTAL=256*1024*1024


def now():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()

def identity(value,root,*,writable=False,readonly=False):
    require(type(value) is dict and value.get('VolumeUUID')==UUID and value.get('MountPoint')==str(root) and
        value.get('Internal') is False and value.get('FilesystemType')=='msdos','wrong card UUID/mount/type')
    disk=value.get('ParentWholeDisk');part=value.get('DeviceIdentifier')
    require(type(disk) is str and re.fullmatch(r'disk[0-9]+',disk) and type(part) is str and
        re.fullmatch(re.escape(disk)+r's[0-9]+',part),'card partition/disk mismatch')
    require(type(value.get('WritableVolume')) is bool,'unknown card write mode')
    require(not writable or value['WritableVolume'],'card is not writable')
    require(not readonly or not value['WritableVolume'],'recovery requires a read-only mount')
    return {k:value[k] for k in ('VolumeUUID','MountPoint','Internal','FilesystemType','ParentWholeDisk','DeviceIdentifier','WritableVolume')}


class DirectoryCard:
    """Only temporary directories; never produces an issuable deployment schema."""
    simulated=True
    def __init__(self,root,*,readonly=False):
        self.root=Path(root);require(self.root.is_absolute() and self.root==self.root.resolve() and
            Path('/private/tmp') in self.root.parents and self.root.is_dir(),'temporary canonical model root required')
        self.attached=True;self.readonly=readonly
        self.info=dict(VolumeUUID=UUID,MountPoint=str(self.root),Internal=False,FilesystemType='msdos',
            ParentWholeDisk='disk42',DeviceIdentifier='disk42s1',WritableVolume=not readonly)
    def check(self,**mode):
        require(self.attached,'model card detached');return identity(self.info,self.root,**mode)
    def sync(self):pass
    def eject(self,expected):
        require(self.check()==expected,'model identity changed before eject');self.attached=False
        return dict(device=expected['ParentWholeDisk'],ejected=True,mount_absent=True,ejected_at=now(),simulation=True)


class MacCard:
    simulated=False
    def __init__(self,root,device):
        self.root=Path(root);self.device=device
        require(self.root.is_absolute() and self.root.parent==Path('/Volumes') and self.root==self.root.resolve() and
            self.root.is_dir() and type(device) is str and re.fullmatch(r'disk[0-9]+s[0-9]+',device),'explicit canonical volume and partition required')
    def check(self,**mode):
        raw=subprocess.check_output(['diskutil','info','-plist','/dev/'+self.device])
        value=identity(plistlib.loads(raw),self.root,**mode)
        require(value['DeviceIdentifier']==self.device,'selected device changed');return value
    def sync(self):subprocess.run(['sync'],check=True,capture_output=True)
    def eject(self,expected):
        require(self.check()==expected,'card identity changed before eject');self.sync()
        result=subprocess.run(['diskutil','eject','/dev/'+expected['ParentWholeDisk']],check=True,capture_output=True,text=True)
        require(not self.root.exists(),'mount remains after ejection')
        return dict(device=expected['ParentWholeDisk'],ejected=True,mount_absent=True,ejected_at=now(),result=result.stdout.strip())


def new_output(path,card,kind):
    path=Path(path)
    require(path.is_absolute() and path==path.resolve() and not path.exists() and not path.is_relative_to(card.root),
        'new canonical computer-side output required')
    allowed=b.ROOT/'private'/kind
    require(path.parent==allowed or Path('/private/tmp') in path.parents,'output must be outside sealed analysis trees')
    require(not card.root.is_relative_to(path),'output overlaps card root');return path


def relative(name):
    require(type(name) is str and re.fullmatch(r'[A-Za-z0-9_.\-/]+',name) and not Path(name).is_absolute() and
        all(part not in ('','.','..') for part in name.split('/')) and len(Path(name).parts)<=9,'unsafe card filename')
    return name


def selected(root,exclude=()):
    root=Path(root);require(root==root.resolve() and root.is_dir(),'card root changed')
    paths=set()
    for name in TREES:
        top=root/name
        require(not top.is_symlink() and top==top.resolve(),'symlinked selected tree')
        if not top.exists():continue
        require(top.is_dir(),'selected tree is not a directory')
        for path in top.rglob('*'):
            require(not path.is_symlink() and (path.is_dir() or path.is_file()),'nonregular selected entry')
            if path.is_file():paths.add(path.relative_to(root).as_posix())
    log=root/'logfile.txt'
    if log.exists() or log.is_symlink():paths.add('logfile.txt')
    for path in root.glob('ep0-*'):
        require(path.is_file() and not path.is_symlink(),'nonregular ep0 original');paths.add(path.name)
    paths-=set(exclude);require(len(paths)<=MAX_FILES,'too many selected card files')
    result={};total=0
    for name in sorted(paths):
        relative(name);raw=read_file(root/name,MAX_FILE);total+=len(raw);require(total<=MAX_TOTAL,'selected card bytes exceed limit')
        result[name]=raw
    return result


def inventory(files):return {n:dict(bytes=len(raw),sha256=b.sha(raw)) for n,raw in sorted(files.items())}

def four(files):return [dict(path=n,size=len(files[n]),sha256=b.sha(files[n])) for n in pkg.PATHS if n in files]

def expected(files,baseline):
    seen={row['path']:dict(bytes=row['size'],sha256=row['sha256']) for row in four(files)}
    require(b.old.typed(seen,baseline),'four-file baseline mismatch; do not write')


def put(root,name,raw):
    path=root/relative(name);path.parent.mkdir(parents=True,exist_ok=True);b.old.durable_write(path,raw)


def seal_verify(root):
    root=Path(root);require(root.is_absolute() and root==root.resolve() and root.is_dir(),'canonical sealed snapshot required')
    entries=list(root.rglob('*'));require(len(entries)<=MAX_FILES+128 and all(not p.is_symlink() and (p.is_dir() or p.is_file()) for p in entries),'invalid sealed tree')
    files={p.relative_to(root).as_posix():read_file(p,MAX_FILE) for p in entries if p.is_file() and p not in (root/'SHA256SUMS',root/'COMMITTED')}
    sums=''.join(b.sha(raw)+'  '+n+'\n' for n,raw in sorted(files.items())).encode()
    require(read_file(root/'SHA256SUMS',1024*1024)==sums and read_file(root/'COMMITTED',65)==(b.sha(sums)+'\n').encode(),'sealed snapshot inventory mismatch')
    return files


def describe_lifecycle(files,recipe):
    rows=[]
    for name,raw in sorted(files.items()):
        if '/' in name or not name.startswith('ep0-life-'):continue
        row=dict(path=name,bytes=len(raw),sha256=b.sha(raw),header_valid=False)
        try:
            prefix=capsule.decode(raw,recipe);row.update(header_valid=True,prefix=prefix,
                filename_matches_nonce=name=='ep0-life-'+prefix['main_nonce_hex']+'.bin')
        except (ValueError,TypeError,OverflowError) as error:row['error']=str(error)
        rows.append(row)
    return rows


def snapshot(card,output,*,recovery=False,eject_after=False):
    require(type(recovery) is bool and type(eject_after) is bool and (not eject_after or recovery),'explicit recovery/ejection mode required')
    output=new_output(output,card,'card-cycles');info=card.check(readonly=recovery)
    pkg.verify_review(once.PACKAGE);report=b.load(once.PACKAGE/'package-report.json')
    original=selected(card.root)
    if not recovery:expected(original,report['historical_baseline'])
    output.mkdir(parents=True,mode=0o700)
    for name,raw in original.items():put(output,'card/'+name,raw)
    require(card.check(readonly=recovery)==info and selected(card.root)==original,'card changed during snapshot')
    require({n:read_file(output/'card'/n,MAX_FILE) for n in original}==original,'computer copy readback mismatch')
    eject=None
    if eject_after:
        eject=card.eject(info)
        require(eject.get('ejected') is True and eject.get('mount_absent') is True and eject.get('device')==info['ParentWholeDisk'],'recovery target disk ejection not confirmed')
        b.write(output/'eject.json',eject)
    result=dict(schema='A23-lifecycle-card-snapshot-1',mode='recovery' if recovery else 'predeployment',simulation=card.simulated,
        collected_at=now(),identity=info,package_manifest_sha256=b.sha(b.plain(once.PACKAGE/'SHA256SUMS')),
        package_directory=str(once.PACKAGE),device_binding_sha256=report['device_binding_sha256'],
        expected_recipe_sha256=report['device_binding']['runtime_recipe_sha256'],ejection_requested=eject_after,
        raw_files=inventory(original),deployment_files=four(original),
        expected_deployment_files=report['deployment_files' if recovery else 'historical_baseline'],
        deployment_files_match={row['path']:dict(bytes=row['size'],sha256=row['sha256']) for row in four(original)}==report['deployment_files' if recovery else 'historical_baseline'],
        ep0_files=[n for n in original if '/' not in n and n.startswith('ep0-')],
        lifecycle=describe_lifecycle(original,report['device_binding']['runtime_recipe_sha256']),
        card_files_written=False,read_only_mount_verified=recovery,physical_run_authenticated=False,hardware_verified=False,
        root_cause_confirmed=False,attempt_issued=False,remaining=0,usb_requests=0)
    b.write(output/'snapshot.json',result);b.seal(output);verify_snapshot(output);return result


def verify_snapshot(root):
    files=seal_verify(Path(root));meta=json.loads(files['snapshot.json'],object_pairs_hook=b.old.unique_object)
    require(type(meta) is dict and meta.get('schema')=='A23-lifecycle-card-snapshot-1' and
        meta.get('mode') in ('predeployment','recovery') and type(meta.get('simulation')) is bool,'snapshot schema mismatch')
    raw={n.removeprefix('card/'):data for n,data in files.items() if n.startswith('card/')}
    require(set(files)=={'snapshot.json'}|{'card/'+n for n in raw}|({'eject.json'} if meta.get('ejection_requested') is True else set()),'snapshot inventory shape mismatch')
    require(inventory(raw)==meta['raw_files'] and b.old.typed(four(raw),meta['deployment_files']),'snapshot copied originals differ from inventory')
    require(type(meta.get('expected_recipe_sha256')) is str and re.fullmatch('[0-9a-f]{64}',meta['expected_recipe_sha256']),'snapshot recipe shape')
    require(b.old.typed(describe_lifecycle(raw,meta['expected_recipe_sha256']),meta['lifecycle']),'saved lifecycle analysis differs')
    require(type(meta.get('ejection_requested')) is bool and
        meta.get('read_only_mount_verified') is (meta['mode']=='recovery') and
        (meta['mode']!='recovery' or meta['identity']['WritableVolume'] is False),'snapshot read-only claims contradict mode')
    seen={row['path']:dict(bytes=row['size'],sha256=row['sha256']) for row in four(raw)}
    require(meta['deployment_files_match'] is b.old.typed(seen,meta['expected_deployment_files']) and
        meta['ep0_files']==[n for n in sorted(raw) if '/' not in n and n.startswith('ep0-')],'snapshot file summary differs')
    require(meta['card_files_written'] is False and meta['physical_run_authenticated'] is False and meta['hardware_verified'] is False and
        meta['root_cause_confirmed'] is False and type(meta['remaining']) is int and meta['remaining']==0 and meta['attempt_issued'] is False,'snapshot policy mismatch')
    if 'eject.json' in files:
        eject=json.loads(files['eject.json'],object_pairs_hook=b.old.unique_object)
        require(eject.get('ejected') is True and eject.get('mount_absent') is True and eject.get('device')==meta['identity']['ParentWholeDisk'],'saved ejection mismatch')
    return files


def recover(card,output,*,eject_after=False):return snapshot(card,output,recovery=True,eject_after=eject_after)


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
        require(card.check(writable=True)==info and selected(card.root,exclude=(temporary,))==original,'card changed before replacement')
        phase='replace';os.replace(card.root/temporary,target);published=True
        phase='sync';card.sync()
        phase='readback';after=selected(card.root);wanted={**original,pkg.PATHS[0]:raw}
        require(card.check(writable=True)==info and after==wanted,'deployment readback or preserved originals mismatch')
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('preview','snapshot','recover','deploy'))
    p.add_argument('--mount',type=Path,required=True);p.add_argument('--device');p.add_argument('--model',action='store_true')
    p.add_argument('--output',type=Path);p.add_argument('--snapshot',type=Path);p.add_argument('--execute',action='store_true')
    p.add_argument('--eject-after',action='store_true',help='recover only: eject target after verified computer copy')
    args=p.parse_args()
    if args.eject_after and args.mode!='recover':p.error('--eject-after is only valid for recover')
    card=DirectoryCard(args.mount,readonly=args.mode=='recover') if args.model else MacCard(args.mount,args.device)
    if args.mode=='preview':
        result=dict(identity=card.check(),simulation=card.simulated,files=inventory(selected(card.root)),card_files_written=False,remaining=0)
    else:
        if args.output is None:p.error('--output required')
        if args.mode=='deploy':
            if not args.execute or args.snapshot is None:p.error('deploy requires --execute and --snapshot, after authorization')
            result=deploy(card,args.snapshot,args.output)
        else:result=recover(card,args.output,eject_after=args.eject_after) if args.mode=='recover' else snapshot(card,args.output)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
