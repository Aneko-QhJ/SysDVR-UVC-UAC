"""Pinned local Python spawn boundary audit and direct-owner topology comparison."""
from pathlib import Path
from unittest.mock import patch
import argparse
import dis
import inspect
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time

import a23_spawn_boundary_owner as repaired
import audit_a23_terminal_owner as previous
f, a, BASE = previous.f, previous.a, previous.BASE
seal, sealed, reference = previous.seal, previous.sealed, previous.reference
PARENT = 'A23-terminal-owner-closeout-20261022'
PARENT_SUM = '6f4594a19da17ec52735168db934b8d15e5b7907cb45558dc483b6de1782f530'
REVIEW_SUM = '76fbed18699e1bae5f8055db82e0f838acd785bf46356dc4dac9532f998d409f'
NEW = ('tools/a23_spawn_boundary_owner.py', 'tests/a23_spawn_boundary_actor.py',
       'tools/audit_a23_spawn_boundary.py', 'tests/test_a23_spawn_boundary.py')
GAPS = ('before-call', 'constructor-return', 'before-child-store', 'before-stream-store',
        'before-spawn-flag', 'after-spawn', 'repaired-stream-store')
TOPOLOGY = ('normal', 'before-request', 'after-request', 'before-owner', 'partial-owner',
            'after-owner', 'during-read', 'after-validation', 'after-worker-wait')
FALSE = previous.candidate.prior.intake.recovery.FALSE


def sources():
    import audit_a23_pinned_view as old
    w = old.w
    root = w.A / PARENT
    w.card.seal_verify(root)
    f.require(f.sha(w.plain(root / 'SHA256SUMS')) == PARENT_SUM, 'parent pin differs')
    out = previous.sources()
    f.require(out == w.load(root / 'closeout.json')['source_hashes'] and len(out) == 565, 'prior565 drift')
    for n in NEW:
        key = BASE + n
        f.require(key not in out, 'source overlap')
        out[key] = f.sha(w.plain(w.ROOT / n))
    return dict(sorted(out.items()))


def runtime():
    owner = previous.candidate.SamplerOwner
    instructions = list(dis.get_instructions(owner.capture))
    targets = {name: next(i.offset for i in instructions if i.opname == 'STORE_ATTR' and i.argval == attr)
               for name, attr in (('before-child-store','child'),('before-stream-store','streams'))}
    lines, start = inspect.getsourcelines(owner.capture)
    flag_line = start + next(i for i, line in enumerate(lines) if "state['spawned'] = True" in line)
    targets['before-spawn-flag'] = next(i.offset for i in instructions if i.opname == 'STORE_SUBSCR' and i.positions.lineno == flag_line)
    source = Path(inspect.getsourcefile(subprocess.Popen)).read_bytes()
    return dict(schema='A23-spawn-boundary-runtime-1', python_version=sys.version,
        implementation=sys.implementation.name, subprocess_source_sha256=f.sha(source),
        owner_capture_source_sha256=f.sha(inspect.getsource(owner.capture).encode()),
        opcode_targets=targets, bytecode_sha256=f.sha(owner.capture.__code__.co_code)), source


