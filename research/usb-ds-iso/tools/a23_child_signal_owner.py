"""Offline ready-gated restoration of the child's original thread signal mask."""
from pathlib import Path
import json
import os
import secrets
import select
import signal
import sys
import time

from a23_sigint_guard_owner import SamplerOwner as PreviousOwner
import a23_terminal_deadline as prior

LIMIT=2048
MODES={'normal','before_reset','after_reset','stall_after_ready','stall_before_ready','bad_token',
       'bad_mask','bad_handler','partial_ready','oversized_ready','exit_before_ready','reset_error'}


def validate_report(policy,report):
    require=prior.require
    require(type(report) is dict and set(report)=={'schema','launch_token','policy_sha256','mask_before','mask_after',
        'sigint_before','sigterm_before','sigint_after','sigterm_after','pending_sigint_before_reset'},'child_ready_fields')
    require(report['schema']=='A23-child-signal-ready-1' and report['launch_token']==policy['launch_token'] and report['policy_sha256']==prior.intake.recovery.sha(prior.encode(policy)),'child_ready_binding')
    for key in ('mask_before','mask_after'):
        values=report[key];require(type(values) is list and all(type(v) is int for v in values) and values==sorted(set(values)),'child_ready_mask_type')
    require(report['mask_before']==sorted(set(policy['target_mask'])|{int(signal.SIGINT)}) and report['mask_after']==policy['target_mask'],'child_ready_mask')
    require(report['sigint_after']=='default_int_handler' and report['sigterm_after']=='SIG_DFL','child_ready_handlers')
    require(report['sigint_before'] in ('default_int_handler','SIG_DFL','SIG_IGN','other') and report['sigterm_before'] in ('default_int_handler','SIG_DFL','SIG_IGN','other') and type(report['pending_sigint_before_reset']) is bool,'child_ready_initial_state')
    return report


class SamplerOwner(PreviousOwner):
    def __init__(self,*,startup_timeout=0.8,_fixture_mode='normal',_startup_checkpoint=None,**kwargs):
        super().__init__(**kwargs)
        prior.require(type(startup_timeout) in (float,int) and 0<startup_timeout<=30,'child_startup_budget')
        prior.require(_fixture_mode in MODES,'child_fixture_mode')
        self.startup_timeout=startup_timeout;self.fixture_mode=_fixture_mode
        self.startup_checkpoint=_startup_checkpoint or (lambda phase,child:True)
        self.policy=None;self.policy_report=None;self.policy_wire=b''
        self._policy_fds=[];self._policy_fd_uncertain=0;self._startup_deadline=None
        self._slot.state.update(child_policy_confirmed=False,child_ready_deadline_expired=False)

    def observation(self):
        state=super().observation();state.update(policy_fd_count=len(self._policy_fds),policy_fd_close_uncertain=self._policy_fd_uncertain)
        if state['owns_runtime_slot'] and self._policy_fd_uncertain:state['owner_status']='policy_fd_unresolved'
        return state

    def _close_fd(self,fd):
        if fd not in self._policy_fds:return
        self._policy_fds.remove(fd)  # Never retry an uncertain numeric FD after close failure.
        try:os.close(fd)
        except OSError as exc:
            self._policy_fd_uncertain+=1;self._error(exc,'child_policy_fd_close',cleanup=True)
            raise

    def _read_ready(self,fd,deadline):
        buffer=bytearray();total=0
        for _ in range(128):
            left=deadline-time.monotonic()
            if left<=0:
                self._slot.state['child_ready_deadline_expired']=True
                raise prior.Rejected('child_ready_deadline')
            ready,_,_=select.select([fd],[],[],left)
            if not ready:
                self._slot.state['child_ready_deadline_expired']=True
                raise prior.Rejected('child_ready_deadline')
            try:block=os.read(fd,min(4096,LIMIT+1-len(buffer)))
            except InterruptedError:continue
            if not block:raise prior.Rejected('child_ready_eof')
            buffer.extend(block);total+=len(block);self.policy_wire+=block
            prior.require(len(buffer)<=LIMIT and total<=8192,'child_ready_limit')
            if b'\n' not in buffer:continue
            raw,_,tail=buffer.partition(b'\n');prior.require(not tail,'child_ready_extra_bytes');buffer.clear()
            value=json.loads(raw);prior.require(prior.encode(value)==raw,'child_ready_encoding')
            if type(value) is dict and set(value)=={'checkpoint'}:
                phase=value['checkpoint']
                prior.require(self.fixture_mode in ('before_reset','after_reset') and phase==self.fixture_mode,'child_ready_checkpoint')
                if self.startup_checkpoint(phase,self._slot.child) is not False:
                    prior.require(os.write(self._slot.child.stdin.fileno(),b'R')==1,'child_gate_progress')
                    self.startup_checkpoint('gate_released_'+phase,self._slot.child)
                continue
            self.policy_report=validate_report(self.policy,value)
            self._slot.state['child_policy_confirmed']=True
            self.startup_checkpoint('ready_validated',self._slot.child)
            prior.require(self._slot.child.returncode is None,'child_policy_child_exited')
            return
        raise prior.Rejected('child_ready_read_budget')

    def _create(self,command,**kwargs):
        expected=[sys.executable,'-B',str(Path(prior.__file__).with_name('a23_terminal_deadline_worker.py'))]
        prior.require(command==expected,'fixed_sampler_command_required')
        target=sorted(int(v) for v in signal.pthread_sigmask(signal.SIG_BLOCK,set()))
        self.policy=dict(schema='A23-child-signal-policy-1',launch_token=secrets.token_hex(16),target_mask=target,mode=self.fixture_mode)
        reader,writer=os.pipe();self._policy_fds.extend((reader,writer))
        kwargs['pass_fds']=(*kwargs.get('pass_fds',()),writer)
        bootstrap=Path(__file__).with_name('a23_child_signal_bootstrap.py')
        deadline=min(self._startup_deadline or float('inf'),time.monotonic()+self.startup_timeout)
        primary=None;child=None
        try:child=super()._create([sys.executable,'-B',str(bootstrap),str(writer),prior.encode(self.policy).decode()],**kwargs)
        except BaseException as exc:primary=exc
        try:self._close_fd(writer)
        except BaseException as exc:
            if primary is None:primary=exc
        if primary is not None:raise primary
        self._read_ready(reader,deadline);self._close_fd(reader)
        return child

    def _cleanup(self,checkpoint):
        primary=None
        try:primary=super()._cleanup(checkpoint)
        finally:
            for fd in list(self._policy_fds):
                try:self._close_fd(fd)
                except OSError:pass
        return primary

    def capture(self,*args,timeout=2.0,**kwargs):
        prior.require(type(timeout) in (float,int) and 0<timeout<=30,'time_budget')
        self._startup_deadline=time.monotonic()+timeout
        return super().capture(*args,timeout=timeout,**kwargs)
