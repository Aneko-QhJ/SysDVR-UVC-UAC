"""Exact argument-fetch instruction profiles; parser entry state is injected."""
import hashlib,json,re
import analyze_a23_elf_boundaries as elf
from analyze_a23_formatter import target

class ArgumentError(ValueError):pass
MASK=(1<<64)-1
# Offsets from the bound _svfprintf_r symbol, not absolute addresses.
PATHS={'d32':(0xc00,0xcf0,'x1'),'d64':(0x92c,0xcf0,'x1'),
       'u32':(0x2470,0x21d4,'x1'),'u64':(0x2194,0x21d4,'x1'),
       'x32':(0x1bf0,0x1ce0,'x1'),'x64':(0x191c,0x1ce0,'x1'),
       's':(0x1e40,0x1f34,'x21')}

def certificate(blob,text):
    fs,metadata=elf.build_functions(blob,text);f=next(f for f in fs.values() if f['name']=='_svfprintf_r');code={p:(o,a) for p,o,a in f['instructions']};start=f['start'];paths={}
    if code[start]!=('sub','sp, sp, #0x4f0'):raise ArgumentError('Formatter frame changed')
    init=[pc for pc,(o,a) in code.items() if (o,a)==('str','wzr, [sp, #308]')]
    if len(init)!=1:raise ArgumentError('Cache initialization changed')
    resets=[pc for pc,(o,a) in code.items() if (o,a)==('str','w3, [sp, #136]')]
    if len(resets)!=1 or code[resets[0]-8]!=('mov','w3, #0x0'):raise ArgumentError('Conversion position reset changed')
    dollar=[pc for pc,(o,a) in code.items() if (o,a)==('cmp','w0, #0x24')]
    if len(dollar)!=3:raise ArgumentError('Dollar parser comparison count changed')
    overlaps=[dict(at=pc,operation=o,operands=a) for pc,(o,a) in code.items() if o.startswith('st') and '[sp, #136]' in a and (a.startswith('x') or o=='stp')]
    if len(overlaps)!=3:raise ArgumentError('Reused position-slot stores changed')
    for name,(offset,stop,result) in PATHS.items():
        entry=start+offset;end=start+stop
        expected=('ldr','w1, [sp, #308]') if name=='s' else ('cbz','w3, '+code[entry][1].split(', ',1)[-1])
        if code[entry]!=expected or end not in code:raise ArgumentError('Fetch block entry changed '+name)
        paths[name]=dict(entry=entry,stop=end,result_register=result)
    return dict(schema='A23-argument-cache-certificate-1',elf_sha256=metadata['elf_sha256'],formatter_sha256=elf.function_digest(f),formatter_frame_bytes=1264,
        cache_count_offset=308,cache_count_initialization=init[0],cache_base_offset=752,cache_stride=16,cache_entries=32,cache_end_offset=1264,
        conversion_position_offset=136,conversion_position_reset=resets[0],dollar_comparisons=dollar,
        reused_position_slot_stores=overlaps,position_slot_global_zero_invariant_valid=False,paths=paths,
        parser_reaches_injected_state_proven=False,get_arg_globally_unreachable_proven=False,whole_thread_stack_verified=False)

