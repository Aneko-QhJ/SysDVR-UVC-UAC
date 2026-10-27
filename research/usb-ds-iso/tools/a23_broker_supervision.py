"""Separate fixed hello/execution deadlines for the fake-SDK model broker.

This new receipt format does not extend or reinterpret the frozen context-only
supervisor's 5-second contract. No deadline is renewed after launch.
"""
import os,time
import a23_model_supervisor as old
v=old.v;a=v.a;f=v.f;ACTIVE=old.ACTIVE;subprocess=old.subprocess
build_info=v.build_info
FALSE=v.FALSE

class ModelSupervisor(old.ModelSupervisor):
    def __init__(self,root,build,mode='normal',budget_ns=30000000000):
        f.require(type(budget_ns) is int and 10000000<=budget_ns<=30000000000,'bounded broker execution budget required');super().__init__(root,build,mode,budget_ns=min(budget_ns,5000000000));self.execution_budget=budget_ns;self.hello_budget=min(budget_ns,5000000000);self.hello_timed_out=False
        self.handoff.update(schema='A23-broker-supervision-handoff-1',execution_budget_ns=budget_ns,hello_budget_ns=self.hello_budget);p=self.root/'handoff.new.tmp';f.exclusive(p,f.encode(self.handoff));os.replace(p,self.root/'handoff.json');f.sync(self.root)
    def start(self):
        super().start();self.deadline=self.begin_ns+self.execution_budget;self.hello_deadline=self.begin_ns+self.hello_budget
    def poll(self,wait_seconds=0.01):
        if not self.settled_ns and not self.hello and time.monotonic_ns()>=self.hello_deadline:self.hello_timed_out=True;self.fail('hello_deadline_expired')
        done=super().poll(wait_seconds)
        if self.hello_ns>=self.hello_deadline or (not self.hello_ns and self.settled_ns>=self.hello_deadline):
            self.hello_timed_out=True;self.fail('hello_deadline_expired')
            if self.hello_ns>=self.hello_deadline:self.hello=False;self.policy=False
        return done
    def result(self):
        r=super().result();r.update(schema='A23-broker-supervision-result-1',hello_deadline_ns=self.hello_deadline,hello_timed_out=self.hello_timed_out);return r

def analyze(root,build):
    files,dirs,_=a.sealed(root);f.require(set(files)=={'OWNER','OWNER-original','handoff.json','handoff-original.json','launch-attempt','result.json','stdout.bin','stderr.bin'} and dirs==['scratch'],'broker supervision inventory differs');h=f.parse(files['handoff-original.json']);r=f.parse(files['result.json']);ref=build_info(build)
    f.require(set(h)=={'schema','nonce','parent','build','environment_sha256','model_only','inherited_environment','execution_budget_ns','hello_budget_ns'} and h['schema']=='A23-broker-supervision-handoff-1' and h['build']==ref and f.hex64(h['nonce']) and f.hex64(h['environment_sha256']),'broker supervision handoff differs');f.require(h['model_only'] is True and h['inherited_environment'] is False,'broker supervision mode differs')
    f.require(type(h['execution_budget_ns']) is int and 10000000<=h['execution_budget_ns']<=30000000000 and type(h['hello_budget_ns']) is int and h['hello_budget_ns']==min(5000000000,h['execution_budget_ns']),'broker supervision budgets differ')
    f.require(set(h['parent'])=={'pid','ppid','uid','euid','gid','egid'} and all(type(n) is int and n>=0 for n in h['parent'].values()) and h['parent']['pid']>0,'broker parent identity differs');f.require(files['OWNER-original']==(h['nonce']+'\n').encode() and files['launch-attempt']==b'one model launch attempt\n','broker supervision owner differs')
    expected={'schema','launch_begin_ns','deadline_ns','hello_deadline_ns','hello_observed_ns','settled_ns','child_pid','binary_path','producer_exited','returncode','timed_out','hello_timed_out','truncated','hello_consistent','child_execution_policy_pass','supervision_complete','stdout_eof','stderr_eof','failure_reasons',*FALSE}
    f.require(set(r)==expected and r['schema']=='A23-broker-supervision-result-1' and all(r[k] is False for k in FALSE),'broker supervision result/authority differs')
    for k in ('producer_exited','timed_out','hello_timed_out','truncated','hello_consistent','child_execution_policy_pass','supervision_complete','stdout_eof','stderr_eof'):f.require(type(r[k]) is bool,'broker supervision flag differs')
    f.require(r['producer_exited'] is True and type(r['child_pid']) is int and r['child_pid']>0 and type(r['returncode']) is int and type(r['binary_path']) is str,'broker supervision producer differs')
    for k in ('launch_begin_ns','deadline_ns','hello_deadline_ns','hello_observed_ns','settled_ns'):f.require(type(r[k]) is int and r[k]>=0,'broker supervision clock differs')
    f.require(0<r['launch_begin_ns']<=r['settled_ns'] and r['deadline_ns']-r['launch_begin_ns']==h['execution_budget_ns'] and r['hello_deadline_ns']-r['launch_begin_ns']==h['hello_budget_ns'],'broker supervision fixed deadlines differ')
    f.require(r['timed_out'] is (r['settled_ns']>=r['deadline_ns']),'broker execution deadline verdict differs');hello_late=r['hello_observed_ns']>=r['hello_deadline_ns'] or (not r['hello_observed_ns'] and r['settled_ns']>=r['hello_deadline_ns']);f.require(r['hello_timed_out'] is bool(hello_late),'broker hello deadline verdict differs')
    f.require(type(r['failure_reasons']) is list and all(type(n) is str for n in r['failure_reasons']) and len(set(r['failure_reasons']))==len(r['failure_reasons']),'broker supervision reasons differ');f.require(len(files['stdout.bin'])<=4096 and len(files['stderr.bin'])<=256,'broker supervision stream bound differs');lines=files['stdout.bin'].splitlines(keepends=True);valid=False;policy=False
    if lines and lines[0].endswith(b'\n'):
        try:policy=v.link(f.parse(lines[0]),h,r['child_pid'],r['binary_path']);valid=True
        except (ValueError,TypeError,KeyError):pass
    if r['hello_consistent']:f.require(valid and r['launch_begin_ns']<=r['hello_observed_ns']<r['hello_deadline_ns'] and r['child_execution_policy_pass']==policy,'broker hello verdict differs')
    complete=len(lines)==1 and valid and r['hello_consistent'] and not r['failure_reasons'] and not r['timed_out'] and not r['hello_timed_out'] and not r['truncated'] and r['returncode']==0 and r['stdout_eof'] and r['stderr_eof']
    if complete:f.require(files['OWNER']==files['OWNER-original'] and files['handoff.json']==files['handoff-original.json'],'complete broker supervision changed')
    f.require(r['supervision_complete'] is complete,'broker supervision verdict differs');return dict(schema='A23-broker-supervision-analysis-1',archive_integrity_valid=True,supervision_complete=complete,hello_consistent=r['hello_consistent'],child_execution_policy_pass=r['child_execution_policy_pass'],timed_out=r['timed_out'],hello_timed_out=r['hello_timed_out'],truncated=r['truncated'],failure_reasons=r['failure_reasons'],**FALSE)
