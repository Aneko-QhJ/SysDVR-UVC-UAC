"""Process interruption and unsafe-input audits; frozen SDK binaries are data only."""
from pathlib import Path
import argparse,copy,json,os,select,shutil,subprocess,sys,tempfile
import build_a23_failure_model as prior
import a23_collection_journal as j
import a23_collection_journal_archive as ar
w=prior.w;a=j.a;f=a.f
PARENT=w.A/'A23-failure-closeout-20261019';PARENT_SUM='63ae8827e42bc3a5e383c93866652e0e81ce6bfbada37f038e22ce944cc85a5d'
NEW=('tools/a23_collection_journal.py','tools/a23_collection_worker.py','tools/a23_collection_journal_archive.py','tools/audit_a23_collection_journal.py','tests/test_a23_collection_journal.py')
CASES=('normal-complete','normal-missing','crash-reserved','crash-final_started','crash-final_frozen','crash-revalidated','crash-completed','error-reserved','source-drift','symlink-input','fifo-input','oversize-report','excess-nodes','hold-reserved')
def sources():
    w.card.seal_verify(PARENT);f.require(f.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'journal parent differs');c=w.load(PARENT/'closeout.json');out=prior.sources();f.require(out==c['source_hashes'] and len(out)==392,'prior392 drift')
    for n,h in c['protected_sha256'].items():f.require(f.sha(w.plain(Path(n)))==h,'protected drift')
    f.require(c['actual_ledger_sha256']=={p.name:f.sha(w.plain(p)) for p in w.LEDGER.iterdir() if p.is_file()},'real ledger drift')
    for n in NEW:key='research/usb-ds-iso/'+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))
def seed(saved,target):
    target.mkdir();shutil.copytree(saved/'supervision',target/'supervision');shutil.copytree(saved/'final/inputs',target/'execution')
    for n in ('plan.json','scope.json','expected-scope.json','control.json','STOP','admission.json','ADMISSION_ATTEMPT'):
        if (saved/n).exists():shutil.copyfile(saved/n,target/n)
def job_for(root,receiver,supervisor,journal,fault,forbidden=None):
    sr=f.load(root/'supervision/result.json');return dict(schema='A23-collection-worker-job-1',root=str(root),receiver=str(receiver),supervisor=str(supervisor),journal=str(journal),child_pid=sr['child_pid'],control_delivery='whole_written',fault=fault,forbidden_path=str(forbidden) if forbidden else None)
