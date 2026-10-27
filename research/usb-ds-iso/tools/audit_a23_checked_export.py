"""Bounded fake-SDK controller and checked-export consumer audit."""
import argparse,copy,json,shutil,subprocess,tempfile,types
from pathlib import Path
import a23_checked_export as candidate
import audit_a23_guard_cadence as previous
from a23_sequence32_model import sha,encode,require

w=candidate.w;b=candidate.b
CASES=('normal','queued-delay','before-pre-source','mid-payload-source','after-payload-source',
 'after-payload-baseline','after-payload-context','stale-getters','after-payload-bytes','payload-collision',
 'acceptance-collision','bad-status','exit-running','after-receipt-bytes','after-post-source')
ACCEPTED={'normal','queued-delay','after-post-source'}
NEGATIVES=('missing-receipt','wrong-pin','same-check','bad-time','wrong-entry','resealed-payload','future-claim','extra-payload')


def strict_entry(host,build):
    with tempfile.TemporaryDirectory(prefix='a23-export-read-',dir='/private/tmp') as temporary:
        overlay=Path(temporary)/'host';shutil.copytree(host,overlay)
        for n in ('entry-current.json','entry-final-status.json','result.json','receipt-status.json'):
            shutil.copyfile(host/'live-final'/n,overlay/n)
        return previous.old.flow.analyze_entry(overlay,build)


def reseal(folder):
    for n in ('SHA256SUMS','COMMITTED'):(folder/n).unlink()
    w.b.seal(folder)


def negatives(normal,root,bound):
    root.mkdir();rows={}
    for name in NEGATIVES:
        target=root/name;shutil.copytree(normal,target);pin=copy.deepcopy(bound)
        acceptance=target/'live-acceptance';final=target/'live-final'
        if name=='missing-receipt':shutil.rmtree(acceptance)
        elif name=='wrong-pin':pin['source_closure_sha256']='0'*64
        elif name in ('same-check','bad-time','wrong-entry'):
            after=w.load(acceptance/'validation-after.json');receipt=w.load(acceptance/'receipt.json')
            if name=='same-check':after=w.load(final/'validation-before.json');receipt['post_full_check_index']=receipt['pre_full_check_index']
            elif name=='bad-time':after['cadence']['full_checks'][-1]['elapsed_ns']=-1
            else:after['entry_binding']['receiver_sha256']='0'*64
            w.replace(acceptance/'validation-after.json',after);receipt['post_evidence_sha256']=sha(w.plain(acceptance/'validation-after.json'))
            w.replace(acceptance/'receipt.json',receipt);reseal(acceptance)
        elif name=='resealed-payload':
            entry=w.load(final/'entry-current.json');entry['complete']=False;w.replace(final/'entry-current.json',entry);reseal(final)
        elif name=='future-claim':
            receipt=w.load(acceptance/'receipt.json');receipt['future_disk_freshness_verified']=True;w.replace(acceptance/'receipt.json',receipt);reseal(acceptance)
        else:w.card.put(final,'unexpected',b'x');reseal(final)
        try:candidate.accept(target,expected_binding=pin)
        except (ValueError,OSError,KeyError,TypeError) as error:rows[name]=dict(rejected=True,error=str(error))
        else:raise ValueError('negative checked export accepted: '+name)
        w.write(root/(name+'-pin.json'),pin)
    return rows


