"""Only current91/145 rebase, checked-export and spent-history wiring checks."""
import argparse,json,shutil,subprocess,tempfile
from pathlib import Path
import build_a23_live91_checked as builder
import a23_live91_checked_workflow as flow
import audit_a23_checked_export as old
from a23_sequence32_model import sha,require
w=builder.w
CASES=('normal','queued-delay','bad-status','exit-running','stale-getters','after-payload-bytes','acceptance-collision',
       'spent113-drift','spent113-extra','spent113-missing','source611-pre','baseline91-pre','new-recovery','between-source611')
ARCHIVES=('frozen-source','binary','resealed-source','frozen-spent113','resealed-generated','descriptor')


def fixture(source):
    raw=builder.checked.fixture(source)
    for before,after in [('first==113+_triggers*16','first==145+_triggers*16'),('113+n*16+p','145+n*16+p'),('113+n*16','145+n*16'),
            ('firstSequence:113','firstSequence:145'),('intValue]==113','intValue]==145'),('intValue]==144','intValue]==176')]:
        require(before in raw,'live91 fixture range anchor missing '+before);raw=raw.replace(before,after)
    raw=raw.replace('20261022-live-two-epoch-first-read',builder.ANCHOR.name)
    raw=builder.one(raw,'assert(v && [v verifyCore]);exportVerifier=v;',
        '''assert(v);BOOL initial=[v verifyCore];exportVerifier=v;
    if(!initial){NSDictionary *row=@{@"initial_core":@NO,@"calls":@{@"iso_submissions":@0,@"burst_triggers":@0,@"sdk_destroys":@0,@"opens":@0},@"usb_requests":@0,@"real_sdk_objects":@0};
        NSData *raw=[NSJSONSerialization dataWithJSONObject:row options:0 error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;}''')
    raw=builder.one(raw,'[loop tick];[loop tick];assert(r.submissions==1);',
        '''[loop tick];
        NSString *prior=[c[@"records"] stringByDeletingLastPathComponent];
        if([name isEqual:@"spent113-drift"])change([[prior stringByAppendingPathComponent:@"spent113"] stringByAppendingPathComponent:@"block-00113.json"]);
        if([name isEqual:@"spent113-extra"])change([[prior stringByAppendingPathComponent:@"spent113"] stringByAppendingPathComponent:@"unexpected"]);
        if([name isEqual:@"spent113-missing"])assert([[NSFileManager defaultManager] removeItemAtPath:[[prior stringByAppendingPathComponent:@"spent113"] stringByAppendingPathComponent:@"block-00113.json"] error:NULL]);
        if([name isEqual:@"source611-pre"])change([c[@"repository"] stringByAppendingPathComponent:@"research/usb-ds-iso/host/a23_checked_export.m"]);
        if([name isEqual:@"baseline91-pre"])change([[c[@"cards"] stringByAppendingPathComponent:@"20261022-live75-first-read"] stringByAppendingPathComponent:@"card/logfile.txt"]);
        if([name isEqual:@"new-recovery"]){NSString *p=[c[@"cards"] stringByAppendingPathComponent:@"later"];assert([[NSFileManager defaultManager] createDirectoryAtPath:p withIntermediateDirectories:NO attributes:nil error:NULL]);change([p stringByAppendingPathComponent:@"snapshot.json"]);}
        [loop tick];BOOL pre=[@[@"spent113-drift",@"spent113-extra",@"spent113-missing",@"source611-pre",@"baseline91-pre",@"new-recovery"] containsObject:name];assert(r.submissions==(pre?0:1));''')
    return builder.one(raw,'if(!n)dispatch_sync(q,^{[loop tick];});',
        'if(!n)dispatch_sync(q,^{if([name isEqual:@"between-source611"])change([c[@"repository"] stringByAppendingPathComponent:@"research/usb-ds-iso/tools/a23_live91_checked_workflow.py"]);[loop tick];});')


def template(build,target):
    old.previous.old.model_template(build,target)
    shutil.copytree(build/'history/spent113',target/'spent113')


def tamper(build,name):
    if name=='frozen-spent113':(build/'history/spent113/block-00113.json').write_bytes(b'changed\n')
    else:old.previous.old.tamper(build,name)


