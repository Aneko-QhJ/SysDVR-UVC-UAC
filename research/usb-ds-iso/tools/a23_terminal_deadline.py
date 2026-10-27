"""Offline sampler supervision. Own the child handle; never infer old actors' wait."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import base64
import json
import math
import os
import selectors
import subprocess
import sys
import time

import a23_terminal_intake as intake

MAX_RESPONSE = 262144
MAX_REQUEST = 16384


@dataclass
class Observation:
    lifecycle: dict
    cache: dict | None = None
    report: dict | None = None
    classification: dict | None = None
    pending_process: object = None


class Rejected(ValueError):
    pass


def require(value, reason):
    if not value:
        raise Rejected(reason)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def decode_response(raw, anchor, pin):
    value = json.loads(raw)
    require(type(value) is dict and encode(value) == raw, 'response_encoding')
    require(set(value) == {'schema', 'files', 'report'} and value['schema'] == 'A23-terminal-deadline-wire-1', 'response_schema')
    files = value['files']
    require(type(files) is dict and set(files) <= intake.recovery.ALLOWED, 'response_files')
    require(all(type(v) is str for v in files.values()), 'response_file_type')
    cache = {name: base64.b64decode(data, validate=True) for name, data in files.items()}
    require(all(base64.b64encode(cache[n]).decode() == v for n, v in files.items()), 'response_base64')
    result = intake.recovery.classify(anchor, pin, cache)
    report = value['report']
    require(type(report) is dict, 'response_report')
    require(set(report) == {'schema', 'equal_views', 'per_file_equal_reads', 'file_metadata', 'file_count', 'total_bytes', 'directory_identity_chain', 'atomic_directory_snapshot_verified', 'historical_sync_or_wait_inferred', 'model_only'}, 'response_report_fields')
    require(report['schema'] == 'A23-terminal-intake-report-1' and type(report['equal_views']) is int and report['equal_views'] == 2 and type(report['per_file_equal_reads']) is int and report['per_file_equal_reads'] == 2, 'response_views')
    for key, expected in (('atomic_directory_snapshot_verified', False), ('historical_sync_or_wait_inferred', False), ('model_only', True)):
        require(report[key] is expected, 'response_report_claim')
    require(type(report['file_count']) is int and report['file_count'] == len(cache) and type(report['total_bytes']) is int and report['total_bytes'] == sum(map(len, cache.values())), 'response_inventory')
    metadata = report['file_metadata']
    require(type(metadata) is dict and set(metadata) == set(cache), 'response_metadata')
    require(all(type(v) is list and len(v) == 9 and all(type(x) is int for x in v) and v[6] == len(cache[n]) for n, v in metadata.items()), 'response_metadata_shape')
    chain = report['directory_identity_chain']
    require(type(chain) is list and 4 <= len(chain) <= 128 and all(type(v) is list and len(v) == 5 and all(type(x) is int for x in v) for v in chain), 'response_chain')
    return cache, report, result


def exchange(child, request, deadline):
    """Nonblocking pipe transport shares one absolute monotonic deadline."""
    output = bytearray()
    sent = 0
    with selectors.DefaultSelector() as selector:
        for stream in (child.stdin, child.stdout):
            os.set_blocking(stream.fileno(), False)
        selector.register(child.stdin, selectors.EVENT_WRITE, 'input')
        selector.register(child.stdout, selectors.EVENT_READ, 'output')
        while selector.get_map():
            left = deadline - time.monotonic()
            if left <= 0:
                return 'deadline', bytes(output)
            for key, _ in selector.select(left):
                if time.monotonic() >= deadline:
                    return 'deadline', bytes(output)
                try:
                    if key.data == 'input':
                        count = os.write(key.fd, request[sent:])
                        require(count > 0, 'input_no_progress')
                        sent += count
                        if sent == len(request):
                            selector.unregister(key.fileobj)
                            child.stdin.close()
                    else:
                        block = os.read(key.fd, min(4096, MAX_RESPONSE + 1 - len(output)))
                        output.extend(block)
                        if len(output) > MAX_RESPONSE:
                            return 'response_limit', bytes(output)
                        if not block:
                            selector.unregister(key.fileobj)
                except (BlockingIOError, InterruptedError):
                    continue
    return 'received', bytes(output)


def reap(child, state, grace):
    """Only use the directly retained Popen object. A signal is not a wait."""
    for method in ('terminate', 'kill'):
        state[method + '_attempted'] = True
        try:
            getattr(child, method)()
            state[method + '_call_returned'] = True
        except OSError as exc:
            state[method + '_error'] = type(exc).__name__
        try:
            state['returncode'] = child.wait(timeout=grace)
            state['direct_wait_verified'] = True
            return None
        except subprocess.TimeoutExpired:
            state['cleanup_wait_timeouts'] += 1
        except OSError as exc:
            state['wait_error'] = type(exc).__name__
    state['pending_handle_retained'] = True
    return child


def capture(directory, anchor, pin, *, timeout=2.0, cleanup_grace=0.25, _command=None):
    """Trusted caller/test command. No production launcher or PID-based recovery."""
    intake.recovery.check(anchor, pin, {})
    intake.path_policy(directory)
    for value in (timeout, cleanup_grace):
        require(type(value) in (int, float) and math.isfinite(value) and 0 < value <= 30, 'time_budget')
    require(len(anchor) <= 8192, 'anchor_limit')
    request = encode(dict(directory=os.fspath(directory), anchor=base64.b64encode(anchor).decode(), pin=pin))
    require(len(request) <= MAX_REQUEST, 'request_limit')
    state = dict(schema='A23-terminal-deadline-observation-1', accepted=False, reason=None, spawned=False,
                 deadline_expired=False, terminate_attempted=False, terminate_call_returned=False,
                 kill_attempted=False, kill_call_returned=False, direct_wait_verified=False,
                 returncode=None, cleanup_wait_timeouts=0, pending_handle_retained=False,
                 response_size=0, response_sha256=None, task_complete=False,
                 atomic_directory_snapshot_verified=False, historical_sync_or_wait_inferred=False,
                 model_only=True, **intake.recovery.FALSE)
    result = Observation(state)
    start = time.monotonic()
    deadline = start + timeout
    child = None
    try:
        command = _command if _command is not None else [sys.executable, '-B', str(Path(__file__).with_name('a23_terminal_deadline_worker.py'))]
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 bufsize=0, close_fds=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        state['spawned'] = True
        status, wire = exchange(child, request, deadline)
        state.update(response_size=len(wire), response_sha256=intake.recovery.sha(wire))
        if status == 'deadline':
            state['deadline_expired'] = True
        require(status == 'received', status)
        left = deadline - time.monotonic()
        if left <= 0:
            state['deadline_expired'] = True
            raise Rejected('deadline')
        try:
            state['returncode'] = child.wait(timeout=left)
            state['direct_wait_verified'] = True
        except subprocess.TimeoutExpired:
            state['deadline_expired'] = True
            raise Rejected('deadline')
        require(time.monotonic() < deadline, 'deadline')
        require(state['returncode'] == 0, 'child_exit')
        cache, report, classification = decode_response(wire, anchor, pin)
        require(time.monotonic() < deadline, 'deadline')
        result.cache, result.report, result.classification = cache, report, classification
        state.update(accepted=True, reason='sampled')
    except (ValueError, OSError, KeyError, TypeError) as exc:
        state['reason'] = str(exc) if isinstance(exc, Rejected) else type(exc).__name__
        if state['reason'] == 'deadline':
            state['deadline_expired'] = True
    finally:
        if child is not None:
            if not state['direct_wait_verified']:
                result.pending_process = reap(child, state, cleanup_grace)
            for stream in (child.stdin, child.stdout):
                try:
                    if not stream.closed:
                        stream.close()
                except OSError as exc:
                    state['stream_close_error'] = type(exc).__name__
                    state.update(accepted=False, reason='stream_close')
        state['elapsed_seconds'] = time.monotonic() - start
        if not state['accepted']:
            result.cache = result.report = result.classification = None
    return result