class FetchMachine:
    def __init__(self,functions,path,index=0,cached=None,position=False,abi='register',value=0xfedcba9876543210):
        f=next(f for f in functions.values() if f['name']=='_svfprintf_r');self.code={p:(o,a) for p,o,a in f['instructions']};start=f['start'];self.path=path;self.pc=start+PATHS[path][0];self.stop=start+PATHS[path][1]
        self.reg={};self.mem={};self.writes=[];self.visited=[];self.flags={};self.sp=0x100000;self.va=0x200000;self.stack_arg=0x300000;self.top=0x400000;self.cache=self.sp+752;self.value=value;self.index=index;self.cached=index if cached is None else cached
        self.put('sp',self.sp);self.put('x24',self.va);self.put('w27',index);self.put('w28',index);self.put('w3',int(position));self.put('w0',self.cached)
        self.store(self.sp+308,self.cached,4);self.store(self.sp+144,0,8);self.store(self.sp+136,int(position),4)
        self.store(self.va,self.stack_arg,8);self.store(self.va+8,self.top,8)
        gr_offset=-56+8*index if abi=='register' and index<7 else 0;self.store(self.va+24,gr_offset,4)
        self.source=self.top+gr_offset if gr_offset<0 else self.stack_arg;self.store(self.source,value,8)
        for i in range(min(self.cached,32)):self.store(self.cache+16*i,value,8)
        self.store(self.cache-1,0xa5,1);self.store(self.cache+512,0x5a,1);self.writes=[]
    def get(self,r):
        if r in ('xzr','wzr'):return 0
        key='x'+r[1:] if r.startswith('w') else r
        return self.reg.get(key,0)&((1<<32)-1 if r.startswith('w') else MASK)
    def put(self,r,v):
        if r in ('xzr','wzr'):return
        self.reg['x'+r[1:] if r.startswith('w') else r]=v&((1<<32)-1 if r.startswith('w') else MASK)
    def value_of(self,x):return int(x[1:],0) if x.startswith('#') else self.get(x)
    def store(self,a,v,n):
        for i in range(n):self.mem[a+i]=(v>>(8*i))&255
        self.writes.append(dict(address=a,bytes=n))
    def load(self,a,n,signed=False):
        if any(a+i not in self.mem for i in range(n)):raise ArgumentError('Uninitialized argument memory')
        v=sum(self.mem[a+i]<<(8*i) for i in range(n));return v-(1<<(8*n)) if signed and v&(1<<(8*n-1)) else v
    def comparison(self,a,b,bits):
        mask=(1<<bits)-1;a&=mask;b&=mask;v=(a-b)&mask;sign=1<<(bits-1)
        self.flags=dict(z=v==0,n=bool(v&sign),c=a>=b,v=bool((a^b)&(a^v)&sign))
    def condition(self,cond):
        f=self.flags;return {'eq':f['z'],'ne':not f['z'],'ge':f['n']==f['v'],'lt':f['n']!=f['v'],'gt':not f['z'] and f['n']==f['v'],'le':f['z'] or f['n']!=f['v'],'hi':f['c'] and not f['z'],'ls':not f['c'] or f['z']}[cond]
    def memory(self,op,arg):
        m=re.fullmatch(r'(\w+), \[(\w+)(?:, (.+))?\]',arg)
        if not m:raise ArgumentError('Unsupported fetch memory operand '+arg)
        r,base,offset=m.groups();a=self.get(base)+(self.value_of(offset) if offset else 0);n=4 if r.startswith('w') else 8
        if op=='ldrsw':n=4
        if op.startswith('st'):
            allowed=self.sp+308<=a and a+n<=self.sp+312 or self.sp+144<=a and a+n<=self.sp+152 or self.cache<=a and a+n<=self.cache+512 or self.va<=a and a+n<=self.va+32
            if not allowed:raise ArgumentError('Fetch write outside cache/counter/va_list')
            self.store(a,self.get(r),n)
        else:self.put(r,self.load(a,n,signed=op=='ldrsw'))
    def run(self,budget=100):
        reached=False
        while self.pc!=self.stop:
            if len(self.visited)>=budget or self.pc not in self.code:raise ArgumentError('Fetch escaped instruction budget or function')
            pc=self.pc;op,arg=self.code[pc];self.visited.append(pc);self.pc+=4;args=[a.strip() for a in arg.split(',')]
            if op=='bl':
                if not arg.endswith('<get_arg>'):raise ArgumentError('Unexpected fetch call')
                reached=True;break
            elif op in ('ldr','ldrsw','str'):self.memory(op,arg)
            elif op in ('add','sub','and','mov','sxtw','sbfiz'):
                v=self.value_of(args[1])
                if op=='sxtw':v=(v&0xffffffff)-(1<<32) if v&(1<<31) else v&0xffffffff
                elif op=='sbfiz':
                    bits=int(args[3][1:],0);v&=(1<<bits)-1
                    if v&(1<<(bits-1)):v-=1<<bits
                    v<<=int(args[2][1:],0)
                elif op!='mov':
                    b=self.value_of(args[2])
                    if len(args)==4:
                        parts=args[3].split();kind=parts[0];shift=int(parts[1][1:],0) if len(parts)>1 else 0
                        if kind=='sxtw' and b&(1<<31):b=(b&0xffffffff)-(1<<32)
                        elif kind not in ('sxtw','lsl'):raise ArgumentError('Unsupported fetch arithmetic shift')
                        b<<=shift
                    v=v+b if op=='add' else v-b if op=='sub' else v&b
                self.put(args[0],v)
            elif op=='cmp':self.comparison(self.get(args[0]),self.value_of(args[1]),32 if args[0].startswith('w') else 64)
            elif op=='b':self.pc=target(arg)
            elif op.startswith('b.'):
                if self.condition(op[2:]):self.pc=target(arg)
            elif op in ('cbz','cbnz'):
                if (self.get(args[0])==0)==(op=='cbz'):self.pc=target(arg)
            elif op in ('tbz','tbnz'):
                if bool(self.get(args[0])&(1<<int(args[1][1:],0)))==(op=='tbnz'):self.pc=target(arg)
            else:raise ArgumentError('Unsupported fetch opcode '+op)
        cache_writes=[r for r in self.writes if self.cache<=r['address']<self.cache+512]
        if self.load(self.cache-1,1)!=0xa5 or self.load(self.cache+512,1)!=0x5a:raise ArgumentError('Cache sentinel changed')
        return dict(path=self.path,index=self.index,initial_cached=self.cached,get_arg_frontier=reached,
            result=None if reached else self.get(PATHS[self.path][2]),final_cached=self.load(self.sp+308,4),
            next_index=self.load(self.sp+144,4) if self.path=='s' else self.get('w27'),cache_writes=cache_writes,
            stack_restored=self.get('sp')==self.sp,visited=self.visited,get_arg_executed=False)

