#!/usr/bin/env python3
"""Relate supplied short24 host bytes to EXE3/OWN2; no provenance inference."""
import argparse
import json
from pathlib import Path
import struct

from analyze_a23_short24 import analyze as payload, require
from analyze_ep0_execution_v3 import decode_execution


def host_observation(host, recipe):
    files = {n: (host / (n + ".bin")).read_bytes() for n in ("raw", "transactions", "before", "after")}
    m = json.loads((host / "metadata.json").read_text())
    require(m["schema"] == "A23-short24-session-1" and m["recipe"] == recipe and
            m["packet_bytes"] == 24 and m["transaction_count"] == 128, "host short24 binding")
    for name in ("started", "iso_accepted", "observation_complete", "resources_retained"):
        require(m[name] is True, "host observation not complete: " + name)
    for name in ("stopped", "io_unresolved", "process_exit_authorized", "buffer_reuse_verified",
                 "callback_drain_verified", "hardware_verified", "continuous_audio_verified"):
        require(m[name] is False, "host fault or unsupported claim: " + name)
    require(m["failure_reasons"] == [] and all(type(m[k]) is int and m[k] == v for k, v in
        {"iso_attempts": 1, "burst_attempts": 1, "iso_callbacks": 1, "control_callbacks": 1,
         "after_reads": 1, "abort_attempts": 0, "control_status_u32": 0, "control_bytes": 0}.items()),
        "host callback/control counts")
    require(len(files["before"]) == 168, "initial STATUS size")
    before = struct.unpack("<14I", files["before"][:56])
    require(before[:2] == (0x31505349, 1) and before[11] == 0x83 and before[10] in (0, 3) and
            all(before[i] == 0 for i in range(2, 14) if i not in (10, 11)), "initial STATUS not fresh")
    checked = payload(files["raw"], files["transactions"], files["after"], m["first_sequence"], m["overall_u32"])
    sample = m["frame_sample"]
    require(all(type(m[k]) is int and m[k] > 0 for k in
        ("submit_ns", "enqueue_return_ns", "trigger_ns", "iso_arrival_ns", "control_arrival_ns")), "host clocks")
    require(sample["begin_ns"] <= sample["end_ns"] <= m["submit_ns"] <= m["enqueue_return_ns"] <= m["trigger_ns"] and
            m["enqueue_return_ns"] - sample["begin_ns"] <= 16000000 and
            m["enqueue_return_ns"] - m["submit_ns"] <= 8000000 and
            m["trigger_ns"] - m["enqueue_return_ns"] <= 8000000 and
            m["trigger_ns"] - sample["begin_ns"] <= 32000000, "host admission budget")
    require(0 <= m["iso_arrival_ns"] - m["submit_ns"] <= 2000000000 and
            0 <= m["control_arrival_ns"] - m["trigger_ns"] <= 16000000, "native ingress deadline")
    events = m["events"]
    require(len(events) <= 64 and all(a["ns"] <= b["ns"] for a, b in zip(events, events[1:])), "host event order")

    def event(name):
        rows = [r for r in events if r["event"] == name]
        require(len(rows) == 1, "host event count: " + name)
        return rows[0]

    for name in ("before", "after"):
        o = event(name)["details"]
        require(o["accepted"] is True and "error" not in o and o["bytes_transferred"] == 168 and
                o["control"] == [0xc1, 0x51, 0, 2, 168] and o["source"] == "sdk_control_reply" and
                o["begin_ns"] <= o["end_ns"] <= event(name)["ns"], "host STATUS observation")
    iso = event("iso_callback")["details"]
    control = event("control_callback")["details"]
    require(iso["pointer_match"] is True and iso["count"] == 1 and iso["status_u32"] == 0 and
            iso["arrival_ns"] == m["iso_arrival_ns"] and control["count"] == 1 and
            control["status_u32"] == 0 and control["bytes"] == 0 and
            control["arrival_ns"] == m["control_arrival_ns"], "host callback facts")
    require(event("after")["details"]["begin_ns"] >= max(m["iso_arrival_ns"], m["control_arrival_ns"]), "after precedes callbacks")
    require(event("iso_intent")["details"]["first_frame"] == sample["current_frame"] + 32 and
            event("burst_intent")["details"]["first_sequence"] == m["first_sequence"], "host request identity")
    require(all(event(n)["details"]["accepted"] is True and event(n)["details"]["error"] is False
                for n in ("iso_return", "burst_return")), "host enqueue result")
    return m, checked, files


