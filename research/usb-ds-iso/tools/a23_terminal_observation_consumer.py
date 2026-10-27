"""Independently recompute a bound OFFLINE terminal-service record.

This checks a recorded history against caller-supplied expected binding. It does
not authenticate a producer or turn model poll completions into SDK callbacks.
"""
import argparse
import json
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def integer(value, low=0, high=(1 << 64) - 1):
    require(type(value) is int and low <= value <= high, 'integer type or bound')
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def load(path):
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique_object,
                      parse_constant=lambda _: require(False, 'nonfinite JSON'))


def validate(row, expected_binding):
    require(type(row) is dict and type(expected_binding) is dict, 'record type')
    require(row.get('schema') == 'A23-terminal-observation-1', 'schema')
    require(json.dumps(row.get('binding'), sort_keys=True) ==
            json.dumps(expected_binding, sort_keys=True) and
            expected_binding.get('model_only') is True, 'external binding')
    require(row.get('clock') == 'CLOCK_MONOTONIC_RAW_ns', 'clock domain')
    for key, expected in dict(requested=True, busy=False,
                              verifier_on_serial_queue=True, exit_allowed=True,
                              accepted=True, hardware_entry_enabled=False,
                              callback_drain_verified=False,
                              buffer_reuse_verified=False).items():
        require(row.get(key) is expected, 'boolean ' + key)
    require(row.get('phase') == 'passed' and row.get('reason') == '', 'terminal state')
    boundary = row.get('boundary')
    require(type(boundary) is dict and set(boundary) == {
        'saved_epochs', 'iso_attempts', 'durable', 'pending', 'stopped'}, 'boundary keys')
    for key in ('saved_epochs', 'iso_attempts'):
        require(integer(boundary[key]) == 3, 'saved boundary')
    for key, expected in dict(durable=True, pending=False, stopped=False).items():
        require(boundary[key] is expected, 'boundary boolean')
    for key in ('full_checks', 'worker_returns', 'rechecks', 'final_checks'):
        require(integer(row.get(key)) == 1, 'one-shot ' + key)
    require(integer(row.get('duration_ns')) == 250_000_000 and
            integer(row.get('gap_limit_ns')) == 32_000_000 and
            integer(row.get('capacity')) == 512, 'fixed policy')
    samples = row.get('samples_ns')
    require(type(samples) is list and 2 <= len(samples) <= 512, 'sample bounds')
    require(integer(row.get('sample_count')) == len(samples) == integer(row.get('polls')),
            'sample/poll count')
    samples = [integer(n, 1) for n in samples]
    require(samples[0] <= (1 << 64) - 1 - 250_000_000, 'start overflow')
    gaps = [b - a for a, b in zip(samples, samples[1:])]
    require(all(0 < gap <= 32_000_000 for gap in gaps), 'service gap')
    require(integer(row.get('max_gap_ns')) == max(gaps), 'computed maximum')
    require(samples[-1] - samples[0] >= 250_000_000 and
            samples[-2] - samples[0] < 250_000_000, 'first eligible endpoint')
    events = row.get('events')
    require(type(events) is list and len(events) == len(samples) + 8, 'event count')
    require(all(type(e) is dict and set(e) == {'event', 'ns'} for e in events), 'event shape')
    times = [integer(e['ns'], 1) for e in events]
    require(all(a <= b for a, b in zip(times, times[1:])), 'event clock order')
    names = [e['event'] for e in events]
    wanted = (['worker_requested', 'worker_returned', 'recheck_started', 'recheck_passed',
               'poll_completed', 'window_started'] + ['poll_completed'] * (len(samples) - 1) +
              ['window_passed', 'final_check_started', 'final_check_passed'])
    require(names == wanted, 'worker/recheck/poll/final ordering')
    require([e['ns'] for e in events if e['event'] == 'poll_completed'] == samples,
            'completed polls differ from samples')
    require(events[5]['ns'] == samples[0] and events[-3]['ns'] == samples[-1], 'window binding')
    begin = integer(row.get('worker_begin_ns'), 1)
    end = integer(row.get('worker_end_ns'), 1)
    deadline = integer(row.get('guard_deadline_ns'), 1)
    require(times[0] <= begin <= end <= times[1] <= times[3] < deadline, 'worker return/deadline')
    return dict(schema='A23-terminal-observation-acceptance-1', binding=expected_binding,
                local_service_window_accepted=True, sample_count=len(samples),
                elapsed_ns=samples[-1] - samples[0], max_gap_ns=max(gaps),
                producer_history_authenticated=False, actual_sdk_poll_verified=False,
                callback_drain_verified=False, buffer_reuse_verified=False,
                hardware_entry_enabled=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('expected_binding', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(load(args.record), load(args.expected_binding)), sort_keys=True))
