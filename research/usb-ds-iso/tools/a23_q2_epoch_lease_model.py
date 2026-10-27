"""One-segment symbolic epoch credit lease. No SDK, backing, clock or I/O.

All conditions and counter reports are model assumptions, not device grants.
The controller never refunds credit or creates a second lease/segment.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json

MAX = 2**63-1


def integer(value, low=0, high=MAX):
    return type(value) is int and low <= value <= high


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def sha(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


@dataclass(frozen=True)
class Step:
    phase: str
    interface: int
    trace_bound: int
    identity_bound: int


SHAPE = tuple(Step(phase,interface,17 if interface==2 else 3,2 if interface==2 else 0)
              for phase in ('before','burst','after') for interface in (0,1,2))
SHAPE_SHA256 = digest([asdict(step) for step in SHAPE])


@dataclass(frozen=True)
class Binding:
    segment: str
    snapshot_sha256: str
    source_sha256: str
    recipe_sha256: str
    shape_sha256: str = SHAPE_SHA256

    def __post_init__(self):
        if not (type(self.segment) is str and 0<len(self.segment)<=64 and
                all(sha(v) for v in (self.snapshot_sha256,self.source_sha256,
                                     self.recipe_sha256,self.shape_sha256))):
            raise ValueError('invalid finite model binding')


@dataclass(frozen=True)
class Watermark:
    binding: Binding
    generation: int
    trace_used: int
    identities_used: int
    tick: int
    deadline: int
    domain: str = 'MODEL_TICKS_ONLY'

    def __post_init__(self):
        if not (type(self.binding) is Binding and integer(self.generation,1,2**32-1) and
                integer(self.trace_used,0,256) and integer(self.identities_used,0,32) and
                integer(self.tick) and integer(self.deadline)):
            raise ValueError('invalid model watermark')


@dataclass(frozen=True)
class Conditions:
    extra_trace: int | None = None
    extra_identities: int | None = None
    stop_trace: int | None = None
    stop_identities: int | None = None
    epoch_ticks: int | None = None
    stop_ticks: int | None = None
    shape_bound_assumed: bool | None = None
    bounded_external_traffic_assumed: bool | None = None
    duration_bound_assumed: bool | None = None
    ownership_ready_assumed: bool | None = None
    schema: str = 'Q2C_CONDITIONS_MODEL_ONLY'

    def __post_init__(self):
        for value in (self.extra_trace,self.extra_identities,self.stop_trace,self.stop_identities,
                      self.epoch_ticks,self.stop_ticks):
            if value is not None and not integer(value):
                raise ValueError('strict model budget integer required')
        for value in (self.shape_bound_assumed,self.bounded_external_traffic_assumed,
                      self.duration_bound_assumed,self.ownership_ready_assumed):
            if value is not None and type(value) is not bool:
                raise ValueError('explicit boolean model condition required')


@dataclass(frozen=True)
class Lease:
    digest: str
    binding: Binding
    generation: int
    schema: str = 'Q2C_LEASE_MODEL_ONLY'


class EpochGate:
    def __init__(self,binding):
        if type(binding) is not Binding:
            raise ValueError('explicit model binding required')
        self.binding=binding
        self._attempted=False
        self._lease=None
        self._initial=None
        self._conditions=None
        self._trace=0
        self._identities=0
        self._tick=0
        self._claimed_at=None
        self._index=0
        self._extra_trace=0
        self._extra_ids=0
        self._reserved_trace=0
        self._reserved_ids=0
        self._claimed=False
        self._iso_armed=False
        self._shape_complete=False
        self._stopped=False
        self._reason=None
        self._stop_at=None
        self._stop_recorded=False
        self._counters_trusted=True
        self._last_report=None
        self._invalid_calls=0

    def _fail(self,reason,*,untrusted=False):
        self._stopped=True
        if self._reason is None:
            self._reason=reason
        if self._stop_at is None:
            self._stop_at=self._tick
        if untrusted:
            self._counters_trusted=False
        self._invalid_calls=min(255,self._invalid_calls+1)
        return False

    def reserve(self,watermark,conditions):
        if self._attempted:
            self._fail('lease_attempt_already_consumed')
            return None
        self._attempted=True
        if (type(watermark) is not Watermark or type(conditions) is not Conditions or
                watermark.binding!=self.binding or self.binding.shape_sha256!=SHAPE_SHA256 or
                watermark.domain!='MODEL_TICKS_ONLY' or conditions.schema!='Q2C_CONDITIONS_MODEL_ONLY'):
            self._fail('binding_or_model_domain_mismatch')
            return None
        self._initial=watermark;self._conditions=conditions
        self._trace=watermark.trace_used;self._identities=watermark.identities_used;self._tick=watermark.tick
        budgets=(conditions.extra_trace,conditions.extra_identities,conditions.stop_trace,
                 conditions.stop_identities,conditions.epoch_ticks,conditions.stop_ticks)
        assumptions=(conditions.shape_bound_assumed,conditions.bounded_external_traffic_assumed,
                     conditions.duration_bound_assumed,conditions.ownership_ready_assumed)
        if (any(v is None for v in budgets) or not all(v is True for v in assumptions) or
                not integer(conditions.extra_trace,0,256) or not integer(conditions.extra_identities,0,32) or
                not integer(conditions.stop_trace,1,256) or not integer(conditions.stop_identities,0,32) or
                not integer(conditions.epoch_ticks,1) or not integer(conditions.stop_ticks,1)):
            self._fail('unknown_or_invalid_admission_conditions')
            return None
        self._reserved_trace=sum(s.trace_bound for s in SHAPE)+conditions.extra_trace+conditions.stop_trace
        self._reserved_ids=sum(s.identity_bound for s in SHAPE)+conditions.extra_identities+conditions.stop_identities
        if (self._trace+self._reserved_trace>256 or self._identities+self._reserved_ids>32 or
                watermark.tick+conditions.epoch_ticks+conditions.stop_ticks>watermark.deadline):
            self._fail('whole_epoch_budget_does_not_fit')
            return None
        value=dict(watermark=asdict(watermark),conditions=asdict(conditions),shape=SHAPE_SHA256,
                   reserved_trace=self._reserved_trace,reserved_ids=self._reserved_ids)
        self._lease=Lease(digest(value),self.binding,watermark.generation)
        return self._lease

    def _check_token(self,lease):
        if type(lease) is not Lease or lease!=self._lease or lease.schema!='Q2C_LEASE_MODEL_ONLY':
            return self._fail('wrong_or_relabelled_lease')
        return True

    def _watermark(self,value,*,begin=False,stopping=False):
        if type(value) is not Watermark:
            return self._fail('missing_current_watermark',untrusted=True)
        self._last_report=asdict(value)
        if (value.binding!=self.binding or value.generation!=self._initial.generation or
                value.deadline!=self._initial.deadline or value.domain!='MODEL_TICKS_ONLY' or
                value.trace_used!=self._trace or value.identities_used!=self._identities):
            return self._fail('watermark_drift',untrusted=True)
        if value.tick<self._tick:
            return self._fail('clock_backwards')
        self._tick=value.tick
        c=self._conditions
        if stopping:
            if self._tick>value.deadline or self._tick-self._stop_at>c.stop_ticks:
                return self._fail('stop_time_assumption_exceeded')
        elif begin:
            if self._tick+c.epoch_ticks+c.stop_ticks>value.deadline:
                return self._fail('lease_expired_before_claim')
        elif (self._claimed_at is None or self._tick-self._claimed_at>c.epoch_ticks or
              self._tick+c.stop_ticks>value.deadline):
            return self._fail('epoch_time_assumption_exceeded')
        return True

    def claim(self,lease,current):
        if not self._check_token(lease):
            return False
        if self._stopped or self._claimed or self._shape_complete:
            return self._fail('lease_not_claimable')
        if not self._watermark(current,begin=True):
            return False
        self._claimed=True;self._claimed_at=self._tick
        return True

    def _running(self,lease):
        if not self._check_token(lease):
            return False
        if not self._claimed or self._stopped or self._shape_complete or not self._counters_trusted:
            return self._fail('segment_not_running')
        return True

    def observe_ready(self,lease,phase,interface,trace_delta,identity_delta,current):
        if not self._running(lease):
            self._counters_trusted=False
            return False
        if not self._watermark(current):
            self._counters_trusted=False
            return False
        if self._index>=len(SHAPE):
            return self._fail('extra_ready_group',untrusted=True)
        expected=SHAPE[self._index]
        if (type(phase) is not str or type(interface) is not int or
                (phase,interface)!=(expected.phase,expected.interface) or
                not integer(trace_delta,3,expected.trace_bound) or
                not integer(identity_delta,0,expected.identity_bound)):
            # The input describes an event already observed, not an undoable operation.
            self._last_report=dict(kind='unexpected_ready',reported_trace_delta=trace_delta if integer(trace_delta) else None,
                                   reported_identity_delta=identity_delta if integer(identity_delta) else None)
            return self._fail('ready_shape_or_bound_violated',untrusted=True)
        if (self._index>=3 and not self._iso_armed) or (self._index<3 and self._iso_armed):
            return self._fail('ISO_order_violated',untrusted=True)
        self._trace+=trace_delta;self._identities+=identity_delta;self._index+=1
        return True

    def arm_iso(self,lease,current):
        if not self._running(lease):
            return False
        if not self._watermark(current):
            return False
        if self._index!=3 or self._iso_armed:
            return self._fail('ISO_arm_out_of_order')
        self._iso_armed=True
        return True

    def observe_nonrequest(self,lease,trace_delta,identity_delta,current):
        if not self._running(lease):
            self._counters_trusted=False
            return False
        if not self._watermark(current):
            self._counters_trusted=False
            return False
        c=self._conditions
        if (not integer(trace_delta,1,256) or not integer(identity_delta,0,32) or
                self._extra_trace+trace_delta>c.extra_trace or
                self._extra_ids+identity_delta>c.extra_identities):
            self._last_report=dict(kind='unexpected_nonrequest',reported_trace_delta=trace_delta if integer(trace_delta) else None,
                                   reported_identity_delta=identity_delta if integer(identity_delta) else None)
            return self._fail('external_traffic_envelope_violated',untrusted=True)
        self._extra_trace+=trace_delta;self._extra_ids+=identity_delta
        self._trace+=trace_delta;self._identities+=identity_delta
        return True

    def finish_shape(self,lease,current):
        if not self._running(lease):
            return None
        if not self._watermark(current):
            return None
        if self._index!=len(SHAPE) or not self._iso_armed:
            self._fail('shape_incomplete')
            return None
        self._shape_complete=True
        return dict(schema='Q2C_SHAPE_RECEIPT_MODEL_ONLY',lease_digest=lease.digest,
                    watermark=asdict(current),shape_groups=self._index,
                    native_IO_complete=False,real_evidence_committed=False,
                    credit_reclaim_authorized=False,next_segment_authorized=False)

    def stop(self,lease):
        if not self._check_token(lease):
            return False
        self._fail('operator_stop_model_only')
        return True

    def record_stop(self,lease,trace_delta,identity_delta,current):
        if not self._check_token(lease):
            return False
        if not self._stopped or not self._counters_trusted or self._stop_recorded:
            return self._fail('stop_receipt_not_admissible')
        if not self._watermark(current,stopping=True):
            return False
        c=self._conditions
        if (not integer(trace_delta,0,c.stop_trace) or not integer(identity_delta,0,c.stop_identities)):
            return self._fail('stop_evidence_bound_violated',untrusted=True)
        self._trace+=trace_delta;self._identities+=identity_delta;self._stop_recorded=True
        return True

    def view(self):
        return dict(schema='A23-q2c-epoch-gate-model-1',simulation=True,binding=asdict(self.binding),
            lease=asdict(self._lease) if self._lease else None,attempt_consumed=self._attempted,
            claimed=self._claimed,ISO_symbolically_armed=self._iso_armed,shape_groups=self._index,
            shape_complete=self._shape_complete,stopped=self._stopped,stop_reason=self._reason,
            counters_trusted_in_model=self._counters_trusted,last_accepted_trace=self._trace,
            last_accepted_identities=self._identities,last_model_tick=self._tick,last_report=self._last_report,
            reserved_trace=self._reserved_trace,reserved_identities=self._reserved_ids,
            extra_trace_used=self._extra_trace,extra_identities_used=self._extra_ids,
            stop_recorded=self._stop_recorded,invalid_calls=self._invalid_calls,
            credit_refunded=False,reservation_retained=self._lease is not None,
            actual_device_grant_authenticated=False,global_cross_controller_serialization=False,
            native_handoff_proven=False,hard_deadline_proven=False,lossless_rollover_verified=False,
            hardware_entry_enabled=False,formal_issuance_available=False,SDK_calls=0,usb_requests=0)
