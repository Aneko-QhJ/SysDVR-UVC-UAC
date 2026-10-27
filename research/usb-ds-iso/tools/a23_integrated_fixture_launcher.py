"""Bounded fixture-only launcher with synchronized prelaunch publication."""
from pathlib import Path
import os,selectors,signal,subprocess,sys,time
import a23_integrated_fixture_materials as m
import a23_integrated_fixture_io as io
import a23_supervisor_unified as cleanup


def run(script,job,external_pin,fixture_pin):
    script,job=map(Path,(script,job))
    for p in (script,job):m.require(p.is_absolute() and p==p.resolve() and p.is_relative_to('/private/tmp'),'canonical temporary integrated fixture required')
    m.require(script.name=='a23_integrated_fixture_worker.py' and job.is_dir(),'fixed integrated fixture/job required')
    raw=(job/'launch.json').read_bytes();praw=(job/'integrated-plan.json').read_bytes()
    # Acquire ownership before any trace write, including on concurrent calls.
    # The use and attempt records are fixture records, never shared32 permits.
    with (job/'launcher-use.json').open('xb',buffering=0) as stream:
        io.write_all(stream.fileno(),m.encode(m.use_record(raw,praw)));os.fsync(stream.fileno())
    plan,launch=m.check_plan(praw,external_pin,raw)
    m.require(m.binding.digest(fixture_pin) and launch['fixture_sha256']==fixture_pin and m.sha(script.read_bytes())==fixture_pin,'integrated worker source pin differs')
    for name,h in plan['library_sha256'].items():m.require(m.sha((script.parent/'lib'/name).read_bytes())==h,'integrated worker library pin differs')
    files={p.relative_to(job/'inputs').as_posix():p.read_bytes() for p in (job/'inputs').rglob('*') if p.is_file()}
    m.binding.same(m.binding.inventory(files),launch['seed_files'],'integrated prelaunch seed bytes differ')
    m.require(not (job/'result').exists(),'integrated preexisting result refused')
    o=m.empty_observation();owned={'child':None,'selector':None,'stdout':None,'stderr':None};attempt=m.encode(m.binding.attempt(raw))
    def checkpoint(label,phase):
        if phase=='before' and plan['prelaunch_fail_before']==label:
            io.record(job,label,'injected_error');raise OSError('fixed parent sync failure')
        if phase=='after':io.record(job,label,'completed')
    try:io.publish_attempt(job,attempt,checkpoint)
    except OSError:
        attempted=(job/'launch-attempt.json').read_bytes() if (job/'launch-attempt.json').exists() else b''
        return m.observe(raw,praw,attempted,o,'prelaunch_io_error'),b'',b'',owned
    io.record(job,'launch.ready','completed');attempted=(job/'launch-attempt.json').read_bytes()
    try:
        if plan['parent_fault']=='spawn-error':raise OSError('fixed integrated spawn error')
        child=subprocess.Popen([sys.executable,'-I','-B',str(script),str(job)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,start_new_session=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    except OSError:return m.observe(raw,praw,attempted,o),b'',b'',owned
    o.update(spawned=True,spawn_error=False,launches=1);owned.update(child=child,stdout=child.stdout,stderr=child.stderr)
    buffers={'stdout':bytearray(),'stderr':bytearray()};deadline=time.monotonic()+0.5
    def terminate():
        if o['group_kill_attempted']:return
        o['group_kill_attempted']=True
        try:os.killpg(child.pid,signal.SIGKILL);o['group_kill_outcome']='sent'
        except ProcessLookupError:o['group_kill_outcome']='not_found'
        except OSError:o['group_kill_outcome']='error'
        if o['group_kill_outcome']!='sent':
            o['fallback_kill_attempted']=True
            try:os.kill(child.pid,signal.SIGKILL);o['fallback_kill_outcome']='sent'
            except ProcessLookupError:o['fallback_kill_outcome']='not_found'
            except OSError:o['fallback_kill_outcome']='error'
    try:
        selector=selectors.DefaultSelector();owned['selector']=selector
        for label in ('stdout','stderr'):
            stream=owned[label];os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,label)
        while selector.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:o['timed_out']=True;terminate();break
            try:ready=selector.select(remaining)
            except InterruptedError:continue
            except OSError:o['selector_error']=True;terminate();break
            for key,_ in ready:
                label=key.data
                try:chunk=os.read(key.fileobj.fileno(),4096)
                except (InterruptedError,BlockingIOError):continue
                except OSError:o['reader_error']=True;terminate();break
                if not chunk:o[label+'_eof']=True;selector.unregister(key.fileobj);continue
                buffers[label].extend(chunk[:max(0,m.supervisor.LIMITS[label]+1-len(buffers[label]))])
                if len(buffers[label])>m.supervisor.LIMITS[label]:o['limit_exceeded']=label;terminate();break
                if plan['parent_fault']=='read-error':o['reader_error']=True;terminate();break
            if o['reader_error'] or o['limit_exceeded']:break
        if not o['group_kill_attempted']:
            o['completion_wait_attempted']=True
            try:
                if plan['parent_fault']=='wait-error':raise OSError('fixed completion wait failure')
                child.wait(timeout=max(0.001,deadline-time.monotonic()));o['reaped']=True;o['returncode']=child.returncode
            except subprocess.TimeoutExpired:o['timed_out']=True;terminate()
            except OSError:o['wait_error']=True;terminate()
    except (OSError,ValueError):o['reader_error']=True;terminate()
    finally:
        for label in m.supervisor.CLOSE_ORDER:
            o['close_attempts'].append(label)
            try:
                if plan['parent_fault']==label+'-close-error':raise OSError('fixed resource close failure')
                if owned[label] is not None:owned[label].close()
                o['close_completed'].append(label)
            except OSError:o['close_errors'].append(label)
        if not o['reaped']:
            terminate();o['cleanup_wait_attempted']=True
            try:
                if plan['parent_fault']=='wait-error':raise OSError('fixed cleanup wait failure')
                child.wait(timeout=0.5);o['reaped']=True;o['returncode']=child.returncode
            except subprocess.TimeoutExpired:o['wait_error']=True;o['wait_timed_out']=True
            except OSError:o['wait_error']=True
    stdout,stderr=bytes(buffers['stdout']),bytes(buffers['stderr']);o['stdout_bytes']=len(stdout);o['stderr_bytes']=len(stderr)
    return m.observe(raw,praw,attempted,o),stdout,stderr,owned


def harness_finish(owned,observed):return cleanup.harness_finish(owned,observed['supervisor'])
