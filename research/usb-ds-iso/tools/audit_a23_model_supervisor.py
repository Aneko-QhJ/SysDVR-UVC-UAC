"""Native context helper and bounded supervisor models only; no USB/SD/SDK."""
import argparse,copy,json,os,shutil,subprocess,tempfile,time
from pathlib import Path
import build_a23_supervisor_model as b
import a23_model_supervisor as s
v=s.v;a=v.a;f=v.f;w=b.w

def run_until(m,condition,seconds=6):
    end=time.monotonic()+seconds;maximum=0
    while not condition():
        f.require(time.monotonic()<end,'model test observation bound exceeded');begin=time.monotonic();m.poll(0.01);maximum=max(maximum,time.monotonic()-begin)
    return maximum

def models(build,root):
    root.mkdir();out={};bounds={};retained={}
    for name in v.MODES+('owner-change','parent-change','ambient-environment'):
        mode=name if name in v.MODES else 'hold-after' if name in ('owner-change','parent-change') else 'normal';m=s.ModelSupervisor(root/name,build,mode,budget_ns=200000000 if mode=='hold-before' else 1500000000 if mode=='hold-after' else 3000000000)
        if name=='ambient-environment':old=os.environ.get('PYTHONPATH');os.environ['PYTHONPATH']='A23-ambient-value-must-not-be-inherited'
        try:m.start()
        finally:
            if name=='ambient-environment':
                if old is None:os.environ.pop('PYTHONPATH',None)
                else:os.environ['PYTHONPATH']=old
        if mode in ('hold-before','hold-after'):
            bounds[name]=run_until(m,lambda:m.timed_out if mode=='hold-before' else m.hello)
            if name=='owner-change':(m.root/'OWNER').write_bytes(b'foreign owner\n');m.poll(0)
            elif name=='parent-change':
                original=s.identity;s.identity=lambda:{**original(),'uid':999999}
                try:m.poll(0)
                finally:s.identity=original
            else:bounds[name]=max(bounds[name],run_until(m,lambda:m.timed_out))
            f.require(m.process.poll() is None and not m.finish() and not (m.root/'COMMITTED').exists(),'running child sealed');f.require(s.ACTIVE.get(m.handoff['nonce']) is m,'unresolved child handle lost');retained[name]=True
            try:s.ModelSupervisor(m.root,build)
            except ValueError:pass
            else:raise ValueError('unresolved model resumed')
            # Explicit fixture action only. Supervisor itself never sends a
            # signal or an automatic command after deadline/failure.
            m.process.stdin.write(b'x');m.process.stdin.flush()
        bounds[name]=max(bounds.get(name,0),run_until(m,lambda:bool(m.settled_ns)));f.require(m.finish(),'exited model not finalized');out[name]=v.analyze(m.root,build)
        try:m.start()
        except ValueError:pass
        else:raise ValueError('model launched twice')
    f.require({n for n,r in out.items() if r['supervision_complete']}=={'normal','ambient-environment'},'supervision classification differs');f.require(not s.ACTIVE,'resolved child handle leaked');return dict(matrix=out,maximum_poll_seconds=max(bounds.values()),retained_unresolved=retained)

def reseal(root):
    (root/'SHA256SUMS').unlink();(root/'COMMITTED').unlink();a.seal(root)

def negatives(normal,late,build,root):
    root.mkdir();out={}
    for name in ('bool-pid','parent-link','claims-acquire','forged-success','nonce','owner','extra-empty','missing-commit','deadline-restored'):
        target=root/name;shutil.copytree(late if name=='deadline-restored' else normal,target)
        if name in ('bool-pid','claims-acquire','forged-success','deadline-restored'):
            p=target/'result.json';r=f.parse(a.read(p))
            if name=='bool-pid':r['child_pid']=True
            elif name=='claims-acquire':r['acquisition_permitted']=True
            elif name=='forged-success':r['supervision_complete']=False
            else:r.update(timed_out=False,failure_reasons=[],supervision_complete=True,hello_consistent=True)
            p.write_bytes(f.encode(r));reseal(target)
        elif name in ('parent-link','nonce'):
            p=target/'handoff-original.json';h=f.parse(a.read(p))
            if name=='parent-link':h['parent']['pid']=1
            else:h['nonce']='0'*64
            p.write_bytes(f.encode(h));reseal(target)
        elif name=='owner':(target/'OWNER').write_bytes(b'foreign');reseal(target)
        elif name=='extra-empty':(target/'unexpected').mkdir()
        elif name=='missing-commit':(target/'COMMITTED').unlink()
        try:v.analyze(target,build)
        except (ValueError,OSError,KeyError,TypeError) as e:out[name]=str(e)
        else:raise ValueError('bad supervisor archive accepted '+name)
    return out

