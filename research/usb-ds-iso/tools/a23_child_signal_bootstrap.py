"""Offline signal-policy bootstrap. Restore before importing the frozen sampler."""
import hashlib
import json
import os
import signal
import sys

LIMIT=2048
MODES={'normal','before_reset','after_reset','stall_after_ready','stall_before_ready',
       'bad_token','bad_mask','bad_handler','partial_ready','oversized_ready','exit_before_ready','reset_error'}


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def label(value):return 'default_int_handler' if value is signal.default_int_handler else 'SIG_DFL' if value==signal.SIG_DFL else 'SIG_IGN' if value==signal.SIG_IGN else 'other'
def write(fd,raw):
    view=memoryview(raw)
    for _ in range(32):
        try:count=os.write(fd,view)
        except InterruptedError:continue
        if count<=0:raise ValueError('status write progress')
        view=view[count:]
        if not view:return
    raise ValueError('status write budget')
def emit(fd,value):write(fd,encode(value)+b'\n')
def block():
    reader,writer=os.pipe()
    os.read(reader,1)
    os.close(writer)
def pause(fd,phase):
    emit(fd,dict(checkpoint=phase))
    if os.read(0,1)!=b'R':raise ValueError('fixture gate')


def main():
    fd=None
    try:
        if len(sys.argv)!=3:return 2
        fd=int(sys.argv[1]);raw=sys.argv[2].encode();policy=json.loads(raw)
        if set(policy)!={'schema','launch_token','target_mask','mode'} or policy['schema']!='A23-child-signal-policy-1' or encode(policy)!=raw:return 2
        mask=policy['target_mask'];mode=policy['mode']
        if type(mask) is not list or any(type(v) is not int or v not in signal.valid_signals() for v in mask) or mask!=sorted(set(mask)) or mode not in MODES:return 2
        if type(policy['launch_token']) is not str or len(policy['launch_token'])!=32 or any(c not in '0123456789abcdef' for c in policy['launch_token']):return 2
        before=sorted(int(v) for v in signal.pthread_sigmask(signal.SIG_BLOCK,set()))
        before_int=label(signal.getsignal(signal.SIGINT));before_term=label(signal.getsignal(signal.SIGTERM))
        if mode=='exit_before_ready':return 2
        if mode=='stall_before_ready':block()
        if mode=='before_reset':pause(fd,'before_reset')
        pending=signal.SIGINT in signal.sigpending()
        signal.signal(signal.SIGINT,signal.default_int_handler)
        signal.signal(signal.SIGTERM,signal.SIG_DFL)
        if mode=='reset_error':raise OSError('injected signal reset error')
        signal.pthread_sigmask(signal.SIG_SETMASK,set(mask))
        after=sorted(int(v) for v in signal.pthread_sigmask(signal.SIG_BLOCK,set()))
        if after!=mask:raise ValueError('child mask mismatch')
        if mode=='after_reset':pause(fd,'after_reset')
        report=dict(schema='A23-child-signal-ready-1',launch_token=policy['launch_token'],
            policy_sha256=hashlib.sha256(raw).hexdigest(),mask_before=before,mask_after=after,
            sigint_before=before_int,sigterm_before=before_term,
            sigint_after=label(signal.getsignal(signal.SIGINT)),sigterm_after=label(signal.getsignal(signal.SIGTERM)),
            pending_sigint_before_reset=pending)
        if mode=='bad_token':report['launch_token']='0'*32
        if mode=='bad_mask':report['mask_after']=[True]
        if mode=='bad_handler':report['sigterm_after']='SIG_IGN'
        if mode=='partial_ready':write(fd,encode(report)[:len(encode(report))//2]);os.close(fd);fd=None;block()
        if mode=='oversized_ready':write(fd,b'x'*(LIMIT+1));os.close(fd);fd=None;block()
        emit(fd,report);os.close(fd);fd=None
        if mode in ('bad_token','bad_mask','bad_handler','stall_after_ready'):block()
        # No target-directory operation occurs until the parent validates ready and sends the request.
        import a23_terminal_deadline_worker as worker
        return worker.main()
    except KeyboardInterrupt:
        return 130
    except (ValueError,OSError,KeyError,TypeError):
        return 2
    finally:
        if fd is not None:
            try:os.close(fd)
            except OSError:pass


if __name__=='__main__':raise SystemExit(main())
