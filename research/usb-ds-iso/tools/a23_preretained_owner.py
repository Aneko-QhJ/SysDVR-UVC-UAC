"""Offline pre-retained Popen prototype, pinned to inspected CPython semantics."""
from pathlib import Path
import base64
import math
import os
import subprocess
import sys
import time

from a23_terminal_owner import Result
from a23_spawn_boundary_owner import SamplerOwner as PreviousOwner
import a23_terminal_deadline as prior

POPEN = subprocess.Popen


class SamplerOwner(PreviousOwner):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._initialization_entered = False
        self._slot.state.update(process_object_reserved=False, initialization_entered=False,
            initialization_returned=False, pid_registered=False, creation_unresolved=False,
            no_process_started_verified=True)
        self._construction_checkpoint = lambda _: None

    def _create(self, *args, **kwargs):
        point = self._construction_checkpoint
        point('before_allocation')
        self._slot.child = POPEN.__new__(POPEN)
        self._slot.state['process_object_reserved'] = True
        point('allocated')
        # From this point an interruption cannot prove that no process was created.
        self._initialization_entered = True
        self._slot.state.update(initialization_entered=True, no_process_started_verified=False)
        point('before_initialize')
        POPEN.__init__(self._slot.child, *args, **kwargs)
        self._slot.state['initialization_returned'] = True
        point('after_initialize')
        return self._slot.child

    def _registered(self):
        pid = getattr(self._slot.child, 'pid', None)
        return type(pid) is int and pid > 0

    def observation(self):
        state = super().observation()
        owns = state['owns_runtime_slot']
        state['pid_registered'] = self._registered()
        state['creation_unresolved'] = bool(self._initialization_entered and not self._registered())
        if owns and state['creation_unresolved']:
            state.update(owner_status='creation_unresolved', pending_handle_retained=True)
        elif owns and not self._initialization_entered:
            state.update(owner_status='closed' if self._slot.started else 'idle', pending_handle_retained=False)
        return state

    def _cleanup(self, checkpoint):
        if self._registered():
            self._slot.state.update(pid_registered=True, creation_unresolved=False)
            return super()._cleanup(checkpoint)
        slot = self._slot
        slot.state['cleanup_passes'] += 1
        slot.state['creation_unresolved'] = self._initialization_entered
        # A reserved object without a registered PID must never enter terminate/wait.
        # Known pipe objects can still be closed. The unresolved object remains retained.
        first = None
        for name in ('stdin', 'stdout', 'stderr'):
            stream = getattr(slot.child, name, None)
            if stream is not None and all(stream is not old for old in slot.streams):
                slot.streams.append(stream)
            if stream is not None and not stream.closed:
                try:
                    checkpoint('before_unregistered_close_' + name)
                    stream.close()
                    checkpoint('after_unregistered_close_' + name)
                except BaseException as exc:
                    self._error(exc, 'unregistered_close_' + name, cleanup=True)
                    if first is None:
                        first = exc
        return first

    def handoff(self, **kwargs):
        # The prior handoff constructs its own class; do not silently downgrade this owner.
        raise prior.Rejected('preretained_handoff_not_implemented')

    def capture(self, directory, anchor, pin, *, timeout=2.0, _command=None, _checkpoint=None):
        self._check()
        slot = self._slot
        prior.require(not slot.started, 'capture_already_attempted')
        prior.intake.recovery.check(anchor, pin, {})
        prior.intake.path_policy(directory)
        prior.require(type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= 30, 'time_budget')
        prior.require(len(anchor) <= 8192, 'anchor_limit')
        request = prior.encode(dict(directory=os.fspath(directory), anchor=base64.b64encode(anchor).decode(), pin=pin))
        prior.require(len(request) <= prior.MAX_REQUEST, 'request_limit')
        checkpoint = _checkpoint or (lambda _: None)
        self._construction_checkpoint = checkpoint
        state = slot.state
        slot.started = slot.busy = True
        start = time.monotonic()
        deadline = start + timeout
        primary = None
        payload = None
        def point(name):
            state['phase'] = name
            checkpoint(name)
        try:
            point('before_spawn')
            command = _command if _command is not None else [sys.executable, '-B', str(Path(prior.__file__).with_name('a23_terminal_deadline_worker.py'))]
            slot.child = self._create(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, bufsize=0, close_fds=True,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            slot.streams = [slot.child.stdin, slot.child.stdout]
            state['spawned'] = True
            point('after_spawn')
            point('exchange')
            status, wire = prior.exchange(slot.child, request, deadline)
            state.update(response_size=len(wire), response_sha256=prior.intake.recovery.sha(wire))
            prior.require(status == 'received', status)
            point('after_exchange')
            left = deadline - time.monotonic()
            prior.require(left > 0, 'deadline')
            point('wait')
            try:
                self._wait(left)
            except subprocess.TimeoutExpired:
                raise prior.Rejected('deadline')
            point('after_wait')
            prior.require(time.monotonic() < deadline, 'deadline')
            prior.require(state['returncode'] == 0, 'child_exit')
            payload = prior.decode_response(wire, anchor, pin)
            point('after_decode')
            prior.require(time.monotonic() < deadline, 'deadline')
        except BaseException as exc:
            self._error(exc, state['phase'])
            payload = None
            if not isinstance(exc, (ValueError, OSError, KeyError, TypeError)):
                primary = exc
        finally:
            # Even a second Python exception in a cleanup step cannot erase the retained slot.
            try:
                cleanup_error = self._cleanup(checkpoint)
                if primary is None:
                    primary = cleanup_error
            finally:
                slot.busy = False
                state['elapsed_seconds'] = time.monotonic() - start
        if primary is not None:
            raise primary
        clean = slot.waited and all(stream.closed for stream in slot.streams)
        if payload is not None and clean and not state['cleanup_errors'] and state['reason'] is None:
            state.update(accepted=True, reason='sampled')
            return Result(self.observation(), *payload)
        return Result(self.observation())
