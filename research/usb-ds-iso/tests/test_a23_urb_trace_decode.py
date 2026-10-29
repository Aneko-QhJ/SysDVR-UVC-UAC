import json
import unittest

from decode_a23_trace import decode


class TraceDecodeTest(unittest.TestCase):
    def test_fields(self):
        data = bytearray(112)
        data[8:16] = (0x1234567890).to_bytes(8, "little")
        data[16:20] = (7).to_bytes(4, "little")
        data[20:24] = (5).to_bytes(4, "little")
        data[24:28] = (2).to_bytes(4, "little")
        result = decode(bytes(data))
        self.assertEqual(result["endpoint"], 0x1234567890)
        self.assertEqual(result["producer"], 7)
        self.assertEqual(result["consumer"], 5)
        self.assertEqual(result["count"], 2)

    def test_json_hex(self):
        data = bytearray(112)
        data[16:20] = (3).to_bytes(4, "little")
        line = json.dumps({"diagnostics_hex": data.hex()})
        obj = json.loads(line)
        self.assertEqual(decode(obj["diagnostics_hex"])["producer"], 3)

    def test_short_buffer(self):
        with self.assertRaises(ValueError):
            decode(bytes(20))
