#!/usr/bin/env python3
"""Replay sealed AArch64 handle-wait paths with injected SVC/ticks, never USB."""
import re
from collections import deque
from analyze_a23_session_stack import parse_disassembly
MASK=(1<<64)-1
class Unsupported(ValueError):pass

class HandleWaitMachine:
    def __init__(self,text,count=1,types=(0,),timeout=0,results=(0,),reset_results=(0,),tick_step=1):
        fs=parse_disassembly(text);self.functions={v['name']:(a,v) for a,v in fs.items()}
        self.allowed=('waitObjects','svcWaitSynchronization','svcResetSignal')
        self.instructions={p:(op,arg,name) for name in self.allowed for p,op,arg in self.functions[name][1]['instructions']}
        self.reg={};self.mem={};self.flags=dict(z=False,n=False,c=False,v=False);self.initial_sp=0x100000
        self.reg['sp']=self.initial_sp;self.reg['x30']=0xdeadbeef
        self.put('x0',0x210000);self.put('x1',0x200000);self.put('w2',count);self.put('x3',timeout)
        self.pc=self.functions['waitObjects'][0];self.peak=0;self.calls=[];self.steps=0;self.tick=1;self.tick_step=tick_step
        self.results=deque(results);self.reset_results=deque(reset_results);self.count=count
        for i in range(max(0,min(count,64))):self.store(0x200000+16*i,types[i%len(types)],4);self.store(0x200008+16*i,100+i,4)
        self.store(0x230000+484,17,4);self.store(0x210000,-1,4)
    def get(self,name):
        if name in ('xzr','wzr'):return 0
        key='x'+name[1:] if name.startswith('w') else name
        return self.reg.get(key,0)&((1<<32)-1 if name.startswith('w') else MASK)
    def put(self,name,n):
        if name in ('xzr','wzr'):return
        key='x'+name[1:] if name.startswith('w') else name
        self.reg[key]=n&((1<<32)-1 if name.startswith('w') else MASK)
    def store(self,address,n,size):
        for i in range(size):self.mem[address+i]=(n>>(8*i))&255
    def load(self,address,size):
        if any(address+i not in self.mem for i in range(size)):raise Unsupported(f'uninitialized memory at {address:x}/{size}')
        return sum(self.mem[address+i]<<(8*i) for i in range(size))
    def imm(self,s):return int(s.removeprefix('#'),0)
    def value(self,s):return self.imm(s) if s.startswith('#') else self.get(s)
    def condition(self,s):
        f=self.flags
        return {'eq':f['z'],'ne':not f['z'],'hi':f['c'] and not f['z'],'ls':not f['c'] or f['z'],
                'cc':not f['c'],'lo':not f['c'],'cs':f['c'],'hs':f['c'],'gt':not f['z'] and f['n']==f['v'],
                'le':f['z'] or f['n']!=f['v'],'ge':f['n']==f['v'],'lt':f['n']!=f['v']}[s]
    def compare(self,a,b,bits,add=False):
        mask=(1<<bits)-1;a&=mask;b&=mask;value=a+b if add else a-b;out=value&mask;sign=1<<(bits-1)
        self.flags=dict(z=out==0,n=bool(out&sign),c=value>mask if add else a>=b,
                        v=bool((~(a^b) if add else (a^b))&(a^out)&sign))
    def memory(self,op,arg):
        m=re.fullmatch(r'(.+?), \[(\w+)(?:, (.+?))?\](!)?(?:, (.+))?',arg)
        if not m:raise Unsupported('memory operand: '+arg)
        registers=[r.strip() for r in m[1].split(',')];base=m[2];offset=m[3] or '#0';pre=bool(m[4]);post=m[5]
        parts=[p.strip() for p in offset.split(',')];delta=self.value(parts[0])
        if len(parts)>1:
            kind,amount=parts[1].split();delta=self.get(parts[0])<<self.imm(amount)
            if kind=='sxtw' and self.get(parts[0])&(1<<31):delta=(self.get(parts[0])-(1<<32))<<self.imm(amount)
            elif kind not in ('lsl','uxtw','sxtw'):raise Unsupported('memory shift '+kind)
        address=(self.get(base)+delta)&MASK
        if pre:self.put(base,address)
        size=4 if registers[0].startswith('w') or op=='ldrsw' else 8
        for i,r in enumerate(registers):
            if op.startswith('st'):self.store(address+i*size,self.get(r),size)
            else:
                n=self.load(address+i*size,size)
                if op=='ldrsw' and n&(1<<31):n-=1<<32
                self.put(r,n)
        if post:self.put(base,self.get(base)+self.value(post))
    def run(self,budget=100000):
        while self.pc!=0xdeadbeef:
            if self.steps>=budget:raise Unsupported('instruction budget, no termination claim')
            if self.pc not in self.instructions:raise Unsupported(f'execution outside audited functions at {self.pc:x}')
            pc=self.pc;op,arg,name=self.instructions[pc];self.pc+=4;self.steps+=1
            target=re.search(r'\b([0-9a-f]+) <([^>]+)>',arg);target_pc=int(target[1],16) if target else None
            args=[s.strip() for s in arg.split(',')]
            if op in ('stp','str','ldr','ldp','ldrsw','ldur'):self.memory(op,arg)
            elif op=='mov':self.put(args[0],self.value(args[1]))
            elif op=='movk':
                shift=self.imm(args[2].split()[-1]) if len(args)>2 else 0
                self.put(args[0],(self.get(args[0])&~(0xffff<<shift))|(self.value(args[1])<<shift))
            elif op in ('add','sub','mul','and','orr','lsl','lsr','umulh','umull'):
                a=self.value(args[1]);b=self.value(args[2]);bits=32 if args[0].startswith('w') else 64
                if len(args)>3:
                    kind,amount=args[3].split();shift=self.imm(amount)
                    if kind=='lsl':b<<=shift
                    elif kind=='lsr':b>>=shift
                    elif kind in ('uxtw','sxtw'):
                        b&=(1<<32)-1
                        if kind=='sxtw' and b&(1<<31):b-=1<<32
                        b<<=shift
                    else:raise Unsupported('register shift '+kind)
                values={'add':lambda:a+b,'sub':lambda:a-b,'mul':lambda:a*b,'and':lambda:a&b,'orr':lambda:a|b,
                        'lsl':lambda:a<<(b%bits),'lsr':lambda:a>>(b%bits),'umulh':lambda:(a*b)>>64,'umull':lambda:(a&0xffffffff)*(b&0xffffffff)}
                self.put(args[0],values[op]())
            elif op=='ubfiz':self.put(args[0],(self.value(args[1])&((1<<self.imm(args[3]))-1))<<self.imm(args[2]))
            elif op in ('cmp','cmn'):self.compare(self.get(args[0]),self.value(args[1]),32 if args[0].startswith('w') else 64,op=='cmn')
            elif op=='csel':self.put(args[0],self.get(args[1] if self.condition(args[3]) else args[2]))
            elif op=='mrs':
                if args[1]=='cntpct_el0':self.put(args[0],self.tick);self.tick+=self.tick_step
                elif args[1]=='tpidrro_el0':self.put(args[0],0x230000)
                else:raise Unsupported('MRS '+args[1])
            elif op=='b':self.pc=target_pc
            elif op.startswith('b.'):
                if self.condition(op[2:]):self.pc=target_pc
            elif op in ('cbz','cbnz'):
                if (self.get(args[0])==0)==(op=='cbz'):self.pc=target_pc
            elif op=='tbz':
                if not (self.get(args[0])&(1<<self.imm(args[1]))):self.pc=target_pc
            elif op=='bl':
                if target_pc not in [self.functions[n][0] for n in self.allowed]:raise Unsupported('unaudited call '+arg)
                self.put('x30',self.pc);self.pc=target_pc
            elif op in ('blr','br'):raise Unsupported('indirect target reached: '+name+' '+arg)
            elif op=='svc':
                svc=self.imm(arg)
                if svc==0x18:
                    if not self.results:raise Unsupported('SVC sequence exhausted, no termination claim')
                    count=self.get('w2');handles=[self.load(self.get('x1')+4*i,4) for i in range(count)]
                    rc=self.results.popleft();self.calls.append(dict(svc=svc,count=count,handles=handles,stack=self.initial_sp-self.get('sp'),result=rc))
                    self.put('w0',rc);self.put('w1',max(count-1,0))
                elif svc==0x17:
                    if not self.reset_results:raise Unsupported('reset sequence exhausted')
                    rc=self.reset_results.popleft();self.calls.append(dict(svc=svc,stack=self.initial_sp-self.get('sp'),result=rc));self.put('w0',rc)
                else:raise Unsupported('SVC '+arg)
            elif op=='ret':self.pc=self.get('x30')
            elif op=='nop':pass
            else:raise Unsupported('instruction '+op+' '+arg)
            self.peak=max(self.peak,self.initial_sp-self.get('sp'))
        if self.get('sp')!=self.initial_sp:raise Unsupported('SP not restored on return')
        return dict(result=self.get('w0'),peak_user_stack_bytes=self.peak,steps=self.steps,svc_calls=self.calls,
                    stack_restored=True,indirect_callbacks_reached=False,hardware_verified=False)

