"""Offline native comparison; every SDK, clock and namespace is a test double."""
import argparse,json,shutil,subprocess,tempfile,types,uuid
from pathlib import Path
import a23_guard_cadence_revision as revision
import audit_a23_live75_two_epoch as old
from a23_sequence32_model import encode,sha

b=revision.parent;w=b.w
EXTRA=('restored-after-observed','between-epochs-baseline','between-epochs-legacy',
       'between-epochs-predecessor','between-epochs-job','between-epochs-context','after-export-source')
CASES=old.CASES+EXTRA
ARCHIVES=old.ARCHIVES
PROBES=('proof-without-core','proof-archive-only')


def prepare_job(store):
    ident=str(uuid.uuid4());ns=store.validate()
    store.prepare(ident,dict(schema='A23-shared32-authorization-1',job_id=ident,
        scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=True,hardware_test_authorized=False))
    return ident


def run(output):
    output=w.canonical(output);w.require(not output.exists(),'new cadence review required')
    hashes=revision.guards();close=w.load(revision.PARENT/'closeout.json')
    build=Path(close['references']['build']['directory']);b.verify(build,current=False)
    scope=w.load(revision.PARENT/'once-record.json')['result']['scope']
    history=w.load(build/'history/predecessor/history.json')+[
        dict(row) for row in w.load(b.FORMAL_ROOT/'history.json')[2:]]
    w.require(len(history)==4 and sha(encode(history))==scope['history_sha256'],'frozen history differs')
    module=types.ModuleType('a23_cadence_simulated_sequence32')
    module.__file__=str(build/'source/research/usb-ds-iso/tools/a23_shared_sequence32.py')
    raw=b.render_engine(w.plain(Path(module.__file__)).decode())
    exec(compile(raw,'<verified-frozen-model32>','exec'),module.__dict__)
    output.mkdir(mode=0o700);w.write(output/'source-hashes.json',hashes)
    for name in revision.NEW:
        w.card.put(output,'candidate-source/'+name,w.plain(w.ROOT/name))
    w.write(output/'parent-reference.json',b.old.prior.reference(revision.PARENT))
    w.write(output/'input-build-reference.json',b.old.prior.reference(build))
    matrix={};accepted={};replays={};completed=[]
    try:
        # This compilation tree is derived code. It is NOT the input build that
        # the verifier checks and is not a source-bound live receiver package.
        native=output/'native';shutil.copytree(build/'source',native/'source')
        shutil.copytree(build/'generated',native/'generated')
        shutil.copyfile(build/'a23_verified_binding.h',native/'a23_verified_binding.h')
        source=native/'source/research/usb-ds-iso'
        shutil.copyfile(w.ROOT/'host/a23_guard_cadence_api.h',source/'host/a23_guard_cadence_api.h')
        fixture=source/'tests/generated_guard_cadence.m';fixture.write_text(revision.fixture(source))
        original=(build/'generated/live_scope.m').read_text();programs={}
        for label,candidate in [('control',False),('candidate',True)]:
            scope_source=native/'generated'/('scope-'+label+'.m')
            scope_source.write_text(revision.render_scope(original,candidate=candidate))
            target=native/('fixture-'+label)
            command=[str(scope_source) if x==str(native/'generated/live_scope.m') else x for x in b.command(native,fixture)]
            command[-1]=str(target)
            compiled=subprocess.run(command,capture_output=True,timeout=60)
            w.card.put(output,'compile-'+label+'.log',compiled.stdout+compiled.stderr)
            w.write(output/('compile-'+label+'.json'),dict(command=command,returncode=compiled.returncode))
            w.require(compiled.returncode==0,'cadence '+label+' compilation failed')
            programs[label]=target
        with tempfile.TemporaryDirectory(prefix='a23-cadence-',dir='/private/tmp') as temporary:
            scratch=Path(temporary);template=scratch/'template';old.model_template(build,template)
            cases=scratch/'cases';cases.mkdir()
            try:
                for label,name in [('control','normal')]+[('candidate',n) for n in CASES+ARCHIVES+PROBES]:
                    key=label+'-'+name;case=cases/key;case.mkdir();host=case/'host';host.mkdir()
                    store=module.SharedSequence32(case/'namespace',simulation=True,fresh_scope=lambda:scope)
                    store.initialize(history);job=prepare_job(store);foreign=prepare_job(store);store.issue(job);store.consume(job)
                    current=scratch/'current';current_build=scratch/'current-build'
                    shutil.copytree(template,current);shutil.copytree(build,current_build)
                    config=dict(case=name,build=str(current_build),repository=str(current/'repository'),cards=str(current/'cards'),
                        ledger=str(current/'ledger'),records=str(current/'records'),predecessor=str(current/'predecessor'),
                        job=str(store.root/'jobs'/job),foreign_job=str(store.root/'jobs'/foreign/'job.json'),host=str(host),binding=store.binding(job),scope=scope)
                    w.write(case/'config.json',config);w.write(case/'case-info.json',dict(job_id=job,foreign_job_id=foreign))
                    if name in ARCHIVES:old.tamper(current_build,name)
                    process=subprocess.run([str(programs[label]),str(case/'config.json')],capture_output=True,timeout=60)
                    w.card.put(case,'native.stdout',process.stdout);w.card.put(case,'native.stderr',process.stderr)
                    w.write(case/'process.json',dict(returncode=process.returncode))
                    w.require(process.returncode==0 and not process.stderr,'cadence case failed: '+key)
                    row=json.loads(process.stdout);matrix[key]=row
                    if name in PROBES:
                        w.require(row['live_job_accepted'] is False and row['verifier']['failed'] is True and
                            row['cadence']['full_invocations']==0 and row['archive_checked']==(name=='proof-archive-only'),'archive-only or absent proof accepted')
                        completed.append(key);shutil.rmtree(current);shutil.rmtree(current_build);continue
                    calls=row['calls'];w.require(calls['iso_submissions']<=2 and calls['burst_triggers']<=2 and calls['sdk_destroys']==0,'native limits differ')
                    w.require(row['real_sdk_objects']==row['usb_requests']==row['sd_accesses']==0,'model authority differs')
                    metrics=row['cadence'];checks=metrics['full_checks']
                    w.require(metrics['full_invocations']==len(checks)>0 and all(x['end_ns']>=x['begin_ns'] and x['elapsed_ns']==x['end_ns']-x['begin_ns'] for x in checks),'missing full-check times')
                    if name in ('normal','queued-delay'):
                        accepted[key]=old.flow.analyze_entry(host,build)
                        w.require(accepted[key]['sdk']['status_captures_verified'] is True and accepted[key]['sdk']['total_bytes']==6144,'strict model chain differs')
                        w.require(row['export_accepted'] is True and calls['iso_submissions']==2,'model success not exportable')
                        if label=='candidate':w.require(row['snapshot_getters_pure'] is True and row['between_epoch_full_checks']==1,'candidate hashing cadence differs')
                        else:w.require(row['between_epoch_full_checks']==6,'control no longer matches frozen live call count')
                        before={p.relative_to(store.root).as_posix():sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()}
                        for kind,call in [('consume',lambda:store.consume(job)),('foreign_issue',lambda:store.issue(foreign))]:
                            try:call()
                            except (ValueError,OSError):replays[key+'/'+kind]=True
                            else:raise ValueError('model replay accepted')
                        w.require(before=={p.relative_to(store.root).as_posix():sha(p.read_bytes()) for p in store.root.rglob('*') if p.is_file()},'model replay mutated namespace')
                    else:w.require(row['entry'].get('complete') is not True,'failure promoted')
                    if name in ARCHIVES:w.require(row['initial_core'] is False and calls['wait_creates']==calls['opens']==0,'bad archive opened fake SDK')
                    if name in ('predecessor-drift','predecessor-extra','predecessor-missing','baseline-drift','legacy-drift','new-recovery','live-source-afterprepare','restored-after-observed','foreign-job','own-native-context','unknown-shared-file'):
                        w.require(calls['iso_submissions']==0,'pre-arm change reached fake ISO')
                    if name.startswith('between-epochs-') or name in ('bad-status','bad-payload','during-pending-source','stopped-pending-source'):
                        w.require(calls['iso_submissions']==1,'failed first reached fake second ISO')
                    if name in ('during-pending-source','stopped-pending-source'):w.require(row['full_checks_skipped_while_pending'] is True,'full IO hashing while pending')
                    if name in ('before-final-source','after-final-source','after-export-source'):w.require(row['export_accepted'] is False,'stale final export accepted')
                    if name=='bad-status':
                        saved=w.card.seal_verify(host/'status-after-epoch-0')
                        w.require(len(saved['raw.bin'])==168 and 'transferred' in json.loads(saved['verdict.json'])['failed_checks'],'bad STATUS original missing')
                    completed.append(key)
                    shutil.rmtree(current);shutil.rmtree(current_build)
            finally:
                shutil.copytree(cases,output/'cases')
        w.require(revision.guards()==hashes,'source/protected drift after native cases')
        report=dict(schema='A23-guard-cadence-audit-1',passed=True,source_hashes=hashes,source_count=601,prior_sources_unchanged=597,
            input_build=b.old.prior.reference(build),input_build_is_historical_model_data=True,input_baseline_files=75,current_sd_files=91,
            native_matrix=matrix,accepted=accepted,replay_rejections=replays,candidate_cases=len(CASES),archive_cases=len(ARCHIVES),proof_cases=len(PROBES),control_cases=1,
            completed=completed,native_compiler_jobs=2,sanitizers=['address','undefined'],
            control_between_epoch_full_checks=6,candidate_between_epoch_full_checks=1,state_getters_hash_files=False,
            explicit_final_export_checks_required=True,live_controller_adoption_implemented=False,hardware_candidate_ready=False,
            timing_scope='Per full-check host CLOCK_MONOTONIC_RAW duration in native fake-SDK processes; not hardware latency or an A/B performance trial.',
            usb_requests=0,sd_accesses=0,real_sdk_objects=0,actual_acquisition_invocations=0,formal_records=0,formal_reservations=0,remaining=0,
            hardware_verified=False,continuous_streaming_verified=False,physical_run_authenticated=False)
        w.write(output/'audit.json',report)
    except BaseException as error:
        w.write(output/'failure.json',dict(type=type(error).__name__,error=str(error),completed=completed))
        w.b.seal(output);b.old.prior.sealed(output)
        raise
    w.b.seal(output);b.old.prior.sealed(output)
    return b.old.prior.reference(output)


def verify(output):
    output=w.canonical(output);b.old.prior.sealed(output);r=w.load(output/'audit.json')
    w.require(r['passed'] is True and r['source_count']==601 and r['candidate_cases']==len(CASES) and r['archive_cases']==len(ARCHIVES),'cadence totals differ')
    w.require(set(r['completed'])=={'control-normal'}|{'candidate-'+n for n in CASES+ARCHIVES+PROBES},'missing native results')
    build=Path(r['input_build']['directory']);b.verify(build,current=False)
    for name,expected in r['accepted'].items():w.require(old.flow.analyze_entry(output/'cases'/name/'host',build)==expected,'saved strict chain drift')
    for name,row in r['native_matrix'].items():
        w.require(json.loads(w.plain(output/'cases'/name/'native.stdout'))==row,'native row drift')
        w.require(w.load(output/'cases'/name/'process.json')['returncode']==0,'native child not waited successfully')
    return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);args=p.parse_args()
    print(json.dumps(run(args.output) if args.output else dict(passed=verify(args.check)['passed']),indent=2))
