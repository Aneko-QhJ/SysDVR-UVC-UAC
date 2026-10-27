"""Continuous formatter plus actual SDK memory-helper instructions in an offline model."""
import analyze_a23_sdk_memory as sdk


class IntegratedError(sdk.MemoryError):
    pass


class IntegratedMachine(sdk.MemoryMachine):
    HELPERS = ('memcpy', 'memset', 'strlen')

    def __init__(self, functions, blob, metadata, address, values, capacity=512, abi='register',
                 string_offset=0, mapped_string_pages=True, **kwargs):
        if not 0 <= string_offset < 4096:
            raise IntegratedError('String page offset outside range')
        self.simd = {}
        self.record_memory = False
        self.active_helper = None
        self.helper_calls = []
        self.string_objects = []
        sdk.fmt.FormatMachine.__init__(self, functions, blob, metadata, address, values,
                                       capacity=capacity, abi=abi, **kwargs)
        for index, value in enumerate(values):
            if isinstance(value, str):
                value = value.encode('ascii')
            if not isinstance(value, bytes):
                continue
            old = self.argument_words[index]
            for i in range(len(value)+1):
                self.mem.pop(old+i, None)
            pointer = 0x710000 + index*0x4000 + string_offset
            first, last = pointer & ~4095, (pointer+len(value)+4096) & ~4095
            if mapped_string_pages:
                self.mem.update((i, 0xa5) for i in range(first, last))
            self.mem.update((pointer+i, v) for i, v in enumerate(value+b'\0'))
            self.argument_words[index] = pointer
            source = self.top-56+8*index if abi == 'register' and index < 7 else self.stack_arg+8*(index-7 if abi == 'register' else index)
            self.store(source, pointer, 8)
            self.string_objects.append(dict(pointer=pointer, length=len(value), mapped_start=first,
                                            mapped_end=last, mapped_padding_injected=mapped_string_pages))
        self.writes = []
        self.slot_events = []
        self.minimum_sp = self.entry_sp

    def modeled_call(self, name):
        raise IntegratedError('Abstract helper call forbidden: '+name)

    def load(self, address, n, signed=False):
        if self.active_helper is not None:
            row = self.active_helper
            if row['name'] == 'memcpy' and not row['source'] <= address <= address+n <= row['source']+row['length']:
                raise IntegratedError('SDK memcpy read outside requested source')
            row['reads'].append(dict(at=self.pc-4, address=address, bytes=n))
        return sdk.fmt.FormatMachine.load(self, address, n, signed)

    def checked_store(self, address, value, n):
        if self.active_helper is not None:
            row = self.active_helper
            if row['name'] == 'strlen' or not row['destination'] <= address <= address+n <= row['destination']+row['length']:
                raise IntegratedError('SDK helper write outside requested destination')
            row['writes'].append(dict(at=self.pc-4, address=address, bytes=n))
        sdk.fmt.FormatMachine.checked_store(self, address, value, n)

    def begin_helper(self, name, destination, pc, tail=False):
        if self.active_helper is not None:
            raise IntegratedError('Nested SDK memory helper')
        row = dict(name=name, at=pc, target=destination, return_pc=self.get('x30') if tail else pc+4,
                   kind='tail' if tail else 'call', reads=[], writes=[], stack=self.get('sp'),
                   callee_saved={r: self.get(r) for r in ['x'+str(i) for i in range(19, 30)]},
                   saved_simd={str(i): value & ((1 << 64)-1) for i, value in self.simd.items() if 8 <= i <= 15},
                   instruction_start=len(self.visited)+1)
        pointer = self.get('x0')
        if name == 'strlen':
            objects = [s for s in self.string_objects if s['pointer'] <= pointer <= s['pointer']+s['length']]
            if not objects:
                sections = [s for s in self.metadata['sections'] if s['flags'] & 2 and not s['flags'] & 1
                            and s['type'] != 8 and s['address'] <= pointer < s['address']+s['size']]
                if len(sections) == 1:
                    section = sections[0]
                    offset = section['offset']+pointer-section['address']
                    raw = self.blob[offset:section['offset']+section['size']]
                    length = raw.find(b'\0', 0, 2048)
                    if length >= 0:
                        obj = dict(pointer=pointer, length=length, mapped_start=section['address'],
                                   mapped_end=section['address']+section['size'], mapped_padding_injected=False,
                                   readonly_elf_object=True)
                        self.string_objects.append(obj)
                        objects = [obj]
            if len(objects) != 1:
                raise IntegratedError('strlen input has no declared string object')
            row.update(source=pointer, length=objects[0]['pointer']+objects[0]['length']-pointer,
                       mapped_start=objects[0]['mapped_start'], mapped_end=objects[0]['mapped_end'])
            row['expected_return'] = row['length']
        else:
            length = self.get('x2')
            if length > 1024:
                raise IntegratedError('SDK helper request exceeds current profile bound')
            row.update(destination=pointer, length=length, expected_return=pointer)
            if name == 'memcpy':
                row['source'] = self.get('x1')
                row['expected_bytes'] = [self.load(row['source']+i, 1) for i in range(length)]
            else:
                row['fill_byte'] = self.get('w1') & 255
                row['expected_bytes'] = [row['fill_byte']]*length
        self.calls.append(dict(at=pc, target=destination, name=name, held_bytes=self.entry_sp-self.get('sp'),
                               actual_instructions_in_model=True, modeled=False, kind=row['kind']))
        self.visited.append(pc)
        if not tail:
            self.put('x30', pc+4)
        self.pc = destination
        self.active_helper = row

    def finish_helper(self):
        row = self.active_helper
        self.active_helper = None
        assert self.get('sp') == row['stack'] and self.get('x0') == row.pop('expected_return')
        assert all(self.get(r) == value for r, value in row.pop('callee_saved').items())
        assert all(self.simd[int(i)] & ((1 << 64)-1) == value for i, value in row.pop('saved_simd').items())
        if row['name'] == 'strlen':
            assert all(row['mapped_start'] <= r['address'] and r['address']+r['bytes'] <= row['mapped_end'] for r in row['reads'])
            row['read_before_string'] = max([row['source']-r['address'] for r in row['reads']]+[0])
            row['read_after_nul'] = max([r['address']+r['bytes']-(row['source']+row['length']+1) for r in row['reads']]+[0])
        else:
            assert [self.load(row['destination']+i, 1) for i in range(row['length'])] == row.pop('expected_bytes')
        row['instruction_count'] = len(self.visited)-row.pop('instruction_start')
        row['stack_restored'] = True
        self.helper_calls.append(row)

    def step(self):
        op, operands = self.code[self.pc]
        if op in ('bl', 'b'):
            destination = sdk.fmt.scan.parser.fmt.target(operands)
            name = next((n for n in self.HELPERS if self.functions[n]['start'] == destination), None)
            if name is not None and self.names[self.pc] != name:
                self.begin_helper(name, destination, self.pc, tail=op == 'b')
                return
        super().step()
        if self.active_helper is not None and self.pc == self.active_helper['return_pc']:
            self.finish_helper()

    def run_full(self, budget=100000):
        row = sdk.fmt.FormatMachine.run_full(self, budget)
        assert self.active_helper is None
        row.pop('actual_sdk_memory_helpers_executed')
        assert not row.pop('modeled_copies')
        assert not any(r.get('modeled') for r in row['calls'])
        row.update(actual_sdk_memory_helpers_executed_in_model=True, actual_sdk_helpers_executed_natively=False,
                   memory_helper_abstract_models_used=False, helper_state_reinjected=False,
                   helper_calls=self.helper_calls, string_objects=self.string_objects,
                   string_page_mapping_is_injected=True)
        return row
