"""Read saved card-job files only; never probe a PID/card or release any claim."""
import argparse
import json
from pathlib import Path
import re
import uuid

import context65_flag_card as adapter
w=adapter.w
PARENT=w.A/'A23-context65-flag-card-closeout-20261018'
NEW=('tools/inspect_a23_context65_flag_card.py','tests/test_a23_context65_flag_inspector.py')
STAGES={'planned','awaiting_reinsert','complete','failed_no_retry','unresolved_no_retry','backup_consumed','repair_consumed'}


def source_hashes():
    w.card.seal_verify(PARENT);source=adapter.source_hashes()
    w.require(source==w.load(PARENT/'closeout.json')['source_hashes'],'old301 sources changed')
    for name in NEW:source['research/usb-ds-iso/'+name]=w.sha(w.plain(w.ROOT/name,2*1024*1024))
    return dict(sorted(source.items()))


def local(path):
    path=Path(path);w.require(path.is_absolute() and (path==w.A or path.is_relative_to(w.A) or Path('/private/tmp') in path.parents),
        'only saved local analysis/temporary files are accepted');return w.canonical(path)


def snapshot(folder):
    folder=local(folder);w.require(folder.is_dir(),'saved job directory required');result={};total=0
    entries=list(folder.rglob('*'));w.require(len(entries)<=4224,'job inventory exceeds bound')
    for path in entries:
        w.require(not path.is_symlink() and (path.is_file() or path.is_dir()),'nonregular job entry')
        if path.is_file():
            raw=w.plain(path,32*1024*1024);total+=len(raw);w.require(total<=256*1024*1024,'job bytes exceed bound')
            result[path.relative_to(folder).as_posix()]=raw
    return result


def parse(raw):return json.loads(raw,object_pairs_hook=w.b.old.unique_object)


def command_allowed(command):
    return type(command) is list and (command==['/bin/sync'] or (len(command)>=2 and command[0]=='/usr/sbin/diskutil' and
        (command[1:]==['list','-plist','external','physical'] or (command[1:-1] in
        (['info','-plist'],['unmount'],['eject'],['mount','nobrowse'],['mount','readOnly','nobrowse']) and
        type(command[-1]) is str and re.fullmatch(r'/dev/disk[0-9]+(?:s[0-9]+)?',command[-1]) is not None))))


