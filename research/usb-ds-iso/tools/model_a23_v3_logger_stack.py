"""Continuous final-ELF logger/vsnprintf model; FS results alone are injected."""
import hashlib
import json
import re

import analyze_a23_integrated_memory as integrated
import analyze_a23_linked_logs as linked
import analyze_a23_elf_boundaries as elf


class LoggerModelError(ValueError):pass


class LoggerMachine(integrated.IntegratedMachine):
    ALLOWED=(*integrated.IntegratedMachine.ALLOWED,'LogFunctionImpl','vsnprintf')
    FS=('fsFsOpenFile','fsFileGetSize','fsFileWrite','fsFileClose')

    def __init__(self,functions,blob,metadata,address,values,*,mounted=True,fs_fault=None,**kwargs):
        super().__init__(functions,blob,metadata,address,values,capacity=512,abi='register',**kwargs)
        if fs_fault not in (None,'open','size','write'):raise LoggerModelError('unsupported FS result profile')
        self.fs_fault=fs_fault;self.fs_calls=[];self.required=None;self.rendered=None;self.mount=mounted
        self.logger_sp=self.entry_sp-832;self.vsnprintf_sp=self.logger_sp-96
        self.wrapper_sp=self.vsnprintf_sp-256;self.sp=self.wrapper_sp-1264;self.cache=self.sp+752
        self.buffer=self.logger_sp+128;self.va=self.logger_sp+32;self.file=self.wrapper_sp+72
        for i in range(512):self.store(self.buffer+i,0xa5,1)
        self.stack_argument_snapshot={}
        for i,word in enumerate(self.argument_words):
            if i<7:self.put('x'+str(i+1),word)
            else:
                address_=self.entry_sp+8*(i-7);self.store(address_,word,8);self.stack_argument_snapshot[address_]=word
        for i in range(len(values)+1,8):self.put('x'+str(i),0xcccc0000+i)
        for i in range(8):self.put('q'+str(i),0x12340000+i)
        self.put('x0',address);self.put('sp',self.entry_sp);self.put('x30',0xfffffffffffffff0)
        mounted_symbols=[s for s in metadata['symbols'] if s['name']=='g_sdMounted' and s['size']==1]
        if len(mounted_symbols)!=1:raise LoggerModelError('mount symbol drift')
        self.store(mounted_symbols[0]['address'],int(mounted),1)
        self.pc=self.functions['LogFunctionImpl']['start'];self.writes=[];self.slot_events=[];self.visited=[];self.calls=[]
        self.minimum_sp=self.entry_sp;self.callee_saved={r:self.get(r) for r in ['x'+str(i) for i in range(19,30)]}

    def step(self):
        op,arg=self.code[self.pc]
        if op=='bl':
            target=linked.fmt.target(arg)
            name=next((n for n in self.FS if self.functions[n]['start']==target),None)
            if name:
                pc=self.pc;self.pc+=4;self.visited.append(pc)
                row=dict(name=name,at=pc,held_bytes=self.entry_sp-self.get('sp'),sdk_instructions_executed=False)
                if name=='fsFsOpenFile':
                    assert self.get('w2')==6
                    assert linked.literal_at(self.blob,self.metadata,self.get('x1'))=='/logfile.txt'
                    row['result']=1 if self.fs_fault=='open' else 0
                    # A successful SDK would fill this object. Later logger
                    # instructions pass its address without reading its fields.
                    row['object_pointer']=self.get('x3')
                elif name=='fsFileGetSize':
                    row['result']=1 if self.fs_fault=='size' else 0
                    if not row['result']:self.checked_store(self.get('x1'),1234,8)
                elif name=='fsFileWrite':
                    row['result']=1 if self.fs_fault=='write' else 0
                    length=self.get('x3');assert self.get('x1')==1234 and self.get('w4')==1
                    assert 0<length<=511 and self.get('x2')==self.buffer
                    row.update(length=length,offset=1234,data=bytes(self.load(self.buffer+i,1) for i in range(length)).hex())
                else:row['result']=0
                self.fs_calls.append(row);self.calls.append(dict(name=name,at=pc,held_bytes=row['held_bytes'],modeled=True))
                self.put('x30',self.pc)
                for i in range(19):self.reg.pop('x'+str(i),None)
                for i in list(self.simd):
                    if i<8 or i>15:del self.simd[i]
                self.put('w0',row['result']);self.flags={};return
        # Capture the actual vsnprintf return before the caller uses it. The
        # returned register and buffer are never re-injected into the machine.
        if self.names[self.pc]=='vsnprintf' and op=='ret':
            self.required=self.get('w0');self.rendered=bytes(self.load(self.buffer+i,1) for i in range(min(self.required,511)))
        super().step()

    def run(self,budget=100000):
        while self.pc!=0xfffffffffffffff0:
            if len(self.visited)>=budget or self.pc not in self.code:raise LoggerModelError('logger escaped modeled instruction budget')
            self.step()
        assert self.active_helper is None and self.get('sp')==self.entry_sp
        assert all(self.get(r)==v for r,v in self.callee_saved.items())
        assert all(self.load(a,8)==v for a,v in self.stack_argument_snapshot.items())
        if self.mount:
            assert self.required is not None and self.load(self.buffer+min(self.required,511),1)==0
            assert self.file_before_formatter['flags']==0x208 and self.load(self.file+16,2)==0x208
            assert self.load(self.sp+308,4)==len(self.argument_words)
        else:assert self.required is None and not self.fs_calls
        assert not any(c['name']=='get_arg' for c in self.calls)
        trace=json.dumps(self.visited,separators=(',',':')).encode()
        return dict(schema='A23-V3-continuous-logger-profile-1',required=self.required,
            rendered_hex=self.rendered.hex() if self.rendered is not None else None,
            observed_user_stack_bytes=self.entry_sp-self.minimum_sp,stack_restored=True,callee_saved_restored=True,
            stack_arguments_preserved=True,fs_calls=self.fs_calls,helper_calls=self.helper_calls,
            instruction_count=len(self.visited),trace_sha256=hashlib.sha256(trace).hexdigest(),
            executed_function_names=sorted({self.names[pc] for pc in self.visited}),
            fs_results_injected=True,fs_sdk_instructions_executed=False,
            logger_and_vsnprintf_actual_instructions_in_model=True,formatter_state_reinjected=False,
            tls_register_reent_locale_and_valid_arguments_injected=True,actual_arm_executed=False,
            whole_thread_stack_verified=False,full_symbolic_proof=False)


