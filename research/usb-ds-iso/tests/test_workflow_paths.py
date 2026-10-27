"""Archive restoration must preserve current state and never launch captures."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from workflows.artifacts import restore, relative_pointer, verify

class WorkflowPathsTests(unittest.TestCase):
    def test_restore_and_dry_run_preserve_archive_and_active_state(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);archive=base/'archive';source=archive/'module/exefs/main';source.parent.mkdir(parents=True);source.write_bytes(b'original input')
            target=base/'destination'
            result=restore(archive,target,scope='patch',dry_run=True)
            self.assertEqual(result['restored'],['module/exefs/main']);self.assertFalse(target.exists())
            restore(archive,target,scope='patch');self.assertEqual((target/'module/exefs/main').read_bytes(),source.read_bytes())
            (target/'module/exefs/main').write_bytes(b'current state')
            result=restore(archive,target,scope='patch')
            self.assertEqual(result['existing_preserved'],['module/exefs/main']);self.assertEqual((target/'module/exefs/main').read_bytes(),b'current state');self.assertEqual(source.read_bytes(),b'original input')

    def test_missing_archive_input_does_not_create_partial_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);a=base/'archive';a.mkdir();d=base/'destination'
            with self.assertRaises(FileNotFoundError):restore(a,d,scope='patch')
            self.assertFalse(d.exists())

    def test_pointer_and_checksum_paths_are_contained(self):
        self.assertEqual(relative_pointer('/old/research/usb-ds-iso/private/runs/run-1'),Path('runs/run-1'))
        for value in ['/etc/passwd','../outside','runs/../../outside']:
            with self.assertRaises(ValueError):relative_pointer(value)
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);p=folder/'data';p.write_bytes(b'original');(folder/'SHA256SUMS').write_text(hashlib.sha256(p.read_bytes()).hexdigest()+'  data\n')
            self.assertEqual(verify(folder)['files'],1);p.write_bytes(b'changed')
            with self.assertRaises(ValueError):verify(folder)

    def test_cli_status_works_from_another_directory_and_failed_stage_blocks_capture(self):
        cmd=[sys.executable,str(ROOT/'tools/experiment.py')]
        r=subprocess.run(cmd+['status'],cwd='/tmp',capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        # A current failed phase must block before receiver/preflight invocation.
        import json
        state=json.loads(r.stdout)
        if state.get('stage') in ['native_guard_serial_prepared','native_guard_serial_matched_prepared','host_clock_audit_prepared','host_serial_clock_prepared']:self.skipTest('active stage is prepared')
        r=subprocess.run(cmd+['test'],cwd='/tmp',capture_output=True,text=True)
        self.assertEqual(r.returncode,1);self.assertIn('no USB accessed',r.stderr)
