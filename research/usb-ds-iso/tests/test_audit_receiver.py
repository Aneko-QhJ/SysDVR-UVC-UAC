"""Test the exact frozen-source audit receiver without opening USB hardware."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AuditReceiverTests(unittest.TestCase):
    def setUp(self):
        self.build = Path(os.environ.get('ISO_AUDIT_RECEIVER', ROOT/'private/darwin-diag-A18-event-audit'))
        if not (self.build/'manifest.json').exists():
            self.skipTest('requires build_event_audit_receiver.py')
        self.meta = json.loads((self.build/'manifest.json').read_text())

    def test_frozen_source_contains_only_compatibility_edits(self):
        before = (ROOT/'private/darwin-diag-host64-timing/iso-probe.c').read_text()
        after = (self.build/'iso-probe.c').read_text()
        if self.meta.get('device_revision') == 'A23':
            self.assertEqual(after.count('ep->bInterval != 1'), 1)
            after = after.replace('ep->bInterval != 1', 'ep->bInterval != 4')
            self.assertEqual(after.count('n < 64 || n > 960'), 1)
            after = after.replace('n < 64 || n > 960', 'n < 64 || n > 512')
            after = after.replace('packets must be 64..960', 'packets must be 64..512')
            after = after.replace('[--packets 64..960]', '[--packets 64..512]')
        after = after.replace('#include "iso_probe_protocol.h"', '#include "../../../source/uvc/iso_probe_protocol.h"')
        after = after.replace('isoProbeIsBurstDiagnostics(state.diagnostics.magic)',
                              'state.diagnostics.magic == ISO_PROBE_BURST_DIAG_MAGIC',1)
        after = after.replace('(burst_mode ? isoProbeIsBurstDiagnostics(state.diagnostics.magic) : state.diagnostics.magic == ISO_PROBE_DIAG_MAGIC)',
                              'state.diagnostics.magic == (burst_mode ? ISO_PROBE_BURST_DIAG_MAGIC : ISO_PROBE_DIAG_MAGIC)')
        self.assertEqual(after, before)
        self.assertEqual(self.meta['host_frame_lead'], 64)
        self.assertEqual(self.meta['requested_bytes'], 192)

    def test_real_callbacks_keep_payload_and_raw_buffer_requirements(self):
        backend = ROOT/'private/darwin-diag-host64/libusb-1.0.30/libusb'
        with tempfile.TemporaryDirectory(dir=ROOT/'private') as directory:
            for name in ('burst_receiver_test','receiver_diagnostics_test'):
                binary = Path(directory)/name
                command = ['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                           '-DISO_HOST_SLOT_SIZE=192',
                           '-DISO_RECEIVER_SOURCE="'+str(self.build/'iso-probe.c')+'"',
                           '-I'+str(backend),str(ROOT/'tests'/(name+'.c')),
                           str(backend/'.libs/libusb-1.0.a'),'-framework','IOKit',
                           '-framework','CoreFoundation','-framework','Security','-lobjc',
                           '-o',str(binary)]
                subprocess.run(command,check=True)
                log = Path(directory)/(name+'.jsonl')
                subprocess.run([str(binary),str(log)],check=True)
                rows = [json.loads(line) for line in log.read_text().splitlines()]
                self.assertTrue(any(row['kind']=='host_callback_time' for row in rows))

    def test_invalid_parameters_rejected_before_usb_or_log_creation(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'private') as directory:
            upper = '961' if self.meta.get('device_revision') == 'A23' else '513'
            for flags in (['--trigger-delay-ms','0'],['--trigger-delay-ms','501'],
                          ['--packets','63'],['--packets',upper],['--repeat','0'],['--burst','--cancel']):
                log = Path(directory)/'must-not-exist.jsonl'
                result = subprocess.run([str(self.build/'iso-probe-native-diag'),'--log',str(log),*flags],
                                        capture_output=True,text=True)
                self.assertEqual(result.returncode,2)
                self.assertFalse(log.exists())

    def test_a23_large_window_keeps_high_index_payload_and_error_checks(self):
        if self.meta.get('device_revision') != 'A23':
            self.skipTest('requires A23 interval1 window')
        backend=ROOT/'private/darwin-diag-host64/libusb-1.0.30/libusb'
        with tempfile.TemporaryDirectory(dir=ROOT/'private') as directory:
            binary=Path(directory)/'large-window';log=Path(directory)/'large-window.jsonl'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                            '-DISO_HOST_SLOT_SIZE=192','-DISO_RECEIVER_SOURCE="'+str(self.build/'iso-probe.c')+'"',
                            '-I'+str(backend),str(ROOT/'tests/interval_receiver_window_test.c'),
                            str(backend/'.libs/libusb-1.0.a'),'-framework','IOKit','-framework','CoreFoundation',
                            '-framework','Security','-lobjc','-o',str(binary)],check=True)
            subprocess.run([str(binary),str(log)],check=True)
            rows=[json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(len([r for r in rows if r['kind']=='iso_transfer']),9)
            for row in rows:
                if row['kind']=='raw_buffer':self.assertEqual(row['size'],960*192);self.assertTrue(row['saved'])
            transfers=[r for r in rows if r['kind']=='iso_transfer']
            self.assertEqual([p['index'] for p in transfers[-1]['packets'] if p['length']],list(range(944,960)))
