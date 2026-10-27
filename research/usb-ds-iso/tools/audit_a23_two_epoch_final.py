"""Compile frozen injected operations; collect only after child exit; no hardware."""
import argparse,copy,json,os,shutil,subprocess,sys,tempfile,types
from pathlib import Path
import audit_a23_scope_verifier as old
import a23_final_archive as a
import collect_a23_two_epoch_final as collector
w=old.w;f=a.f
PARENT=w.A/'A23-verifier-closeout-20261019';PARENT_SUM='46796c6f4b238a9fc4c7c581630d9e5d888dd0c361d57461854680763dfb3575'
NEW=('tools/a23_final_archive.py','tools/collect_a23_two_epoch_final.py','tools/analyze_a23_two_epoch_final.py','tools/audit_a23_two_epoch_final.py','tests/test_a23_two_epoch_final.py')

def sources():
    w.card.seal_verify(PARENT);f.require(f.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'parent seal differs');c=w.load(PARENT/'closeout.json');out=old.builder.authority.sources();f.require(out==c['source_hashes'] and len(out)==367,'prior367 drift')
    for n,h in c['protected_sha256'].items():f.require(f.sha(w.plain(Path(n)))==h,'protected drift')
    f.require(c['actual_ledger_sha256']=={p.name:f.sha(w.plain(p)) for p in w.LEDGER.iterdir() if p.is_file()},'actual ledger drift')
    for n in NEW:key='research/usb-ds-iso/'+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))

def reseal(root):
    for n in ('SHA256SUMS','COMMITTED'):
        if (root/n).exists():(root/n).unlink()
    a.seal(root)

def negatives(normal,build,root):
    root.mkdir();out={}
    for name in ('missing-commit','raw-short','unknown-file','extra-empty-directory','bool-exit','claims-cleanup','forged-analysis','wrong-report','partial-consumed','duplicate-json','wrong-build-reference','numeric-static-exit','rehashed-false-report'):
        target=root/name;shutil.copytree(normal,target)
        if name=='missing-commit':(target/'COMMITTED').unlink()
        elif name=='raw-short':p=target/'inputs/host/epoch-0/raw.bin';p.write_bytes(p.read_bytes()[:-1])
        elif name=='unknown-file':(target/'unexpected').write_bytes(b'x')
        elif name=='extra-empty-directory':(target/'unexpected').mkdir()
        elif name in ('bool-exit','claims-cleanup','wrong-build-reference','numeric-static-exit'):
            p=target/'collection.json';m=f.parse(a.read(p))
            if name=='bool-exit':m['observation']['returncode']=False
            elif name=='claims-cleanup':m['cleanup_authorized']=True
            elif name=='wrong-build-reference':m['build_reference']['receiver_sha256']='0'*64
            else:m.update(origin='supplied_static_model',observation=dict(mode='supplied_static_model',child_exited=0,returncode=None,binary_sha256=None))
            p.write_bytes(f.encode(m));reseal(target)
        elif name=='rehashed-false-report':
            m=f.parse(a.read(target/'collection.json'));row=f.parse(a.read(target/'report.json'));row['verifier']['failed']=True;raw=f.encode(row);(target/'report.json').write_bytes(raw);(target/'process.stdout').write_bytes(raw);m['report_sha256']=f.sha(raw);(target/'collection.json').write_bytes(f.encode(m));reseal(target)
        elif name=='forged-analysis':p=target/'analysis.json';r=f.parse(a.read(p));r['hardware_verified']=True;p.write_bytes(f.encode(r));reseal(target)
        elif name=='wrong-report':p=target/'report.json';p.write_bytes(b'{}');reseal(target)
        elif name=='partial-consumed':p=next((target/'inputs/namespace/jobs').glob('*/consumed.json'));p.write_bytes(b'{');reseal(target)
        elif name=='duplicate-json':p=target/'collection.json';p.write_bytes(b'{"origin":"observed_model_child_exit",'+p.read_bytes()[1:]);reseal(target)
        try:a.analyze(target,build)
        except (ValueError,OSError,KeyError,TypeError) as e:out[name]=str(e).replace(str(target),'<archive>')
        else:raise ValueError('bad final archive accepted '+name)
    return out

