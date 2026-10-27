"""Bound end-of-export repair: focused former counterexamples and pending exit."""
import argparse
import copy
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
import build_a23_live132_completion as b
import a23_live132_completion_consumer as consumer
import audit_a23_postexport_boundary as old

w=b.w
CASES={n:(stage,kind,n in ('normal','postcheck-source')) for n,(stage,kind,_,_) in old.CASES.items()}
CASES.update({'pending-exit':('', '',False),'completion-collision':('', '',False),'receipt-tamper':('after_receipt','',False)})

def fixture():
    raw=old.fixture()
    raw=raw.replace('#include "interepoch_exit.h"','')
    raw=raw.replace('static SDKModelInterface *auditResources;',r'''
#include "interepoch_exit.h"
static A23CheckedTwoEpochRun *completionLoop;
static BOOL pendingGateObserved;
static SDKModelInterface *auditResources;
''')
    raw=raw.replace('    auditCheckpoint(stage);',r'''
    auditCheckpoint(stage);
    NSString *completionCase=exportConfig[@"case"];
    if([stage isEqual:@"completion_pending"]){
        assert([completionLoop.status[@"completion_pending"] boolValue]);
        assert(![completionLoop.status[@"success"] boolValue]);
        assert(!A23CompletionExitAllowed(completionLoop.status,exportCoordinator.queueGuardResult,exportCoordinator.terminalGuardResult));
        NSDictionary *before=exportVerifier.cadenceMetrics;[completionLoop tick];assert([before isEqual:exportVerifier.cadenceMetrics]);
        pendingGateObserved=YES;
        if([completionCase isEqual:@"pending-exit"]){
            [completionLoop requestExit];assert([completionLoop.status[@"unresolved_keep_alive"] boolValue]);
            assert([completionLoop finishAfterOperatorPowerOff]);
            assert([completionLoop.status[@"finished"] boolValue] && [completionLoop.status[@"completion_pending"] boolValue]);
            assert(!A23CompletionExitAllowed(completionLoop.status,exportCoordinator.queueGuardResult,exportCoordinator.terminalGuardResult));
        }
        if([completionCase isEqual:@"completion-collision"]){
            assert([[NSFileManager defaultManager] createDirectoryAtPath:[exportConfig[@"host"] stringByAppendingPathComponent:@"live-completion"] withIntermediateDirectories:NO attributes:nil error:NULL]);
        }
    }
    if([stage isEqual:@"after_receipt"] && [completionCase isEqual:@"receipt-tamper"])
        change([exportConfig[@"host"] stringByAppendingPathComponent:@"live-acceptance/receipt.json"]);
''')
    raw=raw.replace('workerHookLoop=loop;assert(loop && [loop begin]',
        'workerHookLoop=loop;completionLoop=loop;assert(loop && [loop configureCompletionQueue:q]);assert(loop && [loop begin]')
    raw=raw.replace('A23TerminalExitAllowed(loop.status,exportCoordinator.queueGuardResult,exportCoordinator.terminalGuardResult)',
        'A23CompletionExitAllowed(loop.status,exportCoordinator.queueGuardResult,exportCoordinator.terminalGuardResult)')
    raw=raw.replace('&& [exportCoordinator terminalExitAllowed];',
        '&& [exportCoordinator terminalExitAllowed] && ![loop.status[@"completion_pending"] boolValue];')
    raw=raw.replace('@"audit_capture":auditCapture?:@{},', '@"pending_gate_observed":@(pendingGateObserved),@"audit_capture":auditCapture?:@{},')
    return raw

def reject(call):
    try:call()
    except (ValueError,OSError) as error:return str(error)
    raise ValueError('unexpected consumer acceptance')

def mutations(fact):
    result={}
    actions={
        'numeric-accepted':lambda r:r.update(accepted=1),
        'rejected-record':lambda r:r.update(accepted=False),
        'wrong-continuations':lambda r:r.update(continuations=2),
        'missing-queue-handoff':lambda r:r.update(queue_handoffs=0),
        'exit-requested':lambda r:r.update(exit_requests=1),
        'operator-ack':lambda r:r.update(operator_off_acknowledged=True),
        'wrong-payload':lambda r:r['binding'].update(payload_manifest_sha256='0'*64),
        'wrong-receipt':lambda r:r['binding'].update(acceptance_receipt_sha256='0'*64),
        'clock-backwards':lambda r:r.update(continuation_entered_ns=r['queue_requested_ns']-1),
        'wrong-entry-sample':lambda r:r.update(sampled_entry_sha256='0'*64),
        'unsupported-drain':lambda r:r.update(callback_drain_verified=True),
    }
    binding=copy.deepcopy(fact['binding'])
    for name,change in actions.items():
        row=copy.deepcopy(fact);change(row);result[name]=reject(lambda row=row:consumer.validate_fact(row,binding))
    return result

