"""Bound fresh126 wiring checks; retain earlier transport and handoff matrices."""
import argparse,json,re,shutil,subprocess,tempfile
from pathlib import Path
import build_a23_live126_interepoch as b
import a23_live126_interepoch_workflow as flow
import audit_a23_live91_checked as old
w=b.w;require=b.require
PREVIOUS=w.A/'A23-interepoch-entry-integration-20261025-r1'
PREVIOUS_SUM='58de451dea0bbc6bc875f415c9c27687fe434926d7da3cc2d2b754570b965dae'
CASES=('normal','spent369-drift','spent369-extra','spent369-missing','new-source-pre','baseline126-pre',
    'old369-scope','count32-reservation','between-third-source','exit-worker-ack','frozen-spent369','archive-new-main')

def fixture():
    require(b.core.verify_seal(PREVIOUS)==PREVIOUS_SUM,'previous fixture drift')
    raw=w.plain(PREVIOUS/'integration_fixture.m').decode()
    raw=re.sub(r'\b(369|416)\b',lambda m:{'369':'417','416':'464'}[m[0]],raw)
    raw=raw.replace('baseline120-pre','baseline126-pre').replace('source644-pre','source651-pre')
    raw=raw.replace(b.base.ANCHOR.name,b.ANCHOR.name).replace('tools/build_a23_live120_lstat.py','tools/build_a23_live126_interepoch.py')
    raw=b.c.change(raw,'if(!initial){',r'''if([name isEqual:@"old369-scope"]){NSMutableDictionary *s=[v.scope mutableCopy];s[@"schema"]=@"A23-live120-lstat-shared48-scope-1";s[@"first_sequence"]=@369;s[@"last_sequence"]=@416;
        A23SharedSequenceModelPermit *p=[[A23SharedSequenceModelPermit alloc] initWithJob:c[@"job"] expectedScope:s verifier:^BOOL(NSDictionary *scope){return [v verifyLiveJob:scope job:c[@"job"]];}];assert(!p);initial=NO;}
    if(!initial){''')
    hook=r'''
#include "interepoch_exit.h"
static A23CheckedTwoEpochRun *workerHookLoop;
static dispatch_queue_t workerHookQueue;
static BOOL workerExitDeferred;
void A23Live126WorkerStarted(void){
    if(![exportConfig[@"case"] isEqual:@"exit-worker-ack"])return;
    dispatch_semaphore_t handled=dispatch_semaphore_create(0);
    dispatch_async(workerHookQueue,^{
        [workerHookLoop requestExit];[workerHookLoop tick];
        assert([workerHookLoop.status[@"unresolved_keep_alive"] boolValue]);
        assert([workerHookLoop finishAfterOperatorPowerOff]);
        assert([workerHookLoop.status[@"finished"] boolValue]);
        assert(!A23InterepochExitAllowed(workerHookLoop.status,exportCoordinator.queueGuardResult));
        assert([exportCoordinator.exportEvidence[@"verification_pending"] boolValue]);
        assert(![exportCoordinator finalizeOnce] && ![exportCoordinator validateFinalExport]);
        workerExitDeferred=YES;dispatch_semaphore_signal(handled);
    });
    assert(!dispatch_semaphore_wait(handled,dispatch_time(DISPATCH_TIME_NOW,3000000000LL)));
}
'''
    raw=b.c.change(raw,'int main(int argc,const char *argv[])',hook+'\nint main(int argc,const char *argv[])')
    raw=b.c.change(raw,'dispatch_queue_t q=dispatch_queue_create("a23.checked.export",DISPATCH_QUEUE_SERIAL);','dispatch_queue_t q=dispatch_queue_create("a23.checked.export",DISPATCH_QUEUE_SERIAL);workerHookQueue=q;')
    raw=b.c.change(raw,'assert(loop && [loop begin]', 'workerHookLoop=loop;assert(loop && [loop begin]')
    raw=b.c.change(raw,'@"interepoch_guard":exportCoordinator.queueGuardResult,','@"worker_exit_deferred":@(workerExitDeferred),@"interepoch_guard":exportCoordinator.queueGuardResult,')
    raw=b.c.change(raw,'BOOL finished=[loop.status[@"finished"] boolValue];','BOOL finished=[loop.status[@"finished"] boolValue];if(workerExitDeferred)assert(A23InterepochExitAllowed(loop.status,exportCoordinator.queueGuardResult));')
    return raw

