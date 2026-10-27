"""One prepared matched single-burst diagnostic, with consumed gate and fresh preflight."""
from datetime import datetime
import hashlib,json,os
from pathlib import Path
import subprocess,sys
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2];PRIVATE=ROOT/'private'
sys.path.insert(0,str(ROOT/'tools'))
from analyze_burst_window import analyze
from workflows.artifacts import verify
from analyze_native_serial_run import rows

def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def now():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
def checksums(folder):
    files=sorted(p for p in folder.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    (folder/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(folder))+'\n' for p in files))

def main():
    plan_path=PRIVATE/'analysis/A23-next-test.json';plan=json.loads(plan_path.read_text())
    if not plan.get('single_burst_prepared') or plan.get('single_burst_diagnostic_stage')!='prepared' or plan.get('single_burst_remaining')!=1:
        raise ValueError('No single burst window is prepared; no USB accessed')
    for path,key in [(Path(__file__),'single_burst_entry_sha256'),(ROOT/'tools/analyze_burst_window.py','single_burst_analyzer_sha256'),(ROOT/'tools/analyze_native_serial_run.py','single_burst_serial_analyzer_sha256')]:
        assert hashlib.sha256(path.read_bytes()).hexdigest()==plan[key], 'Prepared entry/analysis changed'
    host=PRIVATE/'host-A23-burst-window-1';verify(host);meta=json.loads((host/'manifest.json').read_text())
    assert meta['validation_passed'] and json.loads((host/'validation.json').read_text())['passed']
    assert meta['backend_identical_to_no_td'] and meta['repeats']==1
    baseline=PRIVATE/'host-A23-no-td-window';verify(baseline)
    base=json.loads((baseline/'manifest.json').read_text())
    assert meta['static_library_sha256']==base['static_library_sha256'] and meta['backend_sha256']==base['backend_sha256']
    collection=Path(plan['latest_no_td_collection']);verify(collection)
    assert json.loads((collection/'collection.json').read_text())['strict_no_td_acceptance_passed']
    verify(PRIVATE/'packages-A23-interval1/A');verify(PRIVATE/'host-A23-native-guard-serial')
    deployment=Path((PRIVATE/'deployments/latest-A23.txt').read_text().strip());verify(deployment)
    deployed=json.loads((deployment/'deployment.json').read_text())
    assert deployed['revision']=='A23' and deployed['status']=='deployed_and_readback_verified' and deployed['ejected']
    for file in deployed['files']:
        assert hashlib.sha256((PRIVATE/'packages-A23-interval1/A'/file['path']).read_bytes()).hexdigest()==file['sha256']
    run=PRIVATE/'runs'/('A-A23-HS-burst-window-'+datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S'));run.mkdir(exist_ok=False)
    plan.update(single_burst_prepared=False,single_burst_remaining=0,single_burst_diagnostic_stage='preflight',
        latest_single_burst_run=str(run),next_action='One single-burst invocation in progress; no further submission scheduled.');write(plan_path,plan)
    acquisition=dict(created_at=now(),host_revision='burst-window-1',device_revision='A23',host_build=str(host),
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
        plan.update(single_burst_diagnostic_stage='preflight_failed',next_action='Single-burst tool validated; hardware preflight failed. Fresh HS/IDLE device required before another invocation.');write(plan_path,plan)
        checksums(run);return 1
    cmd=[str(host/'iso-probe-burst-window'),'--burst','--repeat','1','--packets','960','--trigger-delay-ms','40','--log',str(run/'host.jsonl')];write(run/'command.json',cmd)
    acquisition.update(phase='capturing',receiver_invocations=1,started_at=now());write(run/'acquisition.json',acquisition)
    with (run/'stdout.txt').open('x') as out,(run/'native-stderr.txt').open('x') as err:
        process=subprocess.Popen(cmd,stdout=out,stderr=err,env=dict(os.environ,ISO_NATIVE_LOG_PATH=str(run/'native-stderr.txt')))
        try:rc=process.wait(timeout=20);acquisition['watchdog_timeout']=False
        except subprocess.TimeoutExpired:
            acquisition['watchdog_timeout']=True;process.terminate()
            try:rc=process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();rc=process.wait();acquisition['watchdog_kill']=True
    (run/'exit-code.txt').write_text(str(rc)+'\n')
    try:trigger_count=sum(r.get('kind')=='host_trigger_timing' for r in rows(run/'host.jsonl'))
    except (OSError,ValueError):trigger_count=None
    acquisition.update(phase='captured',receiver_exit_code=rc,finished_at=now(),switch_log_pending=True,device_trigger_count=trigger_count);write(run/'acquisition.json',acquisition)
    try:evidence=analyze(run)
    except (OSError,ValueError,KeyError) as error:evidence=dict(evidence_complete=False,host_single_burst_passed=False,error=str(error),switch_log_pending=True)
    write(run/'single-burst-evidence.json',evidence)
    plan.update(single_burst_diagnostic_stage='captured_logs_pending',latest_single_burst_host_passed=bool(evidence['host_single_burst_passed']),
        next_action='One single-burst invocation complete; collect and match full Switch log before another diagnostic; serial remains stopped.');write(plan_path,plan)
    checksums(run);print(json.dumps(evidence,indent=2),flush=True)
    return 0 if rc==0 and evidence['host_single_burst_passed'] else 1

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError,KeyError,AssertionError) as error:print(str(error),file=sys.stderr);sys.exit(1)
