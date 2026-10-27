#!/usr/bin/env python3
"""Freeze/audit completed mock sessions with original reply bytes. No USB entry."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from analyze_io_usb_host_evidence import require, unique_object
from analyze_io_usb_host_session import analyze as analyze_session, status_reply
from audit_io_usb_host_device import audit as audit_device

LIMITS = {"transfer/raw.bin":184320, "transfer/transactions.bin":26880,
          "transfer/metadata.json":16384, "transfer/SHA256SUMS":1024, "transfer/COMMITTED":65,
          "session.jsonl":128*4096, "status-before.bin":2048, "status-after.bin":2048,
          "device-log.txt":1024*1024, "collection.json":4096}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_file(path, limit):
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= limit, f"invalid file: {path.name}")
    return path.read_bytes()


def replies(journal, *, hardware=False):
    rows = [json.loads(line, object_pairs_hook=unique_object) for line in journal.splitlines()]
    result = {}
    for row in rows:
        if row["event"] == "status_observed":
            detail = row["details"]
            result[detail["phase"]] = status_reply(detail, row["ticks"],hardware=hardware)[0]
    require(set(result) == {"before", "after"}, "collection needs both original STATUS observations")
    return result


def analyze(root, *, hardware=False):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "invalid collection directory")
    require({p.name for p in root.iterdir()} == {"transfer", "session.jsonl", "status-before.bin", "status-after.bin",
                                               "device-log.txt", "collection.json", "SHA256SUMS", "COMMITTED"},
            "unexpected/missing collection files")
    transfer = root/"transfer"
    require(transfer.is_dir() and not transfer.is_symlink() and
            {p.name for p in transfer.iterdir()} == {k.split('/')[1] for k in LIMITS if k.startswith('transfer/')},
            "unexpected/missing transfer files")
    files = {name:read_file(root/name, limit) for name, limit in LIMITS.items()}
    manifest = read_file(root/"SHA256SUMS",2048)
    expected = ''.join(f'{sha(files[name])}  {name}\n' for name in sorted(files)).encode()
    require(manifest == expected and read_file(root/"COMMITTED",65) == (sha(manifest)+'\n').encode(),
            "collection manifest/commit mismatch")
    metadata = json.loads(files["collection.json"],object_pairs_hook=unique_object)
    require(type(metadata) is dict and metadata.get("schema") == ('A23-hardware-session-collection-1' if hardware else "A23-session-collection-1") and
            metadata.get("execution_mode") == ('hardware' if hardware else "simulation") and metadata.get("hardware_verified") is False and
            metadata.get("status_source") == ('journal_raw_sdk_reply' if hardware else "journal_raw_mock_reply") and
            metadata.get("device_log_source") == ('supplied_device_log' if hardware else "supplied_mock_log"), "invalid collection mode/source")
    session = analyze_session(root/"session.jsonl",transfer,hardware=hardware)
    require(session["requires_status_binding"] and session["status_raw_journal_binding_verified"] and
            metadata.get("session_id") == session["session_id"] and
            metadata.get("journal_sha256") == sha(files["session.jsonl"]) and
            metadata.get("transfer_manifest_sha256") == sha(files["transfer/SHA256SUMS"]) and
            metadata.get("device_log_sha256") == sha(files["device-log.txt"]), "collection/session identity/hash mismatch")
    original = replies(files["session.jsonl"],hardware=hardware)
    require(original["before"] == files["status-before.bin"] and original["after"] == files["status-after.bin"],
            "collection STATUS differs from original journal bytes")
    native = json.loads(files["transfer/metadata.json"],object_pairs_hook=unique_object)
    require(metadata.get("scenario") == native["scenario"] and
            type(metadata.get("first_frame")) is int and metadata["first_frame"] == native["first_frame"],
            "collection/native scenario mismatch")
    device, device_error = None, None
    try:
        device = audit_device(original["before"],original["after"],files["device-log.txt"],
                              native["scenario"]["kind"],native["scenario"].get("first_sequence",1))
    except (ValueError, UnicodeError) as error:
        # Failed/short replies are intact evidence, not fabricated protocol data.
        device_error = str(error)
    relation = bool(device and device["device_status_and_log_relation_matches"])
    passed = bool(session["simulation_session_pass"] and relation)
    return {"schema":"A23-session-collection-analysis-1", "execution_mode":'hardware' if hardware else "simulation",
            "collection_integrity_verified":True, "simulation_byte_binding_verified":True,
            "session_id":session["session_id"], "collection_manifest_sha256":sha(manifest),
            "status_before_length":len(original["before"]), "status_after_length":len(original["after"]),
            "session":session, "device":device, "device_error":device_error,
            "simulation_collection_pass":passed, "capture_binding_verified":False,
            "callback_drain_verified":False, "firmware_bytes_verified":False,
            "hardware_verified":False, "usb_strict_pass":False}


def durable_write(path, raw):
    fd = os.open(path,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_RDWR,0o600)
    try:
        done = 0
        while done < len(raw):
            try:
                count = os.write(fd,raw[done:])
            except InterruptedError:
                continue
            require(count > 0, "zero write")
            done += count
        os.fsync(fd)
        require(os.pread(fd,len(raw)+1,0) == raw, "collection readback mismatch")
    finally:
        os.close(fd)


def sync_dir(path):
    fd = os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def freeze(journal, bundle, mock_log, output, *, hardware=False):
    """Inputs must be trusted, finished and quiescent. Preserve partial failures."""
    journal, bundle, mock_log, output = map(Path,(journal,bundle,mock_log,output))
    session = analyze_session(journal,bundle,hardware=hardware)
    require(session["requires_status_binding"], "legacy session cannot acquire raw STATUS binding")
    raw_journal = read_file(journal,LIMITS["session.jsonl"])
    original = replies(raw_journal,hardware=hardware)
    require(sha(raw_journal) == session["journal_sha256"], "journal changed while freezing")
    require(bundle.is_dir() and not bundle.is_symlink(), "invalid input bundle")
    files = {k:read_file(bundle/k.split('/')[1],v) for k,v in LIMITS.items() if k.startswith('transfer/')}
    native = json.loads(files["transfer/metadata.json"],object_pairs_hook=unique_object)
    files.update({"session.jsonl":raw_journal,"status-before.bin":original["before"],
                  "status-after.bin":original["after"],"device-log.txt":read_file(mock_log,LIMITS["device-log.txt"])})
    meta = {"schema":'A23-hardware-session-collection-1' if hardware else "A23-session-collection-1",
            "execution_mode":'hardware' if hardware else "simulation","hardware_verified":False,
            "status_source":'journal_raw_sdk_reply' if hardware else "journal_raw_mock_reply",
            "device_log_source":'supplied_device_log' if hardware else "supplied_mock_log",
            "session_id":session["session_id"],"scenario":native["scenario"],"first_frame":native["first_frame"],
            "journal_sha256":sha(raw_journal),"transfer_manifest_sha256":sha(files["transfer/SHA256SUMS"]),
            "device_log_sha256":sha(files["device-log.txt"])}
    files["collection.json"] = (json.dumps(meta,sort_keys=True,indent=2)+'\n').encode()
    # Output parent is trusted; names are fixed. Never replace an existing output.
    output.mkdir(mode=0o700)
    (output/"transfer").mkdir(mode=0o700)
    for name in sorted(files):
        durable_write(output/name,files[name])
    manifest = ''.join(f'{sha(files[name])}  {name}\n' for name in sorted(files)).encode()
    durable_write(output/"SHA256SUMS",manifest)
    sync_dir(output/"transfer"); sync_dir(output)
    durable_write(output/"COMMITTED",(sha(manifest)+'\n').encode())
    sync_dir(output); sync_dir(output.parent)
    return analyze(output,hardware=hardware)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command",required=True)
    check = sub.add_parser("audit"); check.add_argument("collection",type=Path)
    make = sub.add_parser("freeze"); make.add_argument("journal",type=Path); make.add_argument("bundle",type=Path)
    make.add_argument("mock_log",type=Path); make.add_argument("output",type=Path)
    args = parser.parse_args()
    try:
        result = analyze(args.collection) if args.command == "audit" else freeze(args.journal,args.bundle,args.mock_log,args.output)
    except (ValueError,OSError,TypeError,KeyError,UnicodeError) as error:
        print(json.dumps({"collection_integrity_verified":False,"hardware_verified":False,"usb_strict_pass":False,"error":str(error)},indent=2))
        return 2
    print(json.dumps(result,indent=2))
    return 0 if result["simulation_collection_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
