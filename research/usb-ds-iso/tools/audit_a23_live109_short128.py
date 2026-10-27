"""Fixed128/current109 integration: injected SDK, temporary roots only."""
import argparse,json,shutil,subprocess,tempfile
from pathlib import Path
import build_a23_live109_short128 as b
import a23_live109_short128_workflow as flow
import audit_a23_live103_interest as parent
import audit_a23_live97_three as prior
w=b.w;require=b.require
INTEREST={k:parent.INTEREST[k] for k in ('interest-close','interest-open','interest-overflow')}
PROBES=tuple('owner-'+part+'-'+str(n) for part in ('raw','rows') for n in (127,129,960))+tuple('lease-count-'+str(n) for n in (127,129,960))
SUCCESS=('normal','tail128','queued-delay')
CASES=SUCCESS+PROBES+('packet15','packet17','row-error','duplicate-iso','foreign-pointer','third-bad-status','between-third-source','spent225-drift','spent225-extra','spent225-missing','source636-pre','baseline109-pre','old225-scope','count32-reservation','after-receipt-bytes',*INTEREST)
ARCHIVES=('frozen-source','frozen-spent225','generated','binary')

def fixture(source):
    raw=b.narrow(b.rebase(parent.fixture(source))).replace('225+_triggers*16','273+_triggers*16').replace('225+n*16','273+n*16').replace('source632-pre','source636-pre').replace('baseline103-pre','baseline109-pre').replace(b.base.ANCHOR.name,b.ANCHOR.name).replace('@256','@304')
    raw=raw.replace('n*120','start').replace('research/usb-ds-iso/host/a23_checked_export.m','research/usb-ds-iso/tools/a23_live109_short128_workflow.py').replace('research/usb-ds-iso/tools/build_a23_live97_three.py','research/usb-ds-iso/tools/build_a23_live109_short128.py')
    raw=b.c.change(raw,'for(unsigned i=0;i<128;++i){rows[i].status=0;', 'unsigned start=[_fault isEqual:@"tail128"]?112:(unsigned)n*8;unsigned packets=[_fault isEqual:@"packet15"]?15:([_fault isEqual:@"packet17"]?17:16);\n    for(unsigned i=0;i<128;++i){rows[i].status=0;')
    raw=raw.replace('i<start+16','i<start+packets').replace('for(unsigned p=0;p<16;++p)','for(unsigned p=0;p<packets;++p)')
    raw=b.c.change(raw,'if([_fault isEqual:@"bad-payload"]','if([_fault isEqual:@"row-error"])rows[127].status=kIOReturnError;\n    if([_fault isEqual:@"bad-payload"]')
    raw=b.c.change(raw,'if(!initial){',r'''if([name isEqual:@"old225-scope"]){NSMutableDictionary *s=[v.scope mutableCopy];s[@"schema"]=@"A23-live103-interest-shared48-scope-1";s[@"first_sequence"]=@225;s[@"last_sequence"]=@272;
        A23SharedSequenceModelPermit *p=[[A23SharedSequenceModelPermit alloc] initWithJob:c[@"job"] expectedScope:s verifier:^BOOL(NSDictionary *scope){return [v verifyLiveJob:scope job:c[@"job"]];}];assert(!p);initial=NO;}
    if(!initial){''')
    raw=b.c.change(raw,'    PairOperations *op=pairOperations(name,NO);',r'''    if([name hasPrefix:@"owner-"] || [name hasPrefix:@"lease-count-"]){
        NSUInteger count=[[name componentsSeparatedByString:@"-"] lastObject].intValue;
        dispatch_queue_t queue=dispatch_queue_create("a23.short128.dimensions",DISPATCH_QUEUE_SERIAL);
        __block NSDictionary *result=@{};__block NSUInteger submissions=0,opens=0;
        dispatch_sync(queue,^{
            if([name hasPrefix:@"owner-"]){
                NSMutableData *data=[NSMutableData dataWithLength:([name hasPrefix:@"owner-raw-"]?count:128)*192];
                NSMutableData *rows=[NSMutableData dataWithLength:([name hasPrefix:@"owner-rows-"]?count:128)*28];
                assert(![[A23TransactionOwner alloc] initWithData:data transactions:rows queue:queue]);
            }else{
                PairOperations *operations=pairOperations(@"dimensions",NO);
                A23TripleSimulationProvider *provider=pairProvider(operations,queue,YES,^(uint32_t m){(void)m;});
                id<A23TripleResources> lease=[provider openCandidate:pairCandidate() error:NULL];assert(lease);
                A23TransactionOwner *owner=[[A23TransactionOwner alloc] initWithData:lease.dataStores[0] transactions:lease.transactionStores[0] queue:queue];assert(owner);
                assert([[lease readStatus][@"data"] length]==168);NSDictionary *frame=[lease readFrameSample];assert(frame.count);
                assert(![lease.transport enqueueIORequestWithData:lease.dataStores[0] transactionList:lease.transactionStores[0].mutableBytes transactionListCount:count firstFrameNumber:[frame[@"current_frame"] unsignedLongLongValue]+32 options:0 error:NULL completionHandler:^(IOReturn s,IOUSBHostIsochronousTransaction *p){(void)s;(void)p;assert(0);}]);
                result=lease.result;submissions=operations.interface.submissions;opens=operations.opens;assert(opens==1);assert([result[@"poisoned"] boolValue] && !submissions);
            }
        });
        NSDictionary *row=@{@"probe_rejected":@YES,@"count":@(count),@"lease_result":result,@"calls":@{@"iso_submissions":@(submissions),@"opens":@(opens)}};
        NSData *data=[NSJSONSerialization dataWithJSONObject:row options:0 error:NULL];fwrite(data.bytes,1,data.length,stdout);puts("");return 0;
    }
    PairOperations *op=pairOperations(name,NO);''')
    raw=b.c.change(raw,'[loop tick];BOOL pre=',r'''if([name isEqual:@"spent225-drift"])change([[prior stringByAppendingPathComponent:@"spent225"] stringByAppendingPathComponent:@"block-00225.json"]);
        if([name isEqual:@"spent225-extra"])change([[prior stringByAppendingPathComponent:@"spent225"] stringByAppendingPathComponent:@"extra"]);
        if([name isEqual:@"spent225-missing"])assert([[NSFileManager defaultManager] removeItemAtPath:[[prior stringByAppendingPathComponent:@"spent225"] stringByAppendingPathComponent:@"block-00225.json"] error:NULL]);
        [loop tick];BOOL pre=''')
    raw=raw.replace('@"source636-pre",@"baseline109-pre",@"new-recovery",@"interest-open"] containsObject:name]','@"source636-pre",@"baseline109-pre",@"new-recovery",@"interest-open",@"spent225-drift",@"spent225-extra",@"spent225-missing"] containsObject:name]')
    raw=raw.replace('@"normal",@"queued-delay",@"after-post-source",@"after-receipt-bytes"','@"normal",@"tail128",@"queued-delay",@"after-post-source",@"after-receipt-bytes"')
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
        with tempfile.TemporaryDirectory(prefix='a23-live109-short128-',dir='/private/tmp') as temp:
            scratch=Path(temp);template=scratch/'template';prior.old_audit.template(build,template);shutil.copytree(build/'history/spent145',template/'spent145');shutil.copytree(build/'history/spent177',template/'spent177');shutil.copytree(build/'history/spent225',template/'spent225');cases=scratch/'cases';cases.mkdir()
            try:
                for name in CASES+ARCHIVES:
                    case=cases/name;case.mkdir();host=case/'host';host.mkdir();store=engine.SharedSequence48(case/'namespace',simulation=True,fresh_scope=lambda:scope);store.initialize(history);job=flow.implementation(build).prepare_job(store);store.issue(job);store.consume(job)
                    current=scratch/'current';current_build=scratch/'current-build';shutil.copytree(template,current);shutil.copytree(build,current_build)
                    config=dict(case=name,build=str(current_build),host=str(host),repository=str(current/'repository'),cards=str(current/'cards'),ledger=str(current/'ledger'),records=str(current/'records'),job=str(store.root/'jobs'/job),binding=store.binding(job));w.write(case/'config.json',config)
                    if name=='count32-reservation':
                        p=store.root/'block-00273.json';v=w.load(p);v['count']=32;p.write_bytes(b.encode(v))
                    if name=='frozen-source':(current_build/'source/research/usb-ds-iso/tools/build_a23_live109_short128.py').write_text('changed')
                    if name=='frozen-spent225':(current_build/'history/spent225/block-00225.json').write_text('changed')
                    if name=='generated':(current_build/'generated/live_adapter.m').write_text('changed')
                    if name=='binary':(current_build/'verified-entry').write_bytes(b'changed')
                    p=subprocess.run([str(native/'live-fixture'),str(case/'config.json')],capture_output=True,timeout=60);w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr);w.write(case/'process.json',dict(returncode=p.returncode,creator_wait_completed=True));require(p.returncode==0 and not p.stderr,'native failed '+name);row=json.loads(p.stdout);matrix[name]=row
                    if name in SUCCESS:
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
                    elif name in PROBES:
                        require(row['probe_rejected'] is True and row['calls']['iso_submissions']==0,'dimension probe forwarded')
                    elif name in INTEREST:
                        require(row['calls']['iso_submissions']==(0 if name=='interest-open' else 2) and row['loop']['success'] is False,'interest did not stop at expected boundary')
                        if name=='interest-off-collision':
                            require(row['loop']['interest_after_off_attempted'] is True and row['loop']['interest_after_off_saved'] is False,'collision not reported')
                            try:flow.analyze_failure(host,build,require_after_off=True)
                            except (ValueError,OSError) as e:rejected[name]=str(e)
                            else:raise ValueError('missing supplementary evidence accepted')
                        else:
                            failures[name]=flow.analyze_failure(host,build,require_after_off=True);require(failures[name]['initial_trace']['message_values'][0]==INTEREST[name],'raw message changed')
                    elif name in ARCHIVES or name in ('count32-reservation','old225-scope'):require(row['initial_core'] is False and row['calls']['opens']==0,'bad input opened SDK')
                    elif name=='after-receipt-bytes':
                        require(row['loop']['success'] is True,'late payload counterexample missing')
                        try:flow.analyze_host(host,build,simulation=True)
                        except ValueError as e:rejected[name]=str(e)
                        else:raise ValueError('changed payload accepted')
                    else:
                        require(row['loop']['success'] is False,'failure promoted')
                        if name in ('packet15','packet17','row-error','duplicate-iso','foreign-pointer'):require(row['calls']['iso_submissions']==1,'malformed payload continued')
                    done.append(name);shutil.rmtree(current);shutil.rmtree(current_build)
            finally:shutil.copytree(cases,out/'cases')
        host=out/'cases/interest-close/host';negative=out/'after-off-prefix-negative';shutil.copytree(host,negative);folder=negative/'interest-after-power-off'
        state=w.load(folder/'result.json');state['lease']['interest_trace']['rows'][0]['message_u32']=123
        entry=w.load(folder/'entry-current.json');entry['driver']=state;(folder/'result.json').write_bytes(b.encode(state));(folder/'entry-current.json').write_bytes(b.encode(entry));b.core.seal(folder)
        try:flow.analyze_failure(negative,build,require_after_off=True)
        except ValueError as e:rejected['after-off-prefix']=str(e)
        else:raise ValueError('changed immutable prefix accepted')
        for kind in ('raw960','rows960'):
            path=out/('negative-'+kind);shutil.copytree(out/'cases/normal/host',path);epoch=path/'epoch-0';name='raw.bin' if kind=='raw960' else 'transactions.bin';data=(epoch/name).read_bytes();(epoch/name).write_bytes(data+bytes((184320 if kind=='raw960' else 26880)-len(data)));b.core.seal(epoch)
            try:flow.analyze_host(path,build,simulation=True)
            except ValueError as error:rejected[kind]=str(error)
            else:raise ValueError('old960 archive size accepted '+kind)
        try:b.base.verify(build,current=False)
        except ValueError as error:rejected['old103-build-consumer']=str(error)
        else:raise ValueError('old103 consumer accepted new109 build')
        require(b.sources()==hashes and not b.FORMAL_ROOT.exists(),'real sources/namespace changed')
        w.write(out/'report.json',dict(schema='A23-live109-short128-audit-1',passed=True,source_count=636,source_hashes=hashes,completed=done,matrix=matrix,accepted=accepted,interest_failures=failures,rejections=rejected,replay_rejections=replays,file_modes=modes,first_sequence=273,last_sequence=320,formal_reservations=0,new_authorizations=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,remaining=0))
    except BaseException as e:
        w.write(out/'failure.json',dict(error=str(e),completed=done));w.b.seal(out);raise
    w.b.seal(out);return dict(directory=str(out),manifest_sha256=b.core.verify_seal(out),native_cases=len(done),passed=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
