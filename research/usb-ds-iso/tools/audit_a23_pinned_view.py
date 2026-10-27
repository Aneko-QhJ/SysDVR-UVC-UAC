"""Detached baseline byte views, hard-link policy, cached reads and write exits."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys,tempfile
import audit_a23_capture_window as prior
import a23_pinned_view as model
import a23_pinned_view_archive as ar
w=prior.w;a=ar.a;f=a.f
PARENT=w.A/'A23-window-closeout-20261019';PARENT_SUM='ad3c69250ecf4f9652ddd3af1b9690bd530890031fe3219ac3436b369b496d9d'
NEW=('tools/a23_pinned_view.py','tools/a23_pinned_view_archive.py','tools/audit_a23_pinned_view.py','tests/test_a23_pinned_view.py')
SELECT=('source-marker','journal/attempt.json','journal/SOURCE_ATTEMPT','journal/events/00.json','journal/envelope/final/inputs/case-info.json','journal/envelope/final/inputs/host/epoch-0/raw.bin')
CASES=('normal','source-hardlink','internal-hardlink','during-read-hardlink','source-write-after-snapshot','source-write-after-publish','source-rename-after-snapshot','output-hardlink-before-commit','output-write-before-commit','cache-then-rewrite-disk','cache-then-hardlink-write','cache-then-replace-path','missing-source-file','source-symlink','source-fifo','wrong-contract')
def sources():
    w.card.seal_verify(PARENT);f.require(f.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'view parent differs');p=w.load(PARENT/'closeout.json');out=prior.sources();f.require(out==p['source_hashes'] and len(out)==406,'prior406 drift')
    for n,h in p['protected_sha256'].items():f.require(f.sha(w.plain(Path(n)))==h,'protected drift')
    f.require(p['actual_ledger_sha256']=={p.name:f.sha(w.plain(p)) for p in w.LEDGER.iterdir() if p.is_file()},'real ledger drift')
    for n in NEW:key='research/usb-ds-iso/'+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))
def source_proof(root):
    expected=ar.contract(f.load(root/'expected.json'));manifest=a.read(root/'origin-SHA256SUMS');f.require(f.sha(manifest)==expected['source_manifest_sha256'] and a.read(root/'origin-COMMITTED')==(f.sha(manifest)+'\n').encode(),'origin manifest differs');entries={n:h for h,n in (line.split('  ',1) for line in manifest.decode().splitlines())};files,dirs=a.snapshot(root/'selection');f.require(a.inventory(files)==expected['files'] and dirs==expected['directories'],'selection differs')
    for name,raw in files.items():f.require(f.sha(raw)==entries[expected['source_prefix']+name],'selection not in frozen manifest')
    return expected

def current_valid(root,expected):
    try:return True,ar.verify(root,expected)
    except (ValueError,OSError,KeyError,TypeError) as e:return False,str(e)
def cached_equal(cache,reference):return all(cache.read(n)==value for n,value in reference.items()) and set(cache.files)==set(reference)
def worker_run(script,source,expected,output,fault):
    tmp=Path(tempfile.mkdtemp(prefix='view-worker-',dir=str(source.parent)));p=subprocess.Popen([str(Path(sys.executable).resolve()),'-B',str(script),'--source',str(source),'--expected',str(expected),'--output',str(output),'--fault',fault],stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,env=dict(LANG='C',LC_ALL='C',PATH='/usr/bin:/bin:/usr/sbin:/sbin',TMPDIR=str(tmp)));stdout,stderr=p.communicate(timeout=30);f.require(stderr==b'','view worker stderr');return p.returncode,stdout.decode()
def exercise(bundle,script,scratch,output):
    output.mkdir();expected=source_proof(bundle);reference,_=a.snapshot(bundle/'selection');target='source-marker';outside=scratch/'outside';outside.mkdir();(outside/'SECRET').write_bytes(b'VIEW_OUTSIDE_SECRET\n');rows={};partial={};cache_reads=0
    for case in CASES:
        source=scratch/(case+'-source');shutil.copytree(bundle/'selection',source);view=scratch/(case+'-view');alias=outside/(case+'-alias');selected=expected
        if case=='source-hardlink':os.link(source/target,alias)
        if case=='internal-hardlink':(source/'journal/attempt.json').unlink();os.link(source/target,source/'journal/attempt.json')
        if case=='missing-source-file':(source/target).unlink()
        if case=='source-symlink':(source/target).unlink();(source/target).symlink_to(outside/'SECRET')
        if case=='source-fifo':(source/target).unlink();os.mkfifo(source/target)
        if case=='wrong-contract':selected=f.parse(f.encode(expected));selected['files'][target]['sha256']='0'*64
        hooks=[]
        def inject(stage):
            if hooks:return
            if case=='during-read-hardlink' and stage=='source.file_opened:'+target:os.link(source/target,alias);hooks.append(stage)
            elif case=='source-write-after-snapshot' and stage=='snapshotted':(source/target).write_bytes(b'{');hooks.append(stage)
            elif case=='source-rename-after-snapshot' and stage=='snapshotted':source.rename(scratch/(case+'-displaced'));source.symlink_to(outside,target_is_directory=True);hooks.append(stage)
            elif case=='output-hardlink-before-commit' and stage=='before_commit':os.link(view/'data'/target,alias);hooks.append(stage)
            elif case=='output-write-before-commit' and stage=='before_commit':(view/'data'/target).write_bytes(b'{');hooks.append(stage)
        failure=None;published=False;cache=None
        try:model.materialize(source,selected,view,inject);published=True
        except (ValueError,OSError) as e:failure=str(e)
        if published:
            cache=model.PinnedBytes.load(view,expected);f.require(cached_equal(cache,reference),'cache differs from baseline');cache_reads+=1
            if case=='source-write-after-publish':(source/target).write_bytes(b'{')
            if case=='cache-then-rewrite-disk':(view/'data'/target).write_bytes(b'{')
            if case=='cache-then-hardlink-write':os.link(view/'data'/target,alias);alias.write_bytes(b'{')
            if case=='cache-then-replace-path':(view/'data'/target).unlink();(view/'data'/target).write_bytes(b'{')
            f.require(cached_equal(cache,reference),'later filesystem write changed cached bytes')
            try:cache._data[target]=b'changed'
            except TypeError:pass
            else:raise ValueError('cached mapping writable')
            try:cache.contract_sha256='changed'
            except AttributeError:pass
            else:raise ValueError('cached contract writable')
        valid,verdict=current_valid(view,expected);link_count=(view/'data'/target).stat().st_nlink if (view/'data'/target).exists() else None;same_inode=bool(published and source.is_dir() and not source.is_symlink() and (source/target).exists() and (source/target).stat().st_ino==(view/'data'/target).stat().st_ino)
        f.require(not same_inode,'copy retained source inode');before=a.snapshot(view)
        try:model.materialize(source,expected,view)
        except (ValueError,OSError):pass
        else:raise ValueError('view output overwritten')
        f.require(a.snapshot(view)==before,'retry changed view');dest=output/case;dest.mkdir();shutil.copytree(view,dest/'view');row=dict(published=published,storage_valid_at_observation=valid,cached_bytes_match=cache is not None and cached_equal(cache,reference),failure=failure,verifier_result=verdict,hook_stages=hooks,observed_data_nlink=link_count,source_and_view_inode_shared=same_inode,retry_refused=True,**ar.FALSE);a.put(dest,'observation.json',f.encode(row));rows[case]=row
    accepted={n for n,v in rows.items() if v['published']};f.require(accepted=={'normal','source-write-after-snapshot','source-write-after-publish','source-rename-after-snapshot','cache-then-rewrite-disk','cache-then-hardlink-write','cache-then-replace-path'},'view publication matrix differs');f.require(all(rows[n]['storage_valid_at_observation'] is False and rows[n]['cached_bytes_match'] for n in ('cache-then-rewrite-disk','cache-then-hardlink-write','cache-then-replace-path')),'cache detachment counterexample failed')
    for stage in ('reserved','copied','before_commit'):
        source=scratch/('exit-'+stage+'-source');shutil.copytree(bundle/'selection',source);view=scratch/('exit-'+stage+'-view');code,stdout=worker_run(script,source,bundle/'expected.json',view,stage);f.require(code==75 and not (view/'COMMITTED').exists() and (view/'ATTEMPT').exists(),'interrupted view committed');valid,_=current_valid(view,expected);f.require(not valid,'partial view accepted');before=a.snapshot(view);again,_=worker_run(script,source,bundle/'expected.json',view,'none');f.require(again==2 and a.snapshot(view)==before,'interrupted view retried');shutil.copytree(view,output/('exit-'+stage));partial[stage]=dict(returncode=code,committed=False,retry_refused=True)
    source=scratch/'race-source';shutil.copytree(bundle/'selection',source);view=scratch/'race-view';command=[str(Path(sys.executable).resolve()),'-B',str(script),'--source',str(source),'--expected',str(bundle/'expected.json'),'--output',str(view)];processes=[subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(LANG='C',PATH='/usr/bin:/bin',TMPDIR=str(scratch))) for _ in range(2)];codes=[]
    for p in processes:stdout,stderr=p.communicate(timeout=30);f.require(stderr==b'','view race stderr');codes.append(p.returncode)
    f.require(sorted(codes)==[0,2] and ar.verify(view,expected)['byte_contract_matches'],'view race winners differ');shutil.copytree(view,output/'race-view');return dict(matrix=rows,interrupted_publications=partial,race_exitcodes=codes,cached_read_cases=cache_reads)
def reseal(root):
    (root/'SHA256SUMS').unlink();(root/'COMMITTED').unlink();a.seal(root)
def negatives(normal,bundle,output):
    output.mkdir();rows={};expected=source_proof(bundle)
    for name in ('missing-commit','payload','claims-live','claims-os-immutable','self-substituted-contract','extra-empty-directory','bool-file-count'):
        root=output/name;shutil.copytree(normal,root)
        if name=='missing-commit':(root/'COMMITTED').unlink()
        elif name=='payload':(root/'data/source-marker').write_bytes(b'{');reseal(root)
        elif name=='extra-empty-directory':(root/'unexpected').mkdir();reseal(root)
        elif name=='self-substituted-contract':p=root/'contract.json';v=f.load(p);v['source_manifest_sha256']='0'*64;p.write_bytes(f.encode(v));meta=f.load(root/'view.json');meta['contract_sha256']=f.sha(f.encode(v));(root/'view.json').write_bytes(f.encode(meta));reseal(root)
        else:
            p=root/'view.json';v=f.load(p)
            if name=='claims-live':v['live_source_authenticated']=True
            elif name=='claims-os-immutable':v['os_immutability_enforced']=True
            else:v['files']=True
            p.write_bytes(f.encode(v));reseal(root)
        try:ar.verify(root,expected)
        except (ValueError,OSError,KeyError,TypeError) as e:rows[name]=str(e)
        else:raise ValueError('bad pinned view accepted '+name)
    return rows

def run(output):
    output=w.canonical(output);f.require(not output.exists(),'new pinned view review required');source=sources();parent=w.load(PARENT/'closeout.json');saved=Path(parent['references']['review']['directory']);w.card.seal_verify(saved);origin=saved/'models/normal/first';a.sealed(origin);output.mkdir(mode=0o700)
    for n,h in source.items():raw=w.plain(w.b.REPO/n,2*1024*1024);f.require(f.sha(raw)==h,'source drift');w.card.put(output,'source/'+n,raw)
    bundle=output/'bundle';bundle.mkdir();selection=bundle/'selection';selection.mkdir();files={n:a.read(origin/'raw'/n) for n in SELECT}
    for n,raw in files.items():a.put(selection,n,raw)
    (selection/'empty').mkdir();expected=dict(schema='A23-pinned-byte-contract-1',source_manifest_sha256=f.sha(a.read(origin/'SHA256SUMS')),source_prefix='raw/',files=a.inventory(files),directories=sorted(set(a.prefixes(files))|{'empty'}),**ar.FALSE);a.put(bundle,'expected.json',f.encode(expected));a.put(bundle,'origin-SHA256SUMS',a.read(origin/'SHA256SUMS'));a.put(bundle,'origin-COMMITTED',a.read(origin/'COMMITTED'));source_proof(bundle)
    scratch=Path(tempfile.mkdtemp(prefix='a23-view-',dir='/private/tmp'));w.write(output/'scratch-reference.json',dict(directory=str(scratch),failure_policy='retain partial views and unresolved workers'));rows=exercise(bundle,output/'source/research/usb-ds-iso/tools/a23_pinned_view.py',scratch,output/'models');bad=negatives(output/'models/normal/view',bundle,output/'negative');f.require(sources()==source,'pinned view source drift');shutil.rmtree(scratch)
    report=dict(schema='A23-pinned-view-audit-1',passed=True,source_count=len(source),source_hashes=source,prior_sources_unchanged=406,selected_source_files=len(files),model_cases=len(CASES),negative_archives=bad,**rows,native_build_used=False,new_native_build=False,new_sdk_model_execution=False,usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,production_fixed_view_implemented=False,**ar.FALSE);w.write(output/'audit.json',report);w.b.seal(output);w.card.seal_verify(output);return dict(reference=w.reference(output),source_count=len(source),model_cases=len(CASES),negative_archives=len(bad),passed=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