def analyze(host, execution, primary, recipe):
    m, checked, files = host_observation(Path(host), recipe)
    ex = decode_execution(execution, recipe)
    require(ex["primary_kind"] == "ownership" and ex["window"]["window_ms"] == 30000 and
            ex["primary_receipt"]["commit_acknowledged"] is True, "device primary/window/receipt")
    ini = struct.unpack_from("<I", execution, 24)[0]
    require(execution[256 + ini:] == primary, "external primary differs from EXE3")
    tr = ex["primary"]["trace"]
    require(tr["dropped_records"] == tr["invalid_records"] == ex["primary"]["unmatched_reports"] == 0,
            "device trace loss or unmatched report")
    target = [g for g in tr["requests"] if g["interface"] == 2 and g["setup_hex"] and
              bytes.fromhex(g["setup_hex"])[:2] in (b"\xc1\x51", b"\x41\x54")]
    expected = ["c15100000200a800", struct.pack("<BBHHH", 0x41, 0x54, m["first_sequence"], 2, 0).hex(),
                "c15100000200a800"]
    require([g["setup_hex"] for g in target] == expected and
            [g["path"] for g in target] == ["iso_status", "iso_post_and_ack_returned", "iso_status"],
            "target STATUS/BURST/STATUS shape")

    def one(group, stage):
        rows = [r for r in group["records"] if r["stage"] == stage]
        require(len(rows) == 1, "device stage count: " + stage)
        return rows[0]

    require(all(r["result_u32"] == 0 for g in target for r in g["records"]
                if r["stage"] != "ctrl_clear_pre"), "device request stage failed")
    for group, state, sequence in ((target[0], 0, 0), (target[2], 2, m["first_sequence"])):
        row = one(group, "status_snapshot")
        require((row["arg0"], row["arg1"]) == (state, sequence), "device STATUS state/sequence")
        posts = [r for r in group["records"] if r["stage"] == "ctrl_post"]
        parses = [r for r in group["records"] if r["stage"] == "ctrl_parse"]
        require([(r["direction"], r["arg0"]) for r in posts] == [("in", 168), ("out", 0)] and
                [(r["arg0"], r["arg1"]) for r in posts] == [(r["arg0"], r["arg1"]) for r in parses],
                "device STATUS data/status stages")
    burst = target[1]
    require(one(burst, "speed")["arg0"] == 3 and one(burst, "sequence")["arg0"] == m["first_sequence"] and
            one(burst, "iso_post")["arg0"] == 384 and one(burst, "iso_post")["arg1"] == checked["urb_id"] and
            one(burst, "ack")["direction"] == "in", "device ISO length/sequence/URB/ACK")
    require([(r["direction"], r["arg0"]) for r in burst["records"] if r["stage"] == "ctrl_post"] == [("in", 0)],
            "BURST zero-length IN status")
    iso_posts = [r for r in tr["records"] if r["stage"] == "iso_post"]
    require(len(iso_posts) == 1, "extra device ISO submission")
    iso_ledger = [u for u in ex["primary"]["urbs"] if u["channel"] == 8]
    require(iso_ledger == [{"channel": 8, "id": checked["urb_id"], "status": 3}], "device ISO ledger terminal")
    return dict(schema="A23-short24-supplied-session-analysis-1", payload_bytes=384,
                supplied_host_observation_complete=True, supplied_device_relation_consistent=True,
                host_execution_mode=m["execution_mode"], device_trace_records=tr["record_count"],
                recipe=recipe, effective_slots=checked["effective_slots"],
                host_resources_retained=True, process_exit_authorized=False,
                source_authenticated=False, physical_provenance_verified=False, device_lifecycle_verified=False,
                hardware_verified=False, callback_drain_verified=False, buffer_reuse_verified=False,
                continuous_audio_verified=False, usb_strict_pass=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--expected-recipe", required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(args.host, args.execution.read_bytes(), args.primary.read_bytes(), args.expected_recipe), indent=2))
