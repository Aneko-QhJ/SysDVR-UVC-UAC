"""Replay wrapper initialization, TLS/default locale and ASCII scan to first fetch."""
import re
import analyze_a23_parser_bridge as parser
import analyze_a23_linked_logs as linked


class ScanError(parser.BridgeError):
    pass


class FirstScanMachine(parser.ConversionMachine):
    ALLOWED = ('_vsnprintf_r', '_svfprintf_r', '_localeconv_r', '__localeconv_l',
               '__getreent', '__syscall_getreent', '__locale_mb_cur_max',
               '__utf8_mbtowc', '__ssprint_r', '__ssputs_r')

    def __init__(self, functions, blob, metadata, address, capacity=512, abi='register',
                 value=0xfedcba9876543210, tls_magic=0x21545624, thread_locale=0):
        self.functions = {f['name']: f for f in functions.values()}
        self.blob, self.metadata = blob, metadata
        self.code = {pc: (op, arg) for name in self.ALLOWED for pc, op, arg in self.functions[name]['instructions']}
        self.names = {pc: name for name in self.ALLOWED for pc, _, _ in self.functions[name]['instructions']}
        self.reg, self.mem, self.writes, self.visited, self.flags = {}, {}, [], [], {}
        self.slot_tracking = False
        self.slot_events, self.parser_reads, self.calls, self.copies, self.callbacks = [], [], [], [], []
        self.entry_sp = 0x900000
        self.wrapper_sp = self.entry_sp - 256
        self.sp = self.wrapper_sp - 1264
        self.cache = self.sp + 752
        self.va = 0x200000
        self.stack_arg, self.top, self.reent, self.tls = 0x300000, 0x400000, 0x600000, 0x610000
        self.buffer = 0x700000
        self.format_base = address
        self.spec = linked.literal_at(blob, metadata, address)
        self.start = self.functions['_svfprintf_r']['start']
        self.dispatch = parser.fmt.decode_dispatch(blob, metadata['text']) if 'dispatch' not in metadata else metadata['dispatch']
        self.locale = parser.fmt.default_locale(blob, metadata['text']) if 'locale' not in metadata else metadata['locale']
        self.index, self.cached, self.value, self.capacity = 0, 0, value, capacity
        self.source = self.top - 56 if abi == 'register' else self.stack_arg
        for i in range(31): self.put('x'+str(i), 0xa0000000 + i)
        self.put('d15', 0x123456789abcdef0)
        for r, v in [('sp', self.entry_sp), ('x0', self.reent), ('x1', self.buffer),
                     ('x2', capacity), ('x3', address), ('x4', self.va), ('x30', 0xfffffffffffffff0)]: self.put(r, v)
        self.store(self.va, self.stack_arg, 8)
        self.store(self.va+8, self.top, 8)
        self.store(self.va+16, 0, 8)
        self.store(self.va+24, -56 if abi=='register' else 0, 4)
        self.store(self.va+28, 0, 4)
        self.store(self.source, value, 8)
        self.store(self.reent, 0, 4)
        self.store(self.reent+64, thread_locale, 8)
        self.store(self.tls+480, tls_magic, 4)
        self.store(self.tls+496, self.reent, 8)
        for i in range(capacity): self.store(self.buffer+i, 0xa5, 1)
        self.pc = self.functions['_vsnprintf_r']['start']
        self.writes = []
        self.minimum_sp = self.entry_sp
        self.slot_tracking = True
        self.file_before_formatter = None
        self.in_fetch = False

    def get(self, r):
        if r in ('xzr', 'wzr'): return 0
        key = 'x'+r[1:] if r.startswith('w') else r
        if key not in self.reg: raise ScanError('Undefined scan register '+r)
        bits = 32 if r.startswith('w') else 128 if r.startswith('q') else 64
        return self.reg[key] & ((1 << bits)-1)

    def put(self, r, value):
        if r in ('xzr', 'wzr'): return
        key = 'x'+r[1:] if r.startswith('w') else r
        bits = 32 if r.startswith('w') else 128 if r.startswith('q') else 64
        self.reg[key] = value & ((1 << bits)-1)

    def load(self, address, n, signed=False):
        if all(address+i in self.mem for i in range(n)):
            return super().load(address, n, signed)
        sections = [s for s in self.metadata['sections'] if s['flags'] & 2 and s['type'] != 8
                    and s['address'] <= address and address+n <= s['address']+s['size']]
        if len(sections) != 1: raise ScanError('Uninitialized scan memory '+hex(address))
        section = sections[0]
        raw = self.blob[section['offset']+address-section['address']:section['offset']+address-section['address']+n]
        return int.from_bytes(raw, 'little', signed=signed)

    def checked_store(self, address, value, n):
        allowed = (self.get('sp') <= address and address+n <= self.entry_sp or
                   self.buffer <= address and address+n <= self.buffer+self.capacity)
        if not allowed: raise ScanError('Scan write outside active stack/output '+hex(address))
        if self.names.get(self.pc-4)=='__utf8_mbtowc' and self.callbacks:
            self.callbacks[-1].setdefault('writes',[]).append(dict(address=address,bytes=n))
        if self.in_fetch:
            allowed_fetch = (self.cache <= address and address+n <= self.cache+512 or
                             self.sp+308 <= address and address+n <= self.sp+312 or
                             self.sp+144 <= address and address+n <= self.sp+152 or
                             self.wrapper_sp+32 <= address and address+n <= self.wrapper_sp+64)
            if not allowed_fetch: raise ScanError('Fetch write outside cache/counters/copied va_list')
        self.store(address, value, n)

    def memory_instruction(self, op, operands):
        pair = op in ('stp', 'ldp')
        match = re.fullmatch(r'(.*?)\[(\w+)(?:, (.*?))?\](!)?(?:, #(-?\d+))?', operands)
        if not match: raise ScanError('Unsupported scan memory operand '+operands)
        prefix, base, offset, pre, post = match.groups()
        registers = [r.strip() for r in prefix.rstrip(', ').split(',')]
        if len(registers) != (2 if pair else 1): raise ScanError('Memory register count')
        delta = 0
        if offset:
            parts = offset.split(', ')
            delta = self.value_of(parts[0])
            if len(parts)==2:
                kind, shift = parts[1].split()
                if kind not in ('uxtw', 'sxtw'): raise ScanError('Unsupported address extension')
                delta &= 0xffffffff
                if kind=='sxtw' and delta & (1<<31): delta -= 1<<32
                delta <<= int(shift[1:], 0)
        address = self.get(base)+delta
        if pre: self.put(base, address)
        for r in registers:
            n = 16 if r.startswith('q') else 1 if op in ('ldrb', 'strb') else 2 if op in ('ldrh','ldrsh','strh') else 4 if r.startswith('w') or op=='ldrsw' else 8
            if op.startswith('st'): self.checked_store(address, self.get(r), n)
            else: self.put(r, self.load(address, n, signed=op in ('ldrsh','ldrsw')))
            address += n
        if post: self.put(base, self.get(base)+int(post))

    def modeled_call(self, name):
        x0 = self.get('x0')
        if name == 'strlen':
            length = 0
            while self.load(x0+length, 1):
                length += 1
                if length>2048: raise ScanError('Modeled strlen exceeded bound')
            result = length
        elif name == 'memset':
            value, length = self.get('w1') & 255, self.get('x2')
            if length>1024: raise ScanError('Modeled memset exceeded bound')
            for i in range(length): self.checked_store(x0+i, value, 1)
            result = x0
        elif name == 'memcpy':
            source, length = self.get('x1'), self.get('x2')
            if length>512: raise ScanError('Modeled memcpy exceeded bound')
            data = [self.load(source+i, 1) for i in range(length)]
            for i, v in enumerate(data): self.checked_store(x0+i, v, 1)
            self.copies.append(dict(destination=x0, source=source, bytes=length))
            result = x0
        else: raise ScanError('Unknown modeled call '+name)
        # Caller-saved values are unknown after model boundaries; do not silently
        # preserve scratch registers on which later instructions might rely.
        for i in range(19): self.reg.pop('x'+str(i), None)
        self.put('x0', result)

    def step(self):
        if self.pc==self.functions['__ssputs_r']['start']+0x88:
            raise ScanError('FILE growth frontier; allocation unexecuted')
        op, operands = self.code[self.pc]
        pc = self.pc
        self.visited.append(pc)
        self.pc += 4
        a = [p.strip() for p in operands.split(',')]
        if op in ('stp','ldp','ldr','ldrb','ldrh','ldrsh','ldrsw','str','strb','strh'):
            self.memory_instruction(op, operands)
        elif op in ('adr','adrp'): self.put(a[0], parser.fmt.target(operands))
        elif op=='mrs':
            if operands!='x0, tpidrro_el0': raise ScanError('Unknown architectural register')
            self.put('x0', self.tls)
        elif op=='movk':
            shift=int(a[2].split('#')[1],0);mask=0xffff<<shift
            self.put(a[0], (self.get(a[0]) & ~mask) | (self.value_of(a[1])<<shift))
        elif op=='movi':
            if operands!='d15, #0x0': raise ScanError('Unsupported vector initialization')
            self.put('d15', 0)
        elif op=='cmn':
            bits=32 if a[0].startswith('w') else 64
            mask=(1<<bits)-1;left=self.get(a[0]) & mask;right=self.value_of(a[1]) & mask
            value=(left+right) & mask;sign=1<<(bits-1)
            self.flags=dict(z=value==0,n=bool(value & sign),c=left+right>mask,
                            v=bool(~(left^right) & (left^value) & sign))
        elif op=='tst':
            bits=32 if a[0].startswith('w') else 64
            value=(self.get(a[0]) & self.value_of(a[1])) & ((1<<bits)-1)
            self.flags=dict(z=value==0,n=bool(value & (1<<(bits-1))),c=False,v=False)
        elif op in ('csel','cset'):
            condition=a[-1].split()[0]
            self.put(a[0], int(self.condition(condition)) if op=='cset' else self.get(a[1]) if self.condition(condition) else self.get(a[2]))
        elif op in ('bl','blr'):
            destination = self.get(a[0]) if op=='blr' else parser.fmt.target(operands)
            name = next((n for n,f in self.functions.items() if f['start']==destination), None)
            self.calls.append(dict(at=pc, target=destination, name=name, held_bytes=self.entry_sp-self.get('sp')))
            if op=='blr':
                if destination!=self.locale['initial_callback_target']: raise ScanError('Unknown locale callback frontier')
                self.callbacks.append(dict(at=pc, source=self.get('x2'), state=self.load(self.get('x4'),4),
                                           output_pointer=self.get('x1'),state_pointer=self.get('x4'),
                                           byte=self.load(self.get('x2'),1)))
            if name in ('strlen','memset','memcpy'):
                self.put('x30',self.pc)
                self.modeled_call(name)
                self.calls[-1]['modeled']=True
                self.calls[-1]['link_register_after_model']=self.get('x30')
            elif name in self.ALLOWED:
                if name=='_svfprintf_r':
                    self.file = self.get('x1')
                    self.file_before_formatter = dict(address=self.file, flags=self.load(self.file+16,2),
                        remaining=self.load(self.file+12,4), va_pointer=self.get('x3'), format_pointer=self.get('x2'))
                self.put('x30', self.pc)
                self.pc=destination
            else: raise ScanError('Unexecuted call frontier '+str(name))
        elif op=='ret': self.pc=self.get('x30')
        elif op=='b':
            destination=parser.fmt.target(operands)
            if self.names.get(destination)!=self.names[pc]:
                self.calls.append(dict(at=pc,target=destination,name=self.names.get(destination),kind='tail',
                                       held_bytes=self.entry_sp-self.get('sp')))
            self.pc=destination
        elif op in ('sxtw','sbfiz','and'):
            value=self.value_of(a[1])
            if op=='sxtw': value=(value & 0xffffffff)-(1<<32) if value & (1<<31) else value & 0xffffffff
            elif op=='sbfiz':
                bits=int(a[3][1:],0);value &= (1<<bits)-1
                if value & (1<<(bits-1)): value -= 1<<bits
                value <<= int(a[2][1:],0)
            else: value &= self.value_of(a[2])
            self.put(a[0],value)
        elif op in ('add','sub') and len(a)==4 and a[3]=='sxtw':
            other=self.value_of(a[2]) & 0xffffffff
            if other & (1<<31): other -= 1<<32
            self.put(a[0],self.value_of(a[1])+other if op=='add' else self.value_of(a[1])-other)
        else:
            # Reuse the conversion interpreter for arithmetic, comparisons and
            # certified dispatch; undo its bookkeeping before entering it.
            self.pc=pc;self.visited.pop();self.step_parser()
        self.minimum_sp=min(self.minimum_sp,self.get('sp'))

    def run_first(self, budget=30000):
        entries={self.start+p[0]:name for name,p in parser.PATHS.items()}
        terminal=0xfffffffffffffff0
        while self.pc not in entries and self.pc!=terminal:
            if len(self.visited)>=budget or self.pc not in self.code: raise ScanError('Scan escaped budget or allowed function')
            self.step()
        prefix=self.visited
        result=dict(file_initialization=self.file_before_formatter, callbacks=self.callbacks, modeled_copies=self.copies,
            prefix_visited=prefix, observed_prefix_stack_bytes=self.entry_sp-self.minimum_sp,
            cache_count_initialized=self.load(self.sp+308,4), percent_pointer_injected=False,
            index_cache_and_file_state_injected=False, architectural_tls_and_reent_injected=True,
            readonly_load_bias_zero_and_initial_global_locale_assumed=True,
            memset_strlen_memcpy_are_bounded_models=True, actual_sdk_memory_helpers_executed=False,
            conversion_rendering_executed=False, conversion_loop_executed=False,
            whole_thread_stack_verified=False, get_arg_globally_unreachable_proven=False)
        if self.pc==terminal:
            remaining=self.load(self.file+12,4)
            result.update(outcome='literal-only-return', return_value=self.get('w0'), stack_restored=self.get('sp')==self.entry_sp,
                          remaining=remaining, stored_bytes=max(self.capacity-1,0)-remaining,
                          output=[self.load(self.buffer+i,1) for i in range(self.capacity)], calls=self.calls)
            return result
        self.path=entries[self.pc];self.stop=self.start+parser.PATHS[self.path][1]
        state=dict(path=self.path,position=self.get('w3'),index=self.get('w27'),cached=self.load(self.sp+308,4),
                   va_pointer=self.get('x24'),percent_offset=self.get('x12')-self.format_base,
                   next_format_offset=self.load(self.sp+152,8)-self.format_base)
        self.visited=[]
        self.in_fetch=True
        before=len(self.writes)
        helper=False
        while self.pc!=self.stop:
            if len(self.visited)>=128 or self.pc not in self.code: raise ScanError('Fetch escaped budget')
            if self.code[self.pc][0]=='bl' and self.code[self.pc][1].endswith('<get_arg>'):
                helper=True
                break
            self.step()
        fetch=dict(path=self.path,get_arg_frontier=helper,get_arg_executed=False,
                   result=None if helper else self.get(parser.PATHS[self.path][2]),
                   final_cached=self.load(self.sp+308,4),next_index=self.load(self.sp+144,4) if self.path=='s' else self.get('w27'),
                   visited=self.visited,cache_writes=[w for w in self.writes[before:] if self.cache<=w['address']<self.cache+512],
                   stack_held_unchanged=self.get('sp')==self.sp)
        result.update(outcome='first-fetch',parser_state=state,fetch=fetch,calls=self.calls,fetch_state_reinjected=False)
        return result
