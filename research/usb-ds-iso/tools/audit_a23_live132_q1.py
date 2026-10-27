"""Q1 preparation checks: real-entry compilation, model execution, mode/authority rejection."""
import argparse
import copy
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
import build_a23_live132_q1 as b
import a23_live132_q1_consumer as consumer
import a23_live132_q1_workflow as flow
import audit_a23_live132_completion as previous

w=b.w
CASES=('normal','dense-window','terminal-stop','pending-exit','payload-queued','interest-open',
    'completion-collision','new-source-pre','spent417-pre','old666-scope')

def fixture():
    raw=previous.fixture()
    raw=raw.replace('int main(int argc,const char *argv[])', 'extern NSDictionary *A23Q1EncodingFixture(NSDictionary *value);\nint main(int argc,const char *argv[])')
    raw=b.one(raw,'exportConfig=c;',r'''exportConfig=c;
    NSData *wideRaw=[NSData dataWithContentsOfFile:c[@"encoding_fixture"]];assert(wideRaw.length>16384);
    NSDictionary *wide=[NSJSONSerialization JSONObjectWithData:wideRaw options:0 error:NULL];
    NSDictionary *encoding=A23Q1EncodingFixture(wide);assert([encoding[@"legacy_accepts"] isEqual:@NO] &&
        [encoding[@"terminal_accepts"] isEqual:@YES] && [encoding[@"bad_count_rejected"] isEqual:@YES]);''')
    raw=raw.replace('@"pending_gate_observed":@(pendingGateObserved),','@"q1_encoding_checks":encoding,@"pending_gate_observed":@(pendingGateObserved),')
    raw=raw.replace('usleep(1000);','usleep([name isEqual:@"dense-window"]?650:1000);')
    # The fixed fixture already acknowledges retained failures in its common
    # owner-queue exit. Do not repeat its historical interest-specific ack.
    at=raw.index('__block NSDictionary *row;');tail=raw[at:]
    tail=b.one(tail,'if([name hasPrefix:@"interest-"]){','if(NO){');raw=raw[:at]+tail
    anchor='if([name isEqual:@"old369-scope"]){'
    raw=b.one(raw,anchor,r'''
    if([name isEqual:@"old666-scope"]){NSMutableDictionary *s=[v.scope mutableCopy];
        s[@"schema"]=@"A23-live132-completion-offline48-scope-1";s[@"hardware_entry_enabled"]=@NO;
        s[@"formal_issuance_available"]=@NO;s[@"acquisition_mode_implemented"]=@NO;
        A23SharedSequenceModelPermit *p=[[A23SharedSequenceModelPermit alloc] initWithJob:c[@"job"] expectedScope:s
            verifier:^BOOL(NSDictionary *scope){return [v verifyLiveJob:scope job:c[@"job"]];}];assert(!p);initial=NO;
    }
    '''+anchor)
    return raw

def reject(call):
    try:call()
    except (ValueError,OSError,KeyError,TypeError) as error:return str(error)
    raise ValueError('unexpected acceptance')

