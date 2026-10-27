"""Trusted local fault instrumentation; no descendants or target-directory writes."""
from pathlib import Path
import os
import signal
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import a23_terminal_deadline_worker as worker


def block_read():
    read_fd, write_fd = os.pipe()
    os.write(1, b'blocked-read\n')
    os.read(read_fd, 1)  # write_fd stays held: an actual blocked read, not an API budget loop.
    os.close(write_fd)


mode = sys.argv[1]
if mode == 'no-input':
    block_read()
args = worker.request()
if mode in ('blocked-read', 'ignore-term'):
    if mode == 'ignore-term':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    def hook(phase, name):
        if phase == 'after_open':
            block_read()
    worker.sample(args, hook)
elif mode == 'oversized':
    while True:
        os.write(1, b'x' * 4096)
elif mode == 'malformed':
    os.write(1, b'{broken')
elif mode == 'partial':
    os.write(1, b'{"schema":')
    block_read()
elif mode == 'exit7':
    os.write(1, worker.sample(args))
    raise SystemExit(7)
elif mode == 'after-eof':
    os.write(1, worker.sample(args))
    os.close(1)
    read_fd, write_fd = os.pipe()
    os.read(read_fd, 1)
elif mode == 'forged-report':
    value = worker.supervisor.json.loads(worker.sample(args))
    value['report']['historical_sync_or_wait_inferred'] = True
    os.write(1, worker.supervisor.encode(value))
else:
    raise SystemExit(3)
