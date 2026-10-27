"""Actual native-return/PID-store SIGINT comparison; current CPython only."""
from pathlib import Path
from unittest.mock import patch
import argparse
import dis
import inspect
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import _posixsubprocess

import a23_sigint_guard_owner as candidate
import audit_a23_preretained_owner as previous
f,a,BASE=previous.f,previous.a,previous.BASE
seal,sealed,reference=previous.seal,previous.sealed,previous.reference
PARENT='A23-preretained-owner-closeout-20261022'
PARENT_SUM='f3c52034ee305300c19233971ab93a03c4a32ca2617230bdf6d7be9219c005cf'
REVIEW_SUM='09240df46bad3fddb9c97dd98cd2b1ef63f29bcf1ffa7f72e4551daee967101b'
NEW=('tools/a23_sigint_guard_owner.py','tools/audit_a23_sigint_guard.py','tests/test_a23_sigint_guard.py')
CASES=('normal','unguarded-sigint-native-return','guarded-sigint-native-return',
       'guarded-process-sigint-native-return','guarded-sigint-pid-store',
       'guarded-synchronous-pid-store','guarded-sigint-before-init',
       'preblocked-sigint','primary-plus-pending-sigint')
UNRESOLVED={'unguarded-sigint-native-return','guarded-synchronous-pid-store','primary-plus-pending-sigint'}
ACCEPTED={'normal','preblocked-sigint'}
FALSE=previous.FALSE


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    out=previous.sources();f.require(out==w.load(root/'closeout.json')['source_hashes'] and len(out)==572,'prior572 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def runtime():
    cls=previous.candidate.POPEN
    target=next(i.offset for i in dis.get_instructions(cls._execute_child) if i.opname=='STORE_ATTR' and i.argval=='pid')
    py=Path(inspect.getsourcefile(cls)).read_bytes();native=Path(_posixsubprocess.__file__).read_bytes()
    return dict(schema='A23-sigint-runtime-1',python_version=sys.version,subprocess_source_sha256=f.sha(py),
        native_binary_sha256=f.sha(native),native_binary_size=len(native),
        execute_child_bytecode_sha256=f.sha(cls._execute_child.__code__.co_code),pid_store_opcode=target,
        vfork_option=bool(subprocess._USE_VFORK),posix_spawn_option=bool(subprocess._USE_POSIX_SPAWN)),py,native


def wait_native_return(pid):
    """Audit only: wait for this process's fresh _fork_exec result, never a file PID."""
    deadline=time.monotonic()+4
    while time.monotonic()<deadline:
        found,status=os.waitpid(pid,os.WNOHANG)
        if found:
            f.require(found==pid,'native child wait identity differs')
            return os.waitstatus_to_exitcode(status)
        time.sleep(0.005)
    # Only a directly observed, not-yet-reaped native child token reaches this fallback.
    # A timeout fails the audit; this path is not evidence of sampler recovery.
    os.kill(pid,signal.SIGKILL)
    os.waitpid(pid,0)
    raise ValueError('audit native-result child exceeded exit deadline')


def run_case(name,directory,args,target):
    f.require(signal.getsignal(signal.SIGINT) is signal.default_int_handler,'default SIGINT handler required')
    baseline=signal.pthread_sigmask(signal.SIG_BLOCK,set())
    f.require(signal.SIGINT not in baseline and signal.SIGINT not in signal.sigpending(),'audit requires initially clear unblocked SIGINT')
    if name=='preblocked-sigint':signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT})
    initial=signal.pthread_sigmask(signal.SIG_BLOCK,set())
    guarded=name!='unguarded-sigint-native-return'
    owner=candidate.SamplerOwner() if guarded else previous.candidate.SamplerOwner()
    fork=subprocess._fork_exec;tokens=[];injected=[];pending_at_injection=[]
    original=KeyboardInterrupt('primary synchronous')
    caught=None;result=None;native_wait_code=None;native_waited=False
    def sigint(kind):
        injected.append(kind)
        if kind=='process-sigint':os.kill(os.getpid(),signal.SIGINT)
        else:signal.raise_signal(signal.SIGINT)
        pending_at_injection.append(signal.SIGINT in signal.sigpending())
    def native(*a,**kw):
        pid=fork(*a,**kw)
        tokens.append(pid)  # Fresh kernel return, owned here; never reconstructed from journal.
        if name in ('unguarded-sigint-native-return','guarded-sigint-native-return','preblocked-sigint'):sigint('native-return-sigint')
        if name=='guarded-process-sigint-native-return':sigint('process-sigint')
        if name=='primary-plus-pending-sigint':
            sigint('native-return-sigint');raise original
        return pid
    execute=previous.candidate.POPEN._execute_child.__code__
    def trace(frame,event,arg):
        if frame.f_code is execute:
            frame.f_trace_opcodes=True
            if event=='opcode' and frame.f_lasti==target and not injected:
                if name=='guarded-synchronous-pid-store':injected.append('direct-python-exception');raise original
                sigint('pid-store-sigint')
        return trace
    def checkpoint(point):
        if name=='guarded-sigint-before-init' and point=='before_initialize':sigint('before-init-sigint')
    f.require(sys.gettrace() is None,'unoccupied trace hook required')
    try:
        with patch.object(subprocess,'_fork_exec',new=native):
            if name in ('guarded-sigint-pid-store','guarded-synchronous-pid-store'):sys.settrace(trace)
            try:result=owner.capture(directory,*args[:2],timeout=4.0,_checkpoint=checkpoint)
            except KeyboardInterrupt as exc:caught=exc
            finally:sys.settrace(None)
        f.require(len(tokens)==1,'expected one actual _fork_exec child')
        state=owner.observation()
        current=signal.pthread_sigmask(signal.SIG_BLOCK,set())
        f.require(current==initial,'constructor changed original mask')
        pending=signal.SIGINT in signal.sigpending()
        if name in UNRESOLVED:
            # The candidate remains unresolved. Audit owns only the fresh native-return token.
            native_wait_code=wait_native_return(tokens[0]);native_waited=True
        final=owner.finish()
        code=native_wait_code if native_waited else final['returncode']
        row=dict(schema='A23-sigint-case-1',name=name,guarded=guarded,lifecycle=final,
            actual_native_calls=1,actual_child_count=1,native_return_token_waited=native_waited,
            native_return_waitcode=native_wait_code,actual_exitcode=code,
            candidate_direct_wait=final['direct_wait_verified'],candidate_pid_registered=final['pid_registered'],
            exception_type=None if caught is None else type(caught).__name__,
            primary_exception_identity_preserved=(caught is original) if name in ('guarded-synchronous-pid-store','primary-plus-pending-sigint') else None,
            injected=injected,pending_after_injection=pending_at_injection,
            mask_restored_to_original=current==initial,original_mask=[int(v) for v in sorted(initial)],
            pending_sigint_after_capture=pending,accepted=result.lifecycle['accepted'] if result else False,
            actual_open_streams=sum(not stream.closed for stream in owner._slot.streams),
            native_result_token_source='fresh_direct_fork_exec_return',journal_pid_signals=0,
            task_complete=False,**FALSE)
        validate(row)
        return row,result
    finally:
        sys.settrace(None)
        # The preblocked control preserves its signal. Only this audit consumes its own test signal.
        current=signal.pthread_sigmask(signal.SIG_BLOCK,set())
        if signal.SIGINT in signal.sigpending():
            signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT})
            signal.sigwait({signal.SIGINT})
        signal.pthread_sigmask(signal.SIG_SETMASK,baseline)
        for pid in tokens:
            if not native_waited and not owner.observation()['direct_wait_verified']:
                wait_native_return(pid)


