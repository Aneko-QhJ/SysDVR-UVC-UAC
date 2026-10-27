"""Offline child mask/handler restoration and ready-gated termination fixtures."""
from pathlib import Path
import argparse
import json
import os
import shutil
import signal
import sys
import tempfile

import a23_child_signal_owner as candidate
import audit_a23_sigint_guard as previous
import audit_a23_terminal_intake as intake_audit
import audit_a23_terminal_recovery as recovery_audit
f,a,BASE=previous.f,previous.a,previous.BASE
seal,sealed,reference=previous.seal,previous.sealed,previous.reference
FALSE=previous.FALSE
PARENT='A23-sigint-guard-closeout-20261022'
PARENT_SUM='8c36635d5fc550abb65a9611ef939ffd04f6c07c99fd0ebc7966d97d80a11e3a'
REVIEW_SUM='5176f730edda62eddb851c99c00bf28a126ee52caf7b86864149179b50218305'
NEW=('tools/a23_child_signal_bootstrap.py','tools/a23_child_signal_owner.py','tools/audit_a23_child_signal.py','tests/test_a23_child_signal.py')
CASES=('normal','preblocked-int','preblocked-int-pending','before-reset-int','before-reset-term',
    'after-reset-int','after-reset-term','ready-int','ready-term','ignored-term-then-ready-term',
    'timeout-default-term','timeout-blocked-term','bad-token','bad-mask','bad-handler','partial-ready',
    'oversized-ready','exit-before-ready','stall-before-ready','reset-error')
ACCEPTED={'normal','preblocked-int','preblocked-int-pending'}
CONFIRMED=ACCEPTED|{'ready-int','ready-term','ignored-term-then-ready-term','timeout-default-term','timeout-blocked-term'}
MODES={'preblocked-int-pending':'before_reset','before-reset-int':'before_reset','before-reset-term':'before_reset',
    'after-reset-int':'after_reset','after-reset-term':'after_reset','ignored-term-then-ready-term':'before_reset',
    'timeout-default-term':'stall_after_ready','timeout-blocked-term':'stall_after_ready'}


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    out=previous.sources();f.require(out==w.load(root/'closeout.json')['source_hashes'] and len(out)==575,'prior575 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def run_case(name,directory,args):
    baseline=signal.pthread_sigmask(signal.SIG_BLOCK,set());term=signal.getsignal(signal.SIGTERM)
    f.require(not baseline and term==signal.SIG_DFL and not signal.sigpending(),'clear baseline signal policy required')
    events=[];owner=None
    def checkpoint(phase,child):
        events.append(phase)
        if phase in ('before_reset','after_reset'):
            if name in ('preblocked-int-pending','before-reset-int','after-reset-int'):child.send_signal(signal.SIGINT)
            if name in ('before-reset-term','after-reset-term','ignored-term-then-ready-term'):child.send_signal(signal.SIGTERM)
            if name in ('before-reset-term','after-reset-int','after-reset-term'):owner._wait(3.0)
            return name not in ('before-reset-term','after-reset-int','after-reset-term')
        if phase=='gate_released_before_reset' and name=='before-reset-int':owner._wait(3.0)
        if phase=='ready_validated' and name in ('ready-int','ready-term','ignored-term-then-ready-term'):
            child.send_signal(signal.SIGINT if name=='ready-int' else signal.SIGTERM)
            owner._wait(3.0)  # Actual retained-owner wait; never journal PID or external waitpid.
    try:
        if name in ('preblocked-int','preblocked-int-pending'):signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT})
        if name=='timeout-blocked-term':signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM})
        if name=='ignored-term-then-ready-term':signal.signal(signal.SIGTERM,signal.SIG_IGN)
        initial=signal.pthread_sigmask(signal.SIG_BLOCK,set())
        mode=MODES.get(name,name.replace('-','_') if name in {'bad-token','bad-mask','bad-handler','partial-ready','oversized-ready','exit-before-ready','stall-before-ready','reset-error'} else 'normal')
        owner=candidate.SamplerOwner(_fixture_mode=mode,_startup_checkpoint=checkpoint,cleanup_grace=0.15,startup_timeout=0.8)
        result=owner.capture(directory,*args[:2],timeout=1.2 if name.startswith('timeout-') else 4.0)
        state=owner.finish();current=signal.pthread_sigmask(signal.SIG_BLOCK,set())
        row=dict(schema='A23-child-signal-case-1',name=name,lifecycle=state,actual_child_count=1,
            candidate_direct_wait=state['direct_wait_verified'],actual_exitcode=state['returncode'],
            accepted=result.lifecycle['accepted'],events=events,original_mask=sorted(int(v) for v in initial),
            parent_mask_restored=current==initial,parent_term_handler_preserved=signal.getsignal(signal.SIGTERM)==(signal.SIG_IGN if name=='ignored-term-then-ready-term' else term),
            parent_pending_signals=sorted(int(v) for v in signal.sigpending()),
            actual_open_streams=sum(not stream.closed for stream in owner._slot.streams),
            journal_pid_signals=0,task_complete=False,**FALSE)
        return row,result,owner.policy,owner.policy_report,owner.policy_wire
    finally:
        if owner is not None and not owner.observation()['direct_wait_verified']:owner.finish()
        signal.signal(signal.SIGTERM,term);signal.pthread_sigmask(signal.SIG_SETMASK,baseline)


