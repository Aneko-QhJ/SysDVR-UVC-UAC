"""One prepared bounded matched serial diagnostic, with consumed gate and fresh preflight."""
from datetime import datetime
import hashlib,json,os
from pathlib import Path
import subprocess,sys
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2];PRIVATE=ROOT/'private'
sys.path.insert(0,str(ROOT/'tools'))
from analyze_matched_serial_run import analyze
from workflows.artifacts import verify
from analyze_native_serial_run import rows

def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def now():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
def checksums(folder):
    files=sorted(p for p in folder.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    (folder/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(folder))+'\n' for p in files))

def main():
    plan_path=PRIVATE/'analysis/A23-next-test.json';plan=json.loads(plan_path.read_text())
    if not plan.get('matched_serial_prepared') or plan.get('matched_serial_diagnostic_stage')!='prepared' or plan.get('matched_serial_remaining')!=1:
        raise ValueError('No matched serial stage is prepared; no USB accessed')
    assert plan.get('stage')=='native_guard_serial_matched_prepared' and plan.get('next_test_repeats')==16
    for path,key in [(Path(__file__),'matched_serial_entry_sha256'),(ROOT/'tools/analyze_matched_serial_run.py','matched_serial_analyzer_sha256'),(ROOT/'tools/analyze_native_serial_run.py','matched_serial_serial_analyzer_sha256')]:
        assert hashlib.sha256(path.read_bytes()).hexdigest()==plan[key], 'Prepared entry/analysis changed'
    host=PRIVATE/'host-A23-matched-serial-2';verify(host);meta=json.loads((host/'manifest.json').read_text())
    assert hashlib.sha256((host/'manifest.json').read_bytes()).hexdigest()==plan['matched_serial_manifest_sha256']
    assert meta['validation_passed'] and json.loads((host/'validation.json').read_text())['passed']
    assert meta['backend_identical_to_no_td'] and meta['max_repeats']==16
    baseline=PRIVATE/'host-A23-no-td-window';verify(baseline)
    base=json.loads((baseline/'manifest.json').read_text())
    assert meta['static_library_sha256']==base['static_library_sha256'] and meta['backend_sha256']==base['backend_sha256']
    collection=Path(plan['latest_no_td_collection']);verify(collection)
    assert json.loads((collection/'collection.json').read_text())['strict_no_td_acceptance_passed']
    burst_collection=Path(plan['latest_single_burst_collection']);verify(burst_collection)
    assert json.loads((burst_collection/'collection.json').read_text())['strict_single_acceptance_passed']
    verify(PRIVATE/'packages-A23-interval1/A');verify(PRIVATE/'host-A23-native-guard-serial')
    deployment=Path((PRIVATE/'deployments/latest-A23.txt').read_text().strip());verify(deployment)
    deployed=json.loads((deployment/'deployment.json').read_text())
    assert deployed['revision']=='A23' and deployed['status']=='deployed_and_readback_verified' and deployed['ejected']
    for file in deployed['files']:
        assert hashlib.sha256((PRIVATE/'packages-A23-interval1/A'/file['path']).read_bytes()).hexdigest()==file['sha256']
    run=PRIVATE/'runs'/('A-A23-HS-matched-serial-'+datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S'));run.mkdir(exist_ok=False)
    plan.update(stage='native_guard_serial_matched_running',next_test_repeats=0,matched_serial_prepared=False,matched_serial_remaining=0,matched_serial_diagnostic_stage='preflight',
        latest_matched_serial_run=str(run),next_action='One bounded serial invocation in progress, maximum 16, stop at first failure.');write(plan_path,plan)
    acquisition=dict(created_at=now(),host_revision='native-guard-serial-2',device_revision='A23',host_build=str(host),
        receiver_sha256=meta['receiver_sha256'],device_code_changed=False,receiver_invocations=0,device_trigger_count=0,
        preflight_usb_status_invocations=1,video_closed_requested=True,video_closed_independently_verified=False,
        runtime_revision_identity_verified=False,phase='preflight');write(run/'acquisition.json',acquisition)
    with (run/'preflight.jsonl').open('x') as out,(run/'preflight-stderr.txt').open('x') as err:
        try:rc=subprocess.run([str(host/'preflight')],stdout=out,stderr=err,timeout=20).returncode
        except subprocess.TimeoutExpired:rc=124
    acquisition['preflight_exit_code']=rc
    print('Run:',run,flush=True);print((run/'preflight.jsonl').read_text(),(run/'preflight-stderr.txt').read_text(),flush=True)
    if rc:
        acquisition.update(phase='preflight_failed',finished_at=now(),iso_submission_invocations=0);write(run/'acquisition.json',acquisition)
        plan.update(stage='native_guard_serial_matched_preflight_failed',matched_serial_diagnostic_stage='preflight_failed',next_action='Matched serial tool validated; hardware preflight failed. Fresh HS/IDLE device required before another invocation.');write(plan_path,plan)
        checksums(run);return 1
    cmd=[str(host/'iso-probe-matched-serial'),'--burst','--repeat','16','--packets','960','--trigger-delay-ms','40','--log',str(run/'host.jsonl')];write(run/'command.json',cmd)
    acquisition.update(phase='capturing',receiver_invocations=1,started_at=now());write(run/'acquisition.json',acquisition)
    with (run/'stdout.txt').open('x') as out,(run/'native-stderr.txt').open('x') as err:
        process=subprocess.Popen(cmd,stdout=out,stderr=err,env=dict(os.environ,ISO_NATIVE_LOG_PATH=str(run/'native-stderr.txt')))
        try:rc=process.wait(timeout=45);acquisition['watchdog_timeout']=False
        except subprocess.TimeoutExpired:
            acquisition['watchdog_timeout']=True;process.terminate()
            try:rc=process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();rc=process.wait();acquisition['watchdog_kill']=True
    (run/'exit-code.txt').write_text(str(rc)+'\n')
    try:trigger_count=sum(r.get('kind')=='host_trigger_timing' for r in rows(run/'host.jsonl'))
    except (OSError,ValueError):trigger_count=None
    acquisition.update(phase='captured',receiver_exit_code=rc,finished_at=now(),switch_log_pending=True,device_trigger_count=trigger_count);write(run/'acquisition.json',acquisition)
    try:evidence=analyze(run)
    except (OSError,ValueError,KeyError) as error:evidence=dict(evidence_complete=False,host_serial_passed=False,error=str(error),switch_log_pending=True)
    write(run/'matched-serial-evidence.json',evidence)
    plan.update(stage='native_guard_serial_matched_captured_logs_pending',matched_serial_diagnostic_stage='captured_logs_pending',latest_matched_serial_host_passed=bool(evidence['host_serial_passed']),
        next_action='Bounded serial invocation complete; collect full Switch log before any further submission.');write(plan_path,plan)
    checksums(run);print(json.dumps(evidence,indent=2),flush=True)
    return 0 if rc==0 and evidence['host_serial_passed'] else 1

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError,KeyError,AssertionError) as error:print(str(error),file=sys.stderr);sys.exit(1)