def validate(v):
    name=v['name'];f.require(name in CASES,'unknown SIGINT case');s=v['lifecycle'];unknown=name in UNRESOLVED
    f.require(v['actual_native_calls']==v['actual_child_count']==1 and type(v['actual_exitcode']) is int,'SIGINT child inventory differs')
    f.require(v['candidate_direct_wait'] is (not unknown) and s['direct_wait_verified'] is (not unknown),'candidate wait differs')
    f.require(v['native_return_token_waited'] is unknown and v['candidate_pid_registered'] is (not unknown),'native-result rescue differs')
    f.require(s['creation_unresolved'] is unknown,'signal/synchronous boundary promoted')
    f.require(v['accepted'] is (name in ACCEPTED) and s['accepted'] is (name in ACCEPTED),'SIGINT acceptance differs')
    f.require(v['actual_exitcode']==0 if name in ACCEPTED else v['actual_exitcode']!=0,'SIGINT exit result differs')
    f.require(v['exception_type']==(None if name in ACCEPTED else 'KeyboardInterrupt'),'SIGINT propagation differs')
    f.require(v['mask_restored_to_original'] is True and v['pending_sigint_after_capture'] is (name=='preblocked-sigint'),'signal mask/pending state changed')
    f.require(v['actual_open_streams']==0 and v['journal_pid_signals']==0 and v['native_result_token_source']=='fresh_direct_fork_exec_return','signal cleanup scope differs')
    if v['guarded']:f.require(s['mask_installed'] and s['mask_restore_verified'],'guard restoration unverified')
    if name in ('guarded-synchronous-pid-store','primary-plus-pending-sigint'):f.require(v['primary_exception_identity_preserved'] is True,'primary replaced by restore interrupt')
    if name=='primary-plus-pending-sigint':f.require('KeyboardInterrupt' in s['mask_restore_exceptions'],'second restore interrupt missing')
    f.require(all(v[k] is False and s[k] is False for k in FALSE) and not v['task_complete'],'SIGINT grants production authority')
    return v


