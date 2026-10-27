"""Archive round trips and refusal paths protecting the only original copy."""
import hashlib
import json
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from research_storage import MANIFEST, Storage, snapshot


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'analysis' / 'old-review'
        self.source.mkdir(parents=True)
        (self.source / 'empty').mkdir()
        (self.source / 'program').write_bytes(b'original bytes\x00\xff' * 100)
        (self.source / 'program').chmod(0o755)
        sums = hashlib.sha256((self.source / 'program').read_bytes()).hexdigest() + '  program\n'
        (self.source / 'SHA256SUMS').write_text(sums)
        (self.source / 'COMMITTED').write_text(hashlib.sha256(sums.encode()).hexdigest() + '\n')
        self.storage = Storage(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_pack_prune_restore_preserves_bytes_mode_time_and_empty_directories(self):
        before = snapshot(self.source)
        packed = self.storage.pack('old-review')
        self.assertTrue(self.source.exists())
        self.assertEqual(packed['files'], 3)
        self.assertTrue(self.storage.prune('old-review')['restore_rehearsal_passed'])
        self.assertFalse(self.source.exists())
        self.storage.restore('old-review')
        self.assertEqual(snapshot(self.source), before)
        self.assertTrue(os.access(self.source / 'program', os.X_OK))

    def test_modified_original_blocks_prune(self):
        self.storage.pack('old-review')
        (self.source / 'program').write_bytes(b'new work')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            self.storage.prune('old-review')
        self.assertEqual((self.source / 'program').read_bytes(), b'new work')

    def test_added_file_blocks_prune(self):
        self.storage.pack('old-review')
        (self.source / 'new-evidence').write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            self.storage.prune('old-review')
        self.assertTrue((self.source / 'new-evidence').exists())

    def test_corrupt_archive_blocks_prune(self):
        self.storage.pack('old-review')
        self.storage.archive('old-review').write_bytes(b'broken zip')
        with self.assertRaises(zipfile.BadZipFile):
            self.storage.prune('old-review')
        self.assertTrue((self.source / 'program').exists())

    def test_failed_restore_rehearsal_keeps_original(self):
        self.storage.pack('old-review')
        before = snapshot(self.source)
        with patch.object(self.storage, 'unpack', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.storage.prune('old-review')
        self.assertEqual(snapshot(self.source), before)

    def test_restore_refuses_existing_destination(self):
        self.storage.pack('old-review')
        before = snapshot(self.source)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.storage.restore('old-review')
        self.assertEqual(snapshot(self.source), before)

    def test_bad_seal_blocks_pack(self):
        (self.source / 'program').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'sealed file differs'):
            self.storage.pack('old-review')
        self.assertFalse(self.storage.archive('old-review').exists())

    def test_symlink_and_path_escape_are_rejected(self):
        (self.source / 'link').symlink_to(self.source / 'program')
        with self.assertRaisesRegex(ValueError, 'not a regular file'):
            self.storage.pack('old-review')
        for name in ('../runs', '/tmp', 'a/b', '..', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.storage.pack(name)

    def test_malicious_zip_path_does_not_escape_restore(self):
        self.storage.pack('old-review')
        archive = self.storage.archive('old-review')
        manifest = self.storage.read(archive)
        manifest['files'] = {'../escape': dict(size=4, sha256=hashlib.sha256(b'evil').hexdigest(), mode=0o600, mtime_ns=0)}
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr(MANIFEST, json.dumps(manifest))
            z.writestr('../escape', b'evil')
        with self.assertRaisesRegex(ValueError, 'unsafe archive path'):
            self.storage.restore('old-review', self.root / 'restored')
        self.assertFalse((self.root / 'escape').exists())

    def test_finder_cleanup_keeps_manifest_bound_file_and_can_recover(self):
        (self.source / '.DS_Store').write_bytes(b'extraneous')
        bound = self.root / 'analysis' / 'bound'
        bound.mkdir()
        (bound / '.DS_Store').write_bytes(b'sealed metadata')
        (bound / 'SHA256SUMS').write_text(hashlib.sha256(b'sealed metadata').hexdigest() + '  .DS_Store\n')
        result = self.storage.pack_finder('finder-backup')
        self.assertEqual(result['files'], 1)
        self.assertEqual(len(result['bound_metadata_preserved']), 1)
        self.storage.prune('finder-backup')
        self.assertFalse((self.source / '.DS_Store').exists())
        self.assertEqual((bound / '.DS_Store').read_bytes(), b'sealed metadata')
        recovered = self.root / 'metadata-recovery'
        self.storage.restore('finder-backup', recovered)
        self.assertEqual((recovered / 'analysis/old-review/.DS_Store').read_bytes(), b'extraneous')

    def test_metadata_bound_after_pack_blocks_removal(self):
        extra = self.source / '.DS_Store'
        extra.write_bytes(b'now bound')
        self.storage.pack_finder('finder-backup')
        with (self.source / 'SHA256SUMS').open('a') as sums:
            sums.write(hashlib.sha256(extra.read_bytes()).hexdigest() + '  .DS_Store\n')
        with self.assertRaisesRegex(ValueError, 'not disposable'):
            self.storage.prune('finder-backup')
        self.assertTrue(extra.exists())

    def test_duplicate_archive_member_rejected(self):
        self.storage.pack('old-review')
        archive = self.storage.archive('old-review')
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(archive, 'a') as z:
                z.writestr(MANIFEST, b'duplicate')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.storage.prune('old-review')
        self.assertTrue(self.source.exists())

    def test_equal_contents_stored_once_but_restored_as_independent_files(self):
        copy = self.source / 'copy'
        copy.write_bytes((self.source / 'program').read_bytes())
        copy.chmod(0o644)
        packed = self.storage.pack('old-review')
        self.assertEqual(packed['files'], 4)
        self.assertEqual(packed['distinct_contents'], 3)
        restored = self.root / 'restored'
        self.storage.restore('old-review', restored)
        self.assertNotEqual((restored / 'copy').stat().st_ino, (restored / 'program').stat().st_ino)
        (restored / 'copy').write_bytes(b'change one test case')
        self.assertEqual((restored / 'program').read_bytes(), (self.source / 'program').read_bytes())


if __name__ == '__main__':
    unittest.main()
