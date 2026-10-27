"""Offline /private/tmp directory sampler. Equal observations are not an atomic snapshot."""
from contextlib import ExitStack
import os,stat
from pathlib import PurePosixPath
import a23_terminal_recovery_materials as recovery


class IntakeError(ValueError):
    def __init__(self,code):self.code=code;super().__init__(code)


def require(condition,code):
    if not condition:raise IntakeError(code)


def identity(value):return (value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_gid)
def fingerprint(value):return (*identity(value),value.st_nlink,value.st_size,value.st_mtime_ns,value.st_ctime_ns)


def path_policy(directory):
    path=os.fspath(directory);require(type(path) is str and path==str(PurePosixPath(path)) and path.startswith('/private/tmp/') and '..' not in PurePosixPath(path).parts,'path_policy')
    return PurePosixPath(path).parts


def open_chain(parts,stack):
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
    fd=os.open('/',flags);stack.callback(os.close,fd);chain=[identity(os.fstat(fd))]
    for part in parts[1:]:
        fd=os.open(part,flags,dir_fd=fd);stack.callback(os.close,fd);chain.append(identity(os.fstat(fd)))
    return fd,chain


def bounded_read(fd,limit=8192):
    chunks=[];size=0
    for _ in range(32):
        try:data=os.read(fd,min(4096,limit+1-size))
        except InterruptedError:continue
        if not data:return b''.join(chunks)
        size+=len(data);require(size<=limit,'file_limit' if limit==8192 else 'remaining_limit');chunks.append(data)
    raise IntakeError('read_budget')


def entry(directory,name,checkpoint,remaining):
    try:before=os.stat(name,dir_fd=directory,follow_symlinks=False)
    except FileNotFoundError:return None
    require(stat.S_ISREG(before.st_mode),'entry_type');require(before.st_size<=8192,'file_limit');require(before.st_size<=remaining,'total_limit');checkpoint('after_lstat',name)
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory)
    try:
        opened=os.fstat(fd);require(stat.S_ISREG(opened.st_mode),'opened_type');require(fingerprint(opened)==fingerprint(before),'entry_changed');checkpoint('after_open',name)
        first=bounded_read(fd,min(8192,remaining));checkpoint('after_first_read',name);os.lseek(fd,0,os.SEEK_SET);second=bounded_read(fd,min(8192,remaining))
        require(first==second,'content_changed');after=os.fstat(fd);require(fingerprint(opened)==fingerprint(after) and len(first)==opened.st_size,'file_changed')
        checkpoint('after_fd_validation',name);current=os.stat(name,dir_fd=directory,follow_symlinks=False);require(fingerprint(after)==fingerprint(current),'entry_changed')
        return first,fingerprint(after)
    finally:os.close(fd)


def view(directory,checkpoint):
    files={};metadata={};total=0
    for name in sorted(recovery.ALLOWED):
        found=entry(directory,name,checkpoint,131072-total)
        if found is not None:
            data,record=found;files[name]=data;metadata[name]=record;total+=len(data);require(total<=131072,'total_limit')
    return files,metadata


def capture(directory,raw,pin,checkpoint=None):
    recovery.check(raw,pin,{});parts=path_policy(directory);checkpoint=checkpoint or (lambda *_:None)
    try:
        with ExitStack() as stack:
            root,chain=open_chain(parts,stack);before=fingerprint(os.fstat(root));checkpoint('directory_open',None)
            first,first_metadata=view(root,checkpoint);checkpoint('between_views',None)
            second,second_metadata=view(root,checkpoint);require(first==second and first_metadata==second_metadata,'view_changed')
            require(fingerprint(os.fstat(root))==before,'directory_changed')
            with ExitStack() as final_stack:
                current,current_chain=open_chain(parts,final_stack);require(chain==current_chain and fingerprint(os.fstat(current))==before,'directory_path_changed')
            checkpoint('validated',None)
            result=recovery.classify(raw,pin,second)
            report=dict(schema='A23-terminal-intake-report-1',equal_views=2,per_file_equal_reads=2,
                file_metadata={name:list(value) for name,value in second_metadata.items()},file_count=len(second),
                total_bytes=sum(map(len,second.values())),directory_identity_chain=[list(value) for value in chain],
                atomic_directory_snapshot_verified=False,historical_sync_or_wait_inferred=False,model_only=True)
        return second,report,result
    except IntakeError:raise
    except OSError as exc:raise IntakeError('io_error') from exc
