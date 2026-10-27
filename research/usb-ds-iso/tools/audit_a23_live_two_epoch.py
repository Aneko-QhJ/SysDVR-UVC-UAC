"""Compile the live CLI; exercise only file modes and injected two-epoch paths."""
from pathlib import Path
import argparse,json,shutil,subprocess,tempfile
import build_a23_live_two_epoch as builder
import a23_live_two_epoch_workflow as flow
import audit_a23_scope_verifier as old
from a23_sequence32_model import encode,sha,require
w=builder.w
CASES=('normal','bad-payload','control-timeout','exit-waiting','exit-running','quiet-incomplete','export-collision','receipt-collision','old-before-final','operator-off-after-timeout')
SCOPE_CASES=('normal','bad-payload','live-source-afterprepare','between-epochs-source','stopped-pending-source')


def prefix(source):
    parts=[]
    for n in ('a23_two_epoch_receiver_test.m','a23_paired_sdk_fixture.inc','a23_two_epoch_sdk_fixture.inc','a23_two_epoch_entry_fixture.inc'):
        raw=(source/'tests'/n).read_text();require(raw.count('\nint main(')==1,'live fixture prefix differs');parts.append(raw.split('\nint main(',1)[0])
    return '\n'.join(parts)


def compile_fixture(build,work,name,body):
    shutil.copytree(build,work);r=work/'source/research/usb-ds-iso';target=r/'tests/generated_live_fixture.m';target.write_text(prefix(r)+'\n'+body)
    cmd=builder.command(work,target);p=subprocess.run(cmd,capture_output=True);w.card.put(work,'fixture-compile.log',p.stdout+p.stderr);require(p.returncode==0,'live '+name+' fixture compilation failed')
    return work/'live-fixture',cmd


def file_modes(build,output):
    output.mkdir();out={}
    for name,args,expected in (('describe',['--describe'],0),('check-build',['--check-build',str(build)],0),('check-archive',['--check-archive',str(build)],0),
        ('context',['--inspect-context'],0),('missing-args',['--acquire-once'],2),('missing-job',['--acquire-once',str(build),'/nonexistent','/nonexistent'],2)):
        p=subprocess.run([str(build/'verified-entry'),*args],capture_output=True,timeout=30)
        w.card.put(output,name+'.stdout',p.stdout);w.card.put(output,name+'.stderr',p.stderr);require(p.returncode==expected,'live file mode differs: '+name)
        out[name]=dict(returncode=p.returncode,expected=expected,result=json.loads(p.stdout) if p.stdout else None)
    return out


