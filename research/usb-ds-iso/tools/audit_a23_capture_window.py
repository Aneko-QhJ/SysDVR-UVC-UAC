"""Late component mutation and residual final-observation boundary models."""
from pathlib import Path
import argparse,json,shutil,tempfile
import audit_a23_bootstrap_capture as prior
import a23_capture_window as model
import a23_capture_window_archive as ar
w=prior.w;a=ar.a;f=a.f;c=ar.c;j=c.ar.old.j;legacy=prior.prior
PARENT=w.A/'A23-bootstrap-closeout-20261019';PARENT_SUM='148149e2cabe05084851b1ee04c4057b574ed14e5abb7f5d8213086a85ee6482'
NEW=('tools/a23_capture_window.py','tools/a23_capture_window_archive.py','tools/audit_a23_capture_window.py','tests/test_a23_capture_window.py')
CASES=('normal','marker-partial-before-journal','marker-unlink-before-journal','source-rename-before-journal','marker-change-after-first','marker-symlink-after-first','journal-modify-after-first','journal-rename-after-first','marker-change-after-recheck','journal-change-after-recheck','marker-restore-after-first','new-empty-directory-after-first','first-incomplete','after-final-observation','marker-recreate-after-first')
def sources():
    w.card.seal_verify(PARENT);f.require(f.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'window parent differs');p=w.load(PARENT/'closeout.json');out=prior.sources();f.require(out==p['source_hashes'] and len(out)==402,'prior402 drift')
    for n,h in p['protected_sha256'].items():f.require(f.sha(w.plain(Path(n)))==h,'protected drift')
    f.require(p['actual_ledger_sha256']=={p.name:f.sha(w.plain(p)) for p in w.LEDGER.iterdir() if p.is_file()},'real ledger drift')
    for n in NEW:key='research/usb-ds-iso/'+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))
def marker_record(root):return prior.marker_record(root)
def exercise(builds,templates,worker,scratch,output):
    output.mkdir();receiver=builds/'receiver-build';supervisor=builds/'supervisor-build';outside=scratch/'outside';outside.mkdir();(outside/'SECRET').write_bytes(b'OUTSIDE_WINDOW_SENTINEL\n');rows={};retained={};lifecycle={}
    for case in CASES:
        root=scratch/(case+'-source');legacy.seed(templates/'normal-complete',root);journal=scratch/(case+'-journal');actualroot=root;actualjournal=journal;job=scratch/(case+'.json');job.write_bytes(f.encode(legacy.job_for(root,receiver,supervisor,journal,'marker-partial' if case=='first-incomplete' else 'normal')));p=legacy.spawn(worker,job);exited=legacy.finish(p,74 if case=='first-incomplete' else 0);fired=[];original=marker_record(root)[0]
        def fault(stage):
            nonlocal actualroot,actualjournal
            if fired:return
            if case in ('marker-partial-before-journal','marker-unlink-before-journal','source-rename-before-journal') and stage=='first.journal_pinned':
                if case=='marker-partial-before-journal':(root/j.MARKER).write_bytes(b'{')
                elif case=='marker-unlink-before-journal':(root/j.MARKER).unlink()
                else:actualroot=scratch/(case+'-displaced');root.rename(actualroot);root.symlink_to(outside,target_is_directory=True)
                fired.append(stage)
            elif case in ('marker-change-after-first','marker-symlink-after-first','journal-modify-after-first','journal-rename-after-first','marker-restore-after-first','new-empty-directory-after-first','marker-recreate-after-first') and stage=='first_frozen':
                if case=='marker-change-after-first':(root/j.MARKER).write_bytes(b'{')
                elif case=='marker-symlink-after-first':(root/j.MARKER).unlink();(root/j.MARKER).symlink_to(outside/'SECRET')
                elif case=='journal-modify-after-first':(journal/'attempt.json').write_bytes(b'{')
                elif case=='journal-rename-after-first':actualjournal=scratch/(case+'-displaced');journal.rename(actualjournal);journal.symlink_to(outside,target_is_directory=True)
                elif case=='marker-restore-after-first':(root/j.MARKER).write_bytes(b'{');(root/j.MARKER).write_bytes(original)
                elif case=='new-empty-directory-after-first':(journal/'new-empty').mkdir()
                else:(root/j.MARKER).unlink();(root/j.MARKER).write_bytes(original)
                fired.append(stage)
            elif case in ('marker-change-after-recheck','journal-change-after-recheck') and stage=='recheck_recorded':
                (root/j.MARKER if case=='marker-change-after-recheck' else journal/'attempt.json').write_bytes(b'{');fired.append(stage)
            elif case=='after-final-observation' and stage=='final_observed':(root/j.MARKER).write_bytes(b'{');fired.append(stage)
        result=model.freeze(job,receiver,supervisor,output/case,worker=p,checkpoint=fault);post=marker_record(actualroot);snapshot=a.snapshot(actualjournal) if actualjournal.is_dir() else None;f.require(not any(b'OUTSIDE_WINDOW_SENTINEL' in raw for n,raw in a.snapshot(output/case)[0].items() if n.startswith('first/raw/')),'outside bytes captured');drift=post[0]!=a.read(output/case/'first/raw/source-marker');rows[case]=dict(result=result,exit=exited,mutation_checkpoints=fired,marker_bytes_differ_after_capture=drift)
        before_output=a.snapshot(output/case)
        try:model.freeze(job,receiver,supervisor,output/case,worker=p)
        except ValueError:pass
        else:raise ValueError('window output reused')
        f.require(a.snapshot(output/case)==before_output and marker_record(actualroot)==post and (a.snapshot(actualjournal) if actualjournal.is_dir() else None)==snapshot,'rejected retry changed evidence');retry=legacy.spawn(worker,job);legacy.finish(retry,2);f.require(marker_record(actualroot)==post and (a.snapshot(actualjournal) if actualjournal.is_dir() else None)==snapshot,'collector retry changed late mutation fixture');retained[case]=dict(retry_refused=True,physical_originals_unchanged=True)
    accepted={n for n,v in rows.items() if v['result']['analysis']['accepted_model_evidence']};f.require(accepted=={'normal','after-final-observation'},'window acceptance differs');f.require(rows['after-final-observation']['marker_bytes_differ_after_capture'] and rows['after-final-observation']['result']['analysis']['source_unchanged_through_commit_proven'] is False,'residual final window hidden')
    for case in ('marker-partial-before-journal','marker-unlink-before-journal','source-rename-before-journal'):f.require(rows[case]['result']['first_capture']['analysis']['journal_committed'] is True and rows[case]['result']['analysis']['accepted_model_evidence'] is False,'legacy counterexample not reproduced')
    normal=scratch/'normal.json';static=model.freeze(normal,receiver,supervisor,output/'static',static_model=True);lifecycle['static_exit_claimed']=static['first_capture']['observation']['worker_exited']
    try:model.freeze(normal,receiver,supervisor,output/'unknown')
    except ValueError:lifecycle['unknown_refused']=not (output/'unknown').exists()
    else:raise ValueError('unknown worker accepted')
    return dict(matrix=rows,retained_attempts=retained,lifecycle=lifecycle)
