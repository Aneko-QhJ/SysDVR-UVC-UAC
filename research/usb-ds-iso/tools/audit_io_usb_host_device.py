#!/usr/bin/env python3
"""Correlate supplied STATUS bytes and an A23 log offline. Never grants USB pass."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from analyze_io_usb_host_evidence import integer, require

BUILD_ID = "AD8D36F2029822A4C498F055ADBDAA789EB913C6000000000000000000000000"
STATUS_FIELDS = ("magic", "version", "sequence", "state", "post_result", "urb_id", "report_id",
                 "requested", "transferred", "urb_status", "speed", "endpoint", "report_count", "report_result")


def decode_status(raw):
    require(type(raw) is bytes and len(raw) == 168, "STATUS must be exactly 168 bytes")
    result = dict(zip(STATUS_FIELDS, struct.unpack_from("<14I", raw)))
    require(result["magic"] == 0x31505349 and result["version"] == 1 and
            result["sequence"] <= 65535 and result["state"] <= 4 and result["endpoint"] == 0x83,
            "unknown STATUS identity/protocol")
    result["diagnostics_hex"] = raw[56:].hex()
    return result


def iso7(raw, module_base, module_size):
    require(len(raw) == 112, "diagnostic size mismatch")
    magic, error, control, terminal, bitmap, actual, first = struct.unpack_from("<6IQ", raw)
    require(magic == 0x374f5349, "not ISO7 diagnostics")
    selected, valid = struct.unpack_from("<II", raw, 72)
    context = struct.unpack_from("<8I", raw, 80)
    info0, info1, _, _, tx, _, _, _ = context
    configured = ((info0 & 7) == 1 and (info0 >> 8 & 3) == 0 and (info0 >> 16 & 255) == 1 and
                  (info1 >> 3 & 7) == 5 and (info1 >> 8 & 255) == 0 and info1 >> 16 == 256 and tx >> 16 == 256)
    page, slot = first & ~4095, (first & 4095)//16
    pointer_ok = (first % 16 == 0 and slot < 247 and module_base <= page and page+4096 <= module_base+module_size)
    header_ok = (valid == 1 and selected < 16384 and (control >> 10 & 63) == 5 and not control >> 31 and
                 (control >> 20 & 0x7ff) == (((selected >> 3)+32) & 0x7ff))
    events = []
    tags_match = True
    for i in range(2):
        lo, hi, result, flags, mfi = struct.unpack_from("<5I", raw, 32+i*20)
        tag = lo | hi << 32
        expected = page + ((slot+1+2*i) % 247)*16
        good = bool(flags and (flags >> 10 & 63) == 32 and flags & 4 and
                    (flags >> 16 & 31) == 7 and result >> 24 == 1 and (result & 0xffffff) == 192 and tag == expected)
        tags_match = tags_match and good
        record_valid = bool(flags and (flags >> 10 & 63) == 32)
        events.append({"record_valid":record_valid, "raw_words":[lo,hi,result,flags,mfi],
                       "tag":f"{tag:016x}" if record_valid else None,
                       "completion_code":result >> 24 if record_valid else None,
                       "actual":result & 0xffffff if record_valid else None,
                       "flags_u32":flags, "mfi":mfi if record_valid else None, "matches":good})
    return {"magic":"ISO7", "error_offset":error, "first_control":control, "terminal":terminal,
            "completed_bitmap":bitmap, "actual_sum":actual, "first_virtual_trb":f"{first:016x}",
            "frame_select_mfi":selected, "context_words":list(context),
            "context_matches":bool(configured and header_ok), "ring_pointer_matches":pointer_ok,
            "own_first_two_event_tags_match":tags_match, "events":events,
            "completion_matches":bool(terminal == 1 and bitmap == 0xffff and actual == 3072 and error == 0 and
                                      configured and header_ok and pointer_ok and tags_match),
            "atomic_snapshot":False, "bus_phase_verified":False}


def exactly_one(lines, pattern, description):
    matches = [(i, re.fullmatch(pattern, line)) for i, line in enumerate(lines)]
    matches = [(i, m) for i, m in matches if m is not None]
    require(len(matches) == 1, f"missing/duplicate {description}")
    return matches[0]


def audit(before, after, log, kind="single_burst", first_sequence=1):
    require(kind in {"single_burst", "no_td"} and integer(first_sequence, 0, 65535), "invalid scenario")
    before_status, after_status = decode_status(before), decode_status(after)
    require(type(log) is bytes and 0 < len(log) <= 1024*1024 and log.endswith(b"\n"), "truncated/oversized log")
    lines = log.decode("utf-8", errors="strict").splitlines()
    start, _ = exactly_one(lines, r"SysDVR-UVC 1\.0\.0 initializing\.\.\.", "startup")
    revision, _ = exactly_one(lines, r"ISO diagnostic revision A23 HS ISO7 bInterval1 followup-SIA experiment", "A23 revision")
    hos, _ = exactly_one(lines, r"ISO HOS 22\.5\.0", "HOS")
    for pattern, desc in ((r"ISO firmware query rc=0x0", "firmware query"),
                          (r"ISO usb pid=[1-9][0-9]* query rc=0x0", "USB process"),
                          (r"ISO usb module query rc=0x0 count=1", "module query")):
        exactly_one(lines, pattern, desc)
    module, m = exactly_one(lines, rf"ISO usb module\[0\] BuildID={BUILD_ID} base=([0-9a-f]+) size=([0-9a-f]+)", "target BuildID")
    module_base, module_size = int(m[1],16), int(m[2],16)
    require(module_base > 0 and module_base % 4096 == 0 and module_size == 0x369000, "invalid target module range")
    attach, _ = exactly_one(lines, r"ISO usb debug attach rc=0x0", "debug attach")
    runtime, m = exactly_one(lines, r"ISO runtime patch result=0 record=([1-9][0-9]*) last-rc=0x0", "runtime installation")
    runtime_record = int(m[1])
    initialized, _ = exactly_one(lines, r"UVC device initialized", "device initialized")
    running, _ = exactly_one(lines, r"SysDVR-UVC running \(video \+ audio\)", "running marker")
    require(start == 0 and start < revision < hos < module < attach < runtime < initialized < running,
            "startup/install ordering mismatch")
    # Do not let a correct marker hide a second or conflicting boot/installation.
    prefixes = ("SysDVR-UVC ", "ISO diagnostic revision ", "ISO HOS ", "ISO firmware query ",
                "ISO usb pid=", "ISO usb module query ", "ISO usb module[", "ISO usb debug attach ", "ISO runtime patch ")
    expected_counts = (3,1,1,1,1,1,1,1,1) # initializing, starting, running
    for prefix, count in zip(prefixes, expected_counts):
        require(sum(line.startswith(prefix) for line in lines) == count, f"conflicting log identity: {prefix}")
    require(not any(line.startswith(("ISO rollback", "ISO runtime target mismatch")) for line in lines), "rollback/mismatch log")
    submits, timings, completions = [], [], []
    patterns = {
        "ISO submit ":r"ISO submit seq=(\d+) speed=(\d+) length=(\d+) rc=0x([0-9a-f]+) urb=(\d+)",
        "ISO timing ":r"ISO timing seq=(\d+) urb=(\d+) frequency=(\d+) trigger=(\d+) post-before=(\d+) post-after=(\d+) ack-before=(\d+) ack-after=(\d+)",
        "ISO seq=":r"ISO seq=(\d+) URB=(\d+) requested=(\d+) raw-count=(\d+) status=(\d+) diag-word2=(\d+)"}
    for position, line in enumerate(lines):
        for prefix, pattern in patterns.items():
            if line.startswith(prefix):
                match = re.fullmatch(pattern,line)
                require(match is not None, "malformed submission/timing/completion line")
                values = tuple(int(v,16 if prefix == "ISO submit " and i == 3 else 10) for i,v in enumerate(match.groups()))
                {"ISO submit ":submits, "ISO timing ":timings, "ISO seq=":completions}[prefix].append((position,values))
    forbidden_controls = []
    for line in lines:
        m = re.fullmatch(r"EP0\[\d+\]: reqType=0x([0-9a-f]+) req=0x([0-9a-f]+) wVal=0x([0-9a-f]+) wIdx=0x([0-9a-f]+) wLen=(\d+)",line)
        if m and int(m[1],16) == 0x41 and int(m[4],16) == 2:
            request = int(m[2],16)
            if request == 0x52 or (kind == "no_td" and request in {0x50,0x54}):
                forbidden_controls.append(request)
    fresh = (all(before_status[k] == 0 for k in ("sequence","state","post_result","urb_id","report_id",
             "requested","transferred","urb_status","report_count","report_result")) and before_status["speed"] in (0,3))
    diagnostic = None
    relation = False
    if kind == "no_td":
        # Diagnostics contain live software samples. Only the STATUS header must remain unchanged.
        relation = fresh and all(before_status[k] == after_status[k] for k in STATUS_FIELDS) and not submits and not timings and not completions
    else:
        diagnostic = iso7(after[56:],module_base,module_size)
        if len(submits) == len(timings) == len(completions) == 1:
            sp, s = submits[0]; tp, t = timings[0]; cp, c = completions[0]
            ticks = t[3:]
            relation = bool(fresh and running < sp < tp < cp and s[0] == t[0] == c[0] == first_sequence and
                s[1:4] == (3,3072,0) and s[4] == t[1] == c[1] == after_status["urb_id"] > 0 and
                t[2] == 19200000 and list(ticks) == sorted(ticks) and ticks[0] > 0 and
                c[2:5] == (3072,3072,3) and c[5] == diagnostic["first_control"] and
                after_status["sequence"] == first_sequence and after_status["state"] == 2 and
                after_status["post_result"] == after_status["report_result"] == 0 and
                after_status["report_id"] == after_status["urb_id"] and after_status["urb_status"] == 3 and
                after_status["requested"] == after_status["transferred"] == 3072 and after_status["speed"] == 3 and
                diagnostic["completion_matches"])
    relation = bool(relation and not forbidden_controls)
    return {"schema":"A23-device-relation-1", "source_kind":"supplied_artifacts", "scenario":kind,
            "first_sequence":first_sequence, "startup_log_identity_matches":True, "runtime_record":runtime_record,
            "before_status":before_status, "after_status":after_status, "diagnostics":diagnostic,
            "fresh_status_matches":fresh, "submissions":len(submits), "completions":len(completions),
            "forbidden_controls":forbidden_controls, "device_status_and_log_relation_matches":relation,
            "before_sha256":hashlib.sha256(before).hexdigest(), "after_sha256":hashlib.sha256(after).hexdigest(),
            "log_sha256":hashlib.sha256(log).hexdigest(), "capture_binding_verified":False,
            "firmware_bytes_verified":False, "video_closed_verified":False, "hardware_verified":False,
            "usb_strict_pass":False, "root_cause_confirmed":False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("--scenario", choices=("single_burst","no_td"), default="single_burst")
    parser.add_argument("--first-sequence", type=int, default=1)
    args = parser.parse_args()
    try:
        result = audit(args.before.read_bytes(),args.after.read_bytes(),args.log.read_bytes(),args.scenario,args.first_sequence)
    except (ValueError, OSError, UnicodeError, TypeError, KeyError) as error:
        print(json.dumps({"device_status_and_log_relation_matches":False, "usb_strict_pass":False, "error":str(error)},indent=2))
        return 2
    print(json.dumps(result,indent=2))
    return 0 if result["device_status_and_log_relation_matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