def run(output):
    output=w.canonical(output);require(not output.exists(),'new checked-export review required')
    hashes=candidate.sources();actual=w.load(candidate.prior.PARENT/'closeout.json')
    build=Path(actual['references']['build']['directory']);b.verify(build,current=False)
    once=w.load(candidate.prior.PARENT/'once-record.json');scope=once['result']['scope'];history=w.load(b.FORMAL_ROOT/'history.json')
    module=types.ModuleType('a23_export_model32');module.__file__=str(build/'source/research/usb-ds-iso/tools/a23_shared_sequence32.py')
    exec(compile(b.render_engine(w.plain(Path(module.__file__)).decode()),'<checked-export-model32>','exec'),module.__dict__)
    output.mkdir(mode=0o700);w.write(output/'source-hashes.json',hashes)
    for name in candidate.NEW:w.card.put(output,'candidate-source/'+name,w.plain(w.ROOT/name))
    completed=[];matrix={};accepted={};strict={};rejected={}
    try:
        native=output/'native';shutil.copytree(build/'source',native/'source');shutil.copytree(build/'generated',native/'generated')
        shutil.copyfile(build/'a23_verified_binding.h',native/'a23_verified_binding.h');source=native/'source/research/usb-ds-iso'
        for name in ('a23_guard_cadence_api.h','a23_checked_export.h','a23_checked_export.m'):
            shutil.copyfile(w.ROOT/'host'/name,source/'host'/name)
        fixture=source/'tests/generated_checked_export.m';fixture.write_text(candidate.fixture(source))
        scope_source=native/'generated/checked_scope.m';scope_source.write_text(candidate.render_scope((build/'generated/live_scope.m').read_text()))
        bound=candidate.binding(hashes,build,scope_source.read_bytes(),fixture.read_bytes());w.write(output/'candidate-binding.json',bound)
        w.card.put(native,'a23_checked_export_binding.h',candidate.binding_header(bound))
        command=b.command(native,fixture)
        command=[str(scope_source) if x==str(native/'generated/live_scope.m') else
            str(source/'host/a23_checked_export.m') if x==str(source/'host/a23_live_two_epoch.m') else x for x in command]
        command.insert(1,'-DA23_EXPORT_MODEL_FIXTURE=1');command[-1]=str(native/'checked-fixture')
        compiled=subprocess.run(command,capture_output=True,timeout=60);w.card.put(output,'compile.log',compiled.stdout+compiled.stderr)
        w.write(output/'compile.json',dict(command=command,returncode=compiled.returncode));require(compiled.returncode==0,'checked-export native compilation failed')
        with tempfile.TemporaryDirectory(prefix='a23-checked-export-',dir='/private/tmp') as temporary:
            scratch=Path(temporary);template=scratch/'template';previous.old.model_template(build,template);cases=scratch/'cases';cases.mkdir()
            try:
                for name in CASES:
                    case=cases/name;case.mkdir();host=case/'host';host.mkdir()
                    store=module.SharedSequence32(case/'namespace',simulation=True,fresh_scope=lambda:scope)
                    store.initialize(history);job=previous.prepare_job(store);store.issue(job);store.consume(job)
                    current=scratch/'current';shutil.copytree(template,current)
                    config=dict(case=name,host=str(host),build=str(build),repository=str(current/'repository'),cards=str(current/'cards'),
                        ledger=str(current/'ledger'),records=str(current/'records'),job=str(store.root/'jobs'/job),binding=store.binding(job))
                    w.write(case/'config.json',config)
                    process=subprocess.run([str(native/'checked-fixture'),str(case/'config.json')],capture_output=True,timeout=60)
                    w.card.put(case,'native.stdout',process.stdout);w.card.put(case,'native.stderr',process.stderr);w.write(case/'process.json',dict(returncode=process.returncode))
                    require(process.returncode==0 and not process.stderr,'checked-export native case failed: '+name)
                    row=json.loads(process.stdout);matrix[name]=row
                    require(row['real_sdk_objects']==row['usb_requests']==row['sd_accesses']==0 and row['calls']['sdk_destroys']==0,'fake-SDK authority changed')
                    try:result=candidate.accept(host,expected_binding=bound)
                    except (ValueError,OSError,KeyError,TypeError) as error:
                        require(name not in ACCEPTED,'expected export rejected: '+name+' '+str(error));rejected[name]=str(error)
                    else:
                        require(name in ACCEPTED,'stale export accepted: '+name);accepted[name]=result;strict[name]=strict_entry(host,build)
                        require(strict[name]['sdk']['status_captures_verified'] is True and strict[name]['sdk']['total_bytes']==6144,'strict two-epoch payload differs')
                    if name in ('bad-status','exit-running'):require(row['calls']['iso_submissions']==1,'failed first reached second ISO')
                    if name=='exit-running':
                        require(row['pending_full_checks_skipped'] is True and row['loop']['unresolved_keep_alive'] is True,'pending failure lost owner or hashed inputs')
                        require(w.load(host/'live-failure/live.json')['raw_inflight_buffers_copied'] is False,'pending buffers copied')
                    if name=='bad-status':
                        status=w.card.seal_verify(host/'status-after-epoch-0');require('transferred' in json.loads(status['verdict.json'])['failed_checks'],'bad STATUS evidence missing')
                    if name=='stale-getters':require(row['stale_getter_seen'] is True and row['getters_had_no_checks'] is True,'stale getter counterexample missing')
                    completed.append(name);shutil.rmtree(current)
                bad=negatives(cases/'normal/host',scratch/'negative',bound)
                shutil.copytree(scratch/'negative',output/'negative')
            finally:shutil.copytree(cases,output/'cases')
        require(candidate.sources()==hashes,'source or protected evidence drift')
        report=dict(schema='A23-checked-export-audit-1',passed=True,source_hashes=hashes,source_count=607,prior_sources_unchanged=601,
            candidate_binding=bound,input_build=b.old.prior.reference(build),parent=b.old.prior.reference(candidate.PARENT),native_matrix=matrix,
            accepted=accepted,strict_entry=strict,rejected=rejected,negative_archives=bad,completed=completed,native_cases=len(CASES),negative_cases=len(NEGATIVES),
            compiler_jobs=1,native_fixture_waits=len(completed),controller_model_adopted=True,live_acquisition_entry_adopted=False,
            guarded_live_model_sources=597,derived_static_source_closure=607,current91_rebase_implemented=False,hardware_candidate_ready=False,
            after_last_check_source_change_is_accepted_as_historical_evidence=True,after_receipt_payload_change_rejected_by_consumer=True,
            usb_requests=0,sd_accesses=0,real_sdk_objects=0,actual_acquisition_invocations=0,formal_records=0,formal_reservations=0,remaining=0,
            future_disk_freshness_verified=False,hardware_verified=False,physical_run_authenticated=False,callback_drain_verified=False)
        w.write(output/'audit.json',report)
    except BaseException as error:
        w.write(output/'failure.json',dict(type=type(error).__name__,error=str(error),completed=completed));w.b.seal(output);b.old.prior.sealed(output);raise
    w.b.seal(output);b.old.prior.sealed(output);return b.old.prior.reference(output)


def verify(output):
    output=w.canonical(output);b.old.prior.sealed(output);r=w.load(output/'audit.json')
    require(r['passed'] is True and set(r['completed'])==set(CASES) and set(r['accepted'])==ACCEPTED,'checked-export cases differ')
    for name,expected in r['accepted'].items():
        host=output/'cases'/name/'host';require(candidate.accept(host,expected_binding=r['candidate_binding'])==expected,'checked-export chain drift')
        require(strict_entry(host,Path(r['input_build']['directory']))==r['strict_entry'][name],'strict entry drift')
    for name,row in r['native_matrix'].items():
        require(json.loads(w.plain(output/'cases'/name/'native.stdout'))==row and w.load(output/'cases'/name/'process.json')['returncode']==0,'native result drift')
    for name in NEGATIVES:
        try:candidate.accept(output/'negative'/name,expected_binding=w.load(output/'negative'/(name+'-pin.json')))
        except (ValueError,OSError,KeyError,TypeError):pass
        else:raise ValueError('saved negative accepted '+name)
    return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);args=p.parse_args()
    print(json.dumps(run(args.output) if args.output else dict(passed=verify(args.check)['passed']),indent=2))
