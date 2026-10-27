"""Offline read-only directory intake cases; historical byte caches, no process fixtures."""
from pathlib import Path
from contextlib import nullcontext
from unittest.mock import patch
import argparse,errno,json,os,shutil,sys,tempfile
import a23_terminal_intake as sampler
import audit_a23_terminal_recovery as previous
model=sampler.recovery
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-terminal-recovery-closeout-20261021'
PARENT_SUM='608339bd59820a6da4e602b066c9160c181e6e7092bd96cd66ca6ba992fb2c56'
SOURCE_REVIEW_SUM='bb43317f79a07c686c7278edcbf83ae27f44ccce10ec9a34695b586bb7d2d0fe'
NEW=('tools/a23_terminal_intake.py','tools/audit_a23_terminal_intake.py','tests/test_a23_terminal_intake.py')
FALSE=previous.FALSE
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
POSITIVES=('empty','ignored-symlink','hardlinked-pair','stable-conflict','post-validation-change')
REJECTS=('entry-symlink','entry-directory','entry-fifo','ancestor-symlink','root-symlink','oversized','aggregate-oversized','replace-after-lstat','fifo-after-lstat',
    'mutate-between-reads','truncate-between-reads','grow-after-open','replace-after-validation','create-between-views','delete-between-views','mutate-between-views','replace-directory-between-views','read-error','read-budget','outside-path')
TARGET='worker-exit.json'


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==554,'prior554 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def case_names():return tuple('base/'+name for name in previous.previous.model.CASES)+tuple('control/'+name for name in (*POSITIVES,*REJECTS))
def semantic(row):return {k:v for k,v in row.items() if k not in ('fixture_job_id','actual_error_code')}


def prepare(parent,files):
    directory=parent/'data';directory.mkdir(parents=True)
    for name,raw in files.items():a.put(directory,name,raw)
    return directory


def setup_case(name,directory):
    original=directory;target=directory/TARGET;outside=directory.parent/'outside';outside.write_bytes(b'outside sentinel must not be read');action=[]
    if name=='empty':
        for path in directory.iterdir():path.unlink()
    if name=='ignored-symlink':(directory/'not-allowed').symlink_to(outside)
    if name=='hardlinked-pair':part=directory/(TARGET+'.part');part.unlink();os.link(target,part)
    if name=='stable-conflict':target.write_bytes(b'invalid final');(directory/(TARGET+'.part')).write_bytes(b'invalid final')
    if name=='entry-symlink':target.unlink();target.symlink_to(outside)
    if name=='entry-directory':target.unlink();target.mkdir()
    if name=='entry-fifo':target.unlink();os.mkfifo(target)
    if name=='root-symlink':alias=directory.parent/'alias';alias.symlink_to(directory,target_is_directory=True);directory=alias
    if name=='ancestor-symlink':
        nested=directory.parent/'real';nested.mkdir();alias=directory.parent/'alias';alias.symlink_to(nested,target_is_directory=True);directory.rename(nested/'data');directory=alias/'data';original=nested/'data';target=original/TARGET
    if name=='oversized':target.write_bytes(b'x'*8193)
    if name=='aggregate-oversized':
        for path in original.iterdir():path.unlink()
        for filename in model.ALLOWED:(original/filename).write_bytes(b'x'*8192)
    if name=='outside-path':directory=Path('/Volumes/a23-not-opened')
    done=False
    def hook(phase,filename):
        nonlocal done
        expected={'replace-after-lstat':'after_lstat','fifo-after-lstat':'after_lstat','mutate-between-reads':'after_first_read','truncate-between-reads':'after_first_read','grow-after-open':'after_open','replace-after-validation':'after_fd_validation',
            'create-between-views':'between_views','delete-between-views':'between_views','mutate-between-views':'between_views','replace-directory-between-views':'between_views','post-validation-change':'validated'}.get(name)
        if done or phase!=expected or phase not in ('between_views','validated') and filename!=TARGET:return
        done=True;action.append(dict(phase=phase,filename=filename))
        if name in ('replace-after-lstat','replace-after-validation'):
            raw=target.read_bytes();replacement=original/'replacement';replacement.write_bytes(raw);os.replace(replacement,target)
        if name=='fifo-after-lstat':target.unlink();os.mkfifo(target)
        if name in ('mutate-between-reads','mutate-between-views','post-validation-change'):
            raw=target.read_bytes();target.write_bytes(b'!'+raw[1:])
        if name=='truncate-between-reads':target.write_bytes(b'')
        if name=='grow-after-open':target.write_bytes(b'x'*8193)
        if name=='create-between-views':(original/'worker-transport.json').write_bytes(b'appeared')
        if name=='delete-between-views':target.unlink()
        if name=='replace-directory-between-views':old=original.parent/'displaced';original.rename(old);original.mkdir()
    return directory,hook,action,original


