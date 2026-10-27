"""Saved75 live CLI checks and temporary successor namespace/native fixtures."""
import argparse,json,shutil,subprocess,tempfile
from pathlib import Path
import build_a23_live75_two_epoch as builder
import a23_live75_two_epoch_workflow as flow
import audit_a23_live_two_epoch as old_audit
import audit_a23_scope_verifier as scope_audit
from a23_sequence32_model import encode,sha,require
w=builder.w
CASES=('normal','queued-delay','bad-status','bad-payload','live-source-afterprepare','new-recovery','baseline-drift','legacy-drift',
       'predecessor-drift','predecessor-extra','predecessor-missing','foreign-job','own-native-context','unknown-shared-file',
       'during-pending-source','stopped-pending-source','between-epochs-source','before-final-source','after-final-source')
ARCHIVES=('frozen-source','binary','resealed-source','frozen-predecessor','resealed-generated','descriptor')


def prefix(source):
    raw=old_audit.prefix(source)
    for before,after in [('first==81+_triggers*16','first==113+_triggers*16'),('81+n*16+p','113+n*16+p'),
        ('81+n*16','113+n*16'),('firstSequence:81','firstSequence:113'),('intValue]==81','intValue]==113'),('intValue]==112','intValue]==144')]:
        require(before in raw,'fixture range anchor missing: '+before);raw=raw.replace(before,after)
    require('@"request":@81' in raw,'STATUS bRequest accidentally changed')
    return raw


def fixture(source):
    raw=(source/'tests/a23_scope_verifier_fixture.m').read_text()
    raw=raw.replace('SDKModelInterface *r=[SDKModelInterface new]','SDKModelInterface *r=[Live75Status new]')
    raw=raw.replace('20261018-context65-first-live-read',builder.ANCHOR.name)
    raw=raw.replace('    if([name containsString:@"source"]',r'''    if([name isEqual:@"predecessor-drift"])change([c[@"predecessor"] stringByAppendingPathComponent:@"block-00081.json"]);
    else if([name isEqual:@"predecessor-extra"])change([c[@"predecessor"] stringByAppendingPathComponent:@"unexpected"]);
    else if([name isEqual:@"predecessor-missing"])assert([[NSFileManager defaultManager] removeItemAtPath:[c[@"predecessor"] stringByAppendingPathComponent:@"block-00081.json"] error:NULL]);
    else if([name containsString:@"source"]''')
    return prefix(source)+'\n'+(source/'tests/a23_live75_two_epoch_fixture.inc').read_text()+'\n'+raw


def model_template(build,target):
    scope_audit.template(build,target);shutil.copytree(build/'history/predecessor',target/'predecessor')


def file_modes(build,output):
    output.mkdir();result={}
    for name,args,expected in [('describe',['--describe'],0),('archive',['--check-archive',str(build)],0),
            ('current',['--check-build',str(build)],0),('context',['--inspect-context'],0),
            ('missing-job',['--acquire-once',str(build),'/nonexistent','/nonexistent'],2)]:
        p=subprocess.run([str(build/'verified-entry'),*args],capture_output=True,timeout=30)
        w.card.put(output,name+'.stdout',p.stdout);w.card.put(output,name+'.stderr',p.stderr)
        require(p.returncode==expected,'live75 file mode differs: '+name)
        result[name]=dict(returncode=p.returncode,result=json.loads(p.stdout) if p.stdout else None)
    return result


def tamper(build,name):
    if name=='frozen-predecessor':(build/'history/predecessor/block-00081.json').write_bytes(b'changed\n')
    elif name=='resealed-generated':
        (build/'generated/live_driver.m').write_bytes(b'changed\n')
        for p in (build/'SHA256SUMS',build/'COMMITTED'):p.unlink()
        w.b.seal(build)
    else:scope_audit.tamper(build,name)


