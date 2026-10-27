"""Exercise full serial evidence and awake lifecycle without USB or power changes."""
from pathlib import Path
import contextlib,hashlib,io,json,shutil,sys,tempfile,unittest
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from analyze_serial_clock import analyze
from workflows import capture_awake_serial_clock as awake
from workflows import capture_serial_clock as capture

class SerialClockTests(unittest.TestCase):
    def fixture(self,folder,name='loop-16'):
        shutil.copytree(ROOT/'private/host-A23-serial-clock-1/validation'/name,folder,dirs_exist_ok=True)
        records=[json.loads(l) for l in (folder/'native-stderr.txt').read_text().splitlines()]
        index=0;out=[]
        for r in records:
            if r.get('kind')=='darwin_iso_schedule':
                index+=1;start=index*200_000_000
                r.update(queried_frame=index*200,frame_start=index*200+64)
                out.append(r)
                out.append(dict(kind='darwin_iso_clock_audit',clock='mach_absolute_time',frame_result=0,queried_frame=index*200,start_frame=index*200+64,at_time_ticks=start+1,frame_before_ticks=start,frame_after_ticks=start+2,queue_before_ticks=start+3,queue_after_ticks=start+4,callback_ticks=start+180_000_000,numer=1,denom=1))
            else:out.append(r)
        (folder/'native-stderr.txt').write_text(''.join(json.dumps(r)+'\n' for r in out));return out
    def test_full_serial_and_wrap_with_synthetic_clocks(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t);self.fixture(f);e=analyze(f)
            self.assertTrue(e['host_serial_passed']);self.assertTrue(e['clock_audit_complete']);self.assertEqual(e['observed_ring_wraps'],1)
            self.assertFalse(e['serial_acceptance_passed']);self.assertFalse(e['root_cause_confirmed'])
    def test_native_bitmap_ring_failure_stops_and_is_not_hidden(self):
        for name in ['loop-2-0-0','loop-0-2-0','loop-0-0-2']:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as t:
                f=Path(t);self.fixture(f,name);e=analyze(f)
                self.assertTrue(e['clock_audit_complete']);self.assertFalse(e['host_serial_passed']);self.assertEqual(e['callbacks'],2);self.assertTrue(e['no_submission_after_failure'])
    def test_missing_extra_invalid_mismatched_and_reordered_clock_evidence(self):
        for case in ['missing','extra','invalid','mismatch','order','timebase']:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as t:
                f=Path(t);rows=self.fixture(f);clocks=[r for r in rows if r.get('kind')=='darwin_iso_clock_audit']
                if case=='missing':rows.remove(clocks[0])
                if case=='extra':rows.append(clocks[0])
                if case=='invalid':clocks[0]['numer']='bad'
                if case=='mismatch':clocks[0]['queried_frame']+=1
                if case=='order':clocks[0]['callback_ticks']=clocks[1]['frame_before_ticks']+1
                if case=='timebase':clocks[1]['denom']=2
                (f/'native-stderr.txt').write_text(''.join(json.dumps(r)+'\n' for r in rows));e=analyze(f)
                self.assertTrue(e['base_host_serial_passed']);self.assertFalse(e['clock_audit_complete']);self.assertFalse(e['host_serial_passed'])
    def test_capture_consumes_once_before_preflight_and_stale_hash_blocks_USB(self):
        for stale in [False,True]:
            with self.subTest(stale=stale),tempfile.TemporaryDirectory() as t:
                base=Path(t);(base/'analysis').mkdir();(base/'runs').mkdir()
                for name in ['host-A23-serial-clock-1','host-A23-clock-audit-1','host-A23-native-guard-serial','packages-A23-interval1','deployments']:
                    (base/name).symlink_to(ROOT/'private'/name,target_is_directory=True)
                plan=json.loads((ROOT/'private/analysis/A23-next-test.json').read_text())
                plan.update(serial_clock_prepared=True,serial_clock_remaining=1,serial_clock_diagnostic_stage='prepared',serial_clock_max_bursts=16,stage='host_serial_clock_prepared')
                for path,key in [(Path(capture.__file__),'serial_clock_entry_sha256'),(ROOT/'tools/analyze_serial_clock.py','serial_clock_analyzer_sha256'),(ROOT/'tools/analyze_native_serial_run.py','serial_clock_serial_analyzer_sha256'),(ROOT/'tools/analyze_matched_serial_run.py','serial_clock_matched_analyzer_sha256'),(ROOT/'tools/analyze_clock_audit.py','serial_clock_clock_analyzer_sha256'),(ROOT/'tools/analyze_burst_window.py','serial_clock_burst_analyzer_sha256'),(ROOT/'private/host-A23-serial-clock-1/manifest.json','serial_clock_manifest_sha256')]:
                    plan[key]=hashlib.sha256(path.read_bytes()).hexdigest()
                if stale:plan['serial_clock_entry_sha256']='invalid'
                target=base/'analysis/A23-next-test.json';target.write_text(json.dumps(plan))
                # All artifact checks are real; only preflight is mocked, with no receiver allowed.
                with patch.object(capture,'PRIVATE',base),patch.object(capture.subprocess,'run',return_value=Mock(returncode=1)) as preflight,patch.object(capture.subprocess,'Popen') as receiver,contextlib.redirect_stdout(io.StringIO()):
                    if stale:
                        with self.assertRaises(AssertionError):capture.main()
                        preflight.assert_not_called()
                    else:
                        self.assertEqual(capture.main(),1);preflight.assert_called_once()
                        updated=json.loads(target.read_text());self.assertEqual(updated['serial_clock_remaining'],0);self.assertFalse(updated['serial_clock_prepared'])
                        with self.assertRaises(ValueError):capture.main()
                        self.assertEqual(preflight.call_count,1)
                    receiver.assert_not_called()

    def test_awake_assertion_gate_and_release_on_success_or_failure(self):
        for verified in [True,False]:
            with self.subTest(verified=verified),tempfile.TemporaryDirectory() as t:
                base=Path(t);(base/'analysis').mkdir();col=base/'collection';col.mkdir();(col/'collection.json').write_text(json.dumps(dict(runtime_revision_identity_verified=True,all_submissions_and_completions_match=True,ejected=True)))
                plan=base/'analysis/A23-next-test.json';plan.write_text(json.dumps(dict(serial_clock_prepared=True,stage='host_serial_clock_prepared',serial_clock_remaining=1,serial_clock_awake_required=True,awake_serial_clock_entry_sha256=hashlib.sha256(Path(awake.__file__).read_bytes()).hexdigest(),latest_clock_audit_collection=str(col))))
                guard=Mock(pid=123);guard.poll.return_value=None
                def run(cmd,**kw):
                    if cmd[0]=='pmset':return Mock(returncode=0,stdout='pid 123(caffeinate)' if verified else 'no assertion',stderr='')
                    p=json.loads(plan.read_text());p.update(latest_serial_clock_run='mock-run');plan.write_text(json.dumps(p));return Mock(returncode=0)
                with patch.object(awake,'PRIVATE',base),patch.object(awake,'verify'),patch.object(awake.subprocess,'Popen',return_value=guard),patch.object(awake.subprocess,'run',side_effect=run) as calls,patch.object(awake.time,'sleep'),contextlib.redirect_stdout(io.StringIO()):
                    if verified:self.assertEqual(awake.main(),0)
                    else:
                        with self.assertRaises(AssertionError):awake.main()
                    workflows=[c for c in calls.call_args_list if c.args[0][0]!= 'pmset']
                    self.assertEqual(len(workflows),1 if verified else 0)
                guard.terminate.assert_called_once();guard.wait.assert_called_once()
                record=json.loads(next((base/'analysis').glob('A23-awake-serial-clock-*/awake.json')).read_text());self.assertTrue(record['caffeinate_released']);self.assertEqual(record['max_bursts'],16)

if __name__=='__main__':unittest.main()
