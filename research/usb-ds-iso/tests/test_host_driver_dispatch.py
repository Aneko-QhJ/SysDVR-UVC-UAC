import sys
from pathlib import Path
import struct
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_host_driver import Fileset
from audit_host_driver_dispatch import KernelCache, resolve_auth_stub


def cache_bytes(pointer_format=8, cache_level=0):
    data = bytearray(512)
    struct.pack_into('<8I', data, 0, 0xFEEDFACF, 0x100000C, 0, 12, 2, 88, 0, 0)
    struct.pack_into('<II16sQQQQiiII', data, 32, 0x19, 72, b'__TEXT',
                     0x1000, 512, 0, 512, 7, 5, 0, 0)
    struct.pack_into('<IIII', data, 104, 0x80000034, 16, 200, 64)
    struct.pack_into('<7I', data, 200, 0, 28, 0, 0, 0, 0, 0)
    struct.pack_into('<II', data, 228, 1, 8)
    struct.pack_into('<IHHQIH', data, 236, 24, 4096, pointer_format, 0, 0, 1)
    struct.pack_into('<Q', data, 400, 0x8011BF4F00000040 | cache_level << 30)
    return data


class DispatchAuditTest(unittest.TestCase):
    def test_pointer_target_excludes_authentication_fields(self):
        cache = KernelCache(Fileset(bytes(cache_bytes())))
        self.assertEqual(cache.resolve(0x1190)['target'], 0x1040)

    def test_non_root_cache_rejected(self):
        cache = KernelCache(Fileset(bytes(cache_bytes(cache_level=1))))
        with self.assertRaises(ValueError):
            cache.resolve(0x1190)

    def test_other_pointer_format_rejected(self):
        cache = KernelCache(Fileset(bytes(cache_bytes(pointer_format=7))))
        with self.assertRaises(ValueError):
            cache.resolve(0x1190)

    def test_virtual_read_cannot_cross_backed_range(self):
        cache = KernelCache(Fileset(bytes(cache_bytes())))
        with self.assertRaises(ValueError):
            cache.read(0x11FE, 4)

    def test_chained_record_cannot_extend_outside_blob(self):
        data = cache_bytes()
        struct.pack_into('<I', data, 236, 100)
        with self.assertRaises(ValueError):
            KernelCache(Fileset(bytes(data)))

    def test_arbitrary_instructions_are_not_followed_as_stub(self):
        cache = KernelCache(Fileset(bytes(cache_bytes())))
        with self.assertRaises(ValueError):
            resolve_auth_stub(cache, 0x1180)


if __name__ == '__main__':
    unittest.main()
