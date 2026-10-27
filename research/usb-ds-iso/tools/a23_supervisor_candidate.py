"""Bounded, one-shot supervisor for the pinned offline Python fixture only."""
from pathlib import Path
import os,selectors,signal,subprocess,sys,time
import a23_supervisor_materials as m


def run_fixture(script,expected_sha256,name,seed,output,*,popen=subprocess.Popen):
    script=Path(script);seed=Path(seed);output=Path(output)
    m.require(name in m.CASES and script.name=='a23_supervised_worker_fixture.py','fixed fixture required')
    for path in (script,seed,output):m.require(path.is_absolute() and path==path.resolve() and not path.is_relative_to('/Volumes'),'canonical non-volume fixture path required')
    m.require(not output.exists() and seed.is_dir() and m.sha(script.read_bytes())==expected_sha256,'pinned fixture/source/output differs')
    o=dict(schema='A23-supervisor-observation-1',case=name,material_case=m.material_case(name),spawned=False,reaped=False,returncode=None,
           timed_out=False,limit_exceeded=None,group_kill_sent=False,stdout_eof=False,stderr_eof=False,reader_error=False,spawn_error=False,
           cleanup_error=False,stdout_bytes=0,stderr_bytes=0,launches=0,retries=0,clock_domain='supervisor_monotonic',provenance_authenticated=False,native_context_refreshed=False)
    buffers={'stdout':bytearray(),'stderr':bytearray()};limits={'stdout':m.STDOUT_LIMIT,'stderr':m.STDERR_LIMIT}
    command=[sys.executable,'-I','-B',str(script),name,str(seed),str(output)]
    try:child=popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    except OSError:
        o['spawn_error']=True;return o,b'',b''
    o['spawned']=True;o['launches']=1
    deadline=time.monotonic()+(0.5 if name.startswith('timeout-') else 2.0)
    selector=selectors.DefaultSelector()
    def kill_group():
        if o['group_kill_sent']:return
        try:os.killpg(child.pid,signal.SIGKILL);o['group_kill_sent']=True
        except ProcessLookupError:o['group_kill_sent']=True
        except OSError:o['cleanup_error']=True
    try:
        for label,stream in (('stdout',child.stdout),('stderr',child.stderr)):os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,label)
        while selector.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:o['timed_out']=True;kill_group();break
            for key,_ in selector.select(remaining):
                label=key.data
                try:chunk=os.read(key.fileobj.fileno(),4096)
                except BlockingIOError:continue
                if not chunk:o[label+'_eof']=True;selector.unregister(key.fileobj);continue
                buffers[label].extend(chunk[:max(0,limits[label]+1-len(buffers[label]))])
                if len(buffers[label])>limits[label]:o['limit_exceeded']=label;kill_group();break
            if o['limit_exceeded']:break
        if not o['timed_out'] and not o['limit_exceeded']:
            try:child.wait(timeout=max(0.001,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:o['timed_out']=True;kill_group()
    except (OSError,ValueError):o['reader_error']=True;kill_group()
    finally:
        selector.close();child.stdout.close();child.stderr.close()
        if child.poll() is None:kill_group()
        try:child.wait(timeout=1.0);o['reaped']=True;o['returncode']=child.returncode
        except subprocess.TimeoutExpired:o['cleanup_error']=True
    stdout,stderr=bytes(buffers['stdout']),bytes(buffers['stderr']);o['stdout_bytes']=len(stdout);o['stderr_bytes']=len(stderr)
    return o,stdout,stderr