def run(out):
    out=w.canonical(out);require(not out.exists() and not b.FORMAL_ROOT.exists(),'new unissued126 review required')
    hashes=b.sources();out.mkdir(mode=0o700);done=[]
    def process(cmd,name,timeout=60):
        p=subprocess.run(cmd,capture_output=True,timeout=timeout)
        w.card.put(out,name+'.stdout',p.stdout);w.card.put(out,name+'.stderr',p.stderr)
        w.write(out/(name+'.process.json'),dict(command=cmd,returncode=p.returncode,creator_wait_verified=True))
        return p
    try:
        build=out/'build';b.build(build);scope=b.runtime_scope(build);engine=flow.engine_module(build);history=b.inputs()[4]
        native=out/'native';shutil.copytree(build,native);target=native/'generated/model_fixture.m';target.write_text(fixture())
        cmd=b.command(native,target);p=process(cmd,'fixture-compile');require(p.returncode==0,'fixture compile failed')
        modes={}
        for name,args,code in [('describe',['--describe'],0),('archive',['--check-archive',str(build)],0),('current',['--check-build',str(build)],0),('unissued',['--acquire-once',str(build),'/nonexistent','/nonexistent'],2)]:
            p=process([str(build/'verified-entry'),*args],name,30);require(p.returncode==code,'file mode failed '+name);modes[name]=dict(returncode=p.returncode)
            if name=='current':require(json.loads(p.stdout)['scope']==scope,'native/Python scope differs')
        rejections={}
        try:flow.issue(build,authorized=False)
        except ValueError as e:rejections['missing-authorization']=str(e)
        else:raise ValueError('missing authorization accepted')
        try:b.base.verify(build,current=False)
        except ValueError as e:rejections['old120-consumer']=str(e)
        else:raise ValueError('old120 accepted new126 build')
        try:
            import a23_live120_lstat_workflow as old_flow
            old_flow.preview(build)
        except ValueError as e:rejections['old120-workflow']=str(e)
        else:raise ValueError('old120 workflow accepted new126 build')
        matrix={};accepted={}
        with tempfile.TemporaryDirectory(prefix='a23-live126-review-',dir='/private/tmp') as temp:
            scratch=Path(temp);template=scratch/'template';old.template(build,template)
            for n in (145,177,225,273,321,369):shutil.copytree(build/f'history/spent{n}',template/f'spent{n}')
            cases=scratch/'cases';cases.mkdir()
            try:
                for name in CASES:
                    case=cases/name;case.mkdir();host=case/'host';host.mkdir();model=case/'model';shutil.copytree(template,model)
                    current_build=case/'build';shutil.copytree(build,current_build)
                    store=engine.SharedSequence48(case/'namespace',simulation=True,fresh_scope=lambda:scope);store.initialize(history)
                    job=flow.implementation(build).prepare_job(store);store.issue(job);store.consume(job)
                    config=dict(case=name,build=str(current_build),host=str(host),repository=str(model/'repository'),cards=str(model/'cards'),ledger=str(model/'ledger'),records=str(model/'records'),job=str(store.root/'jobs'/job),binding=store.binding(job));w.write(case/'config.json',config)
                    if name=='count32-reservation':
                        p=store.root/'block-00417.json';v=w.load(p);v['count']=32;p.write_bytes(b.encode(v))
                    if name=='spent369-drift':(model/'spent369/block-00369.json').write_text('changed')
                    if name=='spent369-extra':(model/'spent369/extra').write_text('extra')
                    if name=='spent369-missing':(model/'spent369/block-00369.json').unlink()
                    if name=='new-source-pre':(model/'repository/research/usb-ds-iso/host/a23_interepoch_guard.m').write_text('changed')
                    if name=='frozen-spent369':(current_build/'history/spent369/block-00369.json').write_text('changed')
                    if name=='archive-new-main':(current_build/'generated/live_main.m').write_text('changed')
                    p=subprocess.run([str(native/'live-fixture'),str(case/'config.json')],capture_output=True,timeout=60)
                    w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr);w.write(case/'process.json',dict(returncode=p.returncode,creator_wait_verified=True))
                    require(p.returncode==0 and not p.stderr,'native failed '+name);row=json.loads(p.stdout);matrix[name]=row
                    if name=='normal':
                        accepted[name]=flow.analyze_host(host,build,simulation=True);require(accepted[name]['sdk']['total_bytes']==9216 and row['interepoch_guard']['resumed_polls']==2,'normal rebind mismatch')
                        try:flow.analyze_host(host,build,simulation=False)
                        except ValueError as e:rejections['synthetic-as-real']=str(e)
                        else:raise ValueError('model upgraded to real')
                    elif name=='between-third-source':require(row['calls']['iso_submissions']==2 and not row['loop']['success'],'third source not stopped')
                    elif name=='baseline126-pre':require(row['calls']['iso_submissions']==0 and not row['loop']['success'],'baseline not stopped')
                    elif name=='exit-worker-ack':
                        require(row['worker_exit_deferred'] is True and row['calls']['iso_submissions']==1 and row['loop']['finished'] is True and row['interepoch_guard']['worker_returns']==1,'worker exit handoff not preserved')
                    else:require(row['initial_core'] is False and row['calls']['opens']==0,'bad binding opened SDK')
                    done.append(name)
                    shutil.rmtree(model);shutil.rmtree(current_build)
            finally:shutil.copytree(cases,out/'cases')
        for n in ('live_owner.m','live_evidence.m','live_adapter.m','live_driver.m'):
            require(w.plain(build/'generated'/n)==w.plain(b.LIVE/'generated'/n).replace(b'first!=369',b'first!=417'),'transport drift beyond sequence gate '+n)
        require(b.sources()==hashes and not b.FORMAL_ROOT.exists(),'source/formal namespace changed');b.guards()
        w.write(out/'report.json',dict(schema='A23-live126-interepoch-audit-1',passed=True,source_count=651,source_hashes=hashes,completed=done,matrix=matrix,accepted=accepted,rejections=rejections,file_modes=modes,
            first_sequence=417,last_sequence=464,current_raw_files=126,worker_exit_gate_verified_in_model=True,native_compiler_jobs=2,native_fixture_processes=len(done),file_mode_processes=4,creator_wait_verified=True,
            formal_namespaces_added=0,formal_authorizations=0,formal_ranges=0,model_namespaces=len(done),model_authorizations=len(done),real_sdk_objects=0,usb_requests=0,sd_accesses=0,remaining=0,callback_drain_verified=False,continuous_streaming_verified=False,buffer_reuse_verified=False,post_gate_sdk_race_closed=False))
    except BaseException as e:w.write(out/'failure.json',dict(error=str(e),completed=done));w.b.seal(out);raise
    w.b.seal(out);return dict(directory=str(out),manifest_sha256=b.core.verify_seal(out),native_cases=len(done),passed=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
