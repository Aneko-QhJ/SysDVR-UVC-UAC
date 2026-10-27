"""Bounded fresh103 wiring checks; only temporary namespaces and injected SDK."""
import argparse,json,shutil,subprocess,tempfile
from pathlib import Path
import build_a23_live103_interest as b
import a23_live103_interest_workflow as flow
import audit_a23_live97_three as prior
w=b.w;require=b.require
INTEREST={'interest-terminated':0xe0000010,'interest-close':0xe0005003,'interest-configuration':0xe0005000,'interest-unknown':0xffffffff,'interest-zero':0,'interest-overflow':0x12345678,'interest-off-collision':0xe0005003,'interest-open':99}
CASES=('normal','queued-delay','third-bad-status','between-third-source','spent177-drift','spent177-extra','spent177-missing','source632-pre','baseline103-pre','old32-permit','range32-permit','count32-reservation','old177-scope','after-payload-bytes','after-receipt-bytes',*INTEREST)
ARCHIVES=('frozen-source','frozen-spent177','generated','binary')

def fixture(source):
    raw=prior.fixture(source);raw=b.rebase(raw).replace('177+_triggers*16','225+_triggers*16').replace('177+n*16','225+n*16').replace('source623-pre','source632-pre').replace('baseline97-pre','baseline103-pre').replace(b.base.ANCHOR.name,b.ANCHOR.name).replace('@208','@256')
    raw='#include <IOKit/IOMessage.h>\n#include <IOKit/usb/IOUSBHostFamilyDefinitions.h>\n'+raw
    raw=b.base.c.change(raw,'^(uint32_t m){(void)m;[entry detachedRegistryID:102];}','^(uint32_t m){if(m==kIOMessageServiceIsTerminated)[entry requestExit];}')
    raw=b.base.c.change(raw,'if(!initial){',r'''if([name isEqual:@"old177-scope"]){NSMutableDictionary *s=[v.scope mutableCopy];s[@"schema"]=@"A23-live97-three-shared48-scope-1";s[@"first_sequence"]=@177;s[@"last_sequence"]=@224;
        A23SharedSequenceModelPermit *p=[[A23SharedSequenceModelPermit alloc] initWithJob:c[@"job"] expectedScope:s verifier:^BOOL(NSDictionary *scope){return [v verifyLiveJob:scope job:c[@"job"]];}];assert(!p);initial=NO;}
    if(!initial){''')
    raw=b.base.c.change(raw,'[loop tick];BOOL pre=',r'''if([name isEqual:@"spent177-drift"])change([[prior stringByAppendingPathComponent:@"spent177"] stringByAppendingPathComponent:@"block-00177.json"]);
        if([name isEqual:@"spent177-extra"])change([[prior stringByAppendingPathComponent:@"spent177"] stringByAppendingPathComponent:@"extra"]);
        if([name isEqual:@"spent177-missing"])assert([[NSFileManager defaultManager] removeItemAtPath:[[prior stringByAppendingPathComponent:@"spent177"] stringByAppendingPathComponent:@"block-00177.json"] error:NULL]);
        [loop tick];BOOL pre=''')
    raw=b.base.c.change(raw,'@"spent145-drift",@"spent145-extra",@"spent145-missing",@"source632-pre"','@"spent145-drift",@"spent145-extra",@"spent145-missing",@"spent177-drift",@"spent177-extra",@"spent177-missing",@"source632-pre"')
    raw=b.base.c.change(raw,'@"source632-pre",@"baseline103-pre",@"new-recovery"] containsObject:name]','@"source632-pre",@"baseline103-pre",@"new-recovery",@"interest-open"] containsObject:name]')
    anchor='if(n==1 && [name isEqual:@"between-third-source"])'
    inject='''if(n==1 && [name hasPrefix:@"interest-"]){NSDictionary *messages=VALUES;unsigned count=[name isEqual:@"interest-overflow"]?10:1;for(unsigned i=0;i<count;++i)r.interest([messages[name] unsignedIntValue]);}
            '''
    values='@{'+','.join('@"'+name+'":@'+str(v) for name,v in INTEREST.items())+'}'
    raw=b.base.c.change(raw,anchor,inject.replace('VALUES',values)+anchor)
    raw=b.base.c.change(raw,'NSDictionary *before=v.cadenceMetrics;NSUInteger submissions=r.submissions;',r'''if([name hasPrefix:@"interest-"]){
            if([name isEqual:@"interest-off-collision"])assert([[NSFileManager defaultManager] createDirectoryAtPath:[host stringByAppendingPathComponent:@"interest-after-power-off"] withIntermediateDirectories:NO attributes:nil error:NULL]);
            assert([loop.status[@"unresolved_keep_alive"] boolValue]);assert([loop finishAfterOperatorPowerOff]);
        }
        NSDictionary *before=v.cadenceMetrics;NSUInteger submissions=r.submissions;''')
    return raw