def lifecycle_tests(root,source,build):
    root.mkdir();out={};script=root/'hold.py';script.write_text('import sys\nsys.stdin.buffer.read(1)\n')
    child=subprocess.Popen([sys.executable,str(script)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);target=root/'running';digest=f.sha(a.read(Path(sys.executable).resolve()))
    try:
        try:collector.freeze(source,build,target,process=child,binary_sha256=digest)
        except ValueError as e:out['running']=dict(rejected=True,reason=str(e),output_created=target.exists())
        else:raise ValueError('running producer collected')
    finally:child.communicate(b'x',timeout=10)
    f.require(not target.exists(),'running producer created output')
    try:collector.freeze(source,build,root/'unknown')
    except ValueError as e:out['unknown']=str(e)
    else:raise ValueError('unknown producer collected')
    for name in ('failed-write','source-drift','new-empty-directory'):
        src=root/(name+'-source');shutil.copytree(source,src);dest=root/name
        def fault(stage):
            if name=='failed-write' and stage=='reserved':raise OSError('injected write failure')
            if stage=='before_commit':
                if name=='source-drift':(src/'config.json').write_bytes(b'{')
                if name=='new-empty-directory':(src/'unexpected-empty').mkdir()
        try:collector.freeze(src,build,dest,static_model=True,checkpoint=fault)
        except (ValueError,OSError) as e:out[name]=dict(reason=str(e),attempt_retained=(dest/'ATTEMPT').exists(),committed=(dest/'COMMITTED').exists())
        else:raise ValueError('failed collection committed')
        f.require((dest/'ATTEMPT').exists() and not (dest/'COMMITTED').exists(),'failure lost attempt or committed');before=a.snapshot(dest)
        try:collector.freeze(src,build,dest,static_model=True)
        except ValueError:pass
        else:raise ValueError('partial collection retried')
        f.require(before==a.snapshot(dest),'retry changed failed collection')
    failed=root/'fail.py';failed.write_text('import sys\nsys.stdout.buffer.write(b\"partial bytes\")\nsys.stderr.write(\"injected exit\")\nraise SystemExit(3)\n');cmd=[str(Path(sys.executable).resolve()),str(failed)];p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE);stdout,stderr=p.communicate(timeout=10);r=collector.freeze(source,build,root/'exited-failed',process=p,binary_sha256=f.sha(a.read(Path(cmd[0]))),stdout=stdout,stderr=stderr);f.require(not r['analysis']['supplied_model_chain_complete'] and a.read(root/'exited-failed/report.json')==b'partial bytes','failed process bytes lost');out['exited-failed']=r
    target=root/'race';cmd=[sys.executable,'-B',str(Path(collector.__file__).resolve()),'--static-model',str(source),'--build',str(build),'--output',str(target)];processes=[subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)];codes=[]
    for p in processes:stdout,stderr=p.communicate(timeout=30);f.require(not stderr,'collection race stderr');codes.append(p.returncode)
    f.require(sorted(codes)==[0,2] and a.analyze(target,build)['analysis']['supplied_model_chain_complete'],'collection race had wrong winners');out['race_exitcodes']=codes
    return out

def exercise(build,binary,inputs,scope,history,output,scratch,collections):
    collections.mkdir();observed={};digest=f.sha(a.read(binary))
    def run(cmd,**kwargs):
        f.require(cmd[0]==str(binary) and len(cmd)==2,'only frozen injected model allowed');child=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);stdout,stderr=child.communicate(timeout=kwargs.get('timeout',60));case=Path(cmd[1]).parent
        result=collector.freeze(case,build,collections/case.name,process=child,binary_sha256=digest,stdout=stdout.encode(),stderr=stderr.encode());observed[case.name]=result
        return subprocess.CompletedProcess(cmd,child.returncode,stdout,stderr)
    globals_=dict(old.exercise.__globals__,subprocess=types.SimpleNamespace(run=run));model=types.FunctionType(old.exercise.__code__,globals_);rows=model(build,binary,inputs,scope,history,output,scratch)
    complete={n for n,r in observed.items() if r['analysis']['supplied_model_chain_complete']};f.require(complete=={'normal','queued-delay'} and len(observed)==28,'final classification differs');return rows,observed

def run(output):
    output=w.canonical(output);f.require(not output.exists(),'new review required');source=sources();parent=w.load(PARENT/'closeout.json');prior=Path(parent['references']['review']['directory']);w.card.seal_verify(prior);output.mkdir(mode=0o700)
    for n,h in source.items():raw=w.plain(w.b.REPO/n,2*1024*1024);f.require(f.sha(raw)==h,'source drift');w.card.put(output,'source/'+n,raw)
    shutil.copytree(prior/'build',output/'build');scope,ref=a.build_scope(output/'build');f.require(scope==f.load(prior/'scope.json'),'independent build check differs');history=f.load(prior/'history.json');w.write(output/'history.json',history);old.generate(output/'build',output/'native-work')
    cmd=old.builder.compile_command(output/'native-work',output/'native-test',True);r=subprocess.run(cmd,capture_output=True,text=True);w.card.put(output,'compile.log',(r.stdout+r.stderr).encode());f.require(r.returncode==0,'frozen model compile failed')
    w.card.put(output,'generated-test.m',a.read(output/'native-work/source/research/usb-ds-iso/tests/generated_scope_verifier_test.m'));shutil.rmtree(output/'native-work') # Unsealed disposable compile copy; frozen build retains every input.
    with tempfile.TemporaryDirectory(prefix='a23-final-',dir='/private/tmp') as tmp:
        tmp=Path(tmp);old.template(output/'build',tmp/'inputs');rows,collected=exercise(output/'build',output/'native-test',tmp/'inputs',scope,history,tmp/'cases',tmp,output/'collections');bad=negatives(output/'collections/normal',output/'build',output/'negative');life=lifecycle_tests(tmp/'lifecycle',tmp/'cases/normal',output/'build');shutil.copytree(tmp/'lifecycle',output/'lifecycle')
        # Existing context/identity/binding mixes are preserved and classified.
        mixed={}
        for p in sorted((prior/'negative').iterdir()):mixed[p.name]=collector.freeze(p,output/'build',output/('mixed-'+p.name),static_model=True)
        f.require(all(not r['analysis']['supplied_model_chain_complete'] for r in mixed.values()),'mixed chain completed')
    f.require(sources()==source,'source drift after audit')
    report=dict(schema='A23-final-offline-audit-1',passed=True,source_count=len(source),source_hashes=source,prior_sources_unchanged=367,native_cases=28,accepted=2,incomplete=26,collections=collected,combined_mixes=mixed,negative_archives=bad,lifecycle=life,build_reference=ref,compiler_command=cmd,native_inputs=list(old.builder.NATIVE),sanitizers=['address','undefined'],usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,acquisition_mode_implemented=False,**a.FALSE)
    w.write(output/'audit.json',report);w.b.seal(output);w.card.seal_verify(output);return dict(reference=w.reference(output),sources=len(source),native_cases=28,negative_archives=len(bad),passed=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