def gap_case(name, directory, args, targets):
    module = previous.candidate
    owner = repaired.SamplerOwner() if name == 'repaired-stream-store' else module.SamplerOwner()
    real_popen = subprocess.Popen
    children = []
    original = KeyboardInterrupt('spawn boundary')
    traced = []
    def popen(*values, **kw):
        if name == 'before-call':
            raise original
        child = real_popen(*values, **kw)
        children.append(child)  # Trusted outer owner; permits cleanup of negative controls.
        if name == 'constructor-return':
            raise original
        return child
    point = 'before-stream-store' if name == 'repaired-stream-store' else name
    target = targets.get(point)
    def trace(frame, event, value):
        if frame.f_code is module.SamplerOwner.capture.__code__:
            frame.f_trace_opcodes = True
            if event == 'opcode' and frame.f_lasti == target and not traced:
                traced.append(frame.f_lasti)
                raise original
        return trace
    def checkpoint(phase):
        if name == 'after-spawn' and phase == 'after_spawn':
            raise original
    f.require(sys.gettrace() is None, 'audit needs unoccupied trace hook')
    caught = None
    try:
        with patch.object(subprocess, 'Popen', side_effect=popen):
            if target is not None:
                sys.settrace(trace)
            try:
                owner.capture(directory, *args[:2], timeout=4.0, _checkpoint=checkpoint)
            except KeyboardInterrupt as exc:
                caught = exc
            finally:
                sys.settrace(None)
        f.require(caught is original, 'spawn exception identity changed')
        observation = owner.observation()
        stream_open = sum(not stream.closed for c in children for stream in (c.stdin,c.stdout) if stream is not None)
        owner_wait = bool(observation['direct_wait_verified'])
        rescue_wait = 0
        for child in children:
            if not owner_wait:
                child.terminate()
                child.wait(timeout=3)
                rescue_wait += 1
            for stream in (child.stdin, child.stdout):
                if stream is not None and not stream.closed:
                    stream.close()
        row = dict(schema='A23-spawn-gap-case-1', name=name, spawned=len(children),
            owner_slot_present=owner._slot.child is not None, owner_reported_spawned=observation['spawned'],
            owner_direct_wait=owner_wait, owner_reported_pending_streams=observation['pending_streams'],
            actual_open_streams_before_outer_cleanup=stream_open, outer_rescue_waits=rescue_wait,
            actual_returncodes=[c.returncode for c in children], exception_identity_preserved=True,
            opcode_hook_fired=bool(traced), target_opcode=target,
            false_closed_observation=(observation['owner_status']=='closed' and (stream_open>0 or bool(children) and not owner_wait)),
            repaired=name=='repaired-stream-store', task_complete=False, **FALSE)
        validate_gap(row)
        return row
    finally:
        sys.settrace(None)
        for child in children:
            if child.returncode is None:
                child.kill();child.wait(timeout=3)
            for stream in (child.stdin,child.stdout):
                if stream is not None and not stream.closed:stream.close()


def validate_gap(v):
    name = v['name']
    f.require(name in GAPS and v['exception_identity_preserved'] is True, 'gap shape differs')
    f.require(v['spawned'] == (0 if name=='before-call' else 1), 'gap child count differs')
    lost = name in ('constructor-return','before-child-store')
    f.require(v['owner_slot_present'] is (v['spawned']==1 and not lost), 'retained slot claim differs')
    f.require(v['owner_direct_wait'] is (v['spawned']==1 and not lost) and v['outer_rescue_waits']==int(lost), 'gap wait boundary differs')
    open_streams = name in ('constructor-return','before-child-store','before-stream-store')
    f.require(v['actual_open_streams_before_outer_cleanup']==(2 if open_streams else 0), 'gap stream closure differs')
    f.require(v['false_closed_observation'] is open_streams, 'gap observation counterexample missing')
    f.require(v['opcode_hook_fired'] is (v['target_opcode'] is not None), 'opcode hook missing')
    f.require(all(v[k] is False for k in FALSE) and not v['task_complete'], 'gap grants authority')
    return v


def line(fd, timeout=4):
    raw=bytearray();deadline=time.monotonic()+timeout
    while not raw.endswith(b'\n'):
        left=deadline-time.monotonic();f.require(left>0,'fixture line deadline')
        ready,_,_=select.select([fd],[],[],left);f.require(ready,'fixture line timeout')
        block=os.read(fd,1)
        if not block:break
        raw.extend(block);f.require(len(raw)<=64,'fixture line limit')
    return bytes(raw)


