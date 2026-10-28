"""Unicorn replay: one shared mailbox cannot complete three in-flight URBs."""
import unittest

try:
    from test_patch import Machine, ENTRY, RING, MANAGER, PACKAGES
except Exception as exc:  # pragma: no cover - environment dependent
    raise unittest.SkipTest(f"A23 Unicorn harness unavailable: {exc}")


class MailboxMultiplexTests(unittest.TestCase):
    def tags(self, slot):
        return [RING + ((slot + i * 2 + 1) % 247) * 16 for i in range(16)]

    def test_three_inflight_only_latest_urb_completes(self):
        if not (PACKAGES / "A" / "manifest.json").is_file():
            self.skipTest(f"no A23 package under {PACKAGES}")

        m = Machine("A")
        for slot in (0, 32, 64):
            # The real request context is idle per submission; model that gate
            # so the A23 producer accepts the three in-flight URBs.
            m.write(ENTRY + 0x20, "<Q", m.read(ENTRY + 0x18, "<Q")[0])
            self.assertEqual(m.submit(3072), 0)

        # The mailbox was reset by the third submit.  Injecting the earlier
        # URBs' sixteen ED events finds no matching first pointer.
        for slot in (0, 32):
            calls = []
            for tag in self.tags(slot):
                calls.extend(m.event(tag, True))
            self.assertEqual(calls, [], f"slot {slot} must not complete")

        # Only the latest URB's events match and call the original completion.
        calls = []
        for tag in self.tags(64):
            calls.extend(m.event(tag, True))
        self.assertEqual(calls, [(0x2a980, [MANAGER, 0x83, 0, 1, 3072, 1])])
        self.assertEqual(m.read(RING + 0xf90, "<II"), (0xffff, 3072))


if __name__ == "__main__":
    unittest.main()
