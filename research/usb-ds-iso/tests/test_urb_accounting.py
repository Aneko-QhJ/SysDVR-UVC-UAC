"""Model the endpoint URB table and the five-page IOVA domain.

The A23 producer maps a 4 KiB IOVA page per posted URB.  With five pages,
a serial one-in-flight stream still stops after five URBs, and the sixth
mapping asserts.  This model is deliberately small: it isolates whether
the observed five requires a missing unmap, a wrong URB entry, or only a
table-count problem.

Run directly or through the test suite.
"""

import unittest

PAGE = 0x1000
FIVE_PAGES = 5
TABLE_SIZE = 8


class Domain:
    def __init__(self, pages=FIVE_PAGES):
        self.free = [(i * PAGE, PAGE) for i in range(pages)]
        self.allocations = []
        self.free_failures = 0

    def alloc(self, size=PAGE):
        for i, (addr, length) in enumerate(self.free):
            if length >= size:
                self.free.pop(i)
                if length > size:
                    self.free.append((addr + size, length - size))
                self.allocations.append(addr)
                return addr
        return None

    def free_page(self, addr):
        if addr is None or addr not in self.allocations:
            self.free_failures += 1
            return False
        self.allocations.remove(addr)
        self.free.append((addr, PAGE))
        self.free.sort()
        return True


class Endpoint:
    """The +0/+4/+8 table of FUN_0002c520 and FUN_0002c690."""

    def __init__(self, domain, table=TABLE_SIZE):
        self.domain = domain
        self.table = table
        self.producer = 0
        self.consumer = 0
        self.count = 0
        self.entries = [None] * table
        self.posts = 0
        self.completes = 0
        self.busy = 0
        self.map_failures = 0
        self.leaks = 0

    def submit(self, size=3072, map_first=True):
        """FUN_0002c520 maps before checking the eight-entry table."""
        iova = self.domain.alloc(PAGE) if map_first else None
        if map_first and iova is None:
            self.map_failures += 1
            return False
        if self.count == self.table:
            self.busy += 1
            if map_first:
                # The busy branch returns 0x19c8c without unmapping.
                self.leaks += 1
            return False
        if not map_first:
            iova = self.domain.alloc(PAGE)
            if iova is None:
                self.map_failures += 1
                return False
        self.entries[self.producer] = {"iova": iova, "size": size}
        self.producer = (self.producer + 1) % self.table
        self.count += 1
        self.posts += 1
        return True

    def complete(self, unmap=True, free_address=None):
        """FUN_0002c690 picks the consumer entry, unmaps, then advances."""
        if self.count == 0:
            return False
        entry = self.entries[self.consumer]
        if entry is None:
            return False
        if unmap:
            addr = entry["iova"] if free_address is None else free_address
            if not self.domain.free_page(addr):
                # The unmap is skipped or targets the wrong address; the
                # table still advances and the page stays allocated.
                pass
        self.entries[self.consumer] = None
        self.consumer = (self.consumer + 1) % self.table
        self.count -= 1
        self.completes += 1
        return True


def serial(rounds, unmap=True, free_address=None, map_first=True, pages=FIVE_PAGES):
    domain = Domain(pages)
    endpoint = Endpoint(domain)
    for _ in range(rounds):
        if not endpoint.submit(map_first=map_first):
            break
        endpoint.complete(unmap=unmap, free_address=free_address)
    return domain, endpoint


def test_regular_unmap_reuses_the_pages():
    domain, endpoint = serial(6)
    assert endpoint.posts == 6 and endpoint.completes == 6
    assert endpoint.map_failures == 0
    assert endpoint.busy == 0
    assert len(domain.free) == FIVE_PAGES


def test_missing_unmap_stops_at_five():
    domain, endpoint = serial(6, unmap=False)
    # The host reports five completions; the sixth submit cannot map.
    assert endpoint.posts == 5 and endpoint.completes == 5
    assert endpoint.map_failures == 1
    assert endpoint.busy == 0
    assert len(domain.allocations) == 5


def test_wrong_unmap_address_stops_at_five():
    domain, endpoint = serial(6, free_address=0xDEAD0000)
    assert endpoint.posts == 5 and endpoint.completes == 5
    assert endpoint.map_failures == 1
    assert domain.free_failures == 5
    assert len(domain.allocations) == 5


def test_eight_entry_table_cannot_explain_five():
    domain, endpoint = serial(6, unmap=False, pages=8)
    # Eight pages let six URBs through even with no unmap.
    assert endpoint.posts == 6 and endpoint.map_failures == 0
    assert endpoint.completes == 6


def test_busy_map_leak_after_table_full():
    # Nine pages let the ninth submit map before it sees the full table.
    domain = Domain(pages=9)
    endpoint = Endpoint(domain)
    for _ in range(TABLE_SIZE):
        assert endpoint.submit()
    assert endpoint.count == TABLE_SIZE
    assert not endpoint.submit()
    assert endpoint.busy == 1 and endpoint.leaks == 1
    # The mapped page is not in any entry and never freed.
    assert len(domain.allocations) == TABLE_SIZE + 1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("urb accounting model ok")


class UrbAccountingTest(unittest.TestCase):
    def test_regular_unmap(self):
        test_regular_unmap_reuses_the_pages()

    def test_missing_unmap(self):
        test_missing_unmap_stops_at_five()

    def test_wrong_unmap_address(self):
        test_wrong_unmap_address_stops_at_five()

    def test_table_cannot_explain_five(self):
        test_eight_entry_table_cannot_explain_five()

    def test_busy_map_leak(self):
        test_busy_map_leak_after_table_full()
