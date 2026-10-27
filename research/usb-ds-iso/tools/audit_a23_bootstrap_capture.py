"""Legacy bootstrap interruption plus descriptor replacement models; no hardware."""
from pathlib import Path
import argparse,json,os,select,shutil,tempfile
import audit_a23_collection_journal as prior
import a23_bootstrap_capture as c
import a23_bootstrap_archive as ar
w=prior.w;a=c.a;f=c.f;j=prior.j
PARENT=w.A/'A23-journal-closeout-20261019';PARENT_SUM='dcfbf9b3a15e64386673ea0080ccb06ba3eccdb660852c28abc4b83a9ed38cee'
NEW=('tools/a23_bootstrap_archive.py','tools/a23_bootstrap_capture.py','tools/a23_bootstrap_worker.py','tools/audit_a23_bootstrap_capture.py','tests/test_a23_bootstrap_capture.py')
CASES=('normal','hold-marker','marker-empty','marker-partial','marker-full','journal-directory','attempt-empty','attempt-partial','attempt-full','copy-empty','copy-partial','copy-full','event-partial','event-full','float-marker','malformed-marker-complete','mismatched-marker-complete','marker-symlink','marker-fifo','marker-oversized','journal-symlink','source-renamed','marker-replaced','journal-renamed','journal-unsafe-nested','journal-oversized')
def sources():
    w.card.seal_verify(PARENT);f.require(f.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'bootstrap parent differs');p=w.load(PARENT/'closeout.json');out=prior.sources();f.require(out==p['source_hashes'] and len(out)==397,'prior397 drift')
    for n,h in p['protected_sha256'].items():f.require(f.sha(w.plain(Path(n)))==h,'protected drift')
    f.require(p['actual_ledger_sha256']=={p.name:f.sha(w.plain(p)) for p in w.LEDGER.iterdir() if p.is_file()},'real ledger drift')
    for n in NEW:key='research/usb-ds-iso/'+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))
def marker_record(root):
    fd=c.pin(root)
    try:raw,state=c.leaf(fd,j.MARKER);return raw,state
    finally:os.close(fd)
def exercise(builds,templates,worker,scratch,output):
    output.mkdir();receiver=builds/'receiver-build';supervisor=builds/'supervisor-build';rows={};retained={};lifecycle={};outside=scratch/'outside';outside.mkdir();(outside/'SECRET').write_bytes(b'FORBIDDEN_OUTSIDE_BYTES\n');allfaults=set(CASES[:17]);previous=None
    for case in CASES:
        root=scratch/(case+'-source');prior.seed(templates/'normal-complete',root);journal=scratch/(case+'-journal');actualroot=root;actualjournal=journal
        fault=case if case in allfaults else 'marker-full' if case in ('marker-symlink','marker-fifo','marker-oversized','journal-symlink','journal-oversized') else 'normal';job=scratch/(case+'.json');job.write_bytes(f.encode(prior.job_for(root,receiver,supervisor,journal,fault)));p=prior.spawn(worker,job)
        if case=='hold-marker':
            f.require(select.select([p.stdout],[],[],10)[0] and p.stdout.readline()==b'READY\n','bootstrap hold not reached')
            try:c.freeze(job,receiver,supervisor,output/'running',worker=p)
            except ValueError:lifecycle['running_refused']=not (output/'running').exists()
            else:raise ValueError('running bootstrap worker frozen')
            p.stdin.write(b'x');p.stdin.flush()
        expected=0 if fault in ('normal','malformed-marker-complete','mismatched-marker-complete') else 74;exitrow=prior.finish(p,expected)
        if case.startswith('marker-') and case in ('marker-symlink','marker-fifo','marker-oversized'):
            (root/j.MARKER).unlink()
            if case=='marker-symlink':(root/j.MARKER).symlink_to(outside/'SECRET')
            elif case=='marker-fifo':os.mkfifo(root/j.MARKER)
            else:
                with (root/j.MARKER).open('wb') as stream:stream.truncate(1024*1024+1)
        if case=='journal-symlink':journal.symlink_to(outside,target_is_directory=True)
        if case=='journal-unsafe-nested':(journal/'poison').symlink_to(outside/'SECRET')
        if case=='journal-oversized':
            journal.mkdir()
            with (journal/'huge').open('wb') as stream:stream.truncate(1024*1024+1)
        fired=[]
        def replace(stage):
            nonlocal actualroot,actualjournal
            if case=='source-renamed' and stage=='source_pinned' and not fired:actualroot=scratch/(case+'-displaced');root.rename(actualroot);root.symlink_to(outside,target_is_directory=True);fired.append(stage)
            if case=='marker-replaced' and stage=='marker_opened' and not fired:(root/j.MARKER).rename(root/'saved-marker');(root/j.MARKER).symlink_to(outside/'SECRET');fired.append(stage)
            if case=='journal-renamed' and stage=='journal_pinned' and not fired:actualjournal=scratch/(case+'-displaced');journal.rename(actualjournal);journal.symlink_to(outside,target_is_directory=True);fired.append(stage)
        before_marker=marker_record(actualroot);before_journal=a.snapshot(journal) if journal.is_dir() and not journal.is_symlink() and case not in ('journal-unsafe-nested','journal-oversized') else None
        result=c.freeze(job,receiver,supervisor,output/case,worker=p,checkpoint=replace);rows[case]=dict(result=result,exit=exitrow,replacement_checkpoints=fired)
        f.require(not any(b'FORBIDDEN_OUTSIDE_BYTES' in raw for name,raw in a.snapshot(output/case)[0].items() if name.startswith('raw/')),'outside file bytes captured')
        # Capture itself only reads. Replacement hooks are deliberate mutations
        # of private fixtures; compare the resulting physical originals here.
        post_marker=marker_record(actualroot);post_journal=a.snapshot(actualjournal) if actualjournal.is_dir() and not actualjournal.is_symlink() and case not in ('journal-unsafe-nested','journal-oversized') else None
        if not fired:f.require(before_marker==post_marker and before_journal==post_journal,'capture changed originals')
        retry=prior.spawn(worker,job);prior.finish(retry,2);f.require(marker_record(actualroot)==post_marker,'retry changed source marker')
        if post_journal is not None:f.require(a.snapshot(actualjournal)==post_journal,'retry changed journal')
        retained[case]=dict(retry_refused=True,originals_unchanged=True)
        if previous is not None and case=='normal':raise ValueError('unexpected model order')
        if case=='normal':previous=(job,p)
    f.require({n for n,r in rows.items() if r['result']['analysis']['journal_committed']}=={'normal'},'bootstrap classification differs')
    job,p=previous
    try:c.freeze(job,receiver,supervisor,output/'unknown')
    except ValueError:lifecycle['unknown_refused']=not (output/'unknown').exists()
    else:raise ValueError('unknown worker frozen')
    other=scratch/'marker-full.json'
    try:c.freeze(other,receiver,supervisor,output/'other-worker',worker=p)
    except ValueError:lifecycle['other_worker_refused']=not (output/'other-worker').exists()
    else:raise ValueError('other worker accepted')
    static=c.freeze(job,receiver,supervisor,output/'static',static_model=True);lifecycle['static_exit_claimed']=static['observation']['worker_exited']
    return dict(matrix=rows,retained_attempts=retained,lifecycle=lifecycle)