def run(output):
    output=w.canonical(output);require(not output.exists(),'new live75 review required');require(not builder.FORMAL_ROOT.exists(),'successor namespace already exists')
    frozen=builder.sources();pred=builder.predecessor()[0];output.mkdir(mode=0o700)
    build=output/'build';builder.build(build);scope=builder.runtime_scope(build);history=builder.inputs()[4]
    require([(r['first'],r['last']) for r in history]==[(49,64),(65,80),(81,96),(97,112)],'spent history not carried forward')
    native=output/'native';shutil.copytree(build,native);r=native/'source/research/usb-ds-iso'
    target=r/'tests/generated_live75_fixture.m';target.write_text(fixture(r));cmd=builder.command(native,target)
    compiled=subprocess.run(cmd,capture_output=True,timeout=60);w.card.put(output,'fixture-compile.log',compiled.stdout+compiled.stderr);require(compiled.returncode==0,'live75 fixture compilation failed')
    modes=file_modes(build,output/'file-modes');preview=flow.preview(build);w.write(output/'preview.json',preview)
    impl=flow.implementation(build);module=impl.engine_module(build)
    template=output/'inputs';model_template(build,template)
    scratch=Path(tempfile.mkdtemp(prefix='a23-live75-',dir='/private/tmp'));matrix={};accepted={};replay={}
    try:
        cases=scratch/'cases';cases.mkdir()
        for name in CASES+ARCHIVES:
            case=cases/name;case.mkdir();host=case/'host';host.mkdir()
            store=module.SharedSequence32(case/'namespace',simulation=True,fresh_scope=lambda:scope);store.initialize(history)
            job=impl.prepare_job(store);foreign=impl.prepare_job(store);store.issue(job);store.consume(job)
            current=scratch/'current';current_build=scratch/'current-build';shutil.copytree(template,current);shutil.copytree(build,current_build)
            config=dict(case=name,build=str(current_build),repository=str(current/'repository'),cards=str(current/'cards'),
                ledger=str(current/'ledger'),records=str(current/'records'),predecessor=str(current/'predecessor'),
                job=str(store.root/'jobs'/job),foreign_job=str(store.root/'jobs'/foreign/'job.json'),host=str(host),binding=store.binding(job))
            w.write(case/'config.json',config);w.write(case/'case-info.json',dict(job_id=job,foreign_job_id=foreign))
            if name in ARCHIVES:tamper(current_build,name)
            process=subprocess.run([str(native/'live-fixture'),str(case/'config.json')],capture_output=True,timeout=60)
            w.card.put(case,'native.stdout',process.stdout);w.card.put(case,'native.stderr',process.stderr)
            require(process.returncode==0 and not process.stderr,'live75 native case failed: '+name)
            row=json.loads(process.stdout);matrix[name]=row
            require(row['calls']['iso_submissions']<=2 and row['calls']['burst_triggers']<=2 and row['calls']['sdk_destroys']==0,'native limits changed')
            if name in ('normal','queued-delay'):
                accepted[name]=flow.analyze_entry(host,build)
                require(accepted[name]['sdk']['status_captures_verified'] is True and accepted[name]['sdk']['total_bytes']==6144,'missing revised status verification')
                native_context=module.f.load(store.root/'jobs'/job/'native-context.json');host_context=w.load(host/'context.json')
                require(encode(native_context)==encode(host_context) and w.load(host/'entry-current.json')['binding']==store.binding(job),'native/entry consumption differs')
                before={p.relative_to(store.root).as_posix():sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()}
                for kind,call in [('consume',lambda:store.consume(job)),('foreign_issue',lambda:store.issue(foreign))]:
                    try:call()
                    except (ValueError,OSError):replay[name+'/'+kind]=True
                    else:raise ValueError('successor replay accepted')
                require(before=={p.relative_to(store.root).as_posix():sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()},'replay changed namespace bytes')
            else:require(row['entry'].get('complete') is not True,'failed case promoted')
            if name in ARCHIVES:require(row['initial_core'] is False and row['calls']['wait_creates']==row['calls']['opens']==0,'bad archive opened SDK')
            if name in ('predecessor-drift','predecessor-extra','predecessor-missing','baseline-drift','legacy-drift','new-recovery','live-source-afterprepare'):require(row['calls']['iso_submissions']==0,'stale history reached ISO')
            if name in ('bad-status','bad-payload','between-epochs-source','during-pending-source','stopped-pending-source'):require(row['calls']['iso_submissions']==1,'failed first reached second ISO')
            if name=='bad-status':
                saved=w.card.seal_verify(host/'status-after-epoch-0');require('transferred' in json.loads(saved['verdict.json'])['failed_checks'],'specific STATUS failure not saved')
            shutil.rmtree(current);shutil.rmtree(current_build)
        shutil.copytree(cases,output/'cases')
    finally:shutil.rmtree(scratch)
    require(builder.sources()==frozen and builder.predecessor()[0]==pred and not builder.FORMAL_ROOT.exists(),'real sources/history or namespace changed')
    report=dict(schema='A23-live75-two-epoch-audit-1',passed=True,source_count=597,prior_sources_unchanged=592,source_hashes=frozen,
        baseline_files=75,first_sequence=113,last_sequence=144,historical_intervals=history,scope=scope,preview=preview,file_modes=modes,
        native_cases=len(CASES),archive_cases=len(ARCHIVES),native_matrix=matrix,accepted=accepted,replay_rejections=replay,
        native_compiler_jobs=2,sanitizers=['address','undefined'],usb_requests=0,sd_accesses=0,real_sdk_objects=0,
        formal_records=0,formal_reservations=0,authorization_consumptions=0,actual_acquisition_invocations=0,remaining=0,
        successor_namespace_created=False,hardware_verified=False,physical_run_authenticated=False,continuous_streaming_verified=False)
    w.write(output/'audit.json',report);w.b.seal(output);builder.old.prior.sealed(output);return builder.old.prior.reference(output)


def verify(root):
    root=w.canonical(root);builder.old.prior.sealed(root);report=w.load(root/'audit.json');builder.verify(root/'build',current=False)
    require(report['passed'] is True and report['source_count']==597 and report['native_cases']==19 and report['archive_cases']==6,'live75 audit totals differ')
    require(set(report['accepted'])=={'normal','queued-delay'},'live75 accepted cases differ')
    for name in report['accepted']:require(flow.analyze_entry(root/'cases'/name/'host',root/'build')==report['accepted'][name],'saved live75 chain differs')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);args=p.parse_args()
    print(json.dumps(run(args.output) if args.output else dict(passed=verify(args.check)['passed']),indent=2))
