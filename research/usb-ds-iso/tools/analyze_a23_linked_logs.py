"""Literal reaching definitions and bounded string-FILE instruction replay."""
import hashlib,re
from collections import deque
import analyze_a23_elf_boundaries as elf
import analyze_a23_formatter as fmt

class LinkedLogError(ValueError):pass

def literal_at(blob,metadata,address):
    owners=[s for s in metadata['sections'] if s['flags']&2 and not s['flags']&1 and s['type']!=8 and s['address']<=address<s['address']+s['size']]
    if len(owners)!=1:raise LinkedLogError('Format outside readonly allocated file section')
    s=owners[0];n=min(2048,s['address']+s['size']-address);raw=fmt.data_at(blob,metadata,address,n,readonly=True)
    end=raw.find(b'\0')
    if end<0:raise LinkedLogError('Unterminated format literal')
    try:value=raw[:end].decode('ascii')
    except UnicodeDecodeError:raise LinkedLogError('Non-ASCII format')
    return value

def reg_number(reg):
    m=re.fullmatch('[xw](\\d+)',reg)
    if not m or int(m[1])>30:raise LinkedLogError('Unsupported register '+reg)
    return int(m[1])

def origins(f,register,resolved_branches=None):
    resolved_branches=resolved_branches or {}
    code={p:(op,arg) for p,op,arg in f['instructions']};incoming={f['start']:{-1}};work=deque([f['start']]);number=reg_number(register)
    while work:
        pc=work.popleft();op,arg=code[pc]
        writes=fmt.writes_register(op,arg,register) or op in ('bl','blr') and number<=18
        if op.startswith(('stxr','stlxr','stxp','stlxp')) and arg.split(',')[0].strip() in (register,'w'+register[1:]):writes=True
        out={pc} if writes else incoming[pc]
        if op=='b':successors=[fmt.target(arg)]
        elif op=='br':
            if pc not in resolved_branches:raise LinkedLogError('Unknown internal branch in logging caller')
            successors=resolved_branches[pc]
        elif op in ('ret','udf','brk','hlt'):successors=[]
        else:
            successors=[pc+4]
            if op.startswith('b.') or op in ('cbz','cbnz','tbz','tbnz'):successors.append(fmt.target(arg))
        for nxt in successors:
            if nxt not in code:continue
            merged=incoming.get(nxt,set())|out
            if merged!=incoming.get(nxt,set()):incoming[nxt]=merged;work.append(nxt)
    return incoming

class LiteralResolver:
    def __init__(self,f):self.f=f;self.code={p:(o,a) for p,o,a in f['instructions']};self.cache={};self.definition_cache={}
    def values(self,pc,register,ancestors=()):
        n=reg_number(register);r='x'+str(n)
        if r not in self.cache:self.cache[r]=origins(self.f,r)
        defs=self.cache[r].get(pc)
        if not defs:raise LinkedLogError('Logging site unreachable in supported CFG')
        values=set()
        for definition in defs:
            if definition<0:raise LinkedLogError('Unknown incoming format register')
            key=(definition,r)
            if key in ancestors:raise LinkedLogError('Cyclic format definition')
            op,arg=self.code[definition];parts=[x.strip() for x in arg.split(',')]
            if op in ('adrp','adr') and parts[0]==r:result={fmt.target(arg)}
            elif op=='add' and len(parts)==3 and parts[0]==r and parts[2].startswith('#'):
                offset=int(parts[2][1:],0);result={v+offset for v in self.values(definition,parts[1],(*ancestors,key))}
            elif op=='mov' and len(parts)==2 and parts[0]==r and re.fullmatch('x\\d+',parts[1]):result=self.values(definition,parts[1],(*ancestors,key))
            else:raise LinkedLogError('Unknown format definition '+hex(definition)+' '+op+' '+arg)
            values.update(result)
        return values

def linked_calls(blob,text,catalog):
    functions,metadata=elf.build_functions(blob,text);by_format={r['format']:r for r in catalog};sites=[];callers={}
    for f in functions.values():
        calls=[(pc,op,arg) for pc,op,arg in f['instructions'] if op in ('b','bl') and arg.endswith('<LogFunctionImpl>')]
        if not calls:continue
        resolver=LiteralResolver(f);callers[f['name']]=elf.function_digest(f)
        for pc,op,arg in calls:
            addresses=sorted(resolver.values(pc,'x0'));literals=[literal_at(blob,metadata,a) for a in addresses]
            if any(value not in by_format for value in literals):raise LinkedLogError('Linked format missing from source catalog')
            sites.append(dict(caller=f['name'],at=pc,kind=op,format_addresses=addresses,formats=literals,catalog_cases=[by_format[v]['case'] for v in literals],max_declared_output_bytes=max(by_format[v]['max_output_bytes'] for v in literals)))
    if not sites:raise LinkedLogError('No direct logger sites')
    covered={value for row in sites for value in row['formats']}
    return dict(schema='A23-linked-log-literals-1',elf_sha256=metadata['elf_sha256'],sites=sites,direct_sites=len(sites),caller_functions_sha256=callers,
        unique_linked_formats=len(covered),catalog_only_formats=[dict(case=r['case'],unit=r['unit'],format=r['format']) for r in catalog if r['format'] not in covered],
        max_declared_linked_output_bytes=max(r['max_declared_output_bytes'] for r in sites),all_direct_log_call_sites_bound=True,
        valid_readonly_mapping_assumed=True,callee_saved_register_abi_assumed=True,source_string_argument_contracts_assumed=True,
        indirect_log_invocations_excluded=False,hardware_verified=False)

