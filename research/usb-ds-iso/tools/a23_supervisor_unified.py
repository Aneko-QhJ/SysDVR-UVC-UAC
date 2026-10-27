"""Single bounded supervisor candidate; pinned offline fixture, no production API."""
from pathlib import Path
import os,selectors,signal,subprocess,sys,time
import a23_supervisor_unified_materials as m


def run_fixture(script,pin,name,seed,output):
    script,seed,output=map(Path,(script,seed,output))
    m.require(name in m.CASES and script.name=='a23_supervisor_unified_fixture.py','fixed unified fixture required')
    for p in (script,seed,output):m.require(p.is_absolute() and p==p.resolve() and not p.is_relative_to('/Volumes'),'canonical non-volume fixture path required')
    m.require(seed.is_dir() and not output.exists() and m.sha(script.read_bytes())==pin,'unified fixture pin/source/output differs')
    o=dict(schema='A23-supervisor-unified-observation-1',case=name,material_case=m.material_case(name),spawned=False,spawn_error=False,reaped=False,returncode=None,
        timed_out=False,stdout_eof=False,stderr_eof=False,reader_error=False,selector_error=False,read_interrupts=0,wait_error=False,wait_timed_out=False,
        group_kill_attempted=False,group_kill_outcome='none',fallback_kill_attempted=False,fallback_kill_outcome='none',limit_exceeded=None,
        stdout_bytes=0,stderr_bytes=0,launches=0,retries=0,leader_reaped_before_signal=False,provenance_authenticated=False,native_context_refreshed=False,
        clock_domain='supervisor_monotonic',close_attempts=[],close_completed=[],close_errors=[],completion_wait_attempted=False,cleanup_wait_attempted=False)
    owned={'child':None,'selector':None,'stdout':None,'stderr':None}
    try:
        if name=='spawn-error':raise OSError('injected fixed-fixture spawn failure')
        child=subprocess.Popen([sys.executable,'-I','-B',str(script),name,str(seed),str(output)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,start_new_session=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    except OSError:o['spawn_error']=True;return o,b'',b'',owned
    o['spawned']=True;o['launches']=1;owned.update(child=child,stdout=child.stdout,stderr=child.stderr)
    buffers={'stdout':bytearray(),'stderr':bytearray()};deadline=time.monotonic()+0.5
    def terminate_owned():
        if o['group_kill_attempted']:return
        # No poll/reap before signaling the owned leader's process group.
        o['group_kill_attempted']=True
        try:
            if name in ('group-kill-error','cleanup-multiple-errors'):raise PermissionError('injected group signal failure')
            if name=='group-kill-not-found':raise ProcessLookupError('injected missing group')
            os.killpg(child.pid,signal.SIGKILL);o['group_kill_outcome']='sent'
        except ProcessLookupError:o['group_kill_outcome']='not_found'
        except OSError:o['group_kill_outcome']='error'
        if o['group_kill_outcome']!='sent':
            o['fallback_kill_attempted']=True
            try:
                if name=='cleanup-multiple-errors':raise PermissionError('injected direct signal failure')
                os.kill(child.pid,signal.SIGKILL);o['fallback_kill_outcome']='sent'
            except ProcessLookupError:o['fallback_kill_outcome']='not_found'
            except OSError:o['fallback_kill_outcome']='error'
    try:
        selector=selectors.DefaultSelector();owned['selector']=selector
        for label in ('stdout','stderr'):
            stream=owned[label];os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,label)
        while selector.get_map():
            if name=='selector-error' and buffers['stdout']:o['selector_error']=True;terminate_owned();break
            remaining=deadline-time.monotonic()
            if remaining<=0:o['timed_out']=True;terminate_owned();break
            try:ready=selector.select(remaining)
            except InterruptedError:continue
            except OSError:o['selector_error']=True;terminate_owned();break
            for key,_ in ready:
                label=key.data
                try:
                    if name=='read-interrupted' and not o['read_interrupts']:o['read_interrupts']+=1;raise InterruptedError('injected read EINTR')
                    chunk=os.read(key.fileobj.fileno(),4096)
                except (InterruptedError,BlockingIOError):continue
                except OSError:o['reader_error']=True;terminate_owned();break
                if not chunk:o[label+'_eof']=True;selector.unregister(key.fileobj);continue
                buffers[label].extend(chunk[:max(0,m.LIMITS[label]+1-len(buffers[label]))])
                if len(buffers[label])>m.LIMITS[label]:o['limit_exceeded']=label;terminate_owned();break
                if name=='read-error':o['reader_error']=True;terminate_owned();break
            if o['reader_error'] or o['limit_exceeded']:break
        if not o['group_kill_attempted']:
            o['completion_wait_attempted']=True
            try:child.wait(timeout=max(0.001,deadline-time.monotonic()));o['reaped']=True;o['returncode']=child.returncode
            except subprocess.TimeoutExpired:o['timed_out']=True;terminate_owned()
            except OSError:o['wait_error']=True;terminate_owned()
    except (OSError,ValueError):o['reader_error']=True;terminate_owned()
    finally:
        for label in m.CLOSE_ORDER:
            o['close_attempts'].append(label)
            try:
                if label in m.close_errors(name):raise OSError('injected parent resource close failure')
                if owned[label] is not None:owned[label].close()
                o['close_completed'].append(label)
            except OSError:o['close_errors'].append(label)
        if not o['reaped']:
            terminate_owned();o['cleanup_wait_attempted']=True
            try:
                if name in ('wait-error','close-and-wait-error'):raise OSError('injected cleanup wait failure')
                if name in ('wait-timeout','cleanup-multiple-errors'):raise subprocess.TimeoutExpired('unified fixture cleanup',0.5)
                child.wait(timeout=0.5);o['reaped']=True;o['returncode']=child.returncode
            except subprocess.TimeoutExpired:o['wait_error']=True;o['wait_timed_out']=True
            except OSError:o['wait_error']=True
    stdout,stderr=bytes(buffers['stdout']),bytes(buffers['stderr']);o['stdout_bytes']=len(stdout);o['stderr_bytes']=len(stderr)
    return o,stdout,stderr,owned


def harness_finish(owned,o):
    """External test rescue; never updates the candidate's observations."""
    for label in o['close_errors']:
        if owned[label] is not None:owned[label].close()
    child=owned['child'];rescue=bool(child is not None and not o['reaped'])
    if rescue:child.kill()
    code=child.wait(timeout=3) if child is not None else None
    return dict(rescue_used=rescue,resource_rescues=list(o['close_errors']),direct_child_reaped=child is not None,returncode=code,
                admission_upgraded=False,descendant_reaping_verified=False)
