"""Pre-retained constructor boundary fixtures; no production process manager."""
from pathlib import Path
from unittest.mock import patch
import argparse
import dis
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile

import a23_preretained_owner as candidate
import audit_a23_spawn_boundary as previous
f,a,BASE=previous.f,previous.a,previous.BASE
seal,sealed,reference=previous.seal,previous.sealed,previous.reference
PARENT='A23-spawn-boundary-closeout-20261022'
PARENT_SUM='7f1d4dd07d4d7e2d08e77bc70fb9087853fbab373c9a5affaf775993c717c24b'
REVIEW_SUM='ecc5b4bb82815eca77b387b82750e5111fa8ac8f688534f57994d795ccbd49f8'
NEW=('tools/a23_preretained_owner.py','tools/audit_a23_preretained_owner.py','tests/test_a23_preretained_owner.py')
CASES=('normal','before-allocation','allocated','before-initialize','after-initialize',
       'before-child-store','before-stream-store','init-return-interrupt','init-return-eio',
       'after-execute-child','pid-before-created-flag','unregistered-model')
ACTUAL={name for name in CASES if name not in ('before-allocation','allocated','before-initialize','unregistered-model')}
UNRESOLVED={'before-initialize','unregistered-model'}
FALSE=previous.FALSE


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    out=previous.sources();f.require(out==w.load(root/'closeout.json')['source_hashes'] and len(out)==569,'prior569 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def runtime():
    cls=candidate.SamplerOwner;capture=list(dis.get_instructions(cls.capture));execute=candidate.POPEN._execute_child
    targets={name:next(i.offset for i in capture if i.opname=='STORE_ATTR' and i.argval==attr)
        for name,attr in (('before-child-store','child'),('before-stream-store','streams'))}
    targets['pid-before-created-flag']=next(i.offset for i in dis.get_instructions(execute) if i.opname=='STORE_ATTR' and i.argval=='_child_created')
    raw=Path(inspect.getsourcefile(candidate.POPEN)).read_bytes()
    return dict(schema='A23-preretained-runtime-1',python_version=sys.version,
        subprocess_source_sha256=f.sha(raw),capture_bytecode_sha256=f.sha(cls.capture.__code__.co_code),
        capture_source_sha256=f.sha(inspect.getsource(cls.capture).encode()),
        execute_child_bytecode_sha256=f.sha(execute.__code__.co_code),opcode_targets=targets),raw


def run_case(name,directory,args,targets):
    owner=candidate.SamplerOwner();original=KeyboardInterrupt('construction interruption')
    real_init=candidate.POPEN.__init__;real_execute=candidate.POPEN._execute_child
    initialized=[];injected=[];actual_created=[]
    def initialize(obj,*a,**kw):
        if name=='unregistered-model':
            # Intentionally no native call; retain unknown rather than infer absent child.
            obj.stdin=obj.stdout=obj.stderr=None
            obj.pid=None;obj.returncode=None
            injected.append('unregistered-model');raise original
        real_init(obj,*a,**kw)
        initialized.append(obj)
        actual_created.append(obj)
        if name=='init-return-interrupt':injected.append('init-return');raise original
        if name=='init-return-eio':injected.append('init-return-eio');raise OSError('injected after successful init')
    def execute(obj,*a,**kw):
        real_execute(obj,*a,**kw)
        if name=='after-execute-child':
            actual_created.append(obj);injected.append('after-execute-child');raise original
    def checkpoint(point):
        match={'before-allocation':'before_allocation','allocated':'allocated','before-initialize':'before_initialize','after-initialize':'after_initialize'}.get(name)
        if point==match:injected.append(point);raise original
    target=targets.get(name)
    code=candidate.POPEN._execute_child.__code__ if name=='pid-before-created-flag' else candidate.SamplerOwner.capture.__code__
    def trace(frame,event,arg):
        if frame.f_code is code:
            frame.f_trace_opcodes=True
            if event=='opcode' and frame.f_lasti==target and not injected:
                injected.append('opcode')
                if name=='pid-before-created-flag':actual_created.append(frame.f_locals['self'])
                raise original
        return trace
    f.require(sys.gettrace() is None,'unoccupied trace hook required')
    caught=None;result=None
    try:
        with patch.object(candidate.POPEN,'__init__',new=initialize),patch.object(candidate.POPEN,'_execute_child',new=execute):
            if target is not None:sys.settrace(trace)
            try:result=owner.capture(directory,*args[:2],timeout=4.0,_checkpoint=checkpoint)
            except KeyboardInterrupt as exc:caught=exc
            finally:sys.settrace(None)
        state=owner.observation();before_finish=state
        f.require(caught is original if name not in ('normal','init-return-eio') else caught is None,'constructor primary exception differs')
        actual=list({id(c):c for c in actual_created}.values())
        f.require(len(actual)==(1 if name in ACTUAL else 0),'unexpected actual process count')
        slot=owner._slot.child
        same=bool(actual and slot is actual[0])
        f.require(same is (name in ACTUAL),'actual process object lost from reserved slot')
        # finish must not attempt PID operations for unresolved/never-initialized objects.
        if name not in ACTUAL:
            with patch.object(candidate.POPEN,'terminate',side_effect=AssertionError('unregistered terminate')),patch.object(candidate.POPEN,'kill',side_effect=AssertionError('unregistered kill')),patch.object(candidate.POPEN,'wait',side_effect=AssertionError('unregistered wait')):
                final=owner.finish()
        else:final=owner.finish()
        row=dict(schema='A23-preretained-case-1',name=name,lifecycle=final,pre_finish=before_finish,
            actual_child_count=len(actual),actual_returncodes=[c.returncode for c in actual],
            original_exception_preserved=caught is original if caught is not None else None,
            same_runtime_object_retained=same,object_present=slot is not None,
            child_created_flag=getattr(slot,'_child_created',False) is True,
            actual_open_streams=sum(not stream.closed for c in actual for stream in (c.stdin,c.stdout,c.stderr) if stream is not None),
            injected=injected,accepted=result.lifecycle['accepted'] if result else False,
            outer_rescue_waits=0,task_complete=False,**FALSE)
        validate(row)
        return row,result
    finally:
        sys.settrace(None)
        for child in {id(c):c for c in actual_created}.values():
            if getattr(child,'pid',None) is not None and child.returncode is None:
                child.kill();child.wait(timeout=4)
            for stream in (getattr(child,'stdin',None),getattr(child,'stdout',None),getattr(child,'stderr',None)):
                if stream is not None and not stream.closed:stream.close()


def validate(v):
    name=v['name'];f.require(name in CASES,'unknown preretained case')
    s=v['lifecycle'];actual=name in ACTUAL
    f.require(v['actual_child_count']==int(actual) and v['same_runtime_object_retained'] is actual,'reserved object identity differs')
    f.require(all(type(code) is int for code in v['actual_returncodes']) and len(v['actual_returncodes'])==int(actual),'actual wait codes differ')
    if actual:f.require(s['returncode']==v['actual_returncodes'][0] and (s['returncode']==0 if name=='normal' else s['returncode']!=0),'actual exit outcome differs')
    f.require(s['direct_wait_verified'] is actual and v['actual_open_streams']==0 and v['outer_rescue_waits']==0,'reserved cleanup differs')
    f.require(s['creation_unresolved'] is (name in UNRESOLVED),'unknown construction promoted')
    f.require(s['pid_registered'] is actual,'PID registration differs')
    f.require(s['no_process_started_verified'] is (name in ('before-allocation','allocated')),'pre-start certainty differs')
    expected='creation_unresolved' if name in UNRESOLVED else 'closed'
    f.require(s['owner_status']==expected and s['pending_handle_retained'] is (name in UNRESOLVED),'unresolved object lost')
    f.require(v['accepted'] is (name=='normal') and s['accepted'] is (name=='normal'),'failed constructor accepted')
    if name=='pid-before-created-flag':f.require(v['child_created_flag'] is False and s['direct_wait_verified'] is True,'flag-false PID case missing')
    if name not in ('normal','init-return-eio'):f.require(v['original_exception_preserved'] is True,'primary exception replaced')
    f.require(all(v[k] is False and s[k] is False for k in FALSE) and not v['task_complete'] and not s['task_complete'],'constructor grants authority')
    return v


def semantic(row):
    out={k:v for k,v in row.items() if k!='actual_returncodes'}
    for key in ('lifecycle','pre_finish'):
        out[key]={k:v for k,v in row[key].items() if k not in ('elapsed_seconds','response_size','response_sha256')}
        code=out[key]['returncode']
        if type(code) is int and code!=0:out[key]['returncode']='nonzero_exit'
    out['actual_returncodes']=['nonzero_exit' if type(c) is int and c!=0 else c for c in row['actual_returncodes']]
    return out


def exercise(inputs,output,info):
    output.mkdir(mode=0o700);stage=Path(tempfile.mkdtemp(prefix='a23-preretained-',dir='/private/tmp'))
    args=previous.previous.args_at(inputs/'normal');rows={}
    for name in CASES:
        directory=previous.previous.previous.previous.prepare(stage/name,args[2])
        row,result=run_case(name,directory,args,info['opcode_targets']);rows[name]=semantic(row)
        target=output/'cases'/name;a.put(target,'observation.json',f.encode(row))
        if row['accepted']:
            f.require(result.cache==args[2],'normal reserved sample differs')
            for n,raw in result.cache.items():a.put(target,'captured/'+n,raw)
            a.put(target,'report.json',f.encode(result.report));a.put(target,'classification.json',f.encode(result.classification))
    return dict(passed=True,model_cases=12,actual_child_processes=8,direct_child_waits=8,
        unresolved_construction_controls=2,outer_rescue_waits=0,semantic=rows,staging_directory=str(stage),
        usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,
        authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external reserved review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json');f.require(audit['source_count']==572 and audit['prior_sources_unchanged']==569 and len(audit['source_hashes'])==572,'reserved source count differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'reserved source drift')
    info=f.load(root/'runtime.json');f.require(f.sha(a.read(root/'runtime/subprocess.py'))==info['subprocess_source_sha256'],'Python source differs')
    f.require(set(r['semantic'])==set(CASES),'reserved cases differ')
    for n in CASES:
        row=f.load(root/'work/cases'/n/'observation.json');validate(row);f.require(semantic(row)==r['semantic'][n],'saved reserved semantic differs')
        if n=='normal':
            target=root/'work/cases/normal';args=previous.previous.args_at(root/'inputs/normal')
            files=previous.previous.previous.previous.cache(target/'captured');report=f.load(target/'report.json')
            wire=candidate.prior.encode(dict(schema='A23-terminal-deadline-wire-1',files={name:candidate.prior.base64.b64encode(raw).decode() for name,raw in files.items()},report=report))
            _,_,classified=candidate.prior.decode_response(wire,*args[:2])
            f.require(files==args[2] and classified==f.load(target/'classification.json') and f.sha(wire)==row['pre_finish']['response_sha256'],'saved reserved normal bytes differ')
        else:f.require(not any((root/'work/cases'/n/part).exists() for part in ('captured','report.json','classification.json')),'failed reserved artifacts leaked')
    f.require(r['actual_child_processes']==r['direct_child_waits']==8 and r['outer_rescue_waits']==0 and r['unresolved_construction_controls']==2,'reserved counts differ')
    return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new reserved review required')
    frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'reserved source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,REVIEW_SUM)
    shutil.copytree(review/'inputs/normal',output/'inputs/normal')
    info,raw=runtime();a.put(output,'runtime.json',f.encode(info));a.put(output,'runtime/subprocess.py',raw)
    a.put(output,'runtime/preretained-capture.dis',dis.Bytecode(candidate.SamplerOwner.capture).dis().encode())
    try:r=exercise(output/'inputs',output/'work',info)
    except BaseException as exc:a.put(output,'failure.json',f.encode(dict(error=type(exc).__name__+': '+str(exc))));seal(output);raise
    f.require(sources()==frozen,'reserved source drift after exercise')
    a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=572,prior_sources_unchanged=569,source_hashes=frozen)));seal(output)
    return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=12,actual_child_processes=8)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
