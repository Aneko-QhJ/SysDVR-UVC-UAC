"""Single offline sampling child. Read one bounded request; write one bounded response."""
import base64
import sys
import a23_terminal_deadline as supervisor


def request():
    raw = sys.stdin.buffer.read(supervisor.MAX_REQUEST + 1)
    supervisor.require(len(raw) <= supervisor.MAX_REQUEST, 'request_limit')
    value = supervisor.json.loads(raw)
    supervisor.require(type(value) is dict and set(value) == {'directory', 'anchor', 'pin'}, 'request_schema')
    return value['directory'], base64.b64decode(value['anchor'], validate=True), value['pin']


def sample(args, checkpoint=None):
    files, report, _ = supervisor.intake.capture(*args, checkpoint=checkpoint)
    return supervisor.encode(dict(schema='A23-terminal-deadline-wire-1',
        files={n: base64.b64encode(v).decode() for n, v in files.items()}, report=report))


def main():
    try:
        wire = sample(request())
        supervisor.require(len(wire) <= supervisor.MAX_RESPONSE, 'response_limit')
        sys.stdout.buffer.write(wire)
        sys.stdout.buffer.flush()
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
