"""Current quiet ELF instruction models. No native ARM or actual SDK calls."""
import hashlib
import json
import re

from model_a23_v3_logger_stack import LoggerMachine,LoggerModelError
from model_a23_wait_machine import HandleWaitMachine
from analyze_a23_linked_logs import origins


class QuietLoggerMachine(LoggerMachine):
    def __init__(self,functions,blob,metadata,address,values,*,quiet=False,**kwargs):
        if type(quiet) is not bool:raise LoggerModelError('quiet flag must be boolean')
        super().__init__(functions,blob,metadata,address,values,**kwargs)
        symbols=[s for s in metadata['symbols'] if s['name']=='g_diagnosticQuiet' and s['size']==1]
        if len(symbols)!=1:raise LoggerModelError('quiet flag symbol drift')
        self.quiet=quiet;self.quiet_address=symbols[0]['address'];self.store(self.quiet_address,int(quiet),1)
        self.atomic_reads=[]

    def step(self):
        op,arg=self.code[self.pc]
        if op=='ldarb':
            if self.names[self.pc]!='LogFunctionImpl' or arg!='w1, [x8]' or self.get('x8')!=self.quiet_address:
                raise LoggerModelError('unreviewed acquire load')
            pc=self.pc;self.pc+=4;self.visited.append(pc)
            value=self.load(self.get('x8'),1);self.put('w1',value)
            self.atomic_reads.append(dict(at=pc,address=self.quiet_address,value=value))
            self.minimum_sp=min(self.minimum_sp,self.get('sp'));return
        super().step()

    def run(self,budget=100000):
        if not self.quiet:
            row=super().run(budget)
        else:
            while self.pc!=0xfffffffffffffff0:
                if len(self.visited)>=budget or self.pc not in self.code:raise LoggerModelError('quiet logger escaped instruction budget')
                self.step()
            assert self.active_helper is None and self.get('sp')==self.entry_sp
            assert all(self.get(r)==v for r,v in self.callee_saved.items())
            assert all(self.load(a,8)==v for a,v in self.stack_argument_snapshot.items())
            assert self.required is None and self.rendered is None and not self.fs_calls and not self.calls and not self.helper_calls
            assert {self.names[pc] for pc in self.visited}=={'LogFunctionImpl'}
            row=dict(schema='A23-quiet-logger-profile-1',observed_user_stack_bytes=self.entry_sp-self.minimum_sp,
                stack_restored=True,callee_saved_restored=True,stack_arguments_preserved=True,
                fs_calls=[],helper_calls=[],executed_function_names=['LogFunctionImpl'],instruction_count=len(self.visited),
                trace_sha256=hashlib.sha256(json.dumps(self.visited,separators=(',',':')).encode()).hexdigest(),
                actual_arm_executed=False,whole_thread_stack_verified=False,formatter_state_reinjected=False)
        assert len(self.atomic_reads)==1 and self.atomic_reads[0]['value']==int(self.quiet)
        row.update(quiet=self.quiet,atomic_reads=self.atomic_reads,
            acquire_byte_value_injected=True,memory_order_and_scheduler_executed=False,
            valid_stack_and_abi_assumed=True,full_symbolic_proof=False)
        return row


class JoinWaitMachine(HandleWaitMachine):
    """Actual infinite-timeout waitHandles prefix, injected kernel returns."""
    def __init__(self,text,results=(0,)):
        super().__init__(text,count=1,types=(0,),timeout=(1<<64)-1,results=results)
        self.allowed=('waitHandles','svcWaitSynchronization')
        self.instructions={p:(op,arg,name) for name in self.allowed for p,op,arg in self.functions[name][1]['instructions']}
        self.pc=self.functions['waitHandles'][0]
        self.store(0x200000,101,4)
        self.saved_registers={f'x{i}':0xa0000000+i for i in range(19,30)}
        for r,value in self.saved_registers.items():self.put(r,value)

    def run(self,budget=100000):
        row=super().run(budget)
        if any(self.get(r)!=value for r,value in self.saved_registers.items()):raise ValueError('join callee-saved register drift')
        row['callee_saved_restored']=True
        return row