def inspect(job,owner=None):
    job=local(job);raw=snapshot(job);issues=[];commands=[];seal='absent';before_saved=False;complete=False
    owner_path=local(owner) if owner is not None else None
    owner_raw=w.plain(owner_path,16384) if owner_path is not None and owner_path.exists() else None
    plan=parse(raw['plan.json']);state=parse(raw['state.json']);model=plan['simulation'];stage=state['stage']
    w.require(type(model) is bool and stage in STAGES,'unsupported job stage/simulation')
    _,_,scope=adapter.binding()
    if model and plan['scope']['card_workflow_proof'] is None:scope['card_workflow_proof']=None
    w.require(plan['schema']=='A23-context65-flag-card-plan-1' and w.b.old.typed(plan['scope'],scope) and
        type(plan['remaining']) is int and plan['remaining']==0 and type(plan['preparation_id']) is str and
        str(uuid.UUID(plan['preparation_id']))==plan['preparation_id'] and plan['actual_repair_authorized'] is False and plan['test_authorized'] is False and
        state['schema']=='A23-context65-flag-card-state-1' and state['plan_sha256']==w.sha(raw['plan.json']) and
        type(state['remaining']) is int and state['remaining']==0 and
        all(type(state[k]) is int and state[k] in (0,1) for k in ('backup_remaining','repair_remaining')),'saved job binding/policy differs')
    if ('COMMITTED' in raw)!=('SHA256SUMS' in raw):issues.append('partial seal')
    elif 'COMMITTED' in raw:
        try:w.card.seal_verify(job);seal='verified'
        except (OSError,ValueError):seal='invalid';issues.append('job seal differs')
    if stage in ('unresolved_no_retry','backup_consumed','repair_consumed') and seal!='absent':issues.append('unclosed job must not be sealed')
    if stage in ('complete','failed_no_retry') and seal!='verified':issues.append('closed job lacks a verified seal')
    for phase in ('backup','repair'):
        prefix=phase+'-commands/'
        names={n[len(prefix):] for n in raw if n.startswith(prefix)}
        w.require(all(re.fullmatch(r'[0-9]{3}\.(?:json|exit\.json|stdout|stderr)',n) for n in names),'unknown command artifact')
        indexes=sorted(int(n[:3]) for n in names if re.fullmatch(r'[0-9]{3}\.json',n))
        w.require(len(indexes)<256 and indexes==list(range(1,len(indexes)+1)),'command numbering differs')
        w.require(all(int(n[:3]) in indexes for n in names),'orphan command output')
        for index in indexes:
            base=prefix+f'{index:03d}';command=parse(raw[base+'.json'])['command']
            w.require(command_allowed(command),'unbounded disk command in saved job')
            code=parse(raw[base+'.exit.json'])['returncode'] if base+'.exit.json' in raw else None
            w.require(code is None or type(code) is int,'invalid command exit type')
            commands.append(dict(phase=phase,index=index,command=command,exit_code=code,
                outputs_present=all(base+s in raw for s in ('.stdout','.stderr'))))
    if stage=='planned' and (set(raw)!={'plan.json','state.json'} or state['backup_remaining']!=1 or state['repair_remaining']!=1):issues.append('planned job has claimed or unexpected material')
    for phase in ('backup','repair'):
        lock='.'+phase+'.lock'
        if state[phase+'_remaining']==0 and (lock not in raw or raw[lock]!=b''):issues.append('consumed phase lacks empty durable lock: '+phase)
    if any(n.startswith('before/') for n in raw):
        try:
            original=adapter.repair.materials(live=False)[0];receipt=adapter.preimage(job/'before',original,model)
            before_saved=receipt['manifest_sha256']==state.get('before',{}).get('manifest_sha256')
            if not before_saved:issues.append('saved backup receipt differs')
        except (OSError,ValueError,KeyError):issues.append('saved backup is invalid')
    if stage=='awaiting_reinsert' and (not before_saved or state['backup_remaining']!=0 or state['repair_remaining']!=1 or
        state.get('backup_ejected') is not True or any(c['exit_code']!=0 or not c['outputs_present'] for c in commands)):
        issues.append('backup has not completed consistently')
    marker=parse(raw['flag-created.json']) if 'flag-created.json' in raw else None
    if marker is not None:w.require(marker==dict(create_returned_fd=True,simulation=model) and marker['create_returned_fd'] is True and marker['simulation'] is model,'invalid create marker')
    declared=state.get('flag_create_returned_fd')
    w.require(declared is None or type(declared) is bool,'invalid create fact type')
    created=marker is not None or declared is True
    if marker is not None and declared is False:issues.append('create marker and state disagree')
    if stage=='unresolved_no_retry':
        if not (type(state.get('command_pid')) is int and state['command_pid']>0 and state.get('command_left_running') is True and state.get('forced_exit') is False):issues.append('unresolved process evidence missing')
    if stage in ('failed_no_retry','unresolved_no_retry') and not (state.get('actual_card_repaired') is False and
        state.get('automatic_retry') is False and state.get('automatic_rollback') is False and state.get('manual_review_required') is True):issues.append('failure policy differs')
    owner_status='not_checked' if owner_path is None else 'absent'
    if owner_raw is not None:
        value=parse(owner_raw);matches=(value.get('schema')=='A23-context65-flag-card-volume-owner-1' and value.get('job')==plan['job'] and
            value.get('preparation_id')==plan['preparation_id'] and value.get('sd_uuid')==w.card.UUID and value.get('simulation') is model and
            value.get('automatic_release_on_failure') is False)
        owner_status='matches_saved_job' if matches else 'foreign_or_invalid'
        if not matches:issues.append('provided volume owner does not match this job')
    if stage=='complete':
        try:adapter.analyze(job);complete=True
        except (OSError,ValueError,KeyError,TypeError):issues.append('complete job failed static analysis')
    stable=snapshot(job)==raw and (owner_raw==(w.plain(owner_path,16384) if owner_path is not None and owner_path.exists() else None))
    if not stable:issues.append('files changed during inspection; no stable file snapshot')
    classification=('invalid_or_incomplete_input' if issues else
        'prepared_no_disk_phase_claimed' if stage=='planned' else
        'backup_saved_awaiting_reinsert' if stage=='awaiting_reinsert' else
        'supplied_complete_model' if complete and model else 'supplied_complete_physical' if complete else
        'interrupted_or_unresolved_no_retry' if stage in ('unresolved_no_retry','backup_consumed','repair_consumed') else
        'flag_created_not_accepted' if created else 'failed_no_retry')
    return dict(schema='A23-context65-flag-card-inspection-1',stage=stage,simulation=model,classification=classification,
        saved_binding_verified=True,issues=issues,stable_during_inspection=stable,seal=seal,before_saved_and_ejected=before_saved,
        flag_create_recorded=created,complete_supplied_chain_verified=complete,volume_owner=owner_status,
        command_count=len(commands),commands_without_exit=sum(c['exit_code'] is None for c in commands),
        commands_with_nonzero_exit=sum(c['exit_code'] not in (None,0) for c in commands),commands=commands,
        process_liveness_checked=False,media_state_checked=False,physical_run_authenticated=False,
        automatic_unlock_authorized=False,retry_authorized=False,test_authorized=False,remaining=0,
        file_hashes={n:w.sha(v) for n,v in sorted(raw.items())})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('job',type=Path);parser.add_argument('--owner',type=Path);args=parser.parse_args()
    print(json.dumps(inspect(args.job,args.owner),indent=2))