def semantic(row):
    out={k:v for k,v in row.items() if k not in ('actual_exitcode','native_return_waitcode')}
    out['lifecycle']={k:v for k,v in row['lifecycle'].items() if k not in ('elapsed_seconds','response_size','response_sha256')}
    for key in ('actual_exitcode','native_return_waitcode'):
        value=row[key];out[key]='nonzero_exit' if type(value) is int and value!=0 else value
    value=out['lifecycle']['returncode']
    if type(value) is int and value!=0:out['lifecycle']['returncode']='nonzero_exit'
    return out


def exercise(inputs,output,info):
    output.mkdir(mode=0o700);stage=Path(tempfile.mkdtemp(prefix='a23-sigint-',dir='/private/tmp'))
    args=previous.previous.previous.args_at(inputs/'normal');rows={}
    for name in CASES:
        directory=previous.previous.previous.previous.previous.prepare(stage/name,args[2])
        row,result=run_case(name,directory,args,info['pid_store_opcode']);rows[name]=semantic(row)
        target=output/'cases'/name;a.put(target,'observation.json',f.encode(row))
        if row['accepted']:
            f.require(result.cache==args[2],'signal guarded bytes differ')
            for n,raw in result.cache.items():a.put(target,'captured/'+n,raw)
            a.put(target,'report.json',f.encode(result.report));a.put(target,'classification.json',f.encode(result.classification))
    return dict(passed=True,model_cases=9,actual_child_processes=9,candidate_direct_waits=6,
        audit_native_return_waits=3,all_direct_creator_waits=9,semantic=rows,staging_directory=str(stage),
        usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,
        authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external SIGINT review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json');f.require(audit['source_count']==575 and audit['prior_sources_unchanged']==572 and len(audit['source_hashes'])==575,'SIGINT source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'SIGINT source differs')
    info=f.load(root/'runtime.json')
    f.require(f.sha(a.read(root/'runtime/subprocess.py'))==info['subprocess_source_sha256'] and f.sha(a.read(root/'runtime/posixsubprocess.bin'))==info['native_binary_sha256'],'SIGINT runtime differs')
    f.require(set(r['semantic'])==set(CASES),'SIGINT cases differ')
    args=previous.previous.previous.args_at(root/'inputs/normal')
    for n in CASES:
        target=root/'work/cases'/n;row=f.load(target/'observation.json');validate(row);f.require(semantic(row)==r['semantic'][n],'saved SIGINT semantic differs')
        if row['accepted']:
            files=previous.previous.previous.previous.previous.cache(target/'captured');report=f.load(target/'report.json')
            wire=candidate.prior.encode(dict(schema='A23-terminal-deadline-wire-1',files={name:candidate.prior.base64.b64encode(raw).decode() for name,raw in files.items()},report=report))
            _,_,classified=candidate.prior.decode_response(wire,*args[:2])
            f.require(files==args[2] and classified==f.load(target/'classification.json') and f.sha(wire)==row['lifecycle']['response_sha256'],'SIGINT cached bytes differ')
        else:f.require(not any((target/part).exists() for part in ('captured','report.json','classification.json')),'SIGINT failure leaked artifacts')
    f.require(r['candidate_direct_waits']==6 and r['audit_native_return_waits']==3 and r['all_direct_creator_waits']==r['actual_child_processes']==9,'SIGINT wait totals differ')
    return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new SIGINT review required')
    frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'SIGINT source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,REVIEW_SUM)
    shutil.copytree(review/'inputs/normal',output/'inputs/normal');info,py,native=runtime()
    a.put(output,'runtime.json',f.encode(info));a.put(output,'runtime/subprocess.py',py);a.put(output,'runtime/posixsubprocess.bin',native)
    a.put(output,'runtime/execute-child.dis',dis.Bytecode(previous.candidate.POPEN._execute_child).dis().encode())
    try:r=exercise(output/'inputs',output/'work',info)
    except BaseException as exc:a.put(output,'failure.json',f.encode(dict(error=type(exc).__name__+': '+str(exc))));seal(output);raise
    f.require(sources()==frozen,'SIGINT source drift after exercise')
    a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=575,prior_sources_unchanged=572,source_hashes=frozen)));seal(output)
    return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=9,actual_child_processes=9)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