def file_state(blob,text):
    functions,metadata=elf.build_functions(blob,text);named={f['name']:f for f in functions.values()}
    sn=named['_vsnprintf_r'];code={p:(o,a) for p,o,a in sn['instructions']};call=next(p for p,(o,a) in code.items() if o=='bl' and a.endswith('<_svfprintf_r>'))
    setters=[p for p,(o,a) in code.items() if (o,a)==('mov','w1, #0xffff0208')]
    if len(setters)!=1 or code[setters[0]+4]!=('str','w1, [sp, #88]') or code[call-16]!=('add','x1, sp, #0x48'):raise LinkedLogError('Initial string FILE changed')
    pf=named['_svfprintf_r'];body=pf['instructions'];writes=[]
    dispatch=fmt.decode_dispatch(blob,text);definitions=origins(pf,'x0',{dispatch['at']:dispatch['targets']})
    for i,(pc,op,arg) in enumerate(body):
        if op=='strh' and arg=='w0, [x18, #16]':
            definitions_at_store=sorted(definitions.get(pc,set()))
            if not definitions_at_store:raise LinkedLogError('FILE error store has no supported definition')
            updates=[];by={p:(o,a) for p,o,a in body}
            for at in definitions_at_store:
                if by[at]!=('orr','w0, w0, #0x40') or by[at-4]!=('ldrh','w0, [x18, #16]') or definitions.get(at)!={at-4}:raise LinkedLogError('FILE error update definition is not stable along CFG')
                updates.append(dict(flags_load=at-4,flags_or=at,error_mask=64))
            writes.append(dict(at=pc,updates=updates,reaching_definitions_verified=True))
    if len(writes)!=2:raise LinkedLogError('Formatter flags store count changed')
    initial=[p for p,o,a in body if o=='tbz' and a.startswith('w0, #7,')]
    if len(initial)!=1:raise LinkedLogError('Initial allocation guard changed')
    puts=named['__ssputs_r'];by={p:(o,a) for p,o,a in puts['instructions']};gate=[p for p,(o,a) in by.items() if (o,a)==('tst','w6, w1')]
    if len(gate)!=1:raise LinkedLogError('Growth mask changed')
    at=gate[0]
    if by[at-8]!=('mov','w1, #0x480') or by[at+4][0]!='b.eq':raise LinkedLogError('Growth branch changed')
    return dict(schema='A23-string-file-local-state-1',elf_sha256=metadata['elf_sha256'],functions_sha256={n:elf.function_digest(named[n]) for n in ('_vsnprintf_r','_svfprintf_r','__ssputs_r','__ssprint_r')},
        initial_flags=0x208,error_flags=0x248,file_flags_offset=16,initial_allocation_guard=initial[0],growth_gate=at,
        growth_mask=0x480,formatter_local_flag_stores=writes,local_error_or_preserves_growth_mask=True,
        file_flags_lifecycle_verified=False,all_pointer_aliases_resolved=False,all_formatter_callbacks_resolved=False,
        allocator_paths_pruned=False,whole_thread_stack_verified=False,hardware_verified=False)

