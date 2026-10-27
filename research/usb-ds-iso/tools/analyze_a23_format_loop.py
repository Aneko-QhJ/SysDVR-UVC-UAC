"""Actual narrow/integer formatter instruction loop; no graph pruning or device."""
import analyze_a23_literal_scan as scan


class LoopError(scan.ScanError):
    pass


class FormatMachine(scan.FirstScanMachine):
    def __init__(self,functions,blob,metadata,address,values,capacity=512,abi='register',**kwargs):
        super().__init__(functions,blob,metadata,address,capacity=capacity,abi=abi,**kwargs)
        self.input_values=list(values)
        self.argument_words=[]
        for index,value in enumerate(values):
            if isinstance(value,str):
                value=value.encode('ascii')
            if isinstance(value,bytes):
                pointer=0x710000+index*0x1000
                for i,byte in enumerate(value+b'\0'):self.store(pointer+i,byte,1)
                word=pointer
            else:word=value
            self.argument_words.append(word & ((1<<64)-1))
            address=self.top-56+8*index if abi=='register' and index<7 else self.stack_arg+8*(index-7 if abi=='register' else index)
            self.store(address,word,8)
        self.store(self.buffer-1,0x5a,1)
        self.store(self.buffer+capacity,0x5a,1)
        self.writes=[]
        self.slot_events=[]
        self.fetches=[]
        self.scan_entries=[]
        self.resets=[]
        self.vector_flushes=[]

    def condition(self,name):
        if not self.flags:raise LoopError('Condition flags unknown')
        f=self.flags
        values=dict(eq=f['z'],ne=not f['z'],ge=f['n']==f['v'],lt=f['n']!=f['v'],
            gt=not f['z'] and f['n']==f['v'],le=f['z'] or f['n']!=f['v'],
            hi=f['c'] and not f['z'],ls=not f['c'] or f['z'],cs=f['c'],cc=not f['c'],
            hs=f['c'],lo=not f['c'],mi=f['n'],pl=not f['n'],vs=f['v'],vc=not f['v'])
        if name not in values:raise LoopError('Unknown condition '+name)
        return values[name]

    def logical_flags(self,value,bits):
        value &= (1<<bits)-1
        self.flags=dict(z=value==0,n=bool(value & (1<<(bits-1))),c=False,v=False)

    def extended_value(self,value,extension,bits):
        parts=extension.split();kind=parts[0];shift=int(parts[1][1:],0) if len(parts)>1 else 0
        if kind in ('sxtw','sxth'):
            width=32 if kind=='sxtw' else 16;value &= (1<<width)-1
            if value & (1<<(width-1)):value-=1<<width
            return value<<shift
        if kind=='lsl':return value<<shift
        if kind=='lsr':return (value & ((1<<bits)-1))>>shift
        raise LoopError('Unknown arithmetic extension '+extension)

    def modeled_call(self,name):
        super().modeled_call(name)
        # Flags are also caller-saved. Every later conditional path must derive
        # them from a real comparison rather than inheriting a model boundary.
        self.flags={}

    def step(self):
        op,operands=self.code[self.pc]
        if op=='bl' and operands.endswith('<get_arg>'):
            pc=self.pc;self.pc+=4
            self.calls.append(dict(at=pc,target=scan.parser.fmt.target(operands),name='get_arg',frontier_only=True))
            raise LoopError('Unexecuted get_arg frontier')
        a=[p.strip() for p in operands.split(',')]
        bits=32 if a[0].startswith('w') else 64
        custom=op in ('ands','ccmp','ccmn','cinc','csinc','csinv','cneg','neg','lsr','lsl','asr','udiv','msub','mul','sxtb','sxth','uxtb') or op in ('add','sub') and len(a)==4
        if op in ('sturb','ldurb','stur','ldur'):
            pc=self.pc;self.visited.append(pc);self.pc+=4
            self.memory_instruction({'sturb':'strb','ldurb':'ldrb','stur':'str','ldur':'ldr'}[op],operands)
        elif custom:
            pc=self.pc;self.visited.append(pc);self.pc+=4
            if op=='ands':
                value=self.value_of(a[1]) & self.value_of(a[2]);self.put(a[0],value);self.logical_flags(value,bits)
            elif op in ('ccmp','ccmn'):
                if self.condition(a[3].split()[0]):
                    left=self.get(a[0]);right=self.value_of(a[1])
                    if op=='ccmp':self.comparison(left,right,bits)
                    else:
                        mask=(1<<bits)-1;left&=mask;right&=mask;value=(left+right)&mask;sign=1<<(bits-1)
                        self.flags=dict(z=value==0,n=bool(value&sign),c=left+right>mask,v=bool(~(left^right)&(left^value)&sign))
                else:
                    flags=int(a[2][1:],0);self.flags=dict(n=bool(flags&8),z=bool(flags&4),c=bool(flags&2),v=bool(flags&1))
            elif op in ('cinc','cneg'):
                value=self.value_of(a[1]);yes=self.condition(a[2].split()[0])
                self.put(a[0],value+int(yes) if op=='cinc' else -value if yes else value)
            elif op in ('csinc','csinv'):
                value=self.value_of(a[1]) if self.condition(a[3].split()[0]) else self.value_of(a[2])+1 if op=='csinc' else ~self.value_of(a[2])
                self.put(a[0],value)
            elif op in ('neg','sxtb','sxth','uxtb'):
                value=self.value_of(a[1])
                if op=='neg':value=-value
                elif op=='uxtb':value &= 255
                else:
                    width=8 if op=='sxtb' else 16;value &= (1<<width)-1
                    if value & (1<<(width-1)):value-=1<<width
                self.put(a[0],value)
            elif op in ('lsr','lsl','asr'):
                value=self.value_of(a[1]);shift=self.value_of(a[2])
                if op=='asr' and value & (1<<(bits-1)):value-=1<<bits
                self.put(a[0],value<<shift if op=='lsl' else value>>shift)
            elif op in ('udiv','msub','mul'):
                left,right=self.value_of(a[1]),self.value_of(a[2])
                value=(left//right if right else 0) if op=='udiv' else self.value_of(a[3])-left*right if op=='msub' else left*right
                self.put(a[0],value)
            elif op in ('add','sub'):
                left=self.value_of(a[1]);right=self.extended_value(self.value_of(a[2]),a[3],bits)
                self.put(a[0],left+right if op=='add' else left-right)
            else:raise LoopError('Unsupported rendering opcode '+op)
        else:super().step()
        self.minimum_sp=min(self.minimum_sp,self.get('sp'))

    def run_full(self,budget=100000):
        entries={self.start+p[0]:name for name,p in scan.parser.PATHS.items()}
        terminal=0xfffffffffffffff0
        active=None
        while self.pc!=terminal:
            if len(self.visited)>=budget or self.pc not in self.code:raise LoopError('Formatter loop escaped budget or function')
            if active and self.pc==active['stop']:
                active.update(result=self.get(scan.parser.PATHS[active['path']][2]),
                    cached_after=self.load(self.sp+308,4),next_index=self.load(self.sp+144,4) if active['path']=='s' else self.get('w27'),
                    cache_writes=[w for w in self.writes[active.pop('write_start'):] if self.cache<=w['address']<self.cache+512])
                self.fetches.append(active);active=None;self.in_fetch=False
            if self.pc in entries:
                if active:raise LoopError('Nested argument fetch')
                path=entries[self.pc]
                active=dict(path=path,entry=self.pc,stop=self.start+scan.parser.PATHS[path][1],
                    index=self.get('w27'),position=self.get('w3'),cached_before=self.load(self.sp+308,4),
                    percent_offset=self.get('x12')-self.format_base,write_start=len(self.writes))
                self.in_fetch=True
            if self.pc==self.start+0x100:
                self.scan_entries.append(dict(at=self.pc,index=self.get('w27'),cached=self.load(self.sp+308,4),
                    format_offset=self.get('x21')-self.format_base))
            if self.pc==self.start+0x204:
                self.resets.append(dict(at=self.pc,index=self.get('w27'),slot_before=self.load(self.sp+136,4) if all(self.sp+136+i in self.mem for i in range(4)) else None))
            if self.pc==self.functions['__ssprint_r']['start']:
                vector=self.get('x2')
                self.vector_flushes.append(dict(at=self.pc,count=self.load(vector+8,4),total_bytes=self.load(vector+16,8)))
            self.step()
        if active:raise LoopError('Returned during argument fetch')
        if self.load(self.buffer-1,1)!=0x5a or self.load(self.buffer+self.capacity,1)!=0x5a:raise LoopError('Output sentinel overwritten')
        remaining=self.load(self.file+12,4)
        return dict(outcome='formatter-return',return_value=self.get('w0'),stack_restored=self.get('sp')==self.entry_sp,
            file_initialization=self.file_before_formatter,final_file_flags=self.load(self.file+16,2),remaining=remaining,
            stored_bytes=max(self.capacity-1,0)-remaining,output=[self.load(self.buffer+i,1) for i in range(self.capacity)],
            fetches=self.fetches,scan_entries=self.scan_entries,resets=self.resets,slot_events=self.slot_events,
            callbacks=self.callbacks,vector_flushes=self.vector_flushes,calls=self.calls,modeled_copies=self.copies,
            visited=self.visited,observed_stack_bytes=self.entry_sp-self.minimum_sp,
            final_cached=self.load(self.sp+308,4),original_gr_offs=self.load(self.va+24,4),
            copied_gr_offs=self.load(self.wrapper_sp+32+24,4),copied_stack_pointer=self.load(self.wrapper_sp+32,8),
            formatter_conversion_loop_executed_in_model=True,index_cache_percent_and_file_state_reinjected=False,
            architectural_tls_reent_va_values_and_strings_injected=True,actual_sdk_memory_helpers_executed=False,
            whole_thread_stack_verified=False,get_arg_globally_unreachable_proven=False,formatter_cfg_pruned=False)