def profiles():
    rows=[]
    for count in range(1,65):
        for typ in (0,1):
            rows.append(dict(name=f'count-{count}-type-{typ}',count=count,types=(typ,),timeout=0,results=(0,),reset_results=(0,)))
    for timeout in (0,1000000,MASK):
        for typ in (0,1):
            for name,results,resets in (('timeout',(0xea01,),(0,)),('cancel-retry',(0xec01,0),(0,)),
                ('error',(0xee01,),(0,)),('reset-retry',(0,0),(0xfa01,0)),('many-cancels',(0xec01,)*100+(0,),(0,))):
                if name=='reset-retry' and typ==0:continue
                rows.append(dict(name=f'{name}-t{typ}-timeout{timeout}',count=1,types=(typ,),timeout=timeout,results=results,reset_results=resets))
    rows.append(dict(name='bad-count-65',count=65,types=(0,),timeout=0,results=(),reset_results=()))
    return rows

def replay(text):
    rows=[]
    for p in profiles():
        args={k:v for k,v in p.items() if k!='name'};row=HandleWaitMachine(text,**args).run();row.update(name=p['name'],count=p['count'],type=p['types'][0],timeout=p['timeout'])
        expected=224 if p['count']==65 else 224+((4*p['count']+15)//16)*16+48*p['count']+16
        if row['peak_user_stack_bytes']>expected:raise ValueError('SP exceeded shape bound')
        rows.append(row)
    return dict(schema='A23-handle-wait-machine-1',profiles=rows,profile_count=len(rows),event_wait_objects=1,
                wait_objects_one_handle_frame=288,wait_objects_one_handle_with_svc=304,event_wait_with_svc=352,
                conditional_handle_profile_only=True,full_symbolic_proof=False,termination_bound_verified=False,
                kernel_or_exception_stack_included=False,hardware_verified=False)