def main_handoff_certificate(functions):
    """Check dominance plus the two join-result data dependencies in new main."""
    f=next(f for f in functions.values() if 'main' in f['aliases'])
    code={pc:(op,arg) for pc,op,arg in f['instructions']}
    successors={};predecessors={pc:set() for pc in code}
    for pc,(op,arg) in code.items():
        match=re.search(r'\b([0-9a-f]+) <',arg);target=int(match[1],16) if match else None
        if op in ('ret','br','udf','brk','hlt'):nxt=[]
        elif op=='b':nxt=[target] if target in code else []
        else:
            nxt=[pc+4] if pc+4 in code else []
            if op.startswith('b.') or op in ('cbz','cbnz','tbz','tbnz'):
                if target not in code:raise ValueError('main conditional branch outside function')
                nxt.append(target)
        successors[pc]=nxt
        for p in nxt:predecessors[p].add(pc)
    reachable=set();pending=[f['start']]
    while pending:
        pc=pending.pop()
        if pc in reachable:continue
        reachable.add(pc);pending.extend(successors[pc])
    dom={pc:({pc} if pc==f['start'] else set(reachable)) for pc in reachable}
    changed=True
    while changed:
        changed=False
        for pc in sorted(reachable-{f['start']}):
            parents=predecessors[pc]&reachable
            value={pc}|set.intersection(*(dom[p] for p in parents))
            if value!=dom[pc]:dom[pc]=value;changed=True
    def sites(name):return [pc for pc,(op,arg) in code.items() if op=='bl' and arg.endswith('<'+name+'>')]
    setters=sites('CoreSetDiagnosticQuiet');launches=sites('LaunchThread');joins=sites('threadWaitForExit')
    if len(setters)!=2 or len(launches)!=2 or len(joins)!=2:raise ValueError('main handoff call count drift')
    enabled,disabled=sorted(setters);first,second=sorted(joins)
    if code[enabled-4]!=('mov','w0, #0x1') or code[disabled-8]!=('mov','w0, #0x0'):
        raise ValueError('quiet argument value drift')
    if not all(enabled in dom[p] for p in launches):raise ValueError('quiet enable does not dominate launches')
    if not all(p in dom[disabled] for p in joins):raise ValueError('quiet clear not dominated by both joins')
    if code[first+4]!=('mov','w20, w0') or code[second+4]!=('mov','w21, w0'):
        raise ValueError('join result register drift')
    ors=[pc for pc,(op,arg) in code.items() if (op,arg)==('orr','w0, w20, w21')]
    if len(ors)!=1:raise ValueError('join result OR drift')
    check=ors[0]+4;op,arg=code[check];match=re.fullmatch(r'w0, ([0-9a-f]+) <main\+0x[0-9a-f]+>',arg)
    if op!='cbz' or not match:raise ValueError('successful join branch drift')
    good=int(match[1],16)
    if good!=disabled-8 or check not in dom[disabled]:raise ValueError('join success target drift')
    for register,at,expected in (('x0',enabled,{enabled-4}),('x0',disabled,{disabled-8}),
                                 ('x20',ors[0],{first+4}),('x21',ors[0],{second+4}),
                                 ('x0',first+4,{first}),('x0',second+4,{second})):
        if origins(f,register).get(at)!=expected:raise ValueError('quiet/join value reaching-definition drift')
    # From a failed combined result, no CFG path can reach the quiet clear.
    bad_reachable=set();pending=[check+4]
    while pending:
        pc=pending.pop()
        if pc in bad_reachable:continue
        bad_reachable.add(pc);pending.extend(successors[pc])
    if disabled in bad_reachable:raise ValueError('failed join can clear quiet flag')
    saves=sites('Ep0CandidateSaveCapture')+sites('Ep0CandidateSaveDiagnostic')+sites('Ep0ExecutionSaveJoined')
    if len(saves)!=4 or not all(disabled in dom[p] for p in saves):raise ValueError('joined save gate drift')
    return dict(schema='A23-quiet-main-handoff-1',main_address=f['start'],quiet_enable_at=enabled,quiet_disable_at=disabled,
        worker_launch_sites=launches,join_sites=joins,join_success_branch=check,joined_save_sites=saves,
        quiet_enable_dominates_worker_launches=True,both_joins_dominate_quiet_clear=True,
        failed_join_cannot_reach_quiet_clear=True,quiet_clear_dominates_joined_saves=True,
        setter_arguments_and_join_results_have_checked_reaching_definitions=True,
        source_level_thread_contract_and_valid_memory_assumed=True,unknown_writers_or_memory_corruption_excluded=True,
        actual_scheduler_or_device_executed=False,termination_time_bound_verified=False)
