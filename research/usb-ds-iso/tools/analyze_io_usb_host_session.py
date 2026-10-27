#!/usr/bin/env python3
"""Offline simulation session journal audit; no callback-drain or USB claim."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
from analyze_io_usb_host_evidence import analyze as analyze_bundle, integer, require, unique_object
from io_usb_host_probe_plan import validate_plan, validate_hardware_plan
from io_usb_host_runtime_policy import audit_admission, duration_ns

EVENTS = {"prepare_begin", "candidate_selected", "resources_opened", "ready", "submit_begin",
          "submit_result", "callback", "snapshot_ready", "deadline", "abort_result", "detach",
          "unrelated_detach", "save_begin", "bundle_committed", "resources_closing", "resources_closed", "stop", "status_observed", "frame_sample",
          "admission_checked", "exit_requested", "exit_wait_expired"}


def status_reply(detail, event_ticks, *, hardware=False):
    require(detail.get("phase") in {"before", "after"} and type(detail.get("raw_base64")) is str,
            "invalid STATUS phase/bytes")
    raw = base64.b64decode(detail["raw_base64"], validate=True)
    require(len(raw) <= 2048 and base64.b64encode(raw).decode() == detail["raw_base64"] and
            hashlib.sha256(raw).hexdigest() == detail.get("raw_sha256"), "STATUS byte/hash mismatch")
    obs = detail.get("observation")
    require(type(obs) is dict and obs.get("source") == ('sdk_control_reply' if hardware else "mock_control_reply") and type(obs.get("accepted")) is bool and
            integer(obs.get("bytes_transferred"), 0, 2**64-1) and integer(obs.get("begin_ticks"), 1) and
            integer(obs.get("end_ticks"), obs["begin_ticks"], event_ticks), "invalid STATUS observation/time/source")
    control = obs.get("control")
    expected = dict(request_type=0xc1, request=0x51, value=0, index=2, length=168, timeout_ms=3000)
    require(type(control) is dict and control == expected and all(type(v) is int for v in control.values()),
            "invalid STATUS control tuple")
    if "error" in obs:
        error = obs["error"]
        require(type(error) is dict and type(error.get("domain")) is str and error["domain"] and
                type(error.get("code")) is int, "invalid STATUS error")
    valid = bool(len(raw) == 168 and obs["bytes_transferred"] == 168 and obs["accepted"] and "error" not in obs)
    decoded = None
    if valid:
        from audit_io_usb_host_device import decode_status
        try:
            decoded = decode_status(raw)
        except ValueError:
            valid = False
    if valid and detail["phase"] == "before":
        valid = (all(decoded[k] == 0 for k in ("sequence", "state", "post_result", "urb_id", "report_id", "requested",
                                             "transferred", "urb_status", "report_count", "report_result")) and
                 decoded["speed"] in (0, 3))
    return raw, obs, bool(valid)


def analyze(journal, bundle=None, *, hardware=False):
    path = Path(journal)
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 128*4096,
            "invalid journal file/size")
    raw = path.read_bytes()
    require(raw.endswith(b"\n"), "partial journal tail")
    lines = raw.splitlines()
    require(0 < len(lines) <= 128 and all(len(line) <= 4095 for line in lines), "invalid journal bounds")
    records = [json.loads(line, object_pairs_hook=unique_object) for line in lines]
    session_id = None
    previous_ticks = 0
    identity = None
    candidate_count = None
    opened = ready = submitted = closing = closed = False
    accepted = None
    first_frame = None
    callbacks = []
    snapshot = None
    commit = None
    save_count = None
    reasons = []
    deadline = detached = late = False
    aborts = 0
    abort_accepted = None
    required_status = False
    status = {}
    submit_ticks = None
    ready_ticks = snapshot_ticks = None
    probe_plan = frame_sample = None
    submit_result_ticks = None
    admission = exit_request = exit_expiry = None
    runtime = False
    for index, record in enumerate(records, 1):
        require(type(record) is dict and record.get("schema") == "A23-session-event-1" and
                record.get("execution_mode") == ('hardware' if hardware else "simulation"), "unknown session schema/mode")
        require(type(record.get("session_id")) is str and bool(record["session_id"]), "missing session identity")
        if session_id is None:
            session_id = record["session_id"]
        require(session_id == record["session_id"], "mixed sessions")
        require(integer(record.get("index"), index, index) and integer(record.get("ticks"), 1) and
                record["ticks"] >= previous_ticks, "invalid event sequence/time")
        previous_ticks = record["ticks"]
        event, detail = record.get("event"), record.get("details")
        require(event in EVENTS and type(detail) is dict, "unknown event/details")
        if event == "prepare_begin":
            require(index == 1 and integer(detail.get("candidate_count")), "invalid preparation")
            candidate_count = detail["candidate_count"]
            required_status = detail.get("requires_status_binding", False)
            require(type(required_status) is bool, "invalid STATUS requirement")
            if "probe_plan" in detail:
                (validate_hardware_plan if hardware else validate_plan)(detail["probe_plan"])
                require(required_status, "no-TD plan without raw STATUS")
                probe_plan = detail["probe_plan"]
                runtime = 'runtime_budget' in probe_plan
        elif event == "candidate_selected":
            require(candidate_count == 1 and identity is None and not submitted, "ambiguous/repeated selection")
            require(all(integer(detail.get(k), 1) for k in ("device_id", "interface_id", "parent_device_id")) and
                    detail["device_id"] == detail["parent_device_id"] and
                    detail["device_id"] != detail["interface_id"], "invalid registry relationship")
            identity = detail
        elif event == "resources_opened":
            require(identity is not None and not opened and not submitted, "invalid/repeated resource open")
            opened = True
        elif event == "ready":
            require(opened and not ready and not closed and not reasons, "ready after failure")
            require(all(detail.get(k) == v and type(detail.get(k)) is int for k, v in
                        (("interface", 2), ("alternate", 0), ("endpoint", 0x83), ("mps", 256),
                         ("interval", 1), ("connection_speed", 3))), "invalid A23 ready descriptor")
            require(type(detail.get("vendor_id")) is int and detail["vendor_id"] == 0x1209 and
                    type(detail.get("product_id")) is int and detail["product_id"] == 0xca57 and
                    integer(detail.get("configuration_value"), 1, 255) and
                    detail.get("source") == ('sdk_descriptor_bytes' if hardware else "supplied_descriptor_bytes"), "invalid ready identity/source")
            ready = True
            ready_ticks = record["ticks"]
        elif event == "submit_begin":
            require(ready and not submitted and not closed and not reasons and
                    integer(detail.get("first_frame"), 1), "unsafe/repeated submission")
            submitted = True
            first_frame = detail["first_frame"]
            submit_ticks = record["ticks"]
            require(not required_status or ("before" in status and status["before"][2] and
                    status["before"][1]["end_ticks"] <= submit_ticks), "submission without fresh STATUS")
            require(probe_plan is None or (frame_sample is not None and first_frame == frame_sample["first_frame"] and
                    frame_sample["end_ticks"] <= submit_ticks), "submission without planned frame")
        elif event == "frame_sample":
            require(probe_plan is not None and ready and not submitted and not reasons and not closed and
                    frame_sample is None and "before" in status and status["before"][2], "unexpected/repeated frame sample")
            require(detail.get("source") == ('sdk_frame_number' if hardware else "mock_frame_number") and integer(detail.get("current_frame"),int(hardware),2**64-65) and
                    integer(detail.get("begin_ticks"),status["before"][1]["end_ticks"]) and
                    integer(detail.get("end_ticks"),detail["begin_ticks"],record["ticks"]) and
                    integer(detail.get("frame_lead"),64,64) and
                    integer(detail.get("first_frame"),detail["current_frame"]+64,detail["current_frame"]+64),
                    "invalid software frame sample")
            frame_sample = detail
            if hardware: require(integer(detail.get('frame_time')), 'invalid SDK frame timestamp')
            if runtime:
                require(all(integer(detail.get(k),1,2**32-1) for k in ('timebase_numerator','timebase_denominator')),
                        'invalid frame timebase')
        elif event == 'admission_checked':
            require(runtime and submitted and accepted is None and frame_sample is not None and admission is None and
                    submit_ticks <= detail.get('check_ticks',-1) <= detail.get('return_ticks',-1) <= record['ticks'],
                    'unexpected admission/time')
            audit_admission(detail,frame_sample,hardware); admission=detail
        elif event == 'exit_requested':
            require(runtime and exit_request is None and integer(detail.get('begin_ticks'),1,record['ticks']) and integer(detail.get('state'),0,7) and
                    all(integer(detail.get(k),1,2**32-1) for k in ('timebase_numerator','timebase_denominator')),
                    'invalid/repeated exit request')
            require(frame_sample is None or all(detail[k]==frame_sample[k] for k in ('timebase_numerator','timebase_denominator')),
                    'exit/frame timebase mismatch')
            exit_request=detail
        elif event == 'exit_wait_expired':
            require(runtime and exit_request is not None and exit_expiry is None and not closed and
                    integer(detail.get('check_ticks')) and integer(detail.get('elapsed_ns')) and
                    all(type(detail.get(k)) is bool for k in ('converted','storage_retained','resources_retained')),
                    'invalid/repeated exit expiry')
            elapsed=duration_ns(exit_request['begin_ticks'],detail['check_ticks'],
                                exit_request['timebase_numerator'],exit_request['timebase_denominator'])
            require(detail['converted']==(elapsed is not None) and detail['elapsed_ns']==(elapsed or 0) and
                    (elapsed is None or elapsed>=1000000000 or (snapshot is not None and snapshot['owner_state']==3) or
                     (aborts==1 and abort_accepted is False)) and detail['storage_retained'] and detail['resources_retained'],
                    'exit expiry calculation/retention mismatch')
            exit_expiry=detail
        elif event == "status_observed":
            require(required_status and ready and not closed, "unexpected STATUS event")
            phase = detail.get("phase")
            require(type(phase) is str and phase not in status, "duplicate STATUS phase")
            reply = status_reply(detail, record["ticks"],hardware=hardware)
            if phase == "before":
                require(not submitted and not reasons and reply[1]["begin_ticks"] >= ready_ticks,
                        "STATUS before outside ready state/time")
            else:
                require(snapshot is not None and snapshot["owner_state"] in (4, 5) and save_count is None and
                        bool(callbacks) and reply[1]["begin_ticks"] >= max(callbacks[0]["arrival_ticks"],snapshot_ticks),
                        "STATUS after outside completion/time boundary")
            status[phase] = reply
        elif event == "submit_result":
            require(submitted and accepted is None and type(detail.get("accepted")) is bool, "invalid submit result")
            accepted = detail["accepted"]
            submit_result_ticks = record["ticks"]
            require(not runtime or (admission is not None and admission['accepted']==accepted), 'submit without matching admission')
        elif event == "callback":
            require(submitted and integer(detail.get("count"), len(callbacks)+1, len(callbacks)+1) and
                    integer(detail.get("status_u32"), 0, 2**32-1) and integer(detail.get("arrival_ticks"), 1) and
                    type(detail.get("pointer_mismatch")) is bool and
                    integer(detail.get("owner_state_before"), 0, 5), "invalid callback event")
            callbacks.append(detail)
            late = late or closed
        elif event == "snapshot_ready":
            require(submitted and snapshot is None and integer(detail.get("owner_state"), 3, 5), "invalid snapshot")
            if detail["owner_state"] == 5:
                require(not callbacks and "overall_u32" not in detail, "rejection fabricated callback")
            else:
                require(len(callbacks) == 1 and integer(detail.get("overall_u32"), 0, 2**32-1) and
                        detail["overall_u32"] == callbacks[0]["status_u32"],
                        "snapshot does not match first callback")
                require((detail["owner_state"] == 3) == callbacks[0]["pointer_mismatch"], "pointer/ownership mismatch")
            snapshot = detail
            snapshot_ticks = record["ticks"]
        elif event == "deadline":
            require(submitted and snapshot is None and not deadline and not detached, "invalid deadline")
            deadline = True
        elif event == "abort_result":
            require(deadline and aborts == 0 and not detached and type(detail.get("accepted")) is bool,
                    "invalid/repeated abort or abort after detach")
            aborts += 1
            abort_accepted = detail['accepted']
        elif event in {"detach", "unrelated_detach"}:
            require(integer(detail.get("registry_id")), "invalid detach identity")
            matches = identity is not None and detail["registry_id"] in {identity["device_id"], identity["interface_id"]}
            require(matches == (event == "detach"), "incorrect detach association")
            detached = detached or matches
        elif event == "save_begin":
            require(snapshot is not None and snapshot["owner_state"] in (4, 5) and commit is None and
                    integer(detail.get("callback_count"), len(callbacks), len(callbacks)), "invalid save begin")
            save_count = len(callbacks)
            require(not required_status or "after" in status or snapshot['owner_state']==5, "save without STATUS after")
        elif event == "bundle_committed":
            require(save_count is not None and commit is None and snapshot["owner_state"] in (4, 5) and
                    integer(detail.get("callback_count"), save_count, save_count) and
                    type(detail.get("manifest_sha256")) is str and
                    re.fullmatch(r"[0-9a-f]{64}", detail["manifest_sha256"]), "invalid evidence commit")
            commit = detail
        elif event == "resources_closing":
            require(not closing and not closed, "repeated close")
            if submitted:
                require(snapshot is not None and snapshot["owner_state"] in (4, 5) and commit is not None,
                        "closed pending/retained or unsaved request")
            closing = True
        elif event == "resources_closed":
            require(closing and not closed, "close without closing event")
            closed = True
        elif event == "stop":
            require(type(detail.get("reason")) is str and detail["reason"], "invalid stop reason")
            reasons.append(detail["reason"])
    require(candidate_count is not None, "no preparation event")
    if snapshot is not None and accepted is not None:
        require((snapshot["owner_state"] == 5) == (accepted is False), "snapshot/submit result mismatch")
    bundle_result = None
    if bundle is not None:
        require(commit is not None, "bundle supplied without journal commit")
        bundle = Path(bundle)
        bundle_result = analyze_bundle(bundle,hardware=hardware)
        require(hashlib.sha256((bundle/"SHA256SUMS").read_bytes()).hexdigest() == commit["manifest_sha256"],
                "journal/bundle hash mismatch")
        meta = json.loads((bundle/"metadata.json").read_bytes(), object_pairs_hook=unique_object)
        require(meta["callback_count_at_save"] == commit["callback_count"] and
                meta["first_frame"] == first_frame and meta["owner_state"] == snapshot["owner_state"] and
                meta.get("overall_u32") == snapshot.get("overall_u32") and meta["timed_out"] == deadline,
                "journal/bundle metadata mismatch")
        require(probe_plan is None or meta["scenario"] == probe_plan["scenario"], "journal/bundle planned scenario mismatch")
        if probe_plan is not None:
            require(frame_sample is not None and submit_ticks <= meta["submit_begin_ticks"] <= meta["submit_return_ticks"] <=
                    submit_result_ticks and frame_sample["end_ticks"] <= meta["submit_begin_ticks"],
                    "planned frame/native/journal time mismatch")
            if snapshot['owner_state']!=5:
                require(bool(callbacks) and meta['callback_arrival_ticks']==callbacks[0]['arrival_ticks'] and
                        status['after'][1]['begin_ticks']>=meta['callback_arrival_ticks'], 'planned frame/native/journal time mismatch')
            if runtime:
                require(admission is not None and meta['submit_begin_ticks']<=admission['check_ticks']<=admission['return_ticks']<=
                        meta['submit_return_ticks'], 'admission/native time mismatch')
    clean = bool(bundle_result and bundle_result["simulation_logic_pass"] and opened and ready and
                 accepted is True and closed and not reasons and not deadline and not detached and not late and
                 len(callbacks) == 1 and not callbacks[0]["pointer_mismatch"] and
                 (not required_status or (set(status) == {"before", "after"} and all(r[2] for r in status.values()))) and
                 (not runtime or (admission and admission['budget_pass'])) and exit_expiry is None)
    return {"schema":"A23-session-analysis-1", "execution_mode":'hardware' if hardware else "simulation", "session_id":session_id,
            "journal_prefix_verified":True, "journal_sha256":hashlib.sha256(raw).hexdigest(),
            "events":len(records), "submissions":int(submitted), "callbacks":len(callbacks),
            "late_callback_observed":late, "stop_reasons":reasons, "deadline_observed":deadline,
            "detach_observed":detached, "abort_requests":aborts, "resources_closed":closed,
            "bundle_integrity_verified":bundle_result is not None, "simulation_session_pass":clean,
            "requires_status_binding":required_status, "status_replies":len(status),
            "status_raw_journal_binding_verified":bool(required_status and set(status) == {"before", "after"}),
            "status_replies_valid":bool(required_status and set(status) == {"before", "after"} and all(r[2] for r in status.values())),
            "probe_plan_bound":probe_plan is not None, "frame_sample_bound":frame_sample is not None,
            "runtime_budget_bound":runtime,"admission":admission,"exit_requested":exit_request is not None,
            "exit_wait_expired":exit_expiry is not None,"software_budget_verified":bool(runtime and admission and admission['budget_pass']),
            "callback_drain_verified":False, "hardware_verified":False, "usb_strict_pass":False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    try:
        result = analyze(args.journal, args.bundle)
    except (ValueError, OSError, UnicodeError, TypeError, KeyError) as error:
        print(json.dumps({"journal_prefix_verified":False, "usb_strict_pass":False, "error":str(error)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["simulation_session_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