def spawn(worker,job):
    path=Path(tempfile.mkdtemp(prefix=job.stem+'-tmp-',dir=str(job.parent)));return subprocess.Popen([str(Path(sys.executable).resolve()),'-B',str(worker),str(job)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,env=dict(LANG='C',LC_ALL='C',PATH='/usr/bin:/bin:/usr/sbin:/sbin',TMPDIR=str(path)))
def finish(process,expected):
    stdout,stderr=process.communicate(timeout=45);f.require(process.returncode==expected and stderr==b'','worker exit/stderr differs '+str((process.returncode,expected,stderr)));return dict(returncode=process.returncode,stdout=stdout.decode(),stderr_bytes=len(stderr))
def exercise(builds,templates,worker,scratch,output):
    output.mkdir();receiver=builds/'receiver-build';supervisor=builds/'supervisor-build';rows={};retained={};lifecycle={};sentinel=scratch/'forbidden-sentinel';sentinel.write_bytes(b'model forbidden file\n')
    for case in CASES:
        root=scratch/(case+'-source');seed(templates/('normal-missing' if case=='normal-missing' else 'normal-complete'),root);journal=scratch/(case+'-journal');fault=case if case.startswith(('crash-','error-')) or case in ('source-drift','hold-reserved') else 'normal'
        if case=='symlink-input':(root/'execution/poison').symlink_to(sentinel)
        if case=='fifo-input':os.mkfifo(root/'execution/poison')
        if case=='oversize-report':
            with (root/'execution/report.json').open('wb') as stream:stream.truncate(1024*1024+1)
        if case=='excess-nodes':
            for i in range(513):(root/'execution'/('extra-%03d'%i)).mkdir()
        job=scratch/(case+'.json');job.write_bytes(f.encode(job_for(root,receiver,supervisor,journal,fault,sentinel)));p=spawn(worker,job)
        if case=='hold-reserved':
            f.require(select.select([p.stdout],[],[],10)[0] and p.stdout.readline()==b'READY\n','worker did not reach held checkpoint')
            try:ar.freeze(journal,receiver,supervisor,output/'running-worker',worker=p)
            except ValueError:lifecycle['running_refused']=not (output/'running-worker').exists()
            else:raise ValueError('running collector frozen')
            f.require(p.poll() is None,'held worker ownership lost');p.stdin.write(b'x');p.stdin.flush()
        expected=73 if case.startswith('crash-') else 2 if case in ('error-reserved','source-drift','symlink-input','fifo-input','oversize-report','excess-nodes') else 0;exitrow=finish(p,expected);before=a.snapshot(journal);marker=a.read(root/j.MARKER);result=ar.freeze(journal,receiver,supervisor,output/case,worker=p);rows[case]=dict(result=result,exit=exitrow)
        f.require(a.snapshot(journal)==before and a.read(root/j.MARKER)==marker,'inspection changed attempt');again=spawn(worker,job);finish(again,2);f.require(a.snapshot(journal)==before and a.read(root/j.MARKER)==marker,'retry changed journal');retained[case]=dict(marker_retained=True,journal_unchanged=True,retry_refused=True)
    f.require({n for n,r in rows.items() if r['result']['analysis']['journal_committed']}=={'normal-complete','normal-missing','hold-reserved'},'journal completion classification differs');f.require({n for n,r in rows.items() if r['result']['analysis']['complete_injected_model_chain']}=={'normal-complete','hold-reserved'},'journal model chain classification differs')
    # An unknown owner does not get a process-exit assertion or an output.
    try:ar.freeze(scratch/'normal-complete-journal',receiver,supervisor,output/'unknown-worker')
    except ValueError:lifecycle['unknown_refused']=not (output/'unknown-worker').exists()
    else:raise ValueError('unknown worker frozen')
    # Competing processes share a single durable source attempt.
    root=scratch/'race-source';seed(templates/'normal-complete',root);journal=scratch/'race-journal';jobs=[]
    for i in range(2):job=scratch/('race-%d.json'%i);job.write_bytes(f.encode(job_for(root,receiver,supervisor,journal,'normal',sentinel)));jobs.append(job)
    processes=[spawn(worker,job) for job in jobs];codes=[]
    for p in processes:
        stdout,stderr=p.communicate(timeout=45);f.require(stderr==b'','race stderr');codes.append(p.returncode)
    f.require(sorted(codes)==[0,2],'attempt race winners differ');winner=processes[codes.index(0)];race=ar.freeze(journal,receiver,supervisor,output/'race',worker=winner);f.require(race['analysis']['complete_injected_model_chain'],'race winner incomplete');lifecycle['race_exitcodes']=codes
    try:ar.freeze(scratch/'normal-complete-journal',receiver,supervisor,output/'unrelated-worker',worker=winner)
    except ValueError:lifecycle['unrelated_worker_refused']=not (output/'unrelated-worker').exists()
    else:raise ValueError('unrelated worker exit linked')
    static=ar.freeze(scratch/'normal-complete-journal',receiver,supervisor,output/'static-journal',static_model=True);lifecycle['static_worker_exit_claimed']=static['observation']['worker_exited'];lifecycle['static_journal_committed']=static['analysis']['journal_committed']
    # A partial attempt marker stays spent without scanning unsafe input.
    root=scratch/'partial-marker-source';seed(templates/'normal-complete',root);(root/j.MARKER).write_bytes(b'{');(root/'execution/poison').symlink_to(sentinel);journal=scratch/'partial-marker-journal';job=scratch/'partial-marker.json';job.write_bytes(f.encode(job_for(root,receiver,supervisor,journal,'normal',sentinel)));p=spawn(worker,job);finish(p,2);f.require(a.read(root/j.MARKER)==b'{' and not journal.exists(),'partial attempt resumed');a.put(output,'partial-marker/SOURCE_ATTEMPT',b'{');lifecycle['partial_marker_retained']=True
    return dict(matrix=rows,retained_attempts=retained,lifecycle=lifecycle)
def reseal(root):
    (root/'SHA256SUMS').unlink();(root/'COMMITTED').unlink();a.seal(root)
def negatives(models,builds,output):
    output.mkdir();out={}
    for name in ('forged-partial-success','claims-acquire','bool-worker-pid','event-chain','source-marker','early-commit','worker-job-binding','missing-commit'):
        target=output/name;shutil.copytree(models/('crash-reserved' if name in ('forged-partial-success','early-commit') else 'normal-complete'),target)
        if name=='forged-partial-success':p=target/'analysis.json';v=f.parse(a.read(p));v['complete_injected_model_chain']=True;p.write_bytes(f.encode(v));reseal(target)
        elif name in ('claims-acquire','bool-worker-pid'):
            p=target/'forensic.json';v=f.parse(a.read(p))
            if name=='claims-acquire':v['acquisition_permitted']=True
            else:v['observation']['pid']=True
            p.write_bytes(f.encode(v));reseal(target)
        elif name in ('event-chain','source-marker'):
            p=target/('journal/events/00.json' if name=='event-chain' else 'journal/SOURCE_ATTEMPT');p.write_bytes(b'{}\n');reseal(target)
        elif name=='worker-job-binding':
            p=target/'worker-job.json';job=f.parse(a.read(p));job['child_pid']=123;p.write_bytes(f.encode(job));meta=f.load(target/'forensic.json');meta['observation']['job_sha256']=f.sha(f.encode(job));(target/'forensic.json').write_bytes(f.encode(meta));reseal(target)
        elif name=='early-commit':
            a.seal(target/'journal');meta=f.load(target/'forensic.json');raw,dirs=a.snapshot(target/'journal');meta['journal_files']=a.inventory(raw);meta['journal_directories']=dirs;(target/'forensic.json').write_bytes(f.encode(meta));reseal(target)
        else:(target/'COMMITTED').unlink()
        try:ar.analyze(target,builds/'receiver-build',builds/'supervisor-build')
        except (ValueError,OSError,KeyError,TypeError) as e:out[name]=str(e)
        else:raise ValueError('forged journal accepted '+name)
    return out

def run(output):
    output=w.canonical(output);f.require(not output.exists(),'new journal review required');source=sources();parent=w.load(PARENT/'closeout.json');saved=Path(parent['references']['review']['directory']);w.card.seal_verify(saved);output.mkdir(mode=0o700)
    for n,h in source.items():raw=w.plain(w.b.REPO/n,2*1024*1024);f.require(f.sha(raw)==h,'source drift');w.card.put(output,'source/'+n,raw)
    (output/'builds').mkdir()
    for name in ('receiver-build','supervisor-build'):shutil.copytree(saved/'builds'/name,output/'builds'/name)
    (output/'templates').mkdir()
    for name,old in (('normal-complete','injected-normal'),('normal-missing','exit-after-command')):shutil.copytree(saved/'models'/old,output/'templates'/name)
    worker=output/'source/research/usb-ds-iso/tools/a23_collection_worker.py';scratch=Path(tempfile.mkdtemp(prefix='a23-journal-',dir='/private/tmp'));w.write(output/'scratch-reference.json',dict(directory=str(scratch),failure_policy='retain unresolved workers and incomplete journals'))
    rows=exercise(output/'builds',output/'templates',worker,scratch,output/'models');bad=negatives(output/'models',output/'builds',output/'negative');f.require(sources()==source,'journal source drift');shutil.rmtree(scratch)
    report=dict(schema='A23-collection-journal-audit-1',passed=True,source_hashes=source,source_count=len(source),prior_sources_unchanged=392,native_build_source_count=392,new_native_build=False,new_sdk_model_execution=False,model_cases=len(CASES),negative_archives=bad,**rows,usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,production_collector_implemented=False,os_capability_isolation_implemented=False,**ar.FALSE);w.write(output/'audit.json',report);w.b.seal(output);w.card.seal_verify(output);return dict(reference=w.reference(output),source_count=len(source),model_cases=len(CASES),negative_archives=len(bad),passed=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