def validate(v):
    n=v['name'];s=v['lifecycle'];f.require(n in CASES and v['schema']=='A23-child-signal-case-1','child signal case')
    f.require(type(v['actual_child_count']) is int and v['actual_child_count']==1 and type(v['actual_exitcode']) is int,'child inventory')
    f.require(v['candidate_direct_wait'] is True and s['direct_wait_verified'] is True and s['returncode']==v['actual_exitcode'],'child not directly waited')
    f.require(v['accepted'] is (n in ACCEPTED) and s['accepted'] is (n in ACCEPTED),'child acceptance')
    f.require(v['actual_exitcode']==0 if n in ACCEPTED else v['actual_exitcode']!=0,'child exitcode')
    f.require(s['child_policy_confirmed'] is (n in CONFIRMED),'child ready confirmation')
    f.require(v['parent_mask_restored'] is True and v['parent_term_handler_preserved'] is True and v['parent_pending_signals']==[],'parent signal state')
    f.require(v['actual_open_streams']==0 and s['policy_fd_count']==0 and s['policy_fd_close_uncertain']==0,'child stream leak')
    f.require(s['pid_registered'] is True and s['creation_unresolved'] is False and s['mask_restore_verified'] is True,'registered owner state')
    f.require(s['child_ready_deadline_expired'] is (n=='stall-before-ready'),'startup deadline')
    if n=='timeout-blocked-term':f.require(s.get('kill_attempts',0)==1 and v['actual_exitcode']==-int(signal.SIGKILL),'blocked TERM needs KILL')
    if n=='timeout-default-term':f.require(s.get('kill_attempts',0)==0 and v['actual_exitcode']==-int(signal.SIGTERM),'default TERM failed')
    if n in ('ready-term','ignored-term-then-ready-term','before-reset-term','after-reset-term'):f.require(v['actual_exitcode']==-int(signal.SIGTERM),'TERM phase')
    if n in ('ready-int','before-reset-int','after-reset-int'):f.require(v['actual_exitcode']==130,'INT phase')
    f.require(v['journal_pid_signals']==0 and v['task_complete'] is False and all(v[k] is False and s[k] is False for k in FALSE),'authority promoted')
    return v


def semantic(row):
    out={k:v for k,v in row.items() if k!='actual_exitcode'}
    out['lifecycle']={k:v for k,v in row['lifecycle'].items() if k not in ('elapsed_seconds','response_size','response_sha256')}
    # Early EOF versus process exit can race cleanup TERM; keep raw codes in observation.
    for obj,key in ((out,'actual_exitcode'),(out['lifecycle'],'returncode')):
        value=row['actual_exitcode'];obj[key]='early_nonzero' if row['name'] in ('exit-before-ready','reset-error') else value
    return out


