"""Two explicit card phases: readonly backup/eject, then reinsert/one empty create.

Preparation and analysis are file-only. Physical calls require separate human
repair authorization plus shutdown/connection confirmation at each phase. Model
jobs require an injected backend and cannot construct the physical backend.
"""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import uuid

import context65_flag_repair as repair
w=repair.w
PARENT=w.A/'A23-context65-flag-repair-closeout-20261018'
PROOF=w.A/'A23-context65-flag-card-proof.json'
NEW=('tools/context65_flag_card.py','tools/audit_a23_context65_flag_card.py','tests/test_a23_context65_flag_card.py')


def source_hashes():
    w.card.seal_verify(PARENT);source=repair.source_hashes()
    w.require(source==w.load(PARENT/'closeout.json')['source_hashes'],'old298 sources changed')
    for name in NEW:source['research/usb-ds-iso/'+name]=w.sha(w.plain(w.ROOT/name,2*1024*1024))
    return dict(sorted(source.items()))


def proof():
    if not PROOF.exists():return None
    value=w.load(PROOF);w.require(value['schema']=='A23-context65-flag-card-proof-1','wrong card proof schema')
    for key,name in [('review','audit.json'),('validation','validation.json')]:
        row=value[key];folder=w.canonical(row['directory']);w.card.seal_verify(folder);data=w.load(folder/name)
        w.require(w.sha(w.plain(folder/'SHA256SUMS'))==row['manifest_sha256'] and data['passed'] is True and
            data['source_hashes']==source_hashes() and all(type(data[k]) is int and data[k]==0 for k in
            ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations')),'card workflow proof changed')
        if key=='validation':w.require(data['tests_run']>0 and data['failures']==data['errors']==data['skipped']==0,'card tests incomplete')
    return value


def binding():
    original,scope,model=repair.materials(live=False)
    return original,scope,dict(schema='A23-context65-flag-card-scope-1',source_hashes=source_hashes(),
        parent_scope=model,card_workflow_proof=proof(),allowed_changed_files=[repair.FLAG],
        maximum_creates=1,automatic_retry=False,automatic_rollback=False,allow_test_issuance=False)


def prepare(job,before,after):
    job,before,after=map(w.canonical,(job,before,after));model=Path('/private/tmp') in job.parents
    w.require(not job.exists() and job.parent.is_dir() and (model or job.parent==w.A),'new repair job required')
    w.require(before!=after and all(not p.exists() and p.parent.is_dir() and
        ((model and Path('/private/tmp') in p.parents) or (not model and p.parent==w.ROOT/'private/card-cycles')) for p in (before,after)),
        'distinct new recovery outputs required')
    w.require(all(not a.is_relative_to(b) for a,b in ((job,before),(before,job),(job,after),(after,job),(before,after),(after,before))), 'overlapping job outputs')
    w.transition();w.require(w.latest_snapshot()==w.ANCHOR,'saved baseline changed; re-review card repair')
    _,_,scope=binding();w.require(model or scope['card_workflow_proof'] is not None,'formal adapter proof required')
    plan=dict(schema='A23-context65-flag-card-plan-1',job=str(job),preparation_id=str(uuid.uuid4()),
        before=str(before),after=str(after),simulation=model,scope=scope,prepared_at=w.card.now(),
        actual_repair_authorized=False,test_authorized=False,remaining=0)
    job.mkdir(mode=0o700);w.write(job/'plan.json',plan)
    w.write(job/'state.json',dict(schema='A23-context65-flag-card-state-1',stage='planned',backup_remaining=1,repair_remaining=1,
        plan_sha256=w.sha(w.plain(job/'plan.json')),actual_card_repaired=False,remaining=0));return plan


def verify_job(job):
    job=w.canonical(job);plan=w.load(job/'plan.json');state=w.load(job/'state.json');model=Path('/private/tmp') in job.parents
    w.require(plan['schema']=='A23-context65-flag-card-plan-1' and plan['job']==str(job) and plan['simulation'] is model and
        str(uuid.UUID(plan['preparation_id']))==plan['preparation_id'] and plan['actual_repair_authorized'] is False and
        plan['test_authorized'] is False and type(plan['remaining']) is int and plan['remaining']==0,'card job path/policy differs')
    w.require(w.sha(w.plain(job/'plan.json'))==state['plan_sha256'],'plan bytes changed')
    original,scope,expected=binding();w.require(w.b.old.typed(plan['scope'],expected),'card source/plan changed')
    w.require(model or expected['card_workflow_proof'] is not None,'formal adapter proof missing');w.transition()
    w.require(state['schema']=='A23-context65-flag-card-state-1' and type(state['remaining']) is int and state['remaining']==0,'invalid card state')
    if state['stage'] in ('planned','awaiting_reinsert'):
        expected_files={'plan.json','state.json'}|({'.backup.lock','backup-commands','before'} if state['stage']=='awaiting_reinsert' else set())
        w.require({p.name for p in job.iterdir()}==expected_files,'unexpected prepared job artifacts')
    for key in ('before','after'):
        path=w.canonical(plan[key]);w.require((model and Path('/private/tmp') in path.parents) or
            (not model and path.parent==w.ROOT/'private/card-cycles'),'recovery output location changed')
    return plan,state,original,scope


class UnresolvedCommand(OSError):
    def __init__(self,pid):super().__init__('disk command still running; no kill, retry, further I/O or seal');self.pid=pid


class MacBackend:
    simulated=False
    def begin(self,folder):self.log=w.canonical(folder);self.log.mkdir();self.index=0
    def launch(self,command,out,err):
        with out.open('xb') as stdout,err.open('xb') as stderr:
            process=subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True)
            try:return process.wait(timeout=30)
            except (subprocess.TimeoutExpired,OSError):raise UnresolvedCommand(process.pid)
    def command(self,args):
        command=['/usr/sbin/diskutil',*args] if args[0]!='sync' else ['/bin/sync']
        self.index+=1;name=f'{self.index:03d}';w.write(self.log/(name+'.json'),dict(command=command))
        out=self.log/(name+'.stdout');err=self.log/(name+'.stderr')
        code=self.launch(command,out,err)
        w.write(self.log/(name+'.exit.json'),dict(returncode=code));w.require(code==0,'disk command failed: '+str(args))
        return w.plain(out,2*1024*1024)
    def info(self,part,whole):
        value=plistlib.loads(self.command(['info','-plist','/dev/'+part]))
        w.require(type(value) is dict and value.get('VolumeUUID')==w.card.UUID and value.get('Internal') is False and
            value.get('FilesystemType')=='msdos' and value.get('DeviceIdentifier')==part and
            value.get('ParentWholeDisk')==whole,'card UUID/type/partition changed')
        return value
    def resolve(self):
        value=plistlib.loads(self.command(['list','-plist','external','physical']));found=[]
        w.require(type(value) is dict and type(value.get('AllDisksAndPartitions')) is list,'invalid external disk plist')
        for disk in value['AllDisksAndPartitions']:
            w.require(type(disk) is dict and type(disk.get('Partitions',[])) is list,'invalid disk partition list')
            for part in disk.get('Partitions',[]):
                w.require(type(part) is dict,'invalid partition plist')
                if part.get('VolumeUUID')==w.card.UUID:found.append((part['DeviceIdentifier'],disk['DeviceIdentifier']))
        w.require(len(found)==1,'one external physical card with the expected UUID required');part,whole=found[0]
        w.require(type(whole) is str and type(part) is str and re.fullmatch(r'disk[0-9]+',whole) and
            re.fullmatch(re.escape(whole)+r's[0-9]+',part),'unsafe disk identifier')
        self.info(part,whole);return part,whole
    def mounted(self,part,whole,*,readonly):
        value=self.info(part,whole)
        if value.get('MountPoint') and value.get('WritableVolume') is (not readonly):return SessionCard(self,part,whole,Path(value['MountPoint']))
        if value.get('MountPoint'):
            self.command(['unmount','/dev/'+part]);value=self.info(part,whole);w.require(not value.get('MountPoint'),'unmount did not remove mount')
        self.command(['mount',*(['readOnly','nobrowse'] if readonly else ['nobrowse']),'/dev/'+part])
        value=self.info(part,whole);w.require(type(value.get('MountPoint')) is str,'mount absent after mount command')
        card=SessionCard(self,part,whole,Path(value['MountPoint']));card.check(readonly=readonly,writable=not readonly);return card
    def mount_absent(self,root):return not root.exists()


class SessionCard:
    def __init__(self,backend,part,whole,root):
        self.backend=backend;self.simulated=backend.simulated;self.part=part;self.whole=whole;self.root=w.canonical(root)
        w.require(type(self.simulated) is bool and self.root.is_dir() and
            ((self.simulated and Path('/private/tmp') in self.root.parents) or (not self.simulated and self.root.parent==Path('/Volumes'))),'unsafe card mount root')
    def check(self,**mode):return w.card.identity(self.backend.info(self.part,self.whole),self.root,**mode)
    def sync(self):self.backend.command(['sync'])
    def eject(self,expected):
        w.require(self.check()==expected,'identity changed before eject');self.sync()
        w.require(self.check()==expected,'identity changed during sync');self.backend.command(['eject','/dev/'+self.whole])
        w.require(self.backend.mount_absent(self.root),'mount remains after eject')
        return dict(device=self.whole,ejected=True,mount_absent=True,ejected_at=w.card.now(),simulation=self.simulated)


def backend_for(plan,injected):
    if plan['simulation']:
        w.require(injected is not None and injected.simulated is True,'model requires injected disk backend');return injected
    w.require(injected is None,'formal job cannot use an injected backend');return MacBackend()


def preimage(folder,original,simulation):
    files=w.card.verify_snapshot(folder);meta=w.load(folder/'snapshot.json');eject=w.load(folder/'eject.json')
    w.require(meta['simulation'] is simulation and eject.get('simulation',False) is simulation and
        meta['mode']=='recovery' and meta['read_only_mount_verified'] is True and meta['deployment_files_match'] is False and
        meta['identity']['VolumeUUID']==w.card.UUID and eject['ejected'] is True and eject['mount_absent'] is True and
        w.timestamp(meta['collected_at'])>w.timestamp(w.load(w.ANCHOR/'snapshot.json')['collected_at']) and
        {n.removeprefix('card/'):raw for n,raw in files.items() if n.startswith('card/')}==original,'fresh absent-flag59 readonly/eject receipt differs')
    return dict(directory=str(folder),manifest_sha256=w.sha(w.plain(folder/'SHA256SUMS')),simulation=simulation)


def claim(job,state,phase):
    fd=os.open(job/('.'+phase+'.lock'),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:os.fsync(fd)
    finally:os.close(fd)
    w.b.old.sync_dir(job);state.update(stage=phase+'_consumed');state[phase+'_remaining']=0;w.replace(job/'state.json',state)


@contextmanager
def volume_guard(job,plan):
    """Serialize the one physical UUID across jobs; failures keep the owner."""
    parent=job.parent if plan['simulation'] else w.A
    active=parent/'A23-context65-flag-card-volume-owner.json'
    lock=parent/'A23-context65-flag-card-volume.lock'
    fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        w.require(not active.exists() and not active.is_symlink(),'card has a pending owner; manual review required')
        owner=dict(schema='A23-context65-flag-card-volume-owner-1',job=str(job),preparation_id=plan['preparation_id'],
            sd_uuid=w.card.UUID,simulation=plan['simulation'],automatic_release_on_failure=False)
        w.write(active,owner)
        yield
        w.require(w.load(active)==owner,'volume owner changed; retain it for review')
        active.unlink();w.b.old.sync_dir(parent)
    finally:os.close(fd) # exceptions retain the owner; a crashed/unknown child is not a free card


def failed(job,state,phase,error,created=False):
    unresolved=isinstance(error,UnresolvedCommand)
    state.update(stage='unresolved_no_retry' if unresolved else 'failed_no_retry',error=str(error),phase=phase,
        flag_create_returned_fd=created,actual_card_repaired=False,manual_review_required=True,
        automatic_retry=False,automatic_rollback=False,remaining=0)
    if unresolved:state.update(command_pid=error.pid,command_left_running=True,forced_exit=False)
    w.replace(job/'state.json',state)
    if not unresolved:w.b.seal(job) # command logs may still be changing on timeout


def backup(job,*,repair_authorized=False,shutdown_card_connected=False,_backend=None):
    w.require(repair_authorized is True and shutdown_card_connected is True,'explicit repair instruction and shutdown/card-connected confirmation required before disk access')
    job=w.canonical(job);plan,state,original,_=verify_job(job)
    w.require(state['stage']=='planned' and type(state['backup_remaining']) is int and state['backup_remaining']==1 and
        not Path(plan['before']).exists() and not Path(plan['after']).exists(),'no unused backup phase')
    w.require(w.latest_snapshot()==w.ANCHOR,'saved baseline changed before backup')
    backend=backend_for(plan,_backend);claim(job,state,'backup');phase='backup_disk_resolution'
    try:
        with volume_guard(job,plan):
            backend.begin(job/'backup-commands');part,whole=backend.resolve();card=backend.mounted(part,whole,readonly=True)
            w.require(w.card.selected(card.root)==original,'prewrite card differs from59 anchor; no repair')
            phase='backup_readonly_recovery_eject';w.card.recover(card,Path(plan['before']),eject_after=True)
            receipt=preimage(Path(plan['before']),original,plan['simulation']);shutil.copytree(plan['before'],job/'before')
            state.update(stage='awaiting_reinsert',before=receipt,backup_ejected=True,actual_card_repaired=False)
            w.replace(job/'state.json',state)
        return state
    except (OSError,ValueError,TypeError,KeyError) as error:failed(job,state,phase,error);raise


def empty_create(card,original,job):
    info=card.check(writable=True);target=card.root/repair.FLAG;parent=target.parent
    w.require(w.card.selected(card.root)==original and parent.is_dir() and parent==parent.resolve() and
        not target.exists() and not target.is_symlink(),'card/flags changed before create')
    w.write(job/'create-intent.json',dict(schema='A23-context65-flag-card-create-intent-1',identity=info,target=repair.FLAG,
        simulation=card.simulated,original_inventory=w.card.inventory(original),overwrite_allowed=False))
    parent_fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);flag_fd=None;created=False
    try:
        expected=os.fstat(parent_fd);current=parent.stat()
        w.require((expected.st_dev,expected.st_ino)==(current.st_dev,current.st_ino) and card.check(writable=True)==info and
            w.card.selected(card.root)==original,'identity/parent/originals changed before open')
        flag_fd=os.open(target.name,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600,dir_fd=parent_fd);created=True
        w.write(job/'flag-created.json',dict(create_returned_fd=True,simulation=card.simulated))
        w.require(os.fstat(flag_fd).st_size==0,'created flag is not empty');os.fsync(flag_fd)
        os.close(flag_fd);flag_fd=None;os.fsync(parent_fd)
        current=parent.stat();w.require((expected.st_dev,expected.st_ino)==(current.st_dev,current.st_ino),'flags directory replaced')
    except (OSError,ValueError) as error:
        error.flag_create_returned_fd=created;raise
    finally:
        if flag_fd is not None:os.close(flag_fd)
        os.close(parent_fd)
    card.sync();w.require(card.check(writable=True)==info and w.card.selected(card.root)=={**original,repair.FLAG:b''},'write readback differs')


def execute(job,*,repair_authorized=False,shutdown_card_reinserted=False,_backend=None):
    w.require(repair_authorized is True and shutdown_card_reinserted is True,'explicit repair instruction and shutdown/card-reinserted confirmation required before disk access')
    job=w.canonical(job);plan,state,original,scope=verify_job(job)
    w.require(state['stage']=='awaiting_reinsert' and type(state['repair_remaining']) is int and state['repair_remaining']==1 and
        not Path(plan['after']).exists(),'no unused repair phase')
    receipt=preimage(Path(plan['before']),original,plan['simulation']);w.require(receipt==state['before'],'prewrite receipt changed')
    w.require(w.latest_snapshot()==(w.ANCHOR if plan['simulation'] else Path(plan['before'])),'a newer recovery exists; re-review')
    backend=backend_for(plan,_backend);claim(job,state,'repair');phase='repair_disk_resolution';created=False
    try:
        with volume_guard(job,plan):
            backend.begin(job/'repair-commands');part,whole=backend.resolve();card=backend.mounted(part,whole,readonly=True)
            w.require(w.card.selected(card.root)==original,'reinserted card differs; no writable mount')
            phase='writable_mount';card=backend.mounted(part,whole,readonly=False)
            phase='exclusive_empty_create';empty_create(card,original,job);created=True
            phase='readonly_mount_and_readback';card=backend.mounted(part,whole,readonly=True)
            w.require(w.card.selected(card.root)=={**original,repair.FLAG:b''},'readonly postimage differs')
            phase='post_recovery_and_eject';w.card.recover(card,Path(plan['after']),eject_after=True)
            recovered=w.verify_recovery(Path(plan['after']),scope,simulation=plan['simulation'])
            saved=w.card.verify_snapshot(Path(plan['after']))
            w.require({n.removeprefix('card/'):v for n,v in saved.items() if n.startswith('card/')}=={**original,repair.FLAG:b''},'post recovery has unexpected files')
            shutil.copytree(plan['after'],job/'after')
            state.update(stage='complete',post_recovery=recovered,post_ejected=True,flag_create_returned_fd=True,
                actual_card_repaired=not plan['simulation'],formal_baseline_accepted=not plan['simulation'],
                automatic_retry=False,automatic_rollback=False,remaining=0)
            w.replace(job/'state.json',state)
        w.b.seal(job);return state
    except (OSError,ValueError,TypeError,KeyError) as error:
        created=created or getattr(error,'flag_create_returned_fd',False) or (job/'flag-created.json').exists()
        failed(job,state,phase,error,created);raise


def analyze(job):
    """Static supplied-file checks, with no live card/history/latest lookup."""
    job=w.canonical(job);files=w.card.seal_verify(job);plan=w.load(job/'plan.json');state=w.load(job/'state.json')
    w.require({p.name for p in job.iterdir()}=={'plan.json','state.json','.backup.lock','.repair.lock','backup-commands',
        'repair-commands','before','after','create-intent.json','flag-created.json','SHA256SUMS','COMMITTED'},'success inventory differs')
    model=plan['simulation'];w.require(type(model) is bool and plan['schema']=='A23-context65-flag-card-plan-1' and
        type(plan['remaining']) is int and plan['remaining']==0 and state['schema']=='A23-context65-flag-card-state-1' and
        plan['scope']['source_hashes']==source_hashes() and w.b.old.typed(plan['scope']['parent_scope'],repair.materials(live=False)[2]) and
        state['plan_sha256']==w.sha(w.plain(job/'plan.json')) and plan['actual_repair_authorized'] is False and plan['test_authorized'] is False and
        state['stage']=='complete' and all(type(state[k]) is int and state[k]==0 for k in ('remaining','backup_remaining','repair_remaining')) and
        state['flag_create_returned_fd'] is True and state['backup_ejected'] is True and state['post_ejected'] is True and
        state['actual_card_repaired'] is (not model) and state['formal_baseline_accepted'] is (not model) and
        state['automatic_retry'] is False and state['automatic_rollback'] is False,'saved card success differs')
    expected=dict(schema='A23-context65-flag-card-scope-1',source_hashes=source_hashes(),parent_scope=repair.materials(live=False)[2],
        card_workflow_proof=plan['scope']['card_workflow_proof'],allowed_changed_files=[repair.FLAG],maximum_creates=1,
        automatic_retry=False,automatic_rollback=False,allow_test_issuance=False)
    w.require(w.b.old.typed(plan['scope'],expected) and ((model and expected['card_workflow_proof'] is None) or
        expected['card_workflow_proof']==proof()),'saved card scope/proof differs')
    original,scope,_=repair.materials(live=False);before=preimage(job/'before',original,model)
    after=w.verify_recovery(job/'after',scope,simulation=model,require_latest=False)
    w.require(before['manifest_sha256']==state['before']['manifest_sha256'] and after['manifest_sha256']==state['post_recovery']['manifest_sha256'] and
        {n.removeprefix('card/'):v for n,v in w.card.verify_snapshot(job/'after').items() if n.startswith('card/')}=={**original,repair.FLAG:b''},'saved recovery differs')
    intent=w.load(job/'create-intent.json');created=w.load(job/'flag-created.json')
    w.require(intent['target']==repair.FLAG and intent['simulation'] is model and intent['overwrite_allowed'] is False and
        intent['original_inventory']==w.card.inventory(original) and created==dict(create_returned_fd=True,simulation=model),'saved create intent differs')
    root=Path(intent['identity']['MountPoint']);w.card.identity(intent['identity'],root,writable=True)
    w.require(root.is_absolute() and ((model and Path('/private/tmp') in root.parents) or (not model and root.parent==Path('/Volumes'))),'saved mount location differs')
    counts={}
    for phase in ('backup','repair'):
        folder=job/(phase+'-commands');rows=sorted(folder.glob('*.json'));commands=[];indexes=[]
        for path in rows:
            if path.name.endswith('.exit.json'):continue
            w.require(re.fullmatch(r'[0-9]{3}\.json',path.name),'invalid command log name')
            index=path.stem;indexes.append(int(index));command=w.load(path)['command'];commands.append(command)
            code=w.load(folder/(index+'.exit.json'))['returncode'];w.require(type(code) is int and code==0,'command did not close successfully')
            w.require((folder/(index+'.stdout')).is_file() and (folder/(index+'.stderr')).is_file(),'command output missing')
            w.require(command==['/bin/sync'] or (command[:1]==['/usr/sbin/diskutil'] and
                (command[1:]==['list','-plist','external','physical'] or
                 (command[1:-1] in (['info','-plist'],['unmount'],['eject'],['mount','nobrowse'],['mount','readOnly','nobrowse']) and
                  re.fullmatch(r'/dev/disk[0-9]+(?:s[0-9]+)?',command[-1])))),'command outside bounded adapter')
        w.require(indexes==list(range(1,len(indexes)+1)) and 0<len(indexes)<256 and
            {p.name for p in folder.iterdir()}=={f'{n:03d}'+suffix for n in indexes for suffix in ('.json','.exit.json','.stdout','.stderr')},'command log inventory differs')
        writable=sum(c[1:-1]==['mount','nobrowse'] for c in commands);ejects=sum(c[1:-1]==['eject'] for c in commands)
        w.require(writable==(1 if phase=='repair' else 0) and ejects==1,'mount/eject count differs')
        counts[phase]=dict(commands=len(commands),writable_mounts=writable,ejects=ejects)
    w.require(w.card.seal_verify(job)==files,'job archive changed')
    return dict(schema='A23-context65-flag-card-analysis-1',supplied_chain_consistent=True,manifest_sha256=w.sha(w.plain(job/'SHA256SUMS')),
        simulation=model,preserved_originals=59,changed_files=[repair.FLAG],commands=counts,physical_run_authenticated=False,remaining=0)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('prepare');p.add_argument('job',type=Path)
    for name in ('before','after'):p.add_argument('--'+name,type=Path,required=True)
    sub.add_parser('check').add_argument('job',type=Path)
    sub.add_parser('analyze').add_argument('job',type=Path)
    for mode in ('backup','execute'):
        p=sub.add_parser(mode);p.add_argument('job',type=Path);p.add_argument('--repair-authorized',action='store_true')
        p.add_argument('--confirm-shutdown-card-'+('connected' if mode=='backup' else 'reinserted'),action='store_true')
    args=parser.parse_args()
    if args.mode=='prepare':result=prepare(args.job,args.before,args.after)
    elif args.mode=='check':result=verify_job(args.job)[1]
    elif args.mode=='analyze':result=analyze(args.job)
    elif args.mode=='backup':result=backup(args.job,repair_authorized=args.repair_authorized,shutdown_card_connected=args.confirm_shutdown_card_connected)
    else:result=execute(args.job,repair_authorized=args.repair_authorized,shutdown_card_reinserted=args.confirm_shutdown_card_reinserted)
    print(json.dumps(result,indent=2))
