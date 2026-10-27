"""Offline caller-owned sampler. Runtime object transfer is not PID recovery."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import base64
import copy
import math
import os
import subprocess
import sys
import time

import a23_terminal_deadline as prior


@dataclass
class Result:
    lifecycle: dict
    cache: dict | None = None
    report: dict | None = None
    classification: dict | None = None


@dataclass
class _Slot:
    holder: object
    child: object = None
    streams: list = field(default_factory=list)
    waited: bool = False
    busy: bool = False
    started: bool = False
    state: dict = field(default_factory=dict)


class SamplerOwner:
    """Keep this object before capture; exceptions never need to carry a PID."""
    def __init__(self, *, cleanup_grace=0.2):
        prior.require(type(cleanup_grace) in (int, float) and math.isfinite(cleanup_grace) and 0 < cleanup_grace <= 30, 'cleanup_budget')
        self.cleanup_grace = cleanup_grace
        self.successor = None
        self._slot = _Slot(self)
        self._slot.state = dict(schema='A23-terminal-owner-observation-1', accepted=False, reason=None,
            spawned=False, deadline_expired=False, direct_wait_verified=False, returncode=None,
            caller_interrupted=False, interruption_types=[], cleanup_errors=[], cleanup_passes=0,
            handoffs=0, phase='idle', response_size=0, response_sha256=None,
            task_complete=False, atomic_directory_snapshot_verified=False,
            historical_sync_or_wait_inferred=False, model_only=True, **prior.intake.recovery.FALSE)

    def _check(self):
        prior.require(self._slot.holder is self, 'owner_transferred')
        prior.require(not self._slot.busy, 'owner_busy')

    def observation(self):
        slot = self._slot
        state = copy.deepcopy(slot.state)
        owns = slot.holder is self
        pending = slot.child is not None and not slot.waited
        streams = sum(not stream.closed for stream in slot.streams)
        state.update(owner_status='transferred' if not owns else 'pending' if pending or streams else 'closed' if slot.started else 'idle',
                     pending_handle_retained=bool(owns and pending), pending_streams=streams if owns else 0,
                     owns_runtime_slot=owns, successor_available=self.successor is not None)
        return state

    def _error(self, exc, operation, *, cleanup=False):
        state = self._slot.state
        state['accepted'] = False
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            state['caller_interrupted'] = True
            state['interruption_types'].append(dict(operation=operation, type=type(exc).__name__))
        if cleanup:
            state['cleanup_errors'].append(dict(operation=operation, type=type(exc).__name__))
        if state['reason'] is None:
            state['reason'] = str(exc) if isinstance(exc, prior.Rejected) else type(exc).__name__
        if state['reason'] == 'deadline':
            state['deadline_expired'] = True

    def _wait(self, timeout):
        slot = self._slot
        code = slot.child.wait(timeout=timeout)
        slot.waited = True
        slot.state.update(direct_wait_verified=True, returncode=code)

    def _cleanup(self, checkpoint):
        """Finite single pass; retain any wait/stream still pending for explicit finish."""
        slot = self._slot
        state = slot.state
        state['cleanup_passes'] += 1
        first = None
        def step(name, action):
            nonlocal first
            try:
                state['phase'] = 'before_' + name
                checkpoint('before_' + name)
                action()
                state['phase'] = 'after_' + name
                checkpoint('after_' + name)
            except BaseException as exc:
                self._error(exc, state['phase'], cleanup=True)
                if first is None and not isinstance(exc, (OSError, subprocess.TimeoutExpired)):
                    first = exc
        if slot.child is not None:
            for method in ('terminate', 'kill'):
                if slot.waited:
                    break
                def send(method=method):
                    state[method + '_attempts'] = state.get(method + '_attempts', 0) + 1
                    getattr(slot.child, method)()
                    state[method + '_returns'] = state.get(method + '_returns', 0) + 1
                step(method, send)
                if not slot.waited:
                    step('wait_' + method, lambda: self._wait(self.cleanup_grace))
            for index, stream in enumerate(slot.streams):
                if not stream.closed:
                    step('close_' + str(index), stream.close)
        if first is not None:
            state['reason'] = state['reason'] or type(first).__name__
        return first

    def finish(self, *, _checkpoint=None):
        """Explicitly continue cleanup; never relaunch or restore an accepted result."""
        self._check()
        slot = self._slot
        slot.busy = True
        try:
            error = self._cleanup(_checkpoint or (lambda _: None))
        finally:
            slot.busy = False
        if error is not None:
            raise error
        return self.observation()

    def handoff(self, *, _checkpoint=None):
        """One holder assignment commits transfer. Successor remains reachable on error."""
        self._check()
        prior.require(self.observation()['owner_status'] == 'pending', 'nothing_pending')
        checkpoint = _checkpoint or (lambda _: None)
        slot = self._slot
        slot.busy = True
        try:
            successor = SamplerOwner(cleanup_grace=self.cleanup_grace)
            successor._slot = slot
            self.successor = successor
            checkpoint('handoff_prepared')
            # A single holder assignment commits authority; the child never leaves the slot.
            slot.holder = successor
            slot.state['handoffs'] += 1
            checkpoint('handoff_committed')
            return successor
        except BaseException as exc:
            self._error(exc, 'handoff')
            raise
        finally:
            slot.busy = False

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
            slot.child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
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
