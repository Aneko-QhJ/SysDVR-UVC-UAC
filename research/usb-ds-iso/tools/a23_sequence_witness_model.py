#!/usr/bin/env python3
"""Offline sequence witness model. No reservation, firmware, card or USB access.

A distinct 16-packet block can distinguish known old observations, but is not
an authentication token. A future issuer must durably burn a block before use.
"""
import struct


def sequence(value):
    if type(value) is not int or not 0 <= value <= 65535:
        raise ValueError('uint16 sequence required')
    return value


def packet_sequences(first):
    first = sequence(first)
    return tuple((first + i) & 65535 for i in range(16))


def propose_block(previous):
    """Pure proposal, never an allocation or acquisition authorization."""
    if type(previous) is not list:
        raise ValueError('explicit prior sequence list required')
    used = set()
    for value in previous:
        used.update(packet_sequences(value))
    for first in range(1, 65521, 16):
        if not used.intersection(packet_sequences(first)):
            return first
    raise ValueError('sequence space exhausted; do not recycle')


def expected_payload(first):
    return b''.join(b'ISO1' + struct.pack('<H', value) +
                    bytes((i ^ value ^ (value >> 8)) & 255 for i in range(6, 192))
                    for value in packet_sequences(first))


def compare_model(first, setup_value, trace_sequence, status_sequence, payload):
    first = sequence(first)
    for value in (setup_value, trace_sequence, status_sequence):
        sequence(value)
    if type(payload) is not bytes:
        raise ValueError('exact payload bytes required')
    fields = (setup_value == first, trace_sequence == first,
              status_sequence == first, payload == expected_payload(first))
    return dict(schema='A23-sequence-witness-model-1', model_only=True,
                setup_matches=fields[0], trace_matches=fields[1],
                status_matches=fields[2], payload_matches=fields[3],
                supplied_sequence_agreement=all(fields),
                unique_historical_allocation_verified=False,
                physical_run_authenticated=False, source_authenticated=False,
                root_cause_confirmed=False, usb_strict_pass=False,
                acquisition_enabled=False, remaining=0)
