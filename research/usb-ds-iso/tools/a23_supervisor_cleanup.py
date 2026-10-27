"""One-shot cleanup candidate for the fixed offline pipe/exit fixture."""
from pathlib import Path
import os,selectors,signal,subprocess,sys,time
import a23_supervisor_cleanup_materials as m


def run_fixture(script,pin,name,seed,output):
    script,seed,output=map(Path,(script,seed,output))
    m.require(name in m.CASES and script.name=='a23_supervisor_cleanup_fixture.py','fixed cleanup fixture required')
    for p in (script,seed,output):m.require(p.is_absolute() and p==p.resolve() and not p.is_relative_to('/Volumes'),'canonical non-volume fixture path required')
    m.require(seed.is_dir() and not output.exists() and m.sha(script.read_bytes())==pin,'fixture pin/source/output differs')
    o=dict(schema='A23-supervisor-cleanup-observation-1',case=name,spawned=True,reaped=False,returncode=None,timed_out=False,
           stdout_eof=False,stderr_eof=False,reader_error=False,selector_error=False,read_interrupts=0,wait_error=False,wait_timed_out=False,
           group_kill_attempted=False,group_kill_outcome='none',fallback_kill_attempted=False,fallback_kill_outcome='none',
           stdout_bytes=0,stderr_bytes=0,launches=1,retries=0,leader_reaped_before_signal=False,provenance_authenticated=False,
           native_context_refreshed=False,clock_domain='supervisor_monotonic')
    child=subprocess.Popen([sys.executable,'-I','-B',str(script),name,str(seed),str(output)],stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    buffers={'stdout':bytearray(),'stderr':bytearray()};selector=selectors.DefaultSelector();deadline=time.monotonic()+0.5
    def terminate_owned():
        # Never poll/reap the leader before the group signal: retain its PID.
        if o['group_kill_attempted']:return
        o['group_kill_attempted']=True
        try:
            if name in ('group-kill-error','cleanup-multiple-errors'):raise PermissionError('injected killpg failure')
            if name=='group-kill-not-found':raise ProcessLookupError('injected missing group')
            os.killpg(child.pid,signal.SIGKILL);o['group_kill_outcome']='sent'
        except ProcessLookupError:o['group_kill_outcome']='not_found'
        except OSError:o['group_kill_outcome']='error'
        if o['group_kill_outcome']!='sent':
            o['fallback_kill_attempted']=True
            try:
                if name=='cleanup-multiple-errors':raise PermissionError('injected direct kill failure')
                os.kill(child.pid,signal.SIGKILL);o['fallback_kill_outcome']='sent'
            except ProcessLookupError:o['fallback_kill_outcome']='not_found'
            except OSError:o['fallback_kill_outcome']='error'
    try:
        for label,stream in (('stdout',child.stdout),('stderr',child.stderr)):os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,label)
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
                buffers[label].extend(chunk)
                if len(buffers[label])>m.LIMIT:o['reader_error']=True;terminate_owned();break
                if name=='read-error':o['reader_error']=True;terminate_owned();break
            if o['reader_error']:break
        if not o['group_kill_attempted']:
            try:child.wait(timeout=max(0.001,deadline-time.monotonic()));o['reaped']=True;o['returncode']=child.returncode
            except subprocess.TimeoutExpired:o['timed_out']=True;terminate_owned()
            except OSError:o['wait_error']=True;terminate_owned()
    except (OSError,ValueError):o['reader_error']=True;terminate_owned()
    finally:
        selector.close();child.stdout.close();child.stderr.close()
        if not o['reaped']:
            terminate_owned()
            try:
                if name=='wait-error':raise OSError('injected cleanup wait failure')
                if name in ('wait-timeout','cleanup-multiple-errors'):raise subprocess.TimeoutExpired('fixed fixture cleanup',0.5)
                child.wait(timeout=0.5);o['reaped']=True;o['returncode']=child.returncode
            except subprocess.TimeoutExpired:o['wait_error']=True;o['wait_timed_out']=True
            except OSError:o['wait_error']=True
    stdout,stderr=bytes(buffers['stdout'][:m.LIMIT+1]),bytes(buffers['stderr'][:m.LIMIT+1]);o['stdout_bytes']=len(stdout);o['stderr_bytes']=len(stderr)
    # An un-reaped child is returned to the test harness, never certified complete.
    return o,stdout,stderr,child


def harness_reap(child,observation):
    """Test-only rescue, recorded separately; it cannot upgrade admission."""
    rescue=not observation['reaped']
    if rescue:child.kill()
    code=child.wait(timeout=3)
    return dict(rescue_used=rescue,direct_child_reaped=True,returncode=code,admission_upgraded=False,descendant_reaping_verified=False)
