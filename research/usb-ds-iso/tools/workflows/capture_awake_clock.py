"""One prepared serial invocation with temporary, verified idle-sleep prevention."""
from datetime import datetime
import hashlib,json,subprocess,sys,time
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2];PRIVATE=ROOT/'private'
sys.path.insert(0,str(ROOT/'tools'))
from workflows.artifacts import verify
from workflows.capture_clock_audit import checksums,write,now

def main():
    plan_path=PRIVATE/'analysis/A23-next-test.json';plan=json.loads(plan_path.read_text())
    if not (plan.get('clock_audit_prepared') and plan.get('stage')=='host_clock_audit_prepared' and plan.get('clock_audit_remaining')==1 and plan.get('clock_audit_awake_required')):
        raise ValueError('No awake clock invocation is prepared; no USB accessed')
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==plan['awake_clock_entry_sha256']
    collection=Path(plan['latest_matched_serial_collection']);verify(collection)
    collected=json.loads((collection/'collection.json').read_text())
    assert collected['runtime_revision_identity_verified'] and collected['all_submissions_and_completions_match'] and collected['ejected']
    folder=PRIVATE/'analysis'/('A23-awake-clock-'+datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S'));folder.mkdir()
    (folder/'runner.py').write_bytes(Path(__file__).read_bytes())
    (folder/'plan-snapshot.json').write_bytes(plan_path.read_bytes())
    record=dict(started_at=now(),previous_verified_collection=str(collection),max_bursts=1,receiver_changed=False,backend_changed=False,receiver_workflow_started=False,sleep_hypothesis_confirmed=False)
    def save(args,name):
        r=subprocess.run(args,capture_output=True,text=True,timeout=20)
        (folder/name).write_text(r.stdout+r.stderr);return r
    save(['pmset','-g','assertions'],'assertions-before.txt');save(['pmset','-g','batt'],'power-source.txt')
    guard=subprocess.Popen(['/usr/bin/caffeinate','-dims','-t','120'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    record['caffeinate_pid']=guard.pid
    rc=1
    try:
        time.sleep(0.5)
        r=save(['pmset','-g','assertions'],'assertions-during.txt')
        assert guard.poll() is None and r.returncode==0 and 'pid '+str(guard.pid)+'(caffeinate)' in r.stdout
        record['caffeinate_assertion_verified_before_capture']=True
        record['receiver_workflow_started']=True
        with (folder/'workflow-output.txt').open('x') as out,(folder/'workflow-stderr.txt').open('x') as err:
            rc=subprocess.run([sys.executable,str(ROOT/'tools/workflows/capture_clock_audit.py')],stdout=out,stderr=err,timeout=80).returncode
        current=json.loads(plan_path.read_text())
        record.update(workflow_exit_code=rc,run=current.get('latest_clock_audit_run'),caffeinate_alive_after_capture=guard.poll() is None)
        save(['pmset','-g','assertions'],'assertions-after-capture.txt')
        current.update(clock_awake_evidence=str(folder),clock_audit_awake_required=False)
        write(plan_path,current)
        print('Run:',record['run'],'exit:',rc,'awake evidence:',folder,flush=True)
    finally:
        if guard.poll() is None:guard.terminate()
        guard.wait(timeout=5)
        record.update(finished_at=now(),caffeinate_released=True)
        write(folder/'awake.json',record);checksums(folder)
    return rc

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError,KeyError,AssertionError,subprocess.TimeoutExpired) as error:print(str(error),file=sys.stderr);sys.exit(1)
