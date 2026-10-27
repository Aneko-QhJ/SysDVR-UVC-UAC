"""Focused current132 receiver integration checks; mock SDK operations only."""
import argparse
import json
import shutil
import subprocess
import tempfile
import types
import uuid
from pathlib import Path
import build_a23_live132_terminal as b
import audit_a23_live126_interepoch as previous
import a23_live132_terminal_consumer as consumer

w=b.w
CASES=('normal','spent417-pre','baseline132-pre','terminal-source','terminal-stop','terminal-interest',
       'terminal-tail','after-payload-bytes','terminal-old-iso')

def fixture():
    raw=previous.fixture().replace('417','465').replace('464','512')
    # This is a new bound fixture; only prospective sequence constants above
    # move. The new spent417 protection is added by the fresh descriptor.
    raw=raw.replace('static A23CheckedTwoEpochRun *workerHookLoop;',r'''
#include <time.h>
#include <unistd.h>
static uint64_t terminalFirstPoll;
static uint64_t terminalLastPoll;
static TwoClock *terminalModelClock;
static BOOL terminalBlocked,terminalWorkerGate;
static A23CheckedTwoEpochRun *workerHookLoop;
void A23Live132TerminalWorkerStarted(void){
    NSString *mode=exportConfig[@"case"];
    if([mode isEqual:@"terminal-source"]){change([exportConfig[@"repository"] stringByAppendingPathComponent:@"research/usb-ds-iso/tools/build_a23_live132_terminal.py"]);return;}
    if(![mode isEqual:@"terminal-stop"])return;
    dispatch_semaphore_t handled=dispatch_semaphore_create(0);
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_DEFAULT,0),^{
        // Route the exit through the owner queue, preserving exclusive verifier ownership.
        dispatch_async(workerHookQueue,^{
            [workerHookLoop requestExit];[workerHookLoop tick];
            assert([exportCoordinator.terminalGuardResult[@"busy"] boolValue]);
            assert(![exportCoordinator terminalExitAllowed]);
            assert([exportCoordinator.exportEvidence[@"verification_pending"] boolValue]);
            assert(![exportCoordinator finalizeOnce]);
            assert([workerHookLoop finishAfterOperatorPowerOff]);
            assert(!A23TerminalExitAllowed(workerHookLoop.status,exportCoordinator.queueGuardResult,exportCoordinator.terminalGuardResult));
            terminalWorkerGate=YES;dispatch_semaphore_signal(handled);
        });
    });
    assert(!dispatch_semaphore_wait(handled,dispatch_time(DISPATCH_TIME_NOW,3000000000LL)));
}
void A23Live132TerminalPoll(void){
    struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC_RAW,&t));uint64_t now=(uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;
    // Keep this explicitly synthetic SDK clock's minimum-duration predicate
    // satisfied without equating its absolute values to the RAW service clock.
    [terminalModelClock advanceNS:(terminalLastPoll?now-terminalLastPoll:0)+1000000ULL];terminalLastPoll=now;
    if(!terminalFirstPoll)terminalFirstPoll=now;
    NSString *mode=exportConfig[@"case"];
    if([mode isEqual:@"terminal-tail"] && !terminalBlocked && now-terminalFirstPoll>=200000000ULL){terminalBlocked=YES;usleep(80000);}
}
''')
    # The new hook needs the queue declaration before its implementation.
    raw=raw.replace('static uint64_t terminalFirstPoll;','static dispatch_queue_t workerHookQueue;\nstatic uint64_t terminalFirstPoll;')
    raw=raw.replace('op.interface=r;','op.interface=r;terminalModelClock=r.clock;')
    raw=raw.replace('BOOL initial=[v verifyCore];','''if([name isEqual:@"spent417-pre"])change([[c[@"records"] stringByDeletingLastPathComponent] stringByAppendingPathComponent:@"spent417/block-00417.json"]);
    if([name isEqual:@"baseline132-pre"])change([[c[@"cards"] stringByAppendingPathComponent:@"20261025-live126-interepoch-first-read"] stringByAppendingPathComponent:@"card/logfile.txt"]);
    BOOL initial=[v verifyCore];''')
    old='[r.clock advanceNS:250000001];dispatch_sync(q,^{[loop tick];});'
    new=r'''
        for(unsigned tick=0;tick<3000;++tick){
            __block BOOL done;dispatch_sync(q,^{
                [loop tick];
                NSDictionary *term=exportCoordinator.terminalGuardResult;
                if([term[@"phase"] isEqual:@"observing"]){
                    if([name isEqual:@"terminal-interest"])r.interest(0xffffffffU);
                    if([name isEqual:@"terminal-old-iso"])[r oldISO];
                }
                done=([loop.status[@"finished"] boolValue] || [loop.status[@"unresolved_keep_alive"] boolValue]) && [exportCoordinator terminalExitAllowed];
            });if(done)break;usleep(1000);
        }
        dispatch_sync(q,^{
            assert([exportCoordinator terminalExitAllowed]);
            if([name isEqual:@"terminal-stop"])assert(terminalWorkerGate);
            if([name isEqual:@"terminal-tail"])assert(terminalBlocked);
            if([loop.status[@"unresolved_keep_alive"] boolValue])assert([loop finishAfterOperatorPowerOff]);
            assert(A23TerminalExitAllowed(loop.status,exportCoordinator.queueGuardResult,exportCoordinator.terminalGuardResult));
        });
'''
    b.require(old in raw,'terminal wait anchor');raw=raw.replace(old,new)
    raw=raw.replace('@"worker_exit_deferred":@(workerExitDeferred),','@"terminal_guard":exportCoordinator.terminalGuardResult,@"worker_exit_deferred":@(workerExitDeferred),')
    return raw

