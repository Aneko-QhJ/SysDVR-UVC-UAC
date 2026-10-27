"""Descriptor-anchored, bounded reads of source marker and bootstrap journal.

This is model forensics, not an atomic filesystem snapshot or OS isolation.
No execution tree is opened. Unsafe nodes are metadata-only skipped entries.
"""
from pathlib import Path
import os,re,stat,subprocess,sys
import a23_bootstrap_archive as ar
a=ar.a;f=a.f

def identity(st):return [st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns]
def pin(path):
    path=Path(path);f.require(path.is_absolute() and '..' not in path.parts,'absolute anchored path required');fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        return fd
    except BaseException:os.close(fd);raise

def same_path(path,expected):
    try:
        fd=pin(path)
        try:return identity(os.fstat(fd))==expected
        finally:os.close(fd)
    except OSError:return False

def leaf(fd,name,hook=None):
    try:st=os.stat(name,dir_fd=fd,follow_symlinks=False)
    except FileNotFoundError:return None,dict(state='absent',stable=True,identity=None,skipped=[])
    before=identity(st);record=dict(state='blocked',stable=True,identity=before,skipped=[])
    if not stat.S_ISREG(st.st_mode) or st.st_size>1024*1024:return None,record
    handle=None
    try:
        handle=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd);f.require(identity(os.fstat(handle))==before,'file replaced before open')
        if hook:hook()
        raw=bytearray()
        while len(raw)<st.st_size:
            part=os.read(handle,min(65536,st.st_size-len(raw)));f.require(part,'short bootstrap read');raw.extend(part)
        stable=not os.read(handle,1) and identity(os.fstat(handle))==before and identity(os.stat(name,dir_fd=fd,follow_symlinks=False))==before
        record.update(state='regular',stable=bool(stable));return bytes(raw),record
    except (ValueError,OSError):record['stable']=False;return None,record
    finally:
        if handle is not None:os.close(handle)

def capture(job,checkpoint=None):
    source=Path(job['root']);journal=Path(job['journal']);raw={};dirs=[];nodes=0;total=0;skipped=[];stable=True
    for path in (source,journal):f.require(path.is_absolute() and path.is_relative_to('/private/tmp') and '..' not in path.parts,'temporary declared roots required')
    fd=pin(source)
    try:
        start=identity(os.fstat(fd))
        if checkpoint:checkpoint('source_pinned')
        marker,record=leaf(fd,ar.old.j.MARKER,lambda:checkpoint('marker_opened') if checkpoint else None)
        if marker is not None:raw['source-marker']=marker
        source_record=dict(state='directory',stable=identity(os.fstat(fd))==start and same_path(source,start),identity=start,skipped=[])
    finally:os.close(fd)
    def tree(directory,prefix=''):
        nonlocal nodes,total,stable
        before=identity(os.fstat(directory))
        for name in sorted(os.listdir(directory)):
            nodes+=1;n=prefix+name
            if nodes>512:skipped.append(dict(path=prefix,reason='node limit'));stable=False;break
            if not re.fullmatch(r'[A-Za-z0-9_.-]+',name) or len(Path(n).parts)>18:skipped.append(dict(path=n,reason='unsafe name/depth'));continue
            try:st=os.stat(name,dir_fd=directory,follow_symlinks=False)
            except OSError:skipped.append(dict(path=n,reason='stat failed'));stable=False;continue
            if stat.S_ISDIR(st.st_mode):
                child=None
                try:
                    child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory);f.require(identity(os.fstat(child))==identity(st),'directory replaced');dirs.append('journal/'+n);tree(child,n+'/');stable=stable and identity(os.fstat(child))==identity(os.stat(name,dir_fd=directory,follow_symlinks=False))
                except (ValueError,OSError):skipped.append(dict(path=n,reason='directory changed or blocked'));stable=False
                finally:
                    if child is not None:os.close(child)
            else:
                value,part=leaf(directory,name)
                if value is None:skipped.append(dict(path=n,reason='unsafe, oversized or changed file'));stable=stable and part['stable'];continue
                total+=len(value)
                if total>16*1024*1024:skipped.append(dict(path=n,reason='byte limit'));stable=False;break
                raw['journal/'+n]=value;stable=stable and part['stable']
        stable=stable and identity(os.fstat(directory))==before
    handle=None
    try:
        handle=pin(journal);start=identity(os.fstat(handle));dirs.append('journal')
        if checkpoint:checkpoint('journal_pinned')
        tree(handle);journal_record=dict(state='directory',stable=bool(stable and identity(os.fstat(handle))==start and same_path(journal,start)),identity=start,skipped=skipped)
    except FileNotFoundError:journal_record=dict(state='absent',stable=True,identity=None,skipped=[])
    except OSError:journal_record=dict(state='blocked',stable=False,identity=None,skipped=[])
    finally:
        if handle is not None:os.close(handle)
    return dict(source=source_record,marker=record,journal=journal_record),dict(sorted(raw.items())),sorted(set(dirs))

