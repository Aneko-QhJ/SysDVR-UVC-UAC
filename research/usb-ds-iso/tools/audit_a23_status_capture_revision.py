"""Compile an isolated driver revision and run fake SDK + historical byte audits."""
import argparse,difflib,json,shutil,struct,subprocess,types
from pathlib import Path
import a23_status_capture_revision as revision
import audit_a23_live_two_epoch as old_audit
from analyze_io_usb_host_burst_sdk_collection import replies
from analyze_a23_two_epoch_sdk import status as old_status
w=revision.w;old=revision.old
BUILD=w.A/'A23-live-two-epoch-review-20261022-r1/build'
SUCCESS={'normal','count0','count10','count01'}
FIELDS={'bad-magic':'magic','bad-version':'version','bad-sequence':'sequence','bad-state':'state','bad-post':'post_result',
    'bad-urb':'urb_id','bad-report-id':'report_id','bad-requested':'requested','bad-transferred':'transferred',
    'bad-urb-status':'urb_status','bad-speed':'speed','bad-endpoint':'endpoint','bad-count':'report_count',
    'bad-report-result':'report_result','bad-diag-magic':'iso7.magic','bad-terminal':'iso7.terminal','bad-bitmap':'iso7.bitmap',
    'bad-actual':'iso7.actual_sum','bad-context':'iso7.context_valid','bad-mfi':'iso7.frame_select_mfi',
    'bad-type':'iso7.trb_type','bad-sia':'iso7.sia','bad-frame-id':'iso7.frame_id','bad-observation':'sdk_observation',
    'bad-observation-json':'observation_json','short-after':'status.length','before-count2':'before_preserved_state',
    'before-drift':'before_preserved_state','same-urb':'urb_id_reused'}


def analyzer(root):
    path=Path(root)/'revised_sdk_analyzer.py';m=types.ModuleType('status_capture_revised_sdk');m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m


def snapshot(folder):
    files=w.card.seal_verify(folder)
    w.require(set(files)=={'raw.bin','observation.json','verdict.json'},'STATUS snapshot shape differs')
    return files,json.loads(files['observation.json']),json.loads(files['verdict.json'])


def analyze_success(root,sdk):
    result=sdk.analyze(root);journal=[json.loads(x) for x in (root/'session.jsonl').read_bytes().splitlines()]
    binding=journal[0]['details']['binding']
    for epoch in (0,1):
        metadata=json.loads((root/f'epoch-{epoch}/metadata.json').read_bytes())
        for phase in ('before','after'):
            files,observed,v=snapshot(root/f'status-{phase}-epoch-{epoch}')
            w.require(v['schema']=='A23-status-capture-1' and v['binding']==binding and
                v['epoch']==epoch and v['phase']==phase and v['failed_checks']==[] and v['sdk_envelope_valid'] is True and
                v['raw_retained'] is True and v['observation_json_retained'] is True and v['raw_bytes']==168 and
                v['raw_sha256']==w.sha(files['raw.bin']) and v['hardware_verified'] is False and v['physical_run_authenticated'] is False,'STATUS verdict differs')
            w.require(files['raw.bin']==(root/f'epoch-{epoch}/{phase}.bin').read_bytes() and
                observed==metadata[phase+'_observation'],'STATUS snapshot not same bytes/observation as epoch')
    return result