def run(out):
    out=w.canonical(out);require(not out.exists() and not b.FORMAL_ROOT.exists(),'new unissued103 review required');hashes=b.sources();out.mkdir(mode=0o700);done=[]
    try:
        build=out/'build';b.build(build);scope=b.runtime_scope(build);engine=flow.engine_module(build);history=b.inputs()[4]
        native=out/'native';shutil.copytree(build,native);target=native/'generated/model_fixture.m';target.write_text(fixture(native/'source'));cmd=b.command(native,target);p=subprocess.run(cmd,capture_output=True,timeout=60);w.card.put(out,'fixture-compile.log',p.stdout+p.stderr);w.write(out/'fixture-compile.json',dict(command=cmd,returncode=p.returncode));require(p.returncode==0,'103 fixture compile failed')
        modes={}
        for name,args,code in [('describe',['--describe'],0),('archive',['--check-archive',str(build)],0),('current',['--check-build',str(build)],0),('unissued',['--acquire-once',str(build),'/nonexistent','/nonexistent'],2)]:
            p=subprocess.run([str(build/'verified-entry'),*args],capture_output=True,timeout=30);w.card.put(out,name+'.stdout',p.stdout);w.card.put(out,name+'.stderr',p.stderr);w.write(out/(name+'.process.json'),dict(returncode=p.returncode,creator_wait_completed=True));require(p.returncode==code,'file mode failed '+name);modes[name]=dict(returncode=p.returncode)
            if name=='current':require(json.loads(p.stdout)['scope']==scope,'native/Python scope mismatch')
        replays={}
        try:flow.issue(build,authorized=False)
        except ValueError:replays['unauthorized']=True
        else:raise ValueError('missing authorization accepted')
        matrix={};accepted={};failures={};rejected={}
        with tempfile.TemporaryDirectory(prefix='a23-live103-',dir='/private/tmp') as temp:
            scratch=Path(temp);template=scratch/'template';prior.old_audit.template(build,template);shutil.copytree(build/'history/spent145',template/'spent145');shutil.copytree(build/'history/spent177',template/'spent177');cases=scratch/'cases';cases.mkdir()
            try:
                for name in CASES+ARCHIVES:
                    case=cases/name;case.mkdir();host=case/'host';host.mkdir();store=engine.SharedSequence48(case/'namespace',simulation=True,fresh_scope=lambda:scope);store.initialize(history);job=flow.implementation(build).prepare_job(store);store.issue(job);store.consume(job)
                    current=scratch/'current';current_build=scratch/'current-build';shutil.copytree(template,current);shutil.copytree(build,current_build)
                    config=dict(case=name,build=str(current_build),host=str(host),repository=str(current/'repository'),cards=str(current/'cards'),ledger=str(current/'ledger'),records=str(current/'records'),job=str(store.root/'jobs'/job),binding=store.binding(job));w.write(case/'config.json',config)
                    if name=='count32-reservation':
                        p=store.root/'block-00225.json';v=w.load(p);v['count']=32;p.write_bytes(b.encode(v))
                    if name=='frozen-source':(current_build/'source/research/usb-ds-iso/tools/build_a23_live103_interest.py').write_text('changed')
                    if name=='frozen-spent177':(current_build/'history/spent177/block-00177.json').write_text('changed')
                    if name=='generated':(current_build/'generated/live_adapter.m').write_text('changed')
                    if name=='binary':(current_build/'verified-entry').write_bytes(b'changed')
                    p=subprocess.run([str(native/'live-fixture'),str(case/'config.json')],capture_output=True,timeout=60);w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr);w.write(case/'process.json',dict(returncode=p.returncode,creator_wait_completed=True));require(p.returncode==0 and not p.stderr,'native failed '+name);row=json.loads(p.stdout);matrix[name]=row
                    if name in ('normal','queued-delay'):
                        accepted[name]=flow.analyze_host(host,build,simulation=True);require(accepted[name]['sdk']['total_bytes']==9216 and accepted[name]['interest_trace']['message_values']==[],'normal trace/payload mismatch')
                        try:flow.analyze_host(host,build,simulation=False)
                        except ValueError:rejected[name+'/synthetic']=True
                        else:raise ValueError('fake clock accepted as real')
                        foreign=flow.implementation(build).prepare_job(store);before={p.relative_to(store.root).as_posix():b.sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()}
                        for kind,call in [('consume',lambda:store.consume(job)),('takeover',lambda:store.issue(foreign))]:
                            try:call()
                            except (ValueError,OSError):replays[name+'/'+kind]=True
                            else:raise ValueError('replay accepted')
                        require(before=={p.relative_to(store.root).as_posix():b.sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()},'replay mutation')
                    elif name in INTEREST:
                        require(row['calls']['iso_submissions']==(0 if name=='interest-open' else 2) and row['loop']['success'] is False,'interest did not stop at expected boundary')
                        if name=='interest-off-collision':
                            require(row['loop']['interest_after_off_attempted'] is True and row['loop']['interest_after_off_saved'] is False,'collision not reported')
                            try:flow.analyze_failure(host,build,require_after_off=True)
                            except (ValueError,OSError) as e:rejected[name]=str(e)
                            else:raise ValueError('missing supplementary evidence accepted')
                        else:
                            failures[name]=flow.analyze_failure(host,build,require_after_off=True);require(failures[name]['initial_trace']['message_values'][0]==INTEREST[name],'raw message changed')
                    elif name in ARCHIVES or name in ('old32-permit','range32-permit','count32-reservation','old177-scope'):require(row['initial_core'] is False and row['calls']['opens']==0,'bad input opened SDK')
                    elif name=='after-receipt-bytes':
                        require(row['loop']['success'] is True,'late payload counterexample missing')
                        try:flow.analyze_host(host,build,simulation=True)
                        except ValueError as e:rejected[name]=str(e)
                        else:raise ValueError('changed payload accepted')
                    else:require(row['loop']['success'] is False,'failure promoted')
                    done.append(name);shutil.rmtree(current);shutil.rmtree(current_build)
            finally:shutil.copytree(cases,out/'cases')
        host=out/'cases/interest-close/host';negative=out/'after-off-prefix-negative';shutil.copytree(host,negative);folder=negative/'interest-after-power-off'
        state=w.load(folder/'result.json');state['lease']['interest_trace']['rows'][0]['message_u32']=123
        entry=w.load(folder/'entry-current.json');entry['driver']=state;(folder/'result.json').write_bytes(b.encode(state));(folder/'entry-current.json').write_bytes(b.encode(entry));b.base.core.seal(folder)
        try:flow.analyze_failure(negative,build,require_after_off=True)
        except ValueError as e:rejected['after-off-prefix']=str(e)
        else:raise ValueError('changed immutable prefix accepted')
        require(b.sources()==hashes and not b.FORMAL_ROOT.exists(),'real sources/namespace changed')
        w.write(out/'report.json',dict(schema='A23-live103-interest-audit-1',passed=True,source_count=632,source_hashes=hashes,completed=done,matrix=matrix,accepted=accepted,interest_failures=failures,rejections=rejected,replay_rejections=replays,file_modes=modes,first_sequence=225,last_sequence=272,formal_reservations=0,new_authorizations=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,remaining=0))
    except BaseException as e:
        w.write(out/'failure.json',dict(error=str(e),completed=done));w.b.seal(out);raise
    w.b.seal(out);return dict(directory=str(out),manifest_sha256=b.base.core.verify_seal(out),native_cases=len(done),passed=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