class DecimalMachine:
    """Replay the bound numeric width/position scanner, not the full parser."""
    def __init__(self,functions,token):
        self.f=next(f for f in functions.values() if f['name']=='_svfprintf_r');self.code={p:(o,a) for p,o,a in self.f['instructions']};self.start=self.f['start']
        self.pc=self.start+0x5f0;self.reg={'w0':ord(token[0]),'w21':0,'x23':0x500001,'sp':0x100000};self.bytes={0x500000+i:b for i,b in enumerate(token.encode('ascii')+b'\0')};self.position=0;self.visited=[];self.cmp=None
        if not token or not token[0].isdigit():raise ArgumentError('Decimal scanner entry needs a digit')
    def value(self,r):
        if r in ('wzr','xzr'):return 0
        if r.startswith('#'):return int(r[1:],0)
        if r not in self.reg:raise ArgumentError('Undefined decimal register '+r)
        return self.reg[r]
    def write(self,r,value):self.reg[r]=value&((1<<32)-1 if r.startswith('w') else MASK)
    def run(self,budget=256):
        exits={self.start+0x224:'width',self.start+0x2a8:'position',self.start+0x3a48:'rejected-index'}
        while self.pc not in exits:
            if len(self.visited)>=budget or self.pc not in self.code:raise ArgumentError('Decimal scanner escaped budget')
            pc=self.pc;op,arg=self.code[pc];self.visited.append(pc);self.pc+=4;a=[p.strip() for p in arg.split(',')]
            if op in ('mov','add','sub','madd'):
                v=self.value(a[1]);v=v+self.value(a[2]) if op=='add' else v-self.value(a[2]) if op=='sub' else v*self.value(a[2])+self.value(a[3]) if op=='madd' else v;self.write(a[0],v)
            elif op=='ldrb':
                match=re.fullmatch(r'w0, \[x23\], #1',arg)
                if not match or self.reg['x23'] not in self.bytes:raise ArgumentError('Decimal scanner input read outside token')
                self.write('w0',self.bytes[self.reg['x23']]);self.reg['x23']+=1
            elif op=='cmp':
                x,y=self.value(a[0]),self.value(a[1]);bits=32 if a[0].startswith('w') else 64;self.cmp=(x,y,bits)
            elif op.startswith('b.'):
                x,y,bits=self.cmp;sx=x-(1<<bits) if x&(1<<(bits-1)) else x;sy=y-(1<<bits) if y&(1<<(bits-1)) else y
                yes={'ls':x<=y,'ne':x!=y,'eq':x==y,'gt':sx>sy}[op[2:]]
                if yes:self.pc=target(arg)
            elif op=='b':self.pc=target(arg)
            elif op=='str':
                if arg!='w0, [sp, #136]':raise ArgumentError('Unexpected decimal scanner store')
                self.position=self.value('w0')
            else:raise ArgumentError('Unsupported decimal scanner opcode '+op)
        outcome=exits[self.pc]
        return dict(outcome=outcome,position=self.position,parsed_number=self.reg.get('w1'),argument_index=self.reg.get('w28'),
            scanner_stop=self.pc,visited=self.visited,full_parser_executed=False)
