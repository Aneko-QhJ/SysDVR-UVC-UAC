"""Temporary-root tests of real three-round entry/scope/permit/export wiring."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
import build_a23_live97_three as b
import a23_live97_three_workflow as flow
import audit_a23_live91_checked as old_audit
from a23_sequence32_model import sha,require
w=b.w
CASES=('normal','queued-delay','bad-status','third-bad-status','exit-running','stale-getters','after-payload-bytes','after-receipt-bytes','acceptance-collision','spent145-drift','spent145-extra','spent145-missing','source623-pre','baseline97-pre','between-third-source','third-status-collision','old32-permit','range32-permit','count32-reservation')
ARCHIVES=('frozen-source','frozen-spent145','generated','binary')

def fixture(source):
    # Parent fixture already exercises real native scope/permit/coordinator.
    b.core.verify_seal(b.LIVE.parent)
    raw=(b.LIVE.parent/'native/source/research/usb-ds-iso/tests/generated_live91_fixture.m').read_text()
    raw=b.rebase(raw).replace('#import "../host/','#import "')
    raw=raw.replace('_submissions<2','_submissions<3').replace('_triggers<2','_triggers<3').replace('145+_triggers*16','177+_triggers*16').replace('145+n*16','177+n*16').replace('n<4 && length','n<6 && length').replace('n<2;++n','n<3;++n').replace('r.submissions<=2 && r.triggers<=2','r.submissions<=3 && r.triggers<=3')
    raw=b.c.change(raw,'_isoCallbacks=[NSMutableArray new];','_dataStores=[_dataStores arrayByAddingObject:[NSMutableData dataWithLength:184320]];_transactionStores=[_transactionStores arrayByAddingObject:[NSMutableData dataWithLength:26880]];_isoCallbacks=[NSMutableArray new];')
    raw=raw.replace('20261022-live75-first-read',b.ANCHOR.name).replace('source611-pre','source623-pre').replace('baseline91-pre','baseline97-pre')
    raw=b.c.change(raw,'if(!n)dispatch_sync(q,^{','if(n<2)dispatch_sync(q,^{')
    raw=b.c.change(raw,'if(!initial){','if([name isEqual:@"old32-permit"]){\n        NSMutableDictionary *wrong=[v.scope mutableCopy];wrong[@"schema"]=@"A23-live91-checked-shared32-scope-1";A23SharedSequenceModelPermit *p=[[A23SharedSequenceModelPermit alloc] initWithJob:c[@"job"] expectedScope:wrong verifier:^BOOL(NSDictionary *s){return [v verifyLiveJob:s job:c[@"job"]];}];assert(!p);initial=NO;\n    }\n    if(!initial){')
    raw=b.c.change(raw,'if(!initial){',r'''if([name isEqual:@"range32-permit"] || [name isEqual:@"count32-reservation"]){
        NSMutableDictionary *wrong=[v.scope mutableCopy];if([name isEqual:@"range32-permit"])wrong[@"last_sequence"]=@208;
        A23SharedSequenceModelPermit *p=[[A23SharedSequenceModelPermit alloc] initWithJob:c[@"job"] expectedScope:wrong verifier:^BOOL(NSDictionary *s){return [v verifyLiveJob:s job:c[@"job"]];}];assert(!p);initial=NO;
    }
    if(!initial){'''.replace('\\"','"'))
    raw=b.c.change(raw,'[loop tick];BOOL pre=',r'''if([name isEqual:@"spent145-drift"])change([[prior stringByAppendingPathComponent:@"spent145"] stringByAppendingPathComponent:@"block-00145.json"]);
        if([name isEqual:@"spent145-extra"])change([[prior stringByAppendingPathComponent:@"spent145"] stringByAppendingPathComponent:@"extra"]);
        if([name isEqual:@"spent145-missing"])assert([[NSFileManager defaultManager] removeItemAtPath:[[prior stringByAppendingPathComponent:@"spent145"] stringByAppendingPathComponent:@"block-00145.json"] error:NULL]);
        [loop tick];BOOL pre='''.replace('\\"','"'))
    raw=raw.replace('@"spent113-drift",@"spent113-extra",@"spent113-missing",@"source623-pre",@"baseline97-pre",@"new-recovery"] containsObject:name]', '@"spent113-drift",@"spent113-extra",@"spent113-missing",@"spent145-drift",@"spent145-extra",@"spent145-missing",@"source623-pre",@"baseline97-pre",@"new-recovery"] containsObject:name]')
    raw=b.c.change(raw,'[loop tick];});\n        }','if(n==1 && [name isEqual:@"between-third-source"])change([c[@"repository"] stringByAppendingPathComponent:@"research/usb-ds-iso/tools/build_a23_live97_three.py"]);\n            if(n==1 && [name isEqual:@"third-status-collision"])assert([[NSFileManager defaultManager] createDirectoryAtPath:[host stringByAppendingPathComponent:@"status-after-epoch-2"] withIntermediateDirectories:NO attributes:nil error:NULL]);[loop tick];});\n        }')
    raw=b.c.change(raw,'if([self.fault isEqual:@"bad-status"] && self.statusReads==2)s->transferred=0;','if(([self.fault isEqual:@"bad-status"] && self.statusReads==2) || ([self.fault isEqual:@"third-bad-status"] && self.statusReads==6))s->transferred=0;')
    return raw

def run(out):
    out=w.canonical(out);require(not out.exists() and not b.FORMAL_ROOT.exists(),'new unissued review required');hashes=b.sources();out.mkdir(mode=0o700);completed=[]
    try:
        build=out/'build';b.build(build);scope=b.runtime_scope(build);engine=flow.engine_module(build)
        native=out/'native';shutil.copytree(build,native);target=native/'generated/model_fixture.m';target.write_text(fixture(native/'source'))
        cmd=b.command(native,target);p=subprocess.run(cmd,capture_output=True,timeout=60);w.card.put(out,'fixture-compile.log',p.stdout+p.stderr);w.write(out/'fixture-compile.json',dict(command=cmd,returncode=p.returncode));require(p.returncode==0,'three fixture compilation failed')
        modes={};replays={}
        for name,args,code in [('describe',['--describe'],0),('archive',['--check-archive',str(build)],0),('current',['--check-build',str(build)],0),('unissued',['--acquire-once',str(build),'/nonexistent','/nonexistent'],2)]:
            p=subprocess.run([str(build/'verified-entry'),*args],capture_output=True,timeout=30);w.card.put(out,name+'.stdout',p.stdout);w.card.put(out,name+'.stderr',p.stderr);require(p.returncode==code,'file mode failed '+name);modes[name]=dict(returncode=p.returncode)
            if name=='current':require(json.loads(p.stdout)['scope']==scope,'native/Python scope differs')
        try:flow.issue(build,authorized=False)
        except ValueError:replays['unauthorized_issue']=True
        else:raise ValueError('missing authorization accepted')
        matrix={};accepted={};reject_clock={};collector_rejections={}
        with tempfile.TemporaryDirectory(prefix='a23-live97-',dir='/private/tmp') as temp:
            scratch=Path(temp);template=scratch/'template';old_audit.template(build,template);shutil.copytree(build/'history/spent145',template/'spent145')
            cases=scratch/'cases';cases.mkdir()
            try:
                for name in CASES+ARCHIVES:
                    case=cases/name;case.mkdir();host=case/'host';host.mkdir();store=engine.SharedSequence48(case/'namespace',simulation=True,fresh_scope=lambda:scope);store.initialize(b.inputs()[4]);job=flow.implementation(build).prepare_job(store);store.issue(job);store.consume(job)
                    current=scratch/'current';current_build=scratch/'current-build';shutil.copytree(template,current);shutil.copytree(build,current_build)
                    config=dict(case=name,build=str(current_build),host=str(host),repository=str(current/'repository'),cards=str(current/'cards'),ledger=str(current/'ledger'),records=str(current/'records'),job=str(store.root/'jobs'/job),binding=store.binding(job));w.write(case/'config.json',config)
                    if name=='count32-reservation':
                        p=store.root/'block-00177.json';v=w.load(p);v['count']=32;p.write_bytes(b.old.encode(v))
                    if name=='frozen-source':(current_build/'source/research/usb-ds-iso/tools/build_a23_live97_three.py').write_text('changed')
                    if name=='frozen-spent145':(current_build/'history/spent145/block-00145.json').write_text('changed')
                    if name=='generated':(current_build/'generated/live_permit.m').write_text('changed')
                    if name=='binary':(current_build/'verified-entry').write_bytes(b'changed')
                    p=subprocess.run([str(native/'live-fixture'),str(case/'config.json')],capture_output=True,timeout=60);w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr);w.write(case/'process.json',dict(returncode=p.returncode,creator_wait_completed=True));require(p.returncode==0 and not p.stderr,'native failed '+name);row=json.loads(p.stdout);matrix[name]=row
                    if name in ('normal','queued-delay'):
                        accepted[name]=flow.analyze_host(host,build,simulation=True);require(accepted[name]['sdk']['total_bytes']==9216,'three payload differs')
                        try:flow.analyze_host(host,build,simulation=False)
                        except ValueError:reject_clock[name]=True
                        else:raise ValueError('synthetic clock accepted as real')
                        before={p.relative_to(store.root).as_posix():sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()}
                        foreign=flow.implementation(build).prepare_job(store)
                        # Preparation is allowed; consumption/issuance cannot take over a burned range.
                        before={p.relative_to(store.root).as_posix():sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()}
                        for kind,call in [('consume',lambda:store.consume(job)),('takeover',lambda:store.issue(foreign))]:
                            try:call()
                            except (ValueError,OSError):replays[name+'/'+kind]=True
                            else:raise ValueError('replay accepted')
                        require(before=={p.relative_to(store.root).as_posix():sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()},'replay changed namespace')
                    elif name=='after-receipt-bytes':
                        require(row['loop']['success'] is True,'post-receipt counterexample missing')
                        try:flow.analyze_host(host,build,simulation=True)
                        except ValueError as e:collector_rejections[name]=str(e)
                        else:raise ValueError('changed accepted payload promoted')
                    elif name in ARCHIVES or name in ('old32-permit','range32-permit','count32-reservation'):require(row['initial_core'] is False and row['calls']['opens']==0,'rejected input opened SDK')
                    else:require(row['loop']['success'] is False,'failure promoted')
                    completed.append(name);shutil.rmtree(current);shutil.rmtree(current_build)
            finally:shutil.copytree(cases,out/'cases')
        require(b.sources()==hashes and not b.FORMAL_ROOT.exists(),'real source or namespace drift')
        w.write(out/'report.json',dict(schema='A23-live97-three-audit-1',passed=True,source_count=623,source_hashes=hashes,completed=completed,matrix=matrix,accepted=accepted,synthetic_clock_rejected=reject_clock,file_modes=modes,replay_rejections=replays,collector_rejections=collector_rejections,formal_reservations=0,new_authorizations=0,usb_requests=0,sd_accesses=0,real_sdk_objects=0,remaining=0))
    except BaseException as e:
        w.write(out/'failure.json',dict(error=str(e),completed=completed));w.b.seal(out);raise
    w.b.seal(out);return dict(directory=str(out),manifest_sha256=sha(w.plain(out/'SHA256SUMS')),native_cases=len(completed),passed=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
