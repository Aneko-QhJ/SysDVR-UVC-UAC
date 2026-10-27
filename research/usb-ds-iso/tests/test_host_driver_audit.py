import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1] / 'tools/audit_host_driver.py'
spec = importlib.util.spec_from_file_location('audit_host_driver', TOOL)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def sample(symbol_name='foo'):
    """A member at 128 whose code/symbol offsets are fileset-relative."""
    data = bytearray(1200)
    struct.pack_into('<8I', data, 0, 0xFEEDFACF, 0x100000C, 0, 12, 1, 40, 0, 0)
    struct.pack_into('<IIQQII', data, 32, 0x80000035, 40, 0x800, 128, 32, 0)
    data[64:69] = b'test\0'
    struct.pack_into('<8I', data, 128, 0xFEEDFACF, 0x100000C, 0, 11, 2, 176, 0, 0)
    struct.pack_into('<II16sQQQQiiII', data, 160, 0x19, 152, b'__TEXT_EXEC',
                     0x1000, 4, 512, 4, 7, 5, 1, 0)
    struct.pack_into('<16s16sQQIIIIIIII', data, 232, b'__text', b'__TEXT_EXEC',
                     0x1000, 4, 512, 2, 0, 0, 0x80000400, 0, 0, 0)
    strings = b'\0' + symbol_name.encode() + b'\0'
    struct.pack_into('<IIIIII', data, 312, 2, 24, 768, 1, 1000, len(strings))
    data[512:516] = bytes.fromhex('c0035fd6')
    struct.pack_into('<IBBHQ', data, 768, 1, 0xF, 1, 0, 0x1000)
    data[1000:1000 + len(strings)] = strings
    return data


class HostDriverAuditTest(unittest.TestCase):
    def test_selected_function_is_exported_with_disassembly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input'
            source.write_bytes(sample())
            output = root / 'evidence'
            with patch.object(audit.subprocess, 'check_output', return_value='ret\n') as disassemble:
                result = audit.audit(source, output, 'objdump', ('test',), ('foo',))
            target = result['modules'][0]['targets'][0]
            self.assertEqual((target['name'], target['fileoff'], target['end']), ('foo', 512, 0x1004))
            self.assertEqual(target['sha256'], audit.digest(bytes.fromhex('c0035fd6')))
            self.assertEqual((output / 'foo.asm').read_text(), 'ret\n')
            self.assertIn('1000\tfoo\tselected', (output / 'test.tsv').read_text())
            disassemble.assert_called_once()
            self.assertIn('--start-address=0x1000', disassemble.call_args.args[0])

    def test_default_targets_survive_multiple_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input'
            source.write_bytes(sample('translateCompletionCode'))
            result = audit.audit(source, module_names=('test', 'test'))
            self.assertEqual([m['targets'][0]['name'] for m in result['modules']],
                             ['translateCompletionCode', 'translateCompletionCode'])

    def test_member_uses_fileset_offsets(self):
        fs = audit.Fileset(bytes(sample()))
        module = fs.module('test')
        self.assertEqual(module['symbols'][0]['name'], 'foo')
        text = module['sections'][0]
        self.assertEqual(fs.read(text['offset'], text['size']), bytes.fromhex('c0035fd6'))

    def test_bad_load_command_rejected(self):
        data = sample()
        struct.pack_into('<I', data, 36, 0xFFFFFFF8)
        with self.assertRaises(ValueError):
            audit.Fileset(bytes(data))

    def test_symbol_table_bounds_rejected(self):
        data = sample()
        struct.pack_into('<I', data, 320, 1199)
        with self.assertRaises(ValueError):
            audit.Fileset(bytes(data)).module('test')

    def test_string_must_terminate(self):
        data = sample()
        data[1004] = ord('x')
        with self.assertRaises(ValueError):
            audit.Fileset(bytes(data)).module('test')

    def test_existing_output_rejected_before_input_read(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            marker = output / 'preserve'
            marker.write_text('frozen')
            with self.assertRaises(FileExistsError):
                audit.audit(output / 'missing-input', output)
            self.assertEqual(marker.read_text(), 'frozen')


if __name__ == '__main__':
    unittest.main()
