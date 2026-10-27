"""Finite symbolic Q2b model. No backing allocation, SDK, I/O, or permits.

An AssumedHandoff is a model condition, never evidence of native ownership.
Retired request metadata is retained within a lifetime bound; it is not evicted.
All methods are atomic sequential events, not a concurrent implementation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


def integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


@dataclass(frozen=True)
class Token:
    session: str
    slot: int
    generation: int
    request: int

    def __post_init__(self):
        if not (type(self.session) is str and 0 < len(self.session) <= 64 and
                integer(self.slot, 0, 7) and integer(self.generation, 1, 2**32-1) and
                integer(self.request, 1, 32)):
            raise ValueError('invalid model token')


@dataclass(frozen=True)
class Evidence:
    token: Token
    symbolic_address: int
    version: int

    def __post_init__(self):
        if not (type(self.token) is Token and integer(self.symbolic_address, 1, 0xffff) and
                integer(self.version, 1, 2**32-1)):
            raise ValueError('invalid symbolic evidence')


@dataclass(frozen=True)
class AssumedHandoff:
    token: Token
    schema: str = 'Q2b-MODEL-ASSUMPTION-ONLY'


@dataclass
class Record:
    token: Token
    address: int
    version: int
    submitted: bool = False
    iso_arrivals: int = 0
    control_arrivals: int = 0
    iso_queued: bool = False
    control_queued: bool = False
    iso_handled: bool = False
    control_handled: bool = False
    local_readers: int = 0
    snapshot: Evidence | None = None
    snapshot_reads: int = 0
    save_attempted: bool = False
    evidence_committed: bool = False
    model_handoff_assumed: bool = False
    retired: bool = False
    poisoned: bool = False
    late_events: int = 0


class Pool:
    def __init__(self, session, *, slots=2, metadata_limit=4, evidence_credits=4, simulation=True):
        if not (simulation is True and type(session) is str and 0 < len(session) <= 64 and
                integer(slots, 1, 8) and integer(metadata_limit, 1, 32) and
                integer(evidence_credits, 0, 32)):
            raise ValueError('explicit finite model configuration required')
        self.session = session
        self.slot_count = slots
        self.metadata_limit = metadata_limit
        self.credits = evidence_credits
        self._current = [None] * slots
        self._generations = [0] * slots
        self._versions = [0] * slots
        self._records = {}
        self.stopped = False
        self.stop_reason = None
        self.invalid_events = 0

    def _stop(self, reason):
        self.stopped = True
        if self.stop_reason is None:
            self.stop_reason = reason
        return False

    def stop(self):
        return self._stop('operator_stop_model_only')

    def _record(self, token):
        if type(token) is not Token:
            self.invalid_events = min(255, self.invalid_events + 1)
            self._stop('invalid_token')
            return None
        record = self._records.get(token)
        if record is None:
            self.invalid_events = min(255, self.invalid_events + 1)
            self._stop('unknown_token')
            return None
        if record.retired or self._current[token.slot] != token:
            # Metadata only. Do not read the current slot or change its record.
            record.late_events = min(255, record.late_events + 1)
            self._stop('old_generation_event')
            return None
        return record

    def _poison(self, record, reason):
        record.poisoned = True
        return self._stop(reason)

    def admit(self):
        if self.stopped:
            return None
        if len(self._records) >= self.metadata_limit:
            self._stop('metadata_exhausted')
            return None
        if not self.credits:
            self._stop('evidence_credit_exhausted')
            return None
        free = next((i for i, token in enumerate(self._current) if token is None), None)
        if free is None:
            self._stop('pool_exhausted')
            return None
        if self._generations[free] == 2**32-1:
            self._stop('generation_exhausted')
            return None
        self._generations[free] += 1
        self._versions[free] += 1
        token = Token(self.session, free, self._generations[free], len(self._records)+1)
        self._current[free] = token
        self._records[token] = Record(token, 0x1000 + free*0x1000, self._versions[free])
        self.credits -= 1  # Stored evidence consumes lifetime credit; recycle does not refund it.
        return token

    def submit(self, token):
        record = self._record(token)
        if record is None:
            return False
        if self.stopped or record.poisoned or record.submitted:
            return self._poison(record, 'invalid_submission')
        record.submitted = True
        return True

    def callback(self, token, domain, symbolic_address, *, succeeded=True):
        record = self._record(token)
        if record is None:
            return False
        if domain not in ('iso', 'control') or type(succeeded) is not bool:
            return self._poison(record, 'invalid_callback')
        if not record.submitted:
            return self._poison(record, 'callback_before_submission')
        name = domain + '_arrivals'
        count = min(255, getattr(record, name) + 1)
        setattr(record, name, count)
        if (record.poisoned or count != 1 or not succeeded or type(symbolic_address) is not int or
                symbolic_address != record.address):
            return self._poison(record, 'duplicate_failed_or_pointer_mismatch')
        setattr(record, domain + '_queued', True)
        return True

    def handle(self, token, domain):
        record = self._record(token)
        if record is None:
            return False
        if domain not in ('iso', 'control'):
            return self._poison(record, 'invalid_handler_domain')
        if (record.poisoned or not getattr(record, domain + '_queued') or
                getattr(record, domain + '_handled')):
            return self._poison(record, 'handler_without_unique_ingress')
        setattr(record, domain + '_queued', False)
        setattr(record, domain + '_handled', True)
        return True

    def begin_local_read(self, token):
        record = self._record(token)
        if record is None:
            return False
        if record.poisoned or record.local_readers >= 2:
            return self._poison(record, 'local_reader_limit')
        record.local_readers += 1
        return True

    def end_local_read(self, token):
        record = self._record(token)
        if record is None:
            return False
        if not record.local_readers:
            return self._poison(record, 'unmatched_local_return')
        record.local_readers -= 1
        return True

    def snapshot(self, token):
        record = self._record(token)
        if record is None:
            return None
        if (record.poisoned or record.snapshot is not None or
                record.iso_arrivals != 1 or record.control_arrivals != 1 or
                not record.iso_handled or not record.control_handled or
                record.iso_queued or record.control_queued):
            self._poison(record, 'snapshot_before_handlers_or_duplicate')
            return None
        record.snapshot_reads += 1
        record.snapshot = Evidence(token, record.address, record.version)
        return record.snapshot

    def commit(self, token, evidence, *, succeeded=True):
        record = self._record(token)
        if record is None:
            return False
        if record.save_attempted:
            return self._poison(record, 'save_already_attempted')
        record.save_attempted = True
        expected = Evidence(token, record.address, record.version)
        if (type(succeeded) is not bool or not succeeded or record.poisoned or
                type(evidence) is not Evidence or evidence != expected or record.snapshot != expected):
            return self._poison(record, 'evidence_save_failed_or_binding_mismatch')
        record.evidence_committed = True
        return True

    def assume_handoff(self, token, assumption):
        record = self._record(token)
        if record is None:
            return False
        if (record.poisoned or record.model_handoff_assumed or not record.submitted or
                type(assumption) is not AssumedHandoff or assumption.token != token or
                assumption.schema != 'Q2b-MODEL-ASSUMPTION-ONLY'):
            return self._poison(record, 'missing_contradictory_or_replayed_handoff_assumption')
        record.model_handoff_assumed = True
        return True

    def recycle(self, token):
        record = self._record(token)
        if record is None:
            return False
        if (self.stopped or record.poisoned or not record.submitted or
                record.iso_arrivals != 1 or record.control_arrivals != 1 or
                not record.iso_handled or not record.control_handled or
                record.iso_queued or record.control_queued or record.local_readers or
                not record.evidence_committed or not record.model_handoff_assumed):
            return self._poison(record, 'reuse_gate_not_satisfied')
        record.retired = True
        self._current[token.slot] = None
        return True  # Symbolic model transition only; no native permission is returned.

    def interest(self):
        for token in self._current:
            if token is not None:
                self._records[token].poisoned = True
        return self._stop('interest_model_event')

    def view(self):
        return dict(schema='A23-q2b-symbolic-pool-1',simulation=True,
            slots=[dict(slot=i,token=asdict(t) if t else None,generation=self._generations[i],
                        symbolic_address=0x1000+i*0x1000,version=self._versions[i])
                   for i,t in enumerate(self._current)],
            records=[asdict(r) for r in self._records.values()],metadata_limit=self.metadata_limit,
            evidence_credits_remaining=self.credits,stopped=self.stopped,stop_reason=self.stop_reason,
            invalid_events=self.invalid_events,actual_backing_allocated=False,
            real_evidence_commit_verified=False,native_handoff_proven=False,
            all_callback_drain_proven=False,hardware_entry_enabled=False,
            formal_issuance_available=False,physical_buffer_reuse_enabled=False)
