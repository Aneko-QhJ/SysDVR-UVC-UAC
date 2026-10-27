"""Replay bound SDK memory helpers and record their exact memory accesses."""
import re
import analyze_a23_format_loop as fmt


class MemoryError(fmt.LoopError):
    pass


class MemoryMachine(fmt.FormatMachine):
    ALLOWED=(*fmt.FormatMachine.ALLOWED,'memcpy','memset','strlen')

    def __init__(self,functions,blob,metadata,format_address,helper,length,source_offset=0,destination_offset=0,byte=0):
        self.simd={};self.record_memory=False;self.read_accesses=[];self.write_accesses=[]
        super().__init__(functions,blob,metadata,format_address,[],capacity=512)
        self.helper=helper;self.length=length;self.source_base=0x500000;self.destination_base=0x720000
        self.initial_byte=byte & 255
        self.source_address=self.source_base+source_offset;self.destination_address=self.destination_base+destination_offset
        self.expected_source=bytes((i*37+11)&255 for i in range(length))
        if helper=='strlen':
            # A mapped-page precondition, intentionally distinct from the
            # logical C string. Every byte before/after it is nonzero padding.
            self.mapped_bytes=((source_offset+length+32)//4096+1)*4096
            for i in range(self.mapped_bytes):self.store(self.source_base+i,0xa5,1)
            for i in range(length):self.store(self.source_address+i,65+(i%26),1)
            self.store(self.source_address+length,0,1)
            self.put('x0',self.source_address)
        else:
            for i,v in enumerate(self.expected_source):self.store(self.source_address+i,v,1)
            for i in range(-32,length+32):self.store(self.destination_address+i,0xcc,1)
            self.put('x0',self.destination_address)
            self.put('x1',self.source_address if helper=='memcpy' else byte)
            self.put('x2',length)
        self.put('x30',0xfffffffffffffff0);self.pc=self.functions[helper]['start']
        self.visited=[];self.calls=[];self.minimum_sp=self.get('sp');self.writes=[]
        self.record_memory=True

    def vector(self,r):
        match=re.fullmatch(r'([qdv])(\d+)(?:\.(16b|8b|8h|4s|d\[0\]))?',r)
        if not match:return None
        prefix,index,shape=match.groups();bits=128 if prefix=='q' or prefix=='v' and shape not in ('8b','d[0]') else 64
        return int(index),bits

    def get(self,r):
        vector=self.vector(r)
        if vector:
            index,bits=vector
            if index not in self.simd:raise MemoryError('Undefined SIMD register '+r)
            return self.simd[index] & ((1<<bits)-1)
        return super().get(r)

    def put(self,r,value):
        vector=self.vector(r)
        if vector:
            index,bits=vector;self.simd[index]=value & ((1<<bits)-1)
        else:super().put(r,value)

    def load(self,address,n,signed=False):
        if self.record_memory:self.read_accesses.append(dict(at=self.pc-4,address=address,bytes=n))
        return super().load(address,n,signed)

    def checked_store(self,address,value,n):
        if not self.record_memory:return super().checked_store(address,value,n)
        if not (self.destination_address<=address and address+n<=self.destination_address+self.length):
            raise MemoryError('SDK helper write outside requested destination')
        self.write_accesses.append(dict(at=self.pc-4,address=address,bytes=n));self.store(address,value,n)

    @staticmethod
    def lanes(value,width,count):return [(value>>(width*i)) & ((1<<width)-1) for i in range(count)]

    @staticmethod
    def packed(values,width):return sum(v<<(width*i) for i,v in enumerate(values))

    def step(self):
        op,operands=self.code[self.pc];a=[p.strip() for p in operands.split(',')]
        vector_op=op=='and' and a[0].startswith('v')
        if op in ('bti','nop','dup','uminp','cmeq','shrn','addp','ld1','fmov','rbit','rev','clz','bics','bic','subs','sturh') or vector_op:
            self.visited.append(self.pc);self.pc+=4
            if op in ('bti','nop'):pass
            elif op=='dup':
                width,count=(8,16) if a[0].endswith('.16b') else (32,4)
                self.put(a[0],self.packed([self.get(a[1])&((1<<width)-1)]*count,width))
            elif op in ('uminp','addp'):
                left=self.lanes(self.get(a[1]),8,16);right=self.lanes(self.get(a[2]),8,16)
                result=[(min(row[i],row[i+1]) if op=='uminp' else (row[i]+row[i+1])&255) for row in (left,right) for i in range(0,16,2)]
                self.put(a[0],self.packed(result,8))
            elif op=='cmeq':
                count=8 if a[0].endswith('.8b') else 16
                if a[2]!='#0':raise MemoryError('Unsupported vector comparison')
                self.put(a[0],self.packed([255 if b==0 else 0 for b in self.lanes(self.get(a[1]),8,count)],8))
            elif op=='shrn':
                if a[0].split('.')[1]!='8b' or a[1].split('.')[1]!='8h':raise MemoryError('Unsupported narrowing shape')
                self.put(a[0],self.packed([(v>>self.value_of(a[2]))&255 for v in self.lanes(self.get(a[1]),16,8)],8))
            elif vector_op:self.put(a[0],self.get(a[1])&self.get(a[2]))
            elif op=='ld1':
                match=re.fullmatch(r'\{v(\d+)\.16b-v(\d+)\.16b\}, \[(x\d+)\]',operands)
                if not match:raise MemoryError('Unsupported SIMD list load')
                first,last,base=match.groups();address=self.get(base)
                for i in range(int(first),int(last)+1):self.put('q'+str(i),self.load(address+16*(i-int(first)),16))
            elif op=='fmov':self.put(a[0],self.get(a[1]))
            elif op in ('rev','rbit','clz'):
                value=self.get(a[1]);bits=32 if a[0].startswith('w') else 64
                if op=='rev':value=int.from_bytes(value.to_bytes(bits//8,'little'),'big')
                elif op=='rbit':value=int(format(value,'0'+str(bits)+'b')[::-1],2)
                else:value=bits-value.bit_length()
                self.put(a[0],value)
            elif op in ('bics','bic'):
                value=self.get(a[1]) & ~self.get(a[2]);self.put(a[0],value)
                if op=='bics':self.logical_flags(value,32 if a[0].startswith('w') else 64)
            elif op=='subs':
                bits=32 if a[0].startswith('w') else 64;left=self.get(a[1]);right=self.value_of(a[2])
                self.comparison(left,right,bits);self.put(a[0],left-right)
            elif op=='sturh':self.memory_instruction('strh',operands)
        elif op in ('lsr','lsl') and not a[2].startswith('#'):
            self.visited.append(self.pc);self.pc+=4;bits=32 if a[0].startswith('w') else 64
            shift=self.get(a[2]) & (bits-1);value=self.get(a[1])
            self.put(a[0],value>>shift if op=='lsr' else value<<shift)
        elif op=='mrs' and operands.endswith('dczid_el0'):
            raise MemoryError('DCZID/ZVA architectural frontier')
        else:super().step()

    def run_helper(self,budget=4096):
        while self.pc!=0xfffffffffffffff0:
            if len(self.visited)>=budget or self.pc not in self.code:raise MemoryError('SDK helper escaped instruction budget')
            self.step()
        self.record_memory=False
        assert self.get('sp')==self.entry_sp
        if self.helper=='strlen':
            assert self.get('x0')==self.length
            assert all(self.source_base<=r['address'] and r['address']+r['bytes']<=self.source_base+self.mapped_bytes for r in self.read_accesses)
            before=max([self.source_address-r['address'] for r in self.read_accesses]+[0])
            after=max([r['address']+r['bytes']-(self.source_address+self.length+1) for r in self.read_accesses]+[0])
        else:
            expected=self.expected_source if self.helper=='memcpy' else bytes([self.initial_byte])*self.length
            actual=bytes(self.load(self.destination_address+i,1) for i in range(self.length));assert actual==expected
            assert self.get('x0')==self.destination_address
            assert all(self.load(self.destination_address+i,1)==0xcc for i in range(-32,0))
            assert all(self.load(self.destination_address+i,1)==0xcc for i in range(self.length,self.length+32))
            if self.helper=='memcpy':assert all(self.source_address<=r['address'] and r['address']+r['bytes']<=self.source_address+self.length for r in self.read_accesses)
            before=after=0
        return dict(helper=self.helper,length=self.length,source=self.source_address,destination=self.destination_address,
            return_value=self.get('x0'),reads=self.read_accesses,writes=self.write_accesses,visited=self.visited,
            logical_string_read_before=before,logical_string_read_after_nul=after,stack_restored=True,
            actual_instructions_executed_in_model=True,actual_arm_executed=False,mapped_pages_and_valid_inputs_injected=True)