def run(output):
    output=w.canonical(output);w.require(not output.exists(),'new STATUS review required')
    frozen=revision.sources();old.verify(BUILD,current=False)
    output.mkdir(mode=0o700)
    for name,digest in frozen.items():
        raw=w.plain(w.b.REPO/name,2*1024*1024);w.require(w.sha(raw)==digest,'source drift');w.card.put(output,'source/'+name,raw)
    native=output/'native';native.mkdir();shutil.copytree(output/'source',native/'source')
    shutil.copyfile(BUILD/'a23_verified_binding.h',native/'a23_verified_binding.h')
    r=native/'source/research/usb-ds-iso';generated=native/'generated';generated.mkdir()
    for name in ('live_scope.m','live_permit.m','live_entry.m'):shutil.copyfile(BUILD/'generated'/name,generated/name)
    driver=revision.render_driver((r/'host/a23_two_epoch_sdk_driver.m').read_text());(generated/'live_driver.m').write_text(driver)
    w.card.put(output,'driver-revision.diff',''.join(difflib.unified_diff((BUILD/'generated/live_driver.m').read_text().splitlines(True),driver.splitlines(True),fromfile='frozen/live_driver.m',tofile='revised/live_driver.m')).encode())
    text=revision.render_analyzer((r/'tools/analyze_a23_two_epoch_sdk.py').read_text());w.card.put(output,'revised_sdk_analyzer.py',text.encode())
    sdk=analyzer(output);historical={}
    for record_name in ('A23-lead32-once-20261017-interface2-ready.json','A23-lead32-once-20261017-repeat1.json','A23-context65-once-baseline63-live-20261018.json'):
        record=w.load(w.A/record_name);run_path=Path(record['run']);w.card.seal_verify(run_path)
        raw=replies(w.plain(run_path/'host/session.jsonl'))['after'];fields=struct.unpack_from('<14I',raw)
        sdk.status(raw,fields[2]);w.card.put(output,'historical/'+record_name+'.after.bin',raw)
        try:old_status(raw,fields[2])
        except ValueError as e:old_rejected=str(e)
        else:old_rejected=None
        historical[record_name]=dict(sequence=fields[2],report_count=fields[12],original_sha256=w.sha(raw),new_status_passed=True,old_rejection=old_rejected,run=old.prior.reference(run_path))
    historical65=output/'historical/A23-context65-once-baseline63-live-20261018.json.after.bin'
    target=r/'tests/generated_status_revision.m';target.write_text(old_audit.prefix(r)+'\n'+(r/'tests/a23_status_capture_revision_fixture.inc').read_text())
    command=old.command(native,target);compiled=subprocess.run(command,capture_output=True,timeout=60)
    w.card.put(output,'compile.stdout',compiled.stdout);w.card.put(output,'compile.stderr',compiled.stderr);w.write(output/'compile-command.json',dict(command=command,returncode=compiled.returncode))
    w.require(compiled.returncode==0,'STATUS native compile failed')
    models=output/'models';models.mkdir()
    process=subprocess.run([str(native/'live-fixture'),str(models),str(historical65)],capture_output=True,timeout=60)
    w.card.put(output,'native.stdout',process.stdout);w.card.put(output,'native.stderr',process.stderr)
    w.require(process.returncode==0 and not process.stderr,'STATUS native model matrix failed')
    matrix=json.loads(process.stdout);w.require(matrix['case_count']==37 and matrix['historical_native_status65_passed'] is True,'native cases differ')
    accepted={};failures={}
    for name,row in matrix['cases'].items():
        folder=models/name
        w.require(row['sdk_destroys']==0 and row['iso_submissions']<=2 and row['burst_triggers']<=2,'native lifetime/limit differs')
        if name in SUCCESS:
            overlay=output/'accepted'/name;shutil.copytree(folder,overlay)
            for n in ('entry-current.json','entry-final-status.json','result.json','receipt-status.json'):shutil.copyfile(folder/'live-final'/n,overlay/n)
            accepted[name]=analyze_success(overlay,sdk)
        else:
            w.require(row['loop']['success'] is False and row['loop']['unresolved_keep_alive'] is True,'failure promoted')
            if name in FIELDS:
                epoch=1 if name=='same-urb' else 0
                phase='before' if name.startswith('before-') else 'after'
                if name.startswith('before-'):epoch=1
                files,observed,v=snapshot(folder/f'status-{phase}-epoch-{epoch}')
                w.require(FIELDS[name] in v['failed_checks'],'specific failed predicate missing: '+name)
                failures[name]=v['failed_checks']
            else:failures[name]=row['entry']['driver']['failure_reasons']
    w.require(set(accepted)==SUCCESS and all(v['total_bytes']==6144 for v in accepted.values()),'acceptance set differs')
    # The exact same source/status checks remain in force for rejected data:
    # changing report_count cannot cure state/URB/transfer/ISO7 failures.
    negatives={}
    for case,offset,value in [('bad-state',12,1),('bad-urb',20,0),('bad-transferred',32,0),('bad-count',48,2),('bad-terminal',68,0),('bad-bitmap',72,65534)]:
        raw=bytearray(historical65.read_bytes());struct.pack_into('<I',raw,offset,value)
        try:sdk.status(bytes(raw),65)
        except ValueError as e:negatives[case]=dict(rejected=True,error=str(e))
        else:raise ValueError('bad historical STATUS accepted: '+case)
    # Standalone verifier must still reject a semantically bad sealed epoch,
    # and cannot accept a missing/corrupt durable STATUS snapshot.
    negative_root=output/'negative-archives';negative_root.mkdir();archive_negatives={}
    for case in ('missing-status','bad-status-hash','rebound-status-bytes','before-drift'):
        folder=negative_root/case;shutil.copytree(output/'accepted/count10',folder)
        status_folder=folder/'status-after-epoch-0'
        if case=='missing-status':shutil.rmtree(status_folder)
        elif case=='bad-status-hash':(status_folder/'raw.bin').write_bytes(bytes(168))
        elif case=='rebound-status-bytes':
            files,_,_=snapshot(status_folder);files['raw.bin']=bytes(168)
            for p in status_folder.iterdir():p.unlink()
            for n,raw in files.items():w.card.put(status_folder,n,raw)
            w.b.seal(status_folder)
        else:
            epoch=folder/'epoch-1';raw=bytearray((epoch/'before.bin').read_bytes());raw[167]^=1
            (epoch/'before.bin').write_bytes(raw)
            for p in (epoch/'SHA256SUMS',epoch/'COMMITTED'):p.unlink()
            w.b.seal(epoch)
        try:analyze_success(folder,sdk)
        except (ValueError,OSError,KeyError) as e:archive_negatives[case]=dict(rejected=True,error=str(e))
        else:raise ValueError('invalid STATUS archive accepted: '+case)
    w.require(revision.sources()==frozen,'source drift after native review')
    report=dict(schema='A23-status-capture-revision-audit-1',passed=True,source_count=len(frozen),prior_sources_unchanged=587,source_hashes=frozen,native_cases=37,accepted=accepted,native_failures=failures,historical_status=historical,historical_native_status65_passed=True,historical_negatives=negatives,archive_negatives=archive_negatives,native_matrix=matrix,native_compiler_jobs=1,sanitizers=['address','undefined'],formal_records=0,formal_reservations=0,authorization_consumptions=0,usb_requests=0,sd_accesses=0,real_sdk_objects=0,actual_acquisition_invocations=0,remaining=0,hardware_verified=False,physical_run_authenticated=False,callback_drain_verified=False,formal_candidate_built=False,new_scope_bound=False,device_firmware_changed=False)
    w.write(output/'audit.json',report);w.b.seal(output);old.prior.sealed(output)
    return old.prior.reference(output)


def verify(output):
    output=w.canonical(output);old.prior.sealed(output);report=w.load(output/'audit.json')
    w.require(report['source_count']==592 and report['prior_sources_unchanged']==587 and report['native_cases']==37,'audit totals differ')
    w.require(report['passed'] is True and set(report['accepted'])==SUCCESS,'audit acceptance differs')
    sdk=analyzer(output)
    for case in SUCCESS:w.require(analyze_success(output/'accepted'/case,sdk)==report['accepted'][case],'saved STATUS analysis changed')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);args=p.parse_args()
    print(json.dumps(run(args.output) if args.output else dict(passed=verify(args.check)['passed']),indent=2))