def observe(job_path,worker,static_model):
    f.require(type(static_model) is bool and (static_model != (worker is not None)),'explicit static bootstrap or owned worker required');raw=a.read(a.canonical(job_path),limit=1024*1024);base=dict(job_sha256=f.sha(raw))
    if static_model:return dict(mode='supplied_static_bootstrap',worker_exited=False,pid=None,returncode=None,**base),raw
    f.require(isinstance(worker,subprocess.Popen) and type(worker.poll()) is int,'bootstrap worker still running or unknown');f.require(type(worker.args) in (list,tuple) and len(worker.args)==4 and worker.args[0]==str(Path(sys.executable).resolve()) and worker.args[1]=='-B' and Path(worker.args[2]).name=='a23_bootstrap_worker.py' and a.canonical(Path(worker.args[3]))==a.canonical(job_path),'bootstrap worker job differs');f.require(f.sha(a.read(a.canonical(Path(worker.args[2]))))==f.sha(a.read(Path(__file__).resolve().with_name('a23_bootstrap_worker.py'))),'bootstrap worker source differs');return dict(mode='observed_bootstrap_worker_exit',worker_exited=True,pid=worker.pid,returncode=worker.returncode,**base),raw

def freeze(job_path,receiver,supervisor,output,*,worker=None,static_model=False,checkpoint=None):
    observation,job_raw=observe(Path(job_path),worker,static_model);job=f.parse(job_raw);receiver=a.canonical(receiver);supervisor=a.canonical(supervisor);output=a.canonical(output);f.require(type(job) is dict and job.get('schema')=='A23-collection-worker-job-1','bootstrap job schema differs')
    roots=tuple(Path(job[n]) for n in ('root','journal'));f.require(not output.exists() and all(not output.is_relative_to(p) and not p.is_relative_to(output) for p in (*roots,receiver,supervisor)),'new nonoverlapping bootstrap output required');_,ref=a.build_scope(receiver);supref=ar.old.j.ar.old.sv.build_info(supervisor);metadata,files,dirs=capture(job,checkpoint)
    output.mkdir(mode=0o700);a.put(output,'FORENSIC_ATTEMPT',b'one bootstrap forensic copy\n');(output/'raw').mkdir()
    for name in dirs:(output/'raw'/name).mkdir(parents=True,exist_ok=True)
    for name,raw in files.items():a.put(output,'raw/'+name,raw)
    a.put(output,'job.json',job_raw);meta=dict(schema='A23-bootstrap-capture-1',receiver_build=ref,supervisor_build=supref,capture=metadata,raw_files=a.inventory(files),raw_directories=dirs,observation=observation,**ar.FALSE);a.put(output,'capture.json',f.encode(meta));a.put(output,'analysis.json',f.encode(ar.derive(output,meta,job,receiver,supervisor)));f.require(observe(Path(job_path),worker,static_model)[0]==observation,'bootstrap worker changed');a.seal(output);return ar.analyze(output,receiver,supervisor)