def run(out):
    out=Path(out).resolve();b.require(not out.exists(),'fresh completion review required');out.mkdir(mode=0o700)
    before=b.base.prior.protected();hashes=b.sources();done=[]
    def process(cmd,name,code=0):
        p=subprocess.run(cmd,capture_output=True,timeout=60);w.card.put(out,name+'.stdout',p.stdout);w.card.put(out,name+'.stderr',p.stderr)
        w.write(out/(name+'.process.json'),dict(command=cmd,returncode=p.returncode,creator_wait_verified=True))
        b.require(p.returncode==code,'process failed '+name);return p
    try:
        build=out/'build';b.build(build);scope=b.scope(build);modes={}
        for name,args,code in [('describe',['--describe'],0),('archive',['--check-archive',str(build)],0),
            ('current',['--check-build',str(build)],0),('disabled',['--acquire-once',str(build),'/nonexistent','/nonexistent'],2)]:
            p=process([str(build/'verified-entry'),*args],name,code);modes[name]=dict(returncode=p.returncode)
            if name=='current':b.require(json.loads(p.stdout)['scope']==scope,'native/Python scope mismatch')
        native=out/'native';shutil.copytree(build,native);target=native/'generated/completion_fixture.m';target.write_text(fixture())
        process(b.command(native,target),'fixture-compile');engine=consumer.module(build,'fixed48');rows={};proofs={};rejections={}
        with tempfile.TemporaryDirectory(prefix='a23-completion-',dir='/private/tmp') as temp:
            scratch=Path(temp);template=scratch/'template';old.templates.template(build,template)
            for n in (145,177,225,273,321,369,417):shutil.copytree(build/f'history/spent{n}',template/f'spent{n}')
            cases=scratch/'cases';cases.mkdir()
            try:
                for name,(stage,kind,success) in CASES.items():
                    case=cases/name;case.mkdir();host=case/'host';host.mkdir();model=case/'model';shutil.copytree(template,model)
                    store=engine.SharedSequence48(case/'namespace',simulation=True,fresh_scope=lambda:scope);store.initialize(b.inputs()[4])
                    job=str(uuid.uuid4());ns=store.validate();store.prepare(job,dict(schema='A23-shared48-authorization-1',job_id=job,
                        scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=True,hardware_test_authorized=False))
                    store.issue(job);store.consume(job)
                    config=dict(case=name,build=str(build),host=str(host),repository=str(model/'repository'),cards=str(model/'cards'),
                        ledger=str(model/'ledger'),records=str(model/'records'),job=str(store.root/'jobs'/job),binding=store.binding(job),
                        audit_stage=stage,audit_delivery=kind,audit_expected_success=success,audit_capture=str(case/'at-return'))
                    w.write(case/'config.json',config)
                    p=subprocess.run([str(native/'live-fixture'),str(case/'config.json')],capture_output=True,timeout=60)
                    w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr);w.write(case/'process.json',dict(returncode=p.returncode,creator_wait_verified=True))
                    b.require(p.returncode==0 and not p.stderr,'native failed '+name)
                    row=json.loads(p.stdout);rows[name]=row;done.append(name)
                    b.require(row['loop']['success'] is success and row['loop']['completion_pending'] is False,'completion state '+name)
                    if success:proofs[name]=consumer.analyze(host,build,job=config['job'],simulation=True)
                    else:rejections[name]=reject(lambda:consumer.analyze(host,build,job=config['job'],simulation=True))
                    if name not in ('precheck-direct','payload-direct','receipt-tamper'):
                        b.require(row['pending_gate_observed'] is True and row['loop']['completion_dispatches']==row['loop']['completion_continuations']==1,'handoff/gate missing')
                    if name=='receipt-tamper':
                        b.require(row['loop']['completion_dispatches']==0 and row['loop']['completion_failure']=='completion_inputs','tampered receipt not rejected before handoff')
                    if name=='normal':
                        fact=json.loads(w.card.seal_verify(host/'live-completion')['completion.json'])
                        rejections.update(mutations(fact))
                        stagecopy=scratch/'without-completion';shutil.copytree(host,stagecopy);shutil.rmtree(stagecopy/'live-completion')
                        rejections['missing-completion']=reject(lambda:consumer.analyze(stagecopy,build,job=config['job'],simulation=True))
                    shutil.rmtree(model)
            finally:shutil.copytree(cases,out/'cases')
        old_case=old.w.A/'A23-postexport-boundary-20261026-r1/cases/postcheck-direct'
        rejections['old-historical-acceptance']=reject(lambda:consumer.analyze(old_case/'at-return',build,job=w.load(old_case/'config.json')['job'],simulation=True))
        rejections['physical-upgrade']=reject(lambda:consumer.analyze(out/'cases/normal/host',build,job=w.load(out/'cases/normal/config.json')['job'],simulation=False))
        b.require(b.sources()==hashes and b.base.prior.protected()==before,'protected source/state drift')
        w.write(out/'source-hashes.json',hashes);w.write(out/'protected-before.json',before)
        w.write(out/'report.json',dict(schema='A23-live132-completion-review-1',source_count=666,old663_unchanged=True,
            cases=rows,accepted=proofs,rejections=rejections,file_modes=modes,native_compiler_jobs=2,native_fixture_processes=len(done),
            creator_wait_verified=True,model_namespaces=len(done),owner_queue_handoffs=1,completion_fact_required=True,
            former_late_counterexamples_rejected=True,pending_operator_ack_blocks_exit=True,model_sdk_operations_only=True,
            hardware_entry_enabled=False,usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_namespaces_added=0,
            formal_ranges=0,formal_authorizations=0,remaining=0,callback_drain_verified=False,future_events_excluded=False))
        w.b.seal(out);return dict(directory=str(out),seal=b.base.base.core.verify_seal(out),cases=len(done),rejections=len(rejections))
    except BaseException as e:
        w.write(out/'failure.json',dict(error=str(e),completed=done));w.b.seal(out);raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);print(json.dumps(run(p.parse_args().output)))