def exercise(inputs,output,info):
    output.mkdir(mode=0o700);stage=Path(tempfile.mkdtemp(prefix='a23-child-signal-',dir='/private/tmp'))
    args=recovery_audit.args_at(inputs/'normal');rows={}
    for name in CASES:
        directory=intake_audit.prepare(stage/name,args[2])
        row,result,policy,report,wire=run_case(name,directory,args);rows[name]=semantic(row)
        target=output/'cases'/name
        for n,v in (('observation.json',row),('policy.json',policy),('ready.json',report)):a.put(target,n,f.encode(v))
        a.put(target,'ready.wire',wire);validate(row)
        if row['accepted']:
            f.require(result.cache==args[2],'child signal captured bytes differ')
            for n,raw in result.cache.items():a.put(target,'captured/'+n,raw)
            a.put(target,'report.json',f.encode(result.report));a.put(target,'classification.json',f.encode(result.classification))
    return dict(passed=True,model_cases=20,actual_child_processes=20,candidate_direct_waits=20,
        all_direct_creator_waits=20,semantic=rows,staging_directory=str(stage),usb_requests=0,sd_accesses=0,
        formal_records=0,formal_reservations=0,authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external child signal review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json')
    f.require(audit['source_count']==579 and audit['prior_sources_unchanged']==575 and len(audit['source_hashes'])==579,'child signal source inventory')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'child signal source differs')
    info=f.load(root/'runtime.json')
    f.require(f.sha(a.read(root/'runtime/subprocess.py'))==info['subprocess_source_sha256'] and f.sha(a.read(root/'runtime/posixsubprocess.bin'))==info['native_binary_sha256'],'runtime differs')
    f.require(set(r['semantic'])==set(CASES),'child signal cases')
    args=recovery_audit.args_at(root/'inputs/normal')
    for n in CASES:
        target=root/'work/cases'/n;row=f.load(target/'observation.json');validate(row)
        f.require(semantic(row)==r['semantic'][n],'child signal saved semantic')
        policy=f.load(target/'policy.json');report=f.load(target/'ready.json');wire=a.read(target/'ready.wire')
        f.require(policy['target_mask']==row['original_mask'] and policy['mode']==MODES.get(n,n.replace('-','_') if n in {'bad-token','bad-mask','bad-handler','partial-ready','oversized-ready','exit-before-ready','stall-before-ready','reset-error'} else 'normal'),'saved child policy')
        if row['lifecycle']['child_policy_confirmed']:
            candidate.validate_report(policy,report);f.require(f.encode(report)==wire.splitlines(keepends=True)[-1],'ready wire differs')
            f.require(report['pending_sigint_before_reset'] is (n=='preblocked-int-pending'),'pending child INT')
            if n=='ignored-term-then-ready-term':f.require(report['sigterm_before']=='SIG_IGN','ignored TERM not inherited')
        else:f.require(report is None,'unconfirmed child policy report')
        if row['accepted']:
            files=intake_audit.cache(target/'captured');saved=f.load(target/'report.json')
            response=candidate.prior.encode(dict(schema='A23-terminal-deadline-wire-1',files={name:candidate.prior.base64.b64encode(raw).decode() for name,raw in files.items()},report=saved))
            _,_,classified=candidate.prior.decode_response(response,*args[:2])
            f.require(files==args[2] and classified==f.load(target/'classification.json') and f.sha(response)==row['lifecycle']['response_sha256'],'child signal sample bytes')
        else:f.require(not any((target/part).exists() for part in ('captured','report.json','classification.json')),'failure leaked sample')
    f.require(r['candidate_direct_waits']==r['all_direct_creator_waits']==r['actual_child_processes']==r['model_cases']==20,'child signal wait total')
    return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new child signal review required')
    frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'child signal source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,REVIEW_SUM)
    shutil.copytree(review/'inputs/normal',output/'inputs/normal');info,py,native=previous.runtime()
    a.put(output,'runtime.json',f.encode(info));a.put(output,'runtime/subprocess.py',py);a.put(output,'runtime/posixsubprocess.bin',native)
    try:r=exercise(output/'inputs',output/'work',info)
    except BaseException as exc:a.put(output,'failure.json',f.encode(dict(error=type(exc).__name__+': '+str(exc))));seal(output);raise
    f.require(sources()==frozen,'child signal source drift after exercise')
    a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=579,prior_sources_unchanged=575,source_hashes=frozen)));seal(output)
    return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=20,actual_child_processes=20)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