def run(output):
    output=w.canonical(output);require(not output.exists() and not builder.FORMAL_ROOT.exists(),'new unissued live91 review required')
    sources=builder.sources();output.mkdir(mode=0o700);completed=[]
    try:
        build=output/'build';builder.build(build);scope=builder.runtime_scope(build);history=builder.inputs()[4]
        native=output/'native';shutil.copytree(build,native);source=native/'source/research/usb-ds-iso'
        target=source/'tests/generated_live91_fixture.m';target.write_text(fixture(source))
        command=builder.command(native,target);command.insert(1,'-DA23_EXPORT_MODEL_FIXTURE=1')
        compiled=subprocess.run(command,capture_output=True,timeout=60);w.card.put(output,'fixture-compile.log',compiled.stdout+compiled.stderr)
        w.write(output/'fixture-compile.json',dict(command=command,returncode=compiled.returncode));require(compiled.returncode==0,'live91 fixture compilation failed')
        matrix={};accepted={};clock_rejections={};replays={};modes={}
        for name,args,code in [('describe',['--describe'],0),('archive',['--check-archive',str(build)],0),('current',['--check-build',str(build)],0),('missing-job',['--acquire-once',str(build),'/nonexistent','/nonexistent'],2)]:
            p=subprocess.run([str(build/'verified-entry'),*args],capture_output=True,timeout=30);require(p.returncode==code,'live91 file mode failed '+name)
            w.card.put(output,name+'.stdout',p.stdout);w.card.put(output,name+'.stderr',p.stderr);modes[name]=dict(returncode=p.returncode,value=json.loads(p.stdout) if p.stdout else None)
        w.write(output/'preview.json',flow.preview(build));impl=flow.implementation(build);engine=impl.engine_module(build)
        with tempfile.TemporaryDirectory(prefix='a23-live91-',dir='/private/tmp') as temporary:
            scratch=Path(temporary);inputs=scratch/'template';template(build,inputs);cases=scratch/'cases';cases.mkdir()
            try:
                for name in CASES+ARCHIVES:
                    case=cases/name;case.mkdir();host=case/'host';host.mkdir();store=engine.SharedSequence32(case/'namespace',simulation=True,fresh_scope=lambda:scope)
                    store.initialize(history);job=impl.prepare_job(store);foreign=impl.prepare_job(store);store.issue(job);store.consume(job)
                    current=scratch/'current';current_build=scratch/'current-build';shutil.copytree(inputs,current);shutil.copytree(build,current_build)
                    config=dict(case=name,build=str(current_build),host=str(host),repository=str(current/'repository'),cards=str(current/'cards'),ledger=str(current/'ledger'),records=str(current/'records'),job=str(store.root/'jobs'/job),binding=store.binding(job))
                    w.write(case/'config.json',config)
                    if name in ARCHIVES:tamper(current_build,name)
                    p=subprocess.run([str(native/'live-fixture'),str(case/'config.json')],capture_output=True,timeout=60)
                    w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr);w.write(case/'process.json',dict(returncode=p.returncode))
                    require(p.returncode==0 and not p.stderr,'live91 native case failed '+name);row=json.loads(p.stdout);matrix[name]=row
                    require(row['calls']['iso_submissions']<=2 and row['calls']['burst_triggers']<=2 and row['calls']['sdk_destroys']==0,'live91 bounds changed')
                    if name in ('normal','queued-delay'):
                        accepted[name]=flow.analyze_host(host,build,simulation=True)
                        require(accepted[name]['sdk']['total_bytes']==6144 and accepted[name]['sdk']['epochs'][0]['first_sequence']==145 and accepted[name]['sdk']['status_captures_verified'] is True,'live91 payload/status differs')
                        try:flow.analyze_host(host,build,simulation=False)
                        except ValueError:clock_rejections[name]=True
                        else:raise ValueError('fake SDK clock accepted as real')
                        before={p.relative_to(store.root).as_posix():sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()}
                        for kind,call in [('consume',lambda:store.consume(job)),('foreign_issue',lambda:store.issue(foreign))]:
                            try:call()
                            except (ValueError,OSError):replays[name+'/'+kind]=True
                            else:raise ValueError('live91 replay accepted')
                        require(before=={p.relative_to(store.root).as_posix():sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()},'replay changed model namespace')
                    elif name in ARCHIVES:require(row['initial_core'] is False and row['calls']['opens']==0,'bad archive opened fake SDK')
                    else:require(row['loop']['success'] is False,'live91 failure promoted')
                    if name in ('spent113-drift','spent113-extra','spent113-missing','source611-pre','baseline91-pre','new-recovery'):require(row['calls']['iso_submissions']==0,'stale live91 input reached ISO')
                    if name in ('bad-status','exit-running','between-source611'):require(row['calls']['iso_submissions']==1,'failed first reached second')
                    completed.append(name);shutil.rmtree(current);shutil.rmtree(current_build)
            finally:shutil.copytree(cases,output/'cases')
        require(builder.sources()==sources and not builder.FORMAL_ROOT.exists(),'real sources/history or successor changed')
        report=dict(schema='A23-live91-checked-audit-1',passed=True,source_hashes=sources,source_count=611,prior_sources_unchanged=607,
            current91_bound=True,history=history,scope=scope,matrix=matrix,accepted=accepted,clock_domain_rejections=clock_rejections,replay_rejections=replays,
            file_modes=modes,native_cases=len(CASES),archive_cases=len(ARCHIVES),completed=completed,native_compiler_jobs=2,
            first_sequence=145,last_sequence=176,successor_namespace_created=False,formal_records=0,formal_reservations=0,actual_acquisition_invocations=0,
            usb_requests=0,sd_accesses=0,real_sdk_objects=0,remaining=0,hardware_verified=False,continuous_streaming_verified=False)
        w.write(output/'audit.json',report)
    except BaseException as error:
        w.write(output/'failure.json',dict(error=str(error),type=type(error).__name__,completed=completed));w.b.seal(output);builder.base.old.prior.sealed(output);raise
    w.b.seal(output);builder.base.old.prior.sealed(output);return builder.base.old.prior.reference(output)


def verify(output):
    output=w.canonical(output);builder.base.old.prior.sealed(output);r=w.load(output/'audit.json');builder.verify(output/'build',current=False)
    require(r['passed'] is True and set(r['completed'])==set(CASES+ARCHIVES) and r['source_count']==611,'live91 case totals differ')
    for n,result in r['accepted'].items():require(flow.analyze_host(output/'cases'/n/'host',output/'build',simulation=True)==result,'live91 saved chain drift')
    return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);args=p.parse_args()
    print(json.dumps(run(args.output) if args.output else dict(passed=verify(args.check)['passed']),indent=2))