def admissions(build,root):
    root.mkdir();out={}
    for name in ('handoff-before-launch','binary-before-launch','spawn-error','bad-mode','bool-budget'):
        target=root/name;current=build
        if name=='binary-before-launch':current=root/'build-copy';shutil.copytree(build,current)
        if name in ('bad-mode','bool-budget'):
            try:s.ModelSupervisor(target,current,mode='--acquire' if name=='bad-mode' else 'normal',budget_ns=True if name=='bool-budget' else 3000000000)
            except ValueError:out[name]=dict(rejected=True,output_created=target.exists())
            else:raise ValueError('invalid admission accepted')
            continue
        m=s.ModelSupervisor(target,current)
        if name=='handoff-before-launch':(target/'handoff.json').write_bytes(b'{')
        if name=='binary-before-launch':(current/'model-child').write_bytes(b'changed')
        original=s.subprocess.Popen
        def error(*args,**kwargs):raise OSError('injected spawn failure')
        if name=='spawn-error':s.subprocess.Popen=error
        try:
            try:m.start()
            except (ValueError,OSError):pass
            else:raise ValueError('bad launch admitted')
        finally:s.subprocess.Popen=original
        f.require(m.process is None and (target/'launch-attempt').exists() and not m.finish(),'failed launch not retained')
        try:m.start()
        except ValueError:pass
        else:raise ValueError('failed launch retried')
        m.selector.close();out[name]=dict(rejected=True,attempt_retained=True,process_created=False,committed=(target/'COMMITTED').exists())
    # This intentionally invalid compile copy is disposable model input. Its
    # changed binary and receipt are enough to reproduce the failure.
    copyroot=root/'build-copy'
    if copyroot.exists():
        (root/'changed-model-child.bin').write_bytes(a.read(copyroot/'model-child'));shutil.rmtree(copyroot)
    return out

def run(output):
    output=w.canonical(output);f.require(not output.exists(),'new supervisor review required');output.mkdir(mode=0o700);before=b.sources();b.build(output/'build')
    tmp=Path(tempfile.mkdtemp(prefix='a23-supervisor-',dir='/private/tmp'));w.write(output/'scratch-reference.json',dict(directory=str(tmp),on_failure='retain closed or unresolved model evidence without automatic cleanup'))
    rows=models(output/'build',tmp/'models');bad=negatives(tmp/'models/normal',tmp/'models/hold-before',output/'build',tmp/'negative');shutil.copytree(tmp/'models',output/'models');shutil.copytree(tmp/'negative',output/'negative');admission=admissions(output/'build',tmp/'admission');shutil.copytree(tmp/'admission',output/'admission');f.require(not s.ACTIVE,'cannot clean unresolved test scratch');shutil.rmtree(tmp)
    f.require(before==b.sources(),'sources changed during supervisor audit');report=dict(schema='A23-supervisor-audit-1',passed=True,source_count=len(before),source_hashes=before,prior_sources_unchanged=372,model_cases=len(rows['matrix']),negative_archives=bad,admission=admission,**rows,sanitizers=['address','undefined'],usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,production_supervisor_implemented=False,**v.FALSE)
    w.write(output/'audit.json',report);w.b.seal(output);w.card.seal_verify(output);return dict(reference=w.reference(output),sources=len(before),model_cases=len(rows['matrix']),negative_archives=len(bad),passed=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
