"""Offline gated sampler and request-only actor; both owned by the outer caller."""
from pathlib import Path
import os
import select
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import a23_terminal_deadline_worker as worker


class Abort(BaseException):
    pass


def requester(mode, lifetime):
    if mode == 'before-request':
        os._exit(79)
    os.write(1, b'request\n')
    command = os.read(0, 1)
    if command == b'X':
        os._exit(79)
    return 0 if command == b'Q' else 2


def sampler(life, gate, status, pause):
    def message(kind):
        os.write(status, (kind + '\n').encode())
    def resume():
        ready, _, _ = select.select([gate], [], [], 3)
        if not ready or os.read(gate, 1) != b'R':
            raise Abort()
        readable, _, _ = select.select([life], [], [], 0)
        if readable:
            raise Abort()
    try:
        message('ready')
        resume()
        args = worker.request()
        paused = False
        def checkpoint(phase, name):
            nonlocal paused
            if phase == pause and not paused:
                paused = True
                message('checkpoint')
                resume()
        wire = worker.sample(args, checkpoint)
        os.write(1, wire)
        message('end0')
        return 0
    except Abort:
        message('end86')
        return 86
    except (ValueError, OSError, KeyError, TypeError):
        message('end2')
        return 2


if __name__ == '__main__':
    if sys.argv[1] == 'requester':
        raise SystemExit(requester(sys.argv[2], int(sys.argv[3])))
    raise SystemExit(sampler(*map(int, sys.argv[2:5]), sys.argv[5]))
