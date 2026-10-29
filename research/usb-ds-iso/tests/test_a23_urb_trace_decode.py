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

    def test_v4_last_entry_present(self):
        data = bytearray(112)
        data[0:4] = (0x384F5349).to_bytes(4, "little")
        data[8:12] = (5).to_bytes(4, "little")
        data[12:16] = (0x12345000).to_bytes(4, "little")
        data[16:20] = (3072).to_bytes(4, "little")
        result = decode(bytes(data))
        self.assertEqual(result["layout"], "urb-v4")
        self.assertEqual(result["consumer"], 5)
        self.assertEqual(result["last_index"], 4)
        self.assertEqual(result["last_iova"], 0x12345000)
        self.assertEqual(result["last_size"], 3072)
        self.assertEqual(result["unmap_gate"], "last_entry_present")

    def test_v4_zero_size_is_the_unmap_skip(self):
        data = bytearray(112)
        data[0:4] = (0x384F5349).to_bytes(4, "little")
        data[8:12] = (6).to_bytes(4, "little")
        data[12:16] = (0x12345000).to_bytes(4, "little")
        data[16:20] = (0).to_bytes(4, "little")
        result = decode(bytes(data))
        self.assertEqual(result["last_index"], 5)
        self.assertEqual(result["unmap_gate"], "size_zero")

    def test_v5_all_entries(self):
        data = bytearray(112)
        data[0:4] = (0x394F5349).to_bytes(4, "little")
        for index in range(5):
            off = 8 + index * 8
            data[off:off + 4] = (0x80030000 + index * 0x10000).to_bytes(4, "little")
            data[off + 4:off + 8] = (3072).to_bytes(4, "little")
        result = decode(bytes(data))
        self.assertEqual(result["layout"], "urb-v5")
        self.assertEqual(result["nonzero_sizes"], 5)
        self.assertEqual(result["distinct_iovas"], 5)
        self.assertEqual(result["last_nonzero"], 4)
        self.assertEqual(result["zero_iova_indices"], [])
        self.assertEqual(result["entries"][0]["iova"], 0x80030000)
        self.assertEqual(result["entries"][4]["size"], 3072)
        self.assertEqual(result["entries"][5]["size"], 0)

    def test_v5_zero_iova_is_visible(self):
        data = bytearray(112)
        data[0:4] = (0x394F5349).to_bytes(4, "little")
        data[8:12] = (0).to_bytes(4, "little")
        data[12:16] = (3072).to_bytes(4, "little")
        result = decode(bytes(data))
        self.assertEqual(result["zero_iova_indices"], [0])
        self.assertEqual(result["nonzero_sizes"], 1)

    def test_unknown_magic(self):
        data = bytearray(112)
        data[0:4] = (0xDEADBEEF).to_bytes(4, "little")
        with self.assertRaises(ValueError):
            decode(bytes(data))

    def test_short_buffer(self):
        with self.assertRaises(ValueError):
            decode(bytes(20))