class StringAppendMachine:
    """Replay exact non-growing __ssputs_r; stop at the growth frontier."""
    def __init__(self,blob,text,capacity=511,flags=0x208,functions=None):
        fs=functions if functions is not None else elf.build_functions(blob,text)[0];self.function=next(f for f in fs.values() if f['name']=='__ssputs_r')
        self.code={p:(o,a) for p,o,a in self.function['instructions']};self.function_sha256=elf.function_digest(self.function)
        self.registers={};self.memory={};self.sp=0x900000;self.file=0x100000;self.buffer=0x200000;self.source=0x300000;self.capacity=capacity;self.flags=flags;self.copies=[];self.growth_frontier=None
        self.put(self.file,self.buffer,8);self.put(self.file+12,capacity,4);self.put(self.file+16,flags,2)
        self.growth_start=next(p+8 for p,(o,a) in self.code.items() if (o,a)==('tst','w6, w1'))
    def get(self,register):
        if register in ('xzr','wzr'):return 0
        if register=='sp':return self.sp
        return self.registers.get('x'+register[1:],0)&((1<<(32 if register.startswith('w') else 64))-1)
    def set(self,register,value):
        if register in ('xzr','wzr'):return
        if register=='sp':self.sp=value;return
        self.registers['x'+register[1:]]=value&((1<<(32 if register.startswith('w') else 64))-1)
    def put(self,address,value,n):
        for i in range(n):self.memory[address+i]=(value>>(8*i))&255
    def load(self,address,n,signed=False):
        value=sum(self.memory.get(address+i,0)<<(8*i) for i in range(n))
        return value-(1<<(n*8)) if signed and value&(1<<(n*8-1)) else value
    def append(self,length):
        self.set('x0',0x400000);self.set('x1',self.file);self.set('x2',self.source);self.set('x3',length)
        for i in range(min(length,self.capacity)):self.memory[self.source+i]=65+(i%26)
        pc=self.function['start'];start_sp=self.sp;visited=[];compare=None;zero=None
        for step in range(200):
            if pc==self.growth_start:self.growth_frontier=pc;return dict(growth_frontier=True,at=pc,visited=visited)
            if pc not in self.code:raise LinkedLogError('Replay left function')
            op,arg=self.code[pc];visited.append(pc);next_pc=pc+4
            if op in ('stp','ldp','str','ldr','ldrh','ldrsh'):
                match=re.fullmatch(r'(.+?), \[(sp|x\d+)(?:, #(-?(?:0x[0-9a-f]+|\d+)))?\](!)?(?:, #(-?(?:0x[0-9a-f]+|\d+)))?',arg)
                if not match:raise LinkedLogError('Unsupported memory operation '+arg)
                registers,base,offset,pre,post=match.groups();offset=int(offset or '0',0);address=self.get(base)+offset
                if pre:self.set(base,address)
                regs=[v.strip() for v in registers.split(',')]
                for i,r in enumerate(regs):
                    n=2 if op in ('ldrh','ldrsh') else 4 if r.startswith('w') else 8
                    if op.startswith('st'):self.put(address+i*n,self.get(r),n)
                    else:self.set(r,self.load(address+i*n,n,signed=op=='ldrsh'))
                if post:self.set(base,self.get(base)+int(post,0))
            elif op in ('mov','sxtw','add','sub'):
                parts=[p.strip() for p in arg.split(',')];r=parts[0]
                def value(x):return int(x[1:],0) if x.startswith('#') else self.get(x)
                result=value(parts[1])
                if op=='sxtw':result=(result&0xffffffff)-(1<<32) if result&(1<<31) else result&0xffffffff
                elif op=='add':result+=value(parts[2])
                elif op=='sub':result-=value(parts[2])
                self.set(r,result)
            elif op=='cmp':
                a,b=[p.strip() for p in arg.split(',')];compare=(self.get(a),int(b[1:],0) if b.startswith('#') else self.get(b));zero=compare[0]==compare[1]
            elif op=='tst':
                a,b=[p.strip() for p in arg.split(',')];zero=(self.get(a)&self.get(b))==0
            elif op in ('b.ls','b.eq','b'):
                take=True if op=='b' else compare[0]<=compare[1] if op=='b.ls' else zero
                if take:next_pc=fmt.target(arg)
            elif op=='bl':
                if not arg.endswith('<memcpy>'):raise LinkedLogError('Unexpected helper call '+arg)
                dst,src,n=(self.get(r) for r in ('x0','x1','x2'))
                if not self.buffer<=dst<=self.buffer+self.capacity or dst+n>self.buffer+self.capacity or not self.source<=src<=self.source+min(length,self.capacity) or src+n>self.source+min(length,self.capacity):raise LinkedLogError('Modeled memcpy out of bounds')
                for i in range(n):self.memory[dst+i]=self.memory[src+i]
                self.copies.append(dict(destination=dst,source=src,bytes=n))
                # AAPCS64 only x19..x29 and saved memory are relied upon.
                for i in range(19):self.set('x'+str(i),0xdead0000+i)
                self.set('x0',dst)
            elif op=='ret':
                if self.sp!=start_sp:raise LinkedLogError('Replay stack not restored')
                return dict(growth_frontier=False,result=self.get('w0'),remaining=self.load(self.file+12,4),stored=self.load(self.file,8)-self.buffer,
                    flags=self.load(self.file+16,2),stack_restored=True,visited=visited)
            else:raise LinkedLogError('Unsupported append opcode '+op)
            pc=next_pc
        raise LinkedLogError('Append instruction budget exceeded')