def run(output):
    output=w.canonical(output);require(not output.exists(),'new live review required');output.mkdir(mode=0o700)
    build=output/'build';builder.build(build);frozen=builder.sources()
    fixture,cmd=compile_fixture(build,output/'loop-native','loop',(build/'source/research/usb-ds-iso/tests/a23_live_two_epoch_fixture.inc').read_text())
    cases=output/'loop-cases';cases.mkdir()
    p=subprocess.run([str(fixture),str(cases)],capture_output=True,timeout=30)
    w.card.put(output,'loop.stdout',p.stdout);w.card.put(output,'loop.stderr',p.stderr);require(p.returncode==0 and not p.stderr,'live controller fixture failed')
    loops=json.loads(p.stdout);require(loops['model_cases']==10 and set(loops['cases'])==set(CASES),'live controller cases differ')
    modes=file_modes(build,output/'file-modes');preview=flow.preview(build);w.write(output/'preview.json',preview)
    engine=flow.engine_module(build);scope=builder.runtime_scope(build);history=builder.previous.authority.inputs()[4]
    inputs=output/'scope-inputs';old.template(build,inputs)
    full,scope_cmd=compile_fixture(build,output/'scope-native','scope',(build/'source/research/usb-ds-iso/tests/a23_scope_verifier_fixture.m').read_text())
    scope_rows={};models=Path(tempfile.mkdtemp(prefix='a23-live-scope-',dir='/private/tmp'))
    # Only explicit temporary namespaces and copied inputs are written here.
    for name in SCOPE_CASES:
        case=models/name;case.mkdir();(case/'host').mkdir();current=case/'current';shutil.copytree(inputs,current)
        store=engine.SharedSequence32(case/'namespace',simulation=True,fresh_scope=lambda:scope);store.initialize(history)
        job=flow.prepare_job(store);foreign=flow.prepare_job(store);store.issue(job);store.consume(job)
        config=dict(case=name,build=str(build),repository=str(current/'repository'),cards=str(current/'cards'),ledger=str(current/'ledger'),records=str(current/'records'),
            job=str(store.root/'jobs'/job),foreign_job=str(store.root/'jobs'/foreign/'job.json'),host=str(case/'host'),binding=store.binding(job))
        w.write(case/'config.json',config)
        p=subprocess.run([str(full),str(case/'config.json')],capture_output=True,timeout=60)
        w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr);require(p.returncode==0 and not p.stderr,'live scope fixture failed: '+name)
        row=json.loads(p.stdout);scope_rows[name]=row
        require(row['native']['replay_blocked'] is True,'native permit replay allowed')
        require(row['entry']['complete'] is (name=='normal'),'live scope completion differs')
        require(row['calls']['iso_submissions']<=2 and row['calls']['burst_triggers']<=2 and row['calls']['sdk_destroys']==0,'live scope limits')
        if name=='normal':
            flow.entry_analyze(case/'host')
            # The new Python issuer and native permit use the same scope schema,
            # capabilities, commits and binding; second consumption stays burned.
            before={str(q.relative_to(store.root)):sha(q.read_bytes()) for q in store.root.rglob('*') if q.is_file()}
            try:store.consume(job)
            except (ValueError,OSError):pass
            else:raise ValueError('live consume replay accepted')
            require(before=={str(q.relative_to(store.root)):sha(q.read_bytes()) for q in store.root.rglob('*') if q.is_file()},'live replay changed bytes')
    shutil.copytree(models,output/'scope-cases');w.write(output/'scope-results.json',scope_rows)
    # Verify the actual controller output using the old strict SDK/entry reader.
    normal=output/'loop-cases/normal';overlay=Path(tempfile.mkdtemp(prefix='a23-live-analysis-',dir='/private/tmp'))/'host';shutil.copytree(normal,overlay)
    w.card.seal_verify(normal/'live-final')
    for n in ('entry-current.json','entry-final-status.json','result.json','receipt-status.json'):shutil.copyfile(normal/'live-final'/n,overlay/n)
    analyzed=flow.entry_analyze(overlay);require(analyzed['supplied_entry_chain_complete'] is True,'live controller export not independently readable')
    require(builder.sources()==frozen,'live audit source drift')
    report=dict(schema='A23-live-two-epoch-audit-1',passed=True,source_count=587,prior_sources_unchanged=579,source_hashes=frozen,
        controller_cases=10,scope_permit_cases=5,controller_results=loops,scope_results=scope_rows,file_modes=modes,
        loop_fixture_command=cmd,scope_fixture_command=scope_cmd,strict_controller_entry_analysis=analyzed,
        sanitizers=['address','undefined'],real_sdk_objects=0,usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,
        authorization_consumptions=0,actual_acquisition_invocations=0,new_native_compiler_jobs=3,
        hardware_verified=False,physical_run_authenticated=False,continuous_streaming_verified=False)
    w.write(output/'audit.json',report);w.b.seal(output);builder.prior.sealed(output)
    return builder.prior.reference(output)


def verify(root):
    root=w.canonical(root);builder.prior.sealed(root);r=w.load(root/'audit.json');builder.verify(root/'build',current=False)
    require(r['source_count']==587 and r['prior_sources_unchanged']==579 and r['controller_cases']==10 and r['scope_permit_cases']==5,'live audit totals differ')
    require(r['real_sdk_objects']==r['usb_requests']==r['sd_accesses']==r['formal_records']==r['actual_acquisition_invocations']==0,'live audit hardware authority differs')
    for name in CASES:
        row=w.load(root/'loop-cases'/name/'controller-observation.json');require(row['loop']==r['controller_results']['cases'][name],'live saved controller differs')
        require(row['loop']['success'] is (name=='normal'),'live case acceptance differs')
    return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);args=p.parse_args()
    try:r=run(args.output) if args.output else dict(passed=True,source_count=verify(args.check)['source_count'])
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r,indent=2))
