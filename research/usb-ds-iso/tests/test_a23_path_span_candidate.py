import tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_a23_path_span_candidate as p

class PathCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-path-candidate-');cls.root=Path(cls.tmp.name)/'review';cls.result=p.run(cls.root)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_new_bound_identity_and_arm_link(self):
        r=self.result;self.assertEqual(len(r['source_hashes']),219);self.assertEqual(r['build']['object_count'],14);self.assertEqual(r['build']['strict_format_units'],14)
        self.assertNotEqual(r['device_binding']['device_elf_sha256'],p.b.sha(p.b.plain(p.DEVICE/'full.elf')))
    def test_five_full_width_static_objects(self):
        r=self.result['build']['machine_review'];self.assertTrue(r['path_objects_in_bss']);self.assertEqual(len(r['linked_path_objects']),5);self.assertEqual(r['total_path_storage_bytes'],3845)
    def test_only_path_files_and_recipe_change(self):
        self.assertEqual(len(self.result['changed_files']),6)
        for n in ('main.npdm','sysmodule.json','source/sysmodule/main.c','source/core.c','source/uvc/uvc_device.c'):
            self.assertEqual((self.root/'candidate'/n).read_bytes(),(p.DEVICE/n).read_bytes())
    def test_replay_preserves_failures_no_retry_and_retention(self):
        r=self.result;self.assertEqual(r['model_count'],46)
        self.assertTrue(r['models']['lifecycle']['diagnostic-ok-ok']['retained']);self.assertEqual(r['models']['lifecycle']['normal-ok-ok']['thread_closes'],2)
        for row in r['models']['adapter'].values():self.assertLessEqual(row['creates'],1)
    def test_failed_joins_still_precede_filesystem_access(self):
        for n,row in self.result['models']['lifecycle'].items():
            if 'join-error' in n:self.assertEqual(row['fs_open'],0)
    def test_quiet_worker_does_not_reach_file_paths(self):
        for row in self.result['build']['linked_checks']['worker_graphs'].values():
            self.assertFalse(row['production_capture_on_direct_graph']);self.assertFalse(any(n.startswith('Ep0Life') for n in row['direct_reachable_functions']))
    def test_formal_artifacts_and_authority_not_changed(self):
        for n in ('arm_executed','firmware_packaged','deployed','host_receiver_rebound','root_cause_confirmed'):
            self.assertFalse(self.result[n])
        self.assertFalse(self.result['build']['machine_review']['whole_call_graph_stack_verified']);self.assertEqual(self.result['remaining'],0)
        with self.assertRaises(ValueError):p.run(self.root)

if __name__=='__main__':unittest.main()