def reseal(root):
    (root/'SHA256SUMS').unlink();(root/'COMMITTED').unlink();a.seal(root)
def negatives(models,builds,output):
    output.mkdir();rows={}
    for name in ('forged-early-success','claims-repair','bool-worker-pid','job-pid','marker-bytes','raw-inventory','missing-commit'):
        root=output/name;shutil.copytree(models/('marker-full' if name=='forged-early-success' else 'normal'),root)
        if name=='forged-early-success':p=root/'analysis.json';v=f.parse(a.read(p));v['journal_committed']=True;v['complete_injected_model_chain']=True;p.write_bytes(f.encode(v));reseal(root)
        elif name in ('claims-repair','bool-worker-pid','raw-inventory'):
            p=root/'capture.json';v=f.parse(a.read(p))
            if name=='claims-repair':v['bootstrap_repair_authorized']=True
            elif name=='bool-worker-pid':v['observation']['pid']=True
            else:v['raw_files']['source-marker']['bytes']=False
            p.write_bytes(f.encode(v));reseal(root)
        elif name=='job-pid':p=root/'job.json';v=f.parse(a.read(p));v['child_pid']=123;p.write_bytes(f.encode(v));meta=f.load(root/'capture.json');meta['observation']['job_sha256']=f.sha(f.encode(v));(root/'capture.json').write_bytes(f.encode(meta));reseal(root)
        elif name=='marker-bytes':(root/'raw/source-marker').write_bytes(b'{');meta=f.load(root/'capture.json');meta['raw_files']['source-marker']=a.inventory({'x':b'{'})['x'];(root/'capture.json').write_bytes(f.encode(meta));reseal(root)
        else:(root/'COMMITTED').unlink()
        try:ar.analyze(root,builds/'receiver-build',builds/'supervisor-build')
        except (ValueError,OSError,KeyError,TypeError) as e:rows[name]=str(e)
        else:raise ValueError('forged bootstrap archive accepted '+name)
    return rows

def run(output):
    output=w.canonical(output);f.require(not output.exists(),'new bootstrap review required');source=sources();parent=w.load(PARENT/'closeout.json');saved=Path(parent['references']['review']['directory']);w.card.seal_verify(saved);output.mkdir(mode=0o700)
    for n,h in source.items():raw=w.plain(w.b.REPO/n,2*1024*1024);f.require(f.sha(raw)==h,'source drift');w.card.put(output,'source/'+n,raw)
    shutil.copytree(saved/'builds',output/'builds');shutil.copytree(saved/'templates',output/'templates');scratch=Path(tempfile.mkdtemp(prefix='a23-bootstrap-',dir='/private/tmp'));w.write(output/'scratch-reference.json',dict(directory=str(scratch),failure_policy='retain all unresolved bootstrap attempts'))
    rows=exercise(output/'builds',output/'templates',output/'source/research/usb-ds-iso/tools/a23_bootstrap_worker.py',scratch,output/'models');bad=negatives(output/'models',output/'builds',output/'negative');f.require(sources()==source,'bootstrap source drift');shutil.rmtree(scratch)
    report=dict(schema='A23-bootstrap-audit-1',passed=True,source_count=len(source),source_hashes=source,prior_sources_unchanged=397,native_build_source_count=392,model_cases=len(CASES),negative_archives=bad,**rows,new_native_build=False,new_sdk_model_execution=False,usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,production_bootstrap_recovery_implemented=False,os_capability_isolation_implemented=False,**ar.FALSE);w.write(output/'audit.json',report);w.b.seal(output);w.card.seal_verify(output);return dict(reference=w.reference(output),source_count=len(source),model_cases=len(CASES),negative_archives=len(bad),passed=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