def run(out):
    out=Path(out).resolve();b.require(not out.exists() and not b.FORMAL_ROOT.exists(),'fresh unissued Q1 review required');out.mkdir(mode=0o700)
    before=b.base.base.prior.protected();hashes=b.sources();done=[]
    def process(cmd,name,code=0):
        p=subprocess.run(cmd,capture_output=True,timeout=60);w.card.put(out,name+'.stdout',p.stdout);w.card.put(out,name+'.stderr',p.stderr)
        w.write(out/(name+'.process.json'),dict(command=cmd,returncode=p.returncode,creator_wait_verified=True))
        b.require(p.returncode==code,'process failed '+name);return p
    try:
        build=out/'build';b.build(build);scope=b.scope(build);modes={}
        for name,args,code in [('describe',['--describe'],0),('archive',['--check-archive',str(build)],0),
            ('current',['--check-build',str(build)],0),('unissued',['--acquire-once',str(build),'/nonexistent','/nonexistent'],2)]:
            p=process([str(build/'verified-entry'),*args],name,code);modes[name]=dict(returncode=p.returncode)
            if name=='current':b.require(json.loads(p.stdout)['scope']==scope,'native/Python Q1 scope differs')
        preview=flow.preview(build);runtime=flow.implementation(build);engine=runtime.engine_module(build)
        rejections={'no-authorization':reject(lambda:flow.issue(build,authorized=False)),
            'old-completion-builder':reject(lambda:b.base.verify(build,current=False)),
            'no-execution-mode':reject(lambda:runtime.capture(build,Path('/nonexistent'),execution_mode=None))}
        native=out/'native';shutil.copytree(build,native);target=native/'generated/q1_fixture.m';target.write_text(fixture())
        process(b.command(native,target),'fixture-compile');matrix={};accepted={};failed={};sizes={}
        with tempfile.TemporaryDirectory(prefix='a23-q1-review-',dir='/private/tmp') as temp:
            scratch=Path(temp);template=scratch/'template';previous.old.templates.template(build,template)
            for n in (145,177,225,273,321,369,417):shutil.copytree(build/f'history/spent{n}',template/f'spent{n}')
            cases=scratch/'cases';cases.mkdir()
            try:
                for name in CASES:
                    case=cases/name;case.mkdir();host=case/'host';host.mkdir();model=case/'model';shutil.copytree(template,model)
                    store=engine.SharedSequence48(case/'namespace',simulation=True,fresh_scope=lambda:scope);store.initialize(b.inputs()[4])
                    job=str(uuid.uuid4());ns=store.validate();store.prepare(job,dict(schema='A23-shared48-authorization-1',job_id=job,
                        scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=True,hardware_test_authorized=False));store.issue(job);store.consume(job)
                    config=dict(case=name,build=str(build),host=str(host),repository=str(model/'repository'),cards=str(model/'cards'),ledger=str(model/'ledger'),
                        records=str(model/'records'),job=str(store.root/'jobs'/job),binding=store.binding(job),
                        audit_stage='after_payload' if name=='payload-queued' else '',audit_delivery='queued_interest' if name=='payload-queued' else '',
                        audit_expected_success=name in ('normal','dense-window'),audit_capture=str(case/'at-return'),
                        encoding_fixture=str(w.A/'A23-live132-q1-review-20261026-r1/cases/dense-window/host/terminal-observation.json'))
                    w.write(case/'config.json',config)
                    if name=='new-source-pre':(model/'repository/research/usb-ds-iso/tools/build_a23_live132_q1.py').write_text('changed')
                    p=subprocess.run([str(native/'live-fixture'),str(case/'config.json')],capture_output=True,timeout=60)
                    w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr);w.write(case/'process.json',dict(returncode=p.returncode,creator_wait_verified=True))
                    b.require(p.returncode==0 and not p.stderr,'native failed '+name);row=json.loads(p.stdout);matrix[name]=row;done.append(name)
                    if name in ('new-source-pre','spent417-pre','old666-scope'):
                        b.require(row['initial_core'] is False and row['calls']['opens']==0,'pre-open rejection failed')
                    elif name in ('normal','dense-window'):
                        accepted[name]=consumer.analyze_host(host,build,job=config['job'],simulation=True)
                        b.require(accepted[name]['entry']['sdk']['total_bytes']==9216,'Q1 payload differs')
                        sizes[name]=dict(result_json_bytes=(host/'live-final/result.json').stat().st_size,
                            samples=row['terminal_guard']['sample_count'])
                        rejections[name+'-as-real']=reject(lambda:consumer.analyze_host(host,build,job=config['job'],simulation=False))
                        if name=='normal':
                            rejections['numeric-mode']=reject(lambda:consumer.analyze_host(host,build,job=config['job'],simulation=0))
                            record=copy.deepcopy(row['terminal_guard']);expected=copy.deepcopy(record['binding']);expected['model_only']=False
                            rejections['service-model-marker-as-real']=reject(lambda:consumer.service.validate(record,expected,simulation=False))
                            fake=case/'fake-run';fake.mkdir();w.write(fake/'workflow.json',dict(stage='exited',creator_wait_verified=True,exit_code=1,
                                execution_mode='require_escalated',remaining=0,build=str(build),job=config['job'],scope=scope))
                            rejections['temporary-claims-as-real-failure']=reject(lambda:consumer.collect_failure(fake))
                    else:
                        b.require(row['loop']['success'] is False,'failure promoted')
                        failed[name]=consumer.analyze_failure(host,build,job=config['job'],simulation=True,require_after_off=True)
                        rejections[name+'-failure-as-real']=reject(lambda:consumer.analyze_failure(host,build,job=config['job'],simulation=False,require_after_off=True))
                    shutil.rmtree(model)
            finally:shutil.copytree(cases,out/'cases')
        b.require(b.sources()==hashes and b.base.base.prior.protected()==before and not b.FORMAL_ROOT.exists(),'protected source/authority drift')
        # Check the production orchestration links without consuming or spawning.
        main=w.plain(build/'generated/live_main.m').decode();workflow=w.plain(build/'generated/workflow.py').decode()
        b.require('[loop configureCompletionQueue:queue]' in main and 'A23CompletionExitAllowed(s,coordinator.queueGuardResult,coordinator.terminalGuardResult)' in main and
            '@"success_scope":@"historical_completion_sample"' in main,'production completion gate missing')
        b.require(workflow.index('engine.consume(job.name)')<workflow.index('child=subprocess.Popen') and 'collect_failure(run)' in workflow and
            'child.wait(timeout=0.5)' in workflow,'production lifecycle binding missing')
        w.write(out/'source-hashes.json',hashes);w.write(out/'protected-before.json',before)
        w.write(out/'report.json',dict(schema='A23-live132-q1-preparation-review-1',source_count=672,old668_unchanged=True,cases=matrix,
            accepted_models=accepted,failure_models=failed,rejections=rejections,snapshot_sizes=sizes,preview=preview,file_modes=modes,
            native_compiler_jobs=2,native_fixture_processes=len(done),file_mode_processes=4,preview_native_file_checks=1,
            creator_wait_verified=True,model_namespaces=len(done),sdk_capable_entry_implemented=True,
            actual_sdk_capture_tested=False,current_unsandboxed_context_checked=False,launch_plan_prepared=False,
            formal_namespaces_added=0,formal_ranges=0,formal_authorizations=0,actual_records_created=0,
            real_sdk_objects=0,usb_requests=0,sd_accesses=0,acquisition_enabled=False,remaining=0,
            callback_drain_verified=False,buffer_reuse_verified=False,continuous_streaming_verified=False))
        w.b.seal(out);return dict(directory=str(out),seal=b.base.base.base.core.verify_seal(out),cases=len(done),rejections=len(rejections))
    except BaseException as e:
        w.write(out/'failure.json',dict(error=str(e),completed=done));w.b.seal(out);raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);print(json.dumps(run(p.parse_args().output)))