class PathSnprintfMachine(integrated.IntegratedMachine):
    """Only the two current file-name formats, one terminated hex nonce."""
    ALLOWED=(*integrated.IntegratedMachine.ALLOWED,'snprintf')

    def __init__(self,functions,blob,metadata,address,nonce):
        if not isinstance(nonce,bytes) or len(nonce)!=64 or re.fullmatch(b'[0-9a-f]{64}',nonce) is None:
            raise LoggerModelError('path profile requires a 64-byte lowercase hex nonce')
        super().__init__(functions,blob,metadata,address,[nonce],capacity=96,abi='register')
        if self.spec not in ('/ep0-%s.capture.bin','/ep0-%s.diagnostic.bin'):raise LoggerModelError('unreviewed snprintf literal')
        outer=self.entry_sp-496;self.sp=outer-1264;self.cache=self.sp+752;self.wrapper_sp=outer;self.file=outer+136;self.va=outer+64
        self.put('sp',self.entry_sp);self.put('x0',self.buffer);self.put('x1',96);self.put('x2',address);self.put('x3',self.argument_words[0])
        for i in range(4,8):self.put('x'+str(i),0xcccc0000+i)
        for i in range(8):self.put('q'+str(i),0x12340000+i)
        self.put('x30',0xfffffffffffffff0);self.pc=self.functions['snprintf']['start']
        self.visited=[];self.calls=[];self.writes=[];self.slot_events=[];self.minimum_sp=self.entry_sp
        self.callee_saved={r:self.get(r) for r in ['x'+str(i) for i in range(19,30)]}

    def run(self,budget=100000):
        while self.pc!=0xfffffffffffffff0:
            if len(self.visited)>=budget or self.pc not in self.code:raise LoggerModelError('path snprintf escaped instruction budget')
            self.step()
        required=self.get('w0');assert 0<required<96 and self.get('sp')==self.entry_sp
        assert self.active_helper is None and all(self.get(r)==v for r,v in self.callee_saved.items())
        assert self.load(self.buffer+required,1)==0 and self.load(self.file+16,2)==0x208
        assert self.load(self.sp+308,4)==1 and not any(c['name']=='get_arg' for c in self.calls)
        return dict(schema='A23-V3-path-snprintf-profile-1',format=self.spec,required=required,
            rendered_hex=bytes(self.load(self.buffer+i,1) for i in range(required)).hex(),
            observed_user_stack_bytes=self.entry_sp-self.minimum_sp,stack_restored=True,callee_saved_restored=True,
            helper_call_count=len(self.helper_calls),instruction_count=len(self.visited),
            trace_sha256=hashlib.sha256(json.dumps(self.visited,separators=(',',':')).encode()).hexdigest(),
            formatter_state_reinjected=False,tls_reent_arguments_and_mapping_injected=True,
            actual_arm_executed=False,whole_thread_stack_verified=False,full_symbolic_proof=False)