def topology_case(name, directory, args):
    script=Path(__file__).resolve().parents[1]/'tests/a23_spawn_boundary_actor.py'
    life_r,life_w=os.pipe();gate_r,gate_w=os.pipe();status_r,status_w=os.pipe()
    requester=worker=None;events=[];wire=b'';record=None
    def mark(event):events.append(event)
    def exit_requester():
        requester.stdin.write(b'X');requester.stdin.flush()
        f.require(requester.wait(timeout=4)==79,'requester crash code differs');mark('requester_wait79')
    try:
        requester=subprocess.Popen([sys.executable,'-B',str(script),'requester',name,str(life_w)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0,pass_fds=(life_w,))
        os.close(life_w);life_w=None
        request=line(requester.stdout.fileno())
        if name=='before-request':
            f.require(not request and requester.wait(timeout=4)==79,'unexpected early request');mark('requester_wait79')
        else:
            f.require(request==b'request\n','request missing');mark('request')
            if name=='after-request':exit_requester()
            else:
                pause='after_open' if name=='during-read' else 'validated' if name=='after-validation' else '-'
                worker=subprocess.Popen([sys.executable,'-B',str(script),'sampler',str(life_r),str(gate_r),str(status_w),pause],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,pass_fds=(life_r,gate_r,status_w))
                mark('worker_handle_retained')
                for fd in (life_r,gate_r,status_w):os.close(fd)
                life_r=gate_r=status_w=None
                f.require(line(status_r)==b'ready\n','worker readiness differs');mark('worker_ready')
                # A deliberately non-authoritative local record can be absent, partial or complete.
                record=b'{"fixture_owner_record":true}'
                if name=='before-owner':record=None
                if name=='partial-owner':record=record[:len(record)//2]
                if record is not None:(directory.parent/'owner-record.bin').write_bytes(record);mark('owner_record_observed')
                request_wire=previous.candidate.prior.encode(dict(directory=str(directory),anchor=previous.candidate.prior.base64.b64encode(args[0]).decode(),pin=args[1]))
                worker.stdin.write(request_wire);worker.stdin.close()
                if name in ('before-owner','partial-owner','after-owner'):exit_requester()
                os.write(gate_w,b'R');mark('gate_released')
                if name in ('during-read','after-validation'):
                    f.require(line(status_r)==b'checkpoint\n','worker checkpoint missing');mark('worker_checkpoint')
                    exit_requester();os.write(gate_w,b'R')
                end=line(status_r)
                f.require(end in (b'end0\n',b'end86\n'),'worker ending differs');mark(end.decode().strip())
                # stdin has already been closed; communicate must not flush a closed stream.
                worker.stdin=None
                wire,stderr=worker.communicate(timeout=4)
                f.require(not stderr and len(wire)<=previous.candidate.prior.MAX_RESPONSE,'worker output bound differs')
                mark('worker_wait'+str(worker.returncode))
                if name=='after-worker-wait':exit_requester()
                if name=='normal':
                    requester.stdin.write(b'Q');requester.stdin.flush()
                    f.require(requester.wait(timeout=4)==0,'normal requester failed');mark('requester_wait0')
        row=dict(schema='A23-spawn-topology-case-1',name=name,events=events,
            requester_created=True,requester_direct_wait=True,requester_returncode=requester.returncode,
            worker_created=worker is not None,worker_direct_wait=worker is not None,
            worker_returncode=worker.returncode if worker is not None else None,
            worker_wire_size=len(wire),worker_wire_sha256=f.sha(wire),
            record_state='absent' if record is None else 'partial' if name=='partial-owner' else 'complete',
            diagnostic_model_complete=name=='normal',sample_cache_accepted=name=='normal',
            task_complete=False,journal_pid_signals=0,**FALSE)
        classified=None
        if wire:
            files,report,classified=previous.candidate.prior.decode_response(wire,*args[:2])
            f.require(files==args[2],'topology sampled bytes differ')
        validate_topology(row,wire)
        return row,wire,classified
    finally:
        for fd in (life_r,life_w,gate_r,gate_w,status_r,status_w):
            if fd is not None:os.close(fd)
        for process in (requester,worker):
            if process is not None:
                if process.returncode is None:
                    process.kill();process.wait(timeout=4)
                for stream in (process.stdin,process.stdout,process.stderr):
                    if stream is not None and not stream.closed:stream.close()


def validate_topology(v,wire):
    name=v['name'];f.require(name in TOPOLOGY,'unknown topology')
    f.require(type(v['requester_returncode']) is int and (v['worker_returncode'] is None or type(v['worker_returncode']) is int),'non-integer exit code')
    worker=name not in ('before-request','after-request')
    f.require(v['requester_direct_wait'] is True and v['requester_returncode']==(0 if name=='normal' else 79),'requester wait differs')
    f.require(v['worker_created'] is worker and v['worker_direct_wait'] is worker,'topology worker wait differs')
    full=name in ('normal','after-worker-wait')
    f.require(v['worker_returncode']==(0 if full else 86 if worker else None),'topology worker exit differs')
    f.require(bool(wire) is full and len(wire)==v['worker_wire_size'] and f.sha(wire)==v['worker_wire_sha256'],'wire evidence differs')
    f.require(v['diagnostic_model_complete'] is (name=='normal') and v['sample_cache_accepted'] is (name=='normal'),'requester death promoted sample')
    f.require(all(v[k] is False for k in FALSE) and v['task_complete'] is False and v['journal_pid_signals']==0,'topology grants authority')
    return v


def semantic_gap(row):
    out=dict(row);out['actual_returncodes']=['signal' if c<0 else c for c in row['actual_returncodes']];return out


def semantic_topology(row):
    # The wire contains per-directory inode/time observations, retained in raw evidence.
    return {k:v for k,v in row.items() if k not in ('worker_wire_size','worker_wire_sha256')}


def exercise(inputs,output,runtime_info):
    output.mkdir(mode=0o700);stage=Path(tempfile.mkdtemp(prefix='a23-spawn-boundary-',dir='/private/tmp'))
    args=previous.args_at(inputs/'normal');gaps={};topology={}
    for name in GAPS:
        directory=previous.previous.previous.prepare(stage/'gap'/name,args[2])
        row=gap_case(name,directory,args,runtime_info['opcode_targets']);gaps[name]=semantic_gap(row)
        a.put(output/'gap'/name,'observation.json',f.encode(row))
    for name in TOPOLOGY:
        directory=previous.previous.previous.prepare(stage/'topology'/name,args[2])
        row,wire,classified=topology_case(name,directory,args);topology[name]=semantic_topology(row)
        a.put(output/'topology'/name,'observation.json',f.encode(row));a.put(output/'topology'/name,'worker-wire.bin',wire)
        owner_record=directory.parent/'owner-record.bin'
        if owner_record.exists():a.put(output/'topology'/name,'owner-record.bin',a.read(owner_record))
        if classified is not None:a.put(output/'topology'/name,'wire-classification.json',f.encode(classified))
    return dict(passed=True,model_cases=16,spawn_gap_cases=7,topology_cases=9,
        actual_child_processes=22,direct_child_waits=22,gap_outer_rescue_waits=2,
        gap_owner_waits=4,requester_waits=9,topology_worker_waits=7,
        semantic=dict(gaps=gaps,topology=topology),staging_directory=str(stage),
        usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,
        authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external spawn review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json')
    f.require(audit['source_count']==569 and audit['prior_sources_unchanged']==565 and len(audit['source_hashes'])==569,'spawn source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'spawn frozen source differs')
    runtime_info=f.load(root/'runtime.json');f.require(f.sha(a.read(root/'runtime/subprocess.py'))==runtime_info['subprocess_source_sha256'],'Python source drift')
    f.require(set(r['semantic']['gaps'])==set(GAPS) and set(r['semantic']['topology'])==set(TOPOLOGY),'spawn case inventory differs')
    for n in GAPS:
        row=f.load(root/'work/gap'/n/'observation.json');validate_gap(row)
        f.require(semantic_gap(row)==r['semantic']['gaps'][n],'saved gap verdict differs')
    args=previous.args_at(root/'inputs/normal')
    for n in TOPOLOGY:
        directory=root/'work/topology'/n;row=f.load(directory/'observation.json');wire=a.read(directory/'worker-wire.bin')
        validate_topology(row,wire);f.require(semantic_topology(row)==r['semantic']['topology'][n],'saved topology differs')
        record=directory/'owner-record.bin';expected=b'{"fixture_owner_record":true}'
        if row['record_state']=='absent':f.require(not record.exists(),'unexpected owner record')
        else:f.require(a.read(record)==(expected[:len(expected)//2] if row['record_state']=='partial' else expected),'saved owner record differs')
        if wire:
            files,_,classified=previous.candidate.prior.decode_response(wire,*args[:2])
            f.require(files==args[2] and classified==f.load(directory/'wire-classification.json'),'saved topology bytes differ')
    f.require(r['actual_child_processes']==r['direct_child_waits']==22 and all(r[k] is False for k in FALSE),'spawn totals differ')
    return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new spawn review required')
    frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'spawn source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,REVIEW_SUM)
    shutil.copytree(review/'inputs/jobs/normal',output/'inputs/normal')
    info,python_source=runtime();a.put(output,'runtime.json',f.encode(info));a.put(output,'runtime/subprocess.py',python_source)
    a.put(output,'runtime/owner-capture.dis',dis.Bytecode(previous.candidate.SamplerOwner.capture).dis().encode())
    try:r=exercise(output/'inputs',output/'work',info)
    except BaseException as exc:a.put(output,'failure.json',f.encode(dict(error=type(exc).__name__+': '+str(exc))));seal(output);raise
    f.require(sources()==frozen,'spawn source drift after exercise')
    a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=569,prior_sources_unchanged=565,source_hashes=frozen)));seal(output)
    return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=16,actual_child_processes=22)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