def validate_case(name,args,captured,report,row):
    accepted=name.startswith('base/') or name.removeprefix('control/') in POSITIVES
    f.require(row['accepted'] is accepted and row['task_complete'] is False and all(row[k] is False for k in FALSE),'intake acceptance/authority differs '+name)
    if accepted:
        classified=model.classify(*args[:2],captured);f.require(classified==row['classification'],'intake cache classification differs')
        f.require(report['schema']=='A23-terminal-intake-report-1' and report['equal_views']==report['per_file_equal_reads']==2 and report['atomic_directory_snapshot_verified'] is False and report['historical_sync_or_wait_inferred'] is False,'intake report claim differs')
        f.require(report['file_count']==len(captured) and report['total_bytes']==sum(map(len,captured.values())) and set(report['file_metadata'])==set(captured),'intake report inventory differs')
        f.require(all(len(v)==9 and all(type(x) is int for x in v) for v in report['file_metadata'].values()),'intake metadata shape differs')
        if name.startswith('base/'):f.require(captured==args[2],'intake changed historical bytes')
        expected='absent' if name=='control/empty' else 'conflict' if name=='control/stable-conflict' else None
        if expected:f.require(classified['classification']==expected,'control classification differs')
    else:f.require(captured is None and report is None and row['classification'] is None and bool(row['actual_error_code']),'rejected intake leaked partial cache')
    return row


def exercise(inputs,output):
    output.mkdir(mode=0o700);stage=Path(tempfile.mkdtemp(prefix='a23-terminal-intake-',dir='/private/tmp'));rows={};raw_errors={}
    for name in case_names():
        base=name.removeprefix('base/') if name.startswith('base/') else 'normal';args=previous.args_at(inputs/'jobs'/base);job=stage/name;directory=prepare(job,args[2]);hook=None;actions=[];control=name.removeprefix('control/')
        if name.startswith('control/'):directory,hook,actions,physical=setup_case(control,directory)
        manager=patch.object(sampler.os,'read',side_effect=OSError(errno.EIO,'injected read failure')) if control=='read-error' else patch.object(sampler.os,'read',side_effect=InterruptedError(errno.EINTR,'injected interruption')) if control=='read-budget' else nullcontext()
        captured=report=classified=None;error=None
        try:
            with manager:captured,report,classified=sampler.capture(directory,args[0],args[1],hook)
        except sampler.IntakeError as exc:error=exc.code
        group='directory_changed' if error in ('directory_changed','directory_path_changed') else error
        row=dict(schema='A23-terminal-intake-case-1',fixture_job_id=model.parse(args[0])['fixture_job_id'],accepted=error is None,rejection_group=group,actual_error_code=error,
            classification=classified,task_complete=False,atomic_directory_snapshot_verified=False,historical_sync_or_wait_inferred=False,**FALSE)
        validate_case(name,args,captured,report,row);target=output/'cases'/name
        a.put(target,'outcome.json',f.encode(row));a.put(target,'anchor.json',args[0]);a.put(target,'actions.json',f.encode(actions))
        if captured is not None:
            for filename,raw in captured.items():a.put(target,'captured/'+filename,raw)
            a.put(target,'report.json',f.encode(report))
        if control=='post-validation-change':
            after=cache(directory);f.require(after[TARGET]!=captured[TARGET],'post-validation control did not change live bytes')
            a.put(target,'post-validation-live-files.json',f.encode({key:f.sha(raw) for key,raw in after.items()}));f.require(classified['classification']=='commit_associated' and classified['task_complete'] is False,'post-validation control authority upgraded')
        rows[name]=semantic(row);raw_errors[name]=error
    f.require(sum(v['accepted'] for v in rows.values())==63 and len(rows)==83,'intake totals differ')
    return dict(passed=True,model_cases=83,historical_snapshots=58,accepted_cases=63,rejected_cases=20,semantic=rows,actual_error_codes=raw_errors,
        staging_directory=str(stage),sample_case_directories=83,new_fixture_processes=0,new_fixture_jobs=0,process_queries=0,
        atomic_directory_snapshot_verified=False,usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json');f.require(audit['source_count']==557 and audit['prior_sources_unchanged']==554 and len(audit['source_hashes'])==557,'intake source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen intake source differs')
    f.require(set(r['semantic'])==set(case_names()),'intake cases differ')
    for name in case_names():
        target=root/'work/cases'/name;base=name.removeprefix('base/') if name.startswith('base/') else 'normal';args=previous.args_at(root/'inputs/jobs'/base);row=f.load(target/'outcome.json')
        captured=cache(target/'captured') if row['accepted'] else None;report=f.load(target/'report.json') if row['accepted'] else None
        validate_case(name,args,captured,report,row);f.require(semantic(row)==r['semantic'][name] and row['actual_error_code']==r['actual_error_codes'][name] and a.read(target/'anchor.json')==args[0],'saved intake verdict differs')
    f.require(r['accepted_cases']==63 and r['rejected_cases']==20 and r['new_fixture_processes']==r['process_queries']==0 and all(r[k] is False for k in FALSE),'intake aggregate differs');return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new intake review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'intake source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM);shutil.copytree(review/'inputs/jobs',output/'inputs/jobs')
    a.put(output,'inputs/provenance.json',f.encode(dict(source_review=parent['references']['review'],historical_anchors_and_bytes_reused=True,new_fixture_execution=False)))
    try:r=exercise(output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='temporary-directory-intake-only')));seal(output);raise
    f.require(sources()==frozen,'intake source drift after exercise');a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=557,prior_sources_unchanged=554,source_hashes=frozen)));seal(output)
    return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=83,new_fixture_processes=0)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
