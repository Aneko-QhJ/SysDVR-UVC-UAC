"""Bound conversion-reset/dispatch/fetch replay; literal scanning is not executed."""
import re
import analyze_a23_argument_cache as arg
import analyze_a23_formatter as fmt


class BridgeError(arg.ArgumentError):
    pass


PATHS = dict(arg.PATHS, x32=(0x286c, 0x295c, 'x1'), x64=(0x2598, 0x295c, 'x1'))


class ConversionMachine(arg.FetchMachine):
    """Start at the actual percent-conversion entry, retain its state into fetch.

    The caller supplies the percent pointer, sequential index, cache and ABI.
    We do not execute the preceding locale scanner or subsequent rendering.
    """
    def __init__(self, functions, blob, metadata, spec, index=0, abi='register',
                 poison=0xdeadbeef, value=0xfedcba9876543210, cached=None, dispatch=None):
        super().__init__(functions, 'u32', index=index, abi=abi, value=value, cached=cached)
        if not spec.startswith('%') or '\0' in spec:
            raise BridgeError('Conversion input must start with percent')
        self.start = next(f['start'] for f in functions.values() if f['name'] == '_svfprintf_r')
        self.pc = self.start + 0x1e4
        if dispatch is None:
            raise BridgeError('A byte-bound dispatch certificate is required')
        self.dispatch = dispatch
        self.format_base = 0x500000
        self.spec = spec
        self.slot_events = []
        self.parser_reads = []
        self.slot_tracking = False
        self.blob, self.metadata = blob, metadata
        self.reg = {}
        for r, v in [('sp', self.sp), ('x24', self.va), ('x12', self.format_base),
                     ('x25', self.sp + 624), ('x21', self.format_base), ('w27', index), ('x22', 0x600000)]:
            self.put(r, v)
        self.store(self.sp + 136, poison, 8)
        for i, byte in enumerate(spec.encode('ascii') + b'\0'):
            self.store(self.format_base + i, byte, 1)
        self.writes = []
        self.slot_tracking = True

    def get(self, register):
        key = 'x' + register[1:] if register.startswith('w') else register
        if register not in ('xzr', 'wzr') and key not in self.reg:
            raise BridgeError('Undefined bridge register ' + register)
        return super().get(register)

    def store(self, address, value, n):
        if getattr(self, 'slot_tracking', False) and address < self.sp + 140 and address + n > self.sp + 136:
            self.slot_events.append(dict(at=self.pc - 4, kind='write', bytes=n, value=value & ((1 << (n * 8)) - 1)))
        super().store(address, value, n)

    def load(self, address, n, signed=False):
        if getattr(self, 'slot_tracking', False) and address < self.sp + 140 and address + n > self.sp + 136:
            self.slot_events.append(dict(at=self.pc - 4, kind='read', bytes=n))
        return super().load(address, n, signed)

    def parser_memory(self, op, operands):
        match = re.fullmatch(r'(\w+), \[(\w+)(?:, (.*?))?\](?:, #(\d+))?', operands)
        if not match:
            raise BridgeError('Unsupported parser memory operand ' + operands)
        register, base, offset, post = match.groups()
        delta = 0
        if offset:
            parts = offset.split(', ')
            delta = self.value_of(parts[0])
            if len(parts) == 2:
                if parts[1] != 'uxtw #1':
                    raise BridgeError('Unsupported parser address extension')
                delta = (delta & 0xffffffff) << 1
        address = self.get(base) + delta
        n = 1 if op in ('ldrb', 'strb') else 2 if op == 'ldrh' else 4 if register.startswith('w') else 8
        if op.startswith('st'):
            if not (self.sp + 128 <= address and address + n <= self.sp + 184
                    or address == self.sp + 208 and n == 8
                    or address == self.sp + 303 and n == 1):
                raise BridgeError('Parser write outside approved local slots')
            self.store(address, self.get(register), n)
        else:
            table = self.dispatch['table_address']
            if table <= address and address + n <= table + self.dispatch['table_bytes']:
                value = int.from_bytes(fmt.data_at(self.blob, self.metadata, address, n, readonly=True), 'little')
            else:
                value = self.load(address, n)
            if self.format_base <= address < self.format_base + len(self.spec) + 1:
                self.parser_reads.append(dict(at=self.pc - 4, offset=address - self.format_base, value=value))
            self.put(register, value)
        if post:
            self.put(base, self.get(base) + int(post))

    def step_parser(self):
        op, operands = self.code[self.pc]
        self.visited.append(self.pc)
        self.pc += 4
        a = [p.strip() for p in operands.split(',')]
        if op in ('ldr', 'ldrb', 'ldrh', 'str', 'strb'):
            self.parser_memory(op, operands)
        elif op in ('adr', 'adrp'):
            self.put(a[0], fmt.target(operands))
        elif op in ('mov', 'add', 'sub', 'orr', 'madd'):
            value = self.value_of(a[1])
            if op == 'madd':
                value = value * self.value_of(a[2]) + self.value_of(a[3])
            elif op not in ('mov',):
                other = self.value_of(a[2])
                if len(a) == 4:
                    if a[3] != 'sxth #2':
                        raise BridgeError('Unsupported parser arithmetic extension')
                    other &= 0xffff
                    other = (other - 65536 if other & 0x8000 else other) << 2
                value = value + other if op == 'add' else value - other if op == 'sub' else value | other
            self.put(a[0], value)
        elif op == 'cmp':
            self.comparison(self.get(a[0]), self.value_of(a[1]), 32 if a[0].startswith('w') else 64)
        elif op == 'b':
            self.pc = fmt.target(operands)
        elif op.startswith('b.'):
            if self.condition(op[2:]):
                self.pc = fmt.target(operands)
        elif op in ('cbz', 'cbnz'):
            if (self.get(a[0]) == 0) == (op == 'cbz'):
                self.pc = fmt.target(operands)
        elif op in ('tbz', 'tbnz'):
            if bool(self.get(a[0]) & (1 << int(a[1][1:], 0))) == (op == 'tbnz'):
                self.pc = fmt.target(operands)
        elif op == 'br':
            destination = self.get(a[0])
            if self.pc - 4 != self.dispatch['at'] or destination not in self.dispatch['targets']:
                raise BridgeError('Uncertified parser indirect branch')
            self.pc = destination
        else:
            raise BridgeError('Parser frontier: ' + op + ' ' + operands)

    def bridge(self, budget=512):
        entries = {self.start + off: name for name, (off, _, _) in PATHS.items()}
        while self.pc not in entries:
            if self.pc == self.start + 0x3a48:
                return dict(outcome='rejected-index', visited=self.visited, get_arg_executed=False)
            if len(self.visited) >= budget or self.pc not in self.code:
                raise BridgeError('Parser escaped instruction budget or function')
            self.step_parser()
        self.path = entries[self.pc]
        self.stop = self.start + PATHS[self.path][1]
        parser_visited = self.visited
        state = dict(path=self.path, position=self.get('w3'), index=self.get('w27'),
                     positional_index=self.get('w28'), cached=self.load(self.sp + 308, 4),
                     flags=self.get('w20'), width=self.load(self.sp + 128, 4),
                     next_format_offset=self.load(self.sp + 152, 8) - self.format_base,
                     va_pointer=self.get('x24'))
        self.visited = []
        # Same registers/memory; no reinjection at the fetch entry.
        fetch = super().run(budget=128)
        return dict(outcome='fetch', spec=self.spec, parser_state=state,
                    parser_visited=parser_visited, parser_input_reads=self.parser_reads,
                    position_slot_events=self.slot_events, fetch=fetch,
                    fetch_state_reinjected=False, percent_entry_injected=True,
                    sequential_index_and_cache_injected=True,
                    literal_locale_scan_executed=False, conversion_rendering_executed=False,
                    full_parser_executed=False, get_arg_globally_unreachable_proven=False)
