from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_io_usb_host_device import audit, BUILD_ID, decode_status

BASE = 0xb9ac00000
FIRST = BASE+0x17d000
CONTROL = 0x47c01411
STARTUP = f"""SysDVR-UVC 1.0.0 initializing...
SysDVR-UVC starting...
ISO diagnostic revision A23 HS ISO7 bInterval1 followup-SIA experiment
ISO HOS 22.5.0
ISO firmware query rc=0x0
ISO usb pid=86 query rc=0x0
ISO usb module query rc=0x0 count=1
ISO usb module[0] BuildID={BUILD_ID} base=b9ac00000 size=369000
ISO usb debug attach rc=0x0
ISO runtime patch result=0 record=21 last-rc=0x0
UVC device initialized
SysDVR-UVC running (video + audio)
"""
BURST = f"""ISO submit seq=1 speed=3 length=3072 rc=0x0 urb=387
ISO timing seq=1 urb=387 frequency=19200000 trigger=10 post-before=11 post-after=12 ack-before=13 ack-after=14
ISO seq=1 URB=387 requested=3072 raw-count=3072 status=3 diag-word2={CONTROL}
USB host disconnected
"""


def status(active=False):
    values = [0x31505349,1,1 if active else 0,2 if active else 0,0,
              387 if active else 0,387 if active else 0,3072 if active else 0,
              3072 if active else 0,3 if active else 0,3 if active else 0,131,0,0]
    diagnostic = bytearray(112)
    if active:
        struct.pack_into("<6IQ",diagnostic,0,0x374f5349,0,CONTROL,1,0xffff,3072,FIRST)
        for i in range(2):
            tag = FIRST+(1+2*i)*16
            struct.pack_into("<5I",diagnostic,32+20*i,tag & 0xffffffff,tag >> 32,0x010000c0,0x78005,0x23e0+i)
        struct.pack_into("<II8I",diagnostic,72,0x22e3,1,0x10001,0x100002e,0x80023001,0,0x1000c00,0,0,0)
    return struct.pack("<14I",*values)+diagnostic


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.before, self.after = status(), status(True)
        self.log = (STARTUP+BURST).encode()

    def result(self):
        return audit(self.before,self.after,self.log)

    def test_correct_relation_preserves_hardware_boundary(self):
        result = self.result()
        self.assertTrue(result["device_status_and_log_relation_matches"])
        self.assertTrue(result["diagnostics"]["own_first_two_event_tags_match"])
        self.assertFalse(result["capture_binding_verified"])
        self.assertFalse(result["firmware_bytes_verified"])
        self.assertFalse(result["hardware_verified"])
        self.assertFalse(result["usb_strict_pass"])

    def test_status_size_magic_version_and_endpoint(self):
        with self.assertRaisesRegex(ValueError,"168"):
            decode_status(self.after[:-1])
        for index, value in ((0,0),(1,2),(2,65536),(3,5),(11,0x82)):
            with self.subTest(index=index):
                bad = bytearray(self.after); struct.pack_into("<I",bad,index*4,value)
                with self.assertRaisesRegex(ValueError,"protocol"):
                    decode_status(bytes(bad))

    def test_fresh_and_terminal_identity_fields(self):
        for index, value in ((2,2),(3,4),(4,1),(5,388),(6,388),(7,0),(8,0),(9,4),(10,4),(13,1)):
            with self.subTest(index=index):
                original = self.after
                bad = bytearray(original); struct.pack_into("<I",bad,index*4,value); self.after = bytes(bad)
                self.assertFalse(self.result()["device_status_and_log_relation_matches"])
                self.after = original
        bad = bytearray(self.before); struct.pack_into("<I",bad,5*4,387); self.before = bytes(bad)
        self.assertFalse(self.result()["fresh_status_matches"])

    def test_iso7_invalid_sentinels_context_and_tags(self):
        for offset, value in ((12,0x80000000),(16,0xf),(20,768),(24,3),(44,0),
                              (40,0x170000c0),(32,0),(72,16384),(76,0),(80,0x40001),(84,0x1000026),(96,0xc00)):
            with self.subTest(offset=offset):
                original = self.after
                bad = bytearray(original); struct.pack_into("<I",bad,56+offset,value); self.after = bytes(bad)
                self.assertFalse(self.result()["device_status_and_log_relation_matches"])
                self.after = original

    def test_invalid_event_does_not_decode_stale_cc(self):
        bad = bytearray(self.after); struct.pack_into("<I",bad,56+44,0); self.after = bytes(bad)
        event = self.result()["diagnostics"]["events"][0]
        self.assertFalse(event["record_valid"])
        self.assertIsNone(event["completion_code"])

    def test_target_revision_build_runtime_and_log_completeness(self):
        for old, new in (("A23 HS ISO7","A22 HS ISO6"),(BUILD_ID,"0"*64),
                         ("result=0 record=21","result=1 record=21"),("22.5.0","22.6.0")):
            with self.subTest(change=old):
                with self.assertRaises(ValueError):
                    audit(self.before,self.after,self.log.replace(old.encode(),new.encode()))
        with self.assertRaisesRegex(ValueError,"truncated"):
            audit(self.before,self.after,self.log[:-1])
        with self.assertRaisesRegex(ValueError,"startup"):
            audit(self.before,self.after,self.log.split(b"\n",1)[1])
        with self.assertRaisesRegex(ValueError,"duplicate"):
            audit(self.before,self.after,self.log+STARTUP.encode())

    def test_duplicate_or_wrong_submission_and_completion_fail(self):
        for extra in (BURST.splitlines()[0],BURST.splitlines()[2]):
            self.assertFalse(audit(self.before,self.after,self.log+extra.encode()+b"\n")["device_status_and_log_relation_matches"])
        for old, new in (("seq=1 speed=3","seq=2 speed=3"),("URB=387","URB=388"),
                         ("status=3 diag","status=4 diag"),("ack-after=14","ack-after=9")):
            self.assertFalse(audit(self.before,self.after,self.log.replace(old.encode(),new.encode()))["device_status_and_log_relation_matches"])

    def test_malformed_critical_line_is_not_silently_skipped(self):
        with self.assertRaisesRegex(ValueError,"malformed"):
            audit(self.before,self.after,self.log.replace(b"ISO submit seq=1",b"ISO submit seq=x"))

    def test_cancel_rejected(self):
        cancel = b"EP0[0]: reqType=0x41 req=0x52 wVal=0x0000 wIdx=0x0002 wLen=0\n"
        self.assertFalse(audit(self.before,self.after,self.log+cancel)["device_status_and_log_relation_matches"])

    def test_no_td_preserves_header_allows_live_diag(self):
        after = bytearray(self.before); after[56:] = bytes([0xd1])+bytes(111)
        result = audit(self.before,bytes(after),STARTUP.encode(),"no_td")
        self.assertTrue(result["device_status_and_log_relation_matches"])
        self.assertIsNone(result["diagnostics"])
        self.assertFalse(audit(self.before,self.before,self.log,"no_td")["device_status_and_log_relation_matches"])
        trigger = b"EP0[1]: reqType=0x41 req=0x54 wVal=0x0001 wIdx=0x0002 wLen=0\n"
        self.assertFalse(audit(self.before,self.before,STARTUP.encode()+trigger,"no_td")["device_status_and_log_relation_matches"])

    def test_historical_log_and_reconstructed_status_only(self):
        # Reconstruct ABI bytes from old JSON fields; these are not original
        # binary captures and cannot be associated with the new backend.
        import json
        base = Path(__file__).resolve().parents[1]/"private"
        run = base/"runs/A-A23-HS-burst-window-20261009-203446/host.jsonl"
        log = base/"collections/A23-burst-window-20261009-204302/switch-logfile.txt"
        if not run.exists() or not log.exists():
            self.skipTest("local historical inputs unavailable")
        statuses = [json.loads(line) for line in run.read_text().splitlines()
                    if line.startswith('{"kind":"device_status"')]
        from audit_io_usb_host_device import STATUS_FIELDS
        def encode(row):
            fields = dict(row,magic=0x31505349,version=1,transferred=row["raw_count"])
            return struct.pack("<14I",*(fields[k] for k in STATUS_FIELDS))+bytes.fromhex(row["diagnostics_hex"])
        result = audit(encode(statuses[0]),encode(statuses[-1]),log.read_bytes())
        self.assertTrue(result["device_status_and_log_relation_matches"])
        self.assertFalse(result["capture_binding_verified"])
        self.assertEqual(result["log_sha256"],"53eda5f61219329820a790611fef2c00daa1d929e4b82f87cf7069ad98e31f9e")


if __name__ == "__main__":
    unittest.main()