def run(out):
    out=Path(out).resolve();b.require(not out.exists(),'fresh audit required');out.mkdir(mode=0o700)
    before=b.prior.protected();hashes=b.sources();done=[]
    def process(cmd,name,code=0,timeout=60):
        p=subprocess.run(cmd,capture_output=True,timeout=timeout)
        w.card.put(out,name+'.stdout',p.stdout);w.card.put(out,name+'.stderr',p.stderr)
        w.write(out/(name+'.process.json'),dict(command=cmd,returncode=p.returncode,creator_wait_verified=True))
        b.require(p.returncode==code,'process failed '+name);return p
    try:
        build=out/'build';b.build(build);scope=b.scope(build)
        modes={}
        for name,args,code in [('describe',['--describe'],0),('archive',['--check-archive',str(build)],0),
            ('current',['--check-build',str(build)],0),('disabled',['--acquire-once',str(build),'/nonexistent','/nonexistent'],2)]:
            p=process([str(build/'verified-entry'),*args],name,code);modes[name]=dict(returncode=p.returncode)
            if name=='current':b.require(json.loads(p.stdout)['scope']==scope,'native/Python scope differs')
        native=out/'native';shutil.copytree(build,native);target=native/'generated/model_fixture.m';target.write_text(fixture())
        process(b.command(native,target),'fixture-compile');matrix={};accepted={}
        engine=consumer.module(build,'fixed48')
        with tempfile.TemporaryDirectory(prefix='a23-live132-terminal-',dir='/private/tmp') as temp:
            scratch=Path(temp);template=scratch/'template';previous.old.template(build,template)
            for n in (145,177,225,273,321,369,417):shutil.copytree(build/f'history/spent{n}',template/f'spent{n}')
            b.require(len(list(template.iterdir()))==13,'model roots differ')
            cases=scratch/'cases';cases.mkdir()
            try:
                for name in CASES:
                    case=cases/name;case.mkdir();host=case/'host';host.mkdir();model=case/'model';shutil.copytree(template,model)
                    store=engine.SharedSequence48(case/'namespace',simulation=True,fresh_scope=lambda:scope);store.initialize(b.inputs()[4])
                    job=str(uuid.uuid4());ns=store.validate()
                    auth=dict(schema='A23-shared48-authorization-1',job_id=job,scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=True,hardware_test_authorized=False)
                    store.prepare(job,auth);store.issue(job);store.consume(job)
                    config=dict(case=name,build=str(build),host=str(host),repository=str(model/'repository'),cards=str(model/'cards'),ledger=str(model/'ledger'),records=str(model/'records'),job=str(store.root/'jobs'/job),binding=store.binding(job))
                    w.write(case/'config.json',config)
                    p=subprocess.run([str(native/'live-fixture'),str(case/'config.json')],capture_output=True,timeout=60)
                    w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr);w.write(case/'process.json',dict(returncode=p.returncode,creator_wait_verified=True))
                    b.require(p.returncode==0 and not p.stderr,'native failed '+name)
                    row=json.loads(p.stdout);matrix[name]=row;done.append(name)
                    if name=='normal':accepted[name]=consumer.analyze(host,build,job=config['job'],simulation=True)
                    elif name in ('spent417-pre','baseline132-pre'):b.require(row['initial_core'] is False and row['calls']['opens']==0,'pre-open rejection failed')
                    else:
                        b.require(row['loop']['success'] is False,'fault accepted')
                        if name!='after-payload-bytes':accepted[name]=consumer.analyze_failure(host,build,job=config['job'])
                    shutil.rmtree(model)
            finally:shutil.copytree(cases,out/'cases')
        b.require(b.sources()==hashes and b.prior.protected()==before,'source/protected drift')
        w.write(out/'source-hashes.json',hashes);w.write(out/'protected-before.json',before)
        w.write(out/'report.json',dict(schema='A23-live132-terminal-offline-audit-1',source_count=662,old659_unchanged=True,
            cases=matrix,accepted=accepted,file_modes=modes,native_compiler_jobs=2,native_fixture_processes=len(done),
            model_namespaces=len(done),creator_wait_verified=True,receiver_adapter_integrated=True,current132_bound=True,
            real_sdk_objects=0,usb_requests=0,sd_accesses=0,formal_ranges=0,formal_authorizations=0,remaining=0,
            callback_drain_verified=False,buffer_reuse_verified=False,hardware_entry_enabled=False))
        w.b.seal(out);return dict(directory=str(out),seal=b.base.core.verify_seal(out),cases=len(done))
    except BaseException as e:
        w.write(out/'failure.json',dict(error=str(e),completed=done));w.b.seal(out);raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output)))