def reseal(root):
    (root/'SHA256SUMS').unlink();(root/'COMMITTED').unlink();a.seal(root)
def negatives(models,builds,output):
    output.mkdir();out={}
    for name in ('forged-late-success','claims-atomic','claims-through-commit','bool-stability','digest','extra-directory','missing-commit'):
        root=output/name;shutil.copytree(models/('marker-change-after-first' if name=='forged-late-success' else 'first-incomplete'),root)
        if name=='forged-late-success':p=root/'analysis.json';v=f.load(p);v['accepted_model_evidence']=True;v['complete_injected_model_chain']=True;p.write_bytes(f.encode(v));reseal(root)
        elif name in ('claims-atomic','claims-through-commit','digest'):
            p=root/'window.json';v=f.load(p)
            if name=='claims-atomic':v['atomic_snapshot_verified']=True
            elif name=='claims-through-commit':v['source_unchanged_through_commit_proven']=True
            else:v['recheck_sha256']='0'*64
            p.write_bytes(f.encode(v));reseal(root)
        elif name=='bool-stability':p=root/'recheck.json';v=f.load(p);v['capture']['source']['stable']=1;p.write_bytes(f.encode(v));m=f.load(root/'window.json');m['recheck_sha256']=f.sha(f.encode(v));(root/'window.json').write_bytes(f.encode(m));reseal(root)
        elif name=='extra-directory':(root/'unexpected').mkdir();reseal(root)
        else:(root/'COMMITTED').unlink()
        try:ar.analyze(root,builds/'receiver-build',builds/'supervisor-build')
        except (ValueError,OSError,KeyError,TypeError) as e:out[name]=str(e)
        else:raise ValueError('forged observation window accepted '+name)
    return out

def run(output):
    output=w.canonical(output);f.require(not output.exists(),'new window review required');source=sources();parent=w.load(PARENT/'closeout.json');saved=Path(parent['references']['review']['directory']);w.card.seal_verify(saved);output.mkdir(mode=0o700)
    for n,h in source.items():raw=w.plain(w.b.REPO/n,2*1024*1024);f.require(f.sha(raw)==h,'source drift');w.card.put(output,'source/'+n,raw)
    shutil.copytree(saved/'builds',output/'builds');shutil.copytree(saved/'templates',output/'templates');scratch=Path(tempfile.mkdtemp(prefix='a23-window-',dir='/private/tmp'));w.write(output/'scratch-reference.json',dict(directory=str(scratch),failure_policy='retain unresolved attempts and uncommitted outputs'))
    rows=exercise(output/'builds',output/'templates',output/'source/research/usb-ds-iso/tools/a23_bootstrap_worker.py',scratch,output/'models');bad=negatives(output/'models',output/'builds',output/'negative');f.require(sources()==source,'window source drift');shutil.rmtree(scratch)
    report=dict(schema='A23-capture-window-audit-1',passed=True,source_count=len(source),source_hashes=source,prior_sources_unchanged=402,native_build_source_count=392,model_cases=len(CASES),negative_archives=bad,**rows,new_native_build=False,new_sdk_model_execution=False,usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,production_window_guard_implemented=False,os_capability_isolation_implemented=False,**ar.FALSE);w.write(output/'audit.json',report);w.b.seal(output);w.card.seal_verify(output);return dict(reference=w.reference(output),source_count=len(source),model_cases=len(CASES),negative_archives=len(bad),passed=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
