from a23_context65_binding import FIRST
#!/usr/bin/env python3
"""Independent, offline, simulation-only transaction bundle validator.

Integrity is not provenance: SHA256 detects changed bytes, not fabricated USB
evidence. This format never grants hardware verification or capture permission.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct

ROW = struct.Struct("<IIIIQI")
FILES = {"raw.bin": 184320, "transactions.bin": 26880,
         "metadata.json": 16384, "SHA256SUMS": 1024, "COMMITTED": 65}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def integer(value, low=0, high=2**64 - 1):
    return type(value) is int and low <= value <= high


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON field: {key}")
        result[key] = value
    return result


def analyze(directory, *, hardware=False, burst=False):
    require(not (hardware and burst), "select one explicit hardware backend")
    observation = hardware or burst
    root = Path(directory)
    require(not root.is_symlink() and root.is_dir(), "not a plain bundle directory")
    require({p.name for p in root.iterdir()} == set(FILES), "missing/extra bundle files")
    data = {}
    for name, maximum in FILES.items():
        path = root / name
        require(not path.is_symlink() and path.is_file(), f"not a plain file: {name}")
        require(path.stat().st_size <= maximum, f"oversized file: {name}")
        data[name] = path.read_bytes()
    require(len(data["raw.bin"]) == 184320 and len(data["transactions.bin"]) == 26880,
            "binary length mismatch")
    require(data["COMMITTED"] == (hashlib.sha256(data["SHA256SUMS"]).hexdigest() + "\n").encode(),
            "missing/invalid commit hash")
    manifest = {}
    for line in data["SHA256SUMS"].decode("ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (raw\.bin|transactions\.bin|metadata\.json)", line)
        require(match is not None, "invalid manifest entry")
        digest, name = match.groups()
        require(name not in manifest, "duplicate manifest entry")
        manifest[name] = digest
        require(hashlib.sha256(data[name]).hexdigest() == digest, f"hash mismatch: {name}")
    require(set(manifest) == {"raw.bin", "transactions.bin", "metadata.json"}, "incomplete manifest")
    meta = json.loads(data["metadata.json"], object_pairs_hook=unique_object)
    require(type(meta) is dict, "metadata must be an object")
    require(meta.get("schema") == "A23-transaction-owner-1" and
            meta.get("bundle_schema") == ('A23-burst-hardware-transaction-bundle-1' if burst else
                'A23-hardware-transaction-bundle-1' if hardware else "A23-transaction-bundle-1") and
            meta.get("backend") == ('iousbhost-single-burst-1' if burst else
                'iousbhost-no-td-1' if hardware else "iousbhost-transaction-prototype-1"), "unknown backend/schema")
    require(meta.get("execution_mode") == ('hardware' if observation else "simulation") and meta.get("hardware_verified") is False,
            "invalid execution mode/verification flag")
    if burst:
        import uuid
        binding = meta.get("binding")
        require(type(binding) is dict and set(binding) == {"session_id", "identity", "descriptor_sha256"}, "invalid burst binding")
        require(type(binding["session_id"]) is str and str(uuid.UUID(binding["session_id"])).upper() == binding["session_id"].upper(), "invalid session UUID")
        identity = binding["identity"]
        require(type(identity) is dict and len(identity) == 3 and all(integer(identity.get(k), 1) for k in
            ("device_id", "interface_id", "parent_device_id")) and
            identity["device_id"] == identity["parent_device_id"] and identity["device_id"] != identity["interface_id"], "invalid burst identity")
        hashes = binding["descriptor_sha256"]
        require(type(hashes) is dict and set(hashes) == {"device_descriptor", "configuration_descriptor", "active_interface"} and
            all(type(v) is str and re.fullmatch(r"[0-9a-f]{64}", v) for v in hashes.values()), "invalid burst descriptor hashes")
        require(meta.get("scenario") == {"kind": "single_burst", "first_sequence": FIRST} and
            type(meta["scenario"]["first_sequence"]) is int, "invalid fixed burst scenario")
    for field, expected in (("transaction_count", 960), ("request_bytes_per_transaction", 192),
                            ("transfer_options", 0)):
        require(type(meta.get(field)) is int and meta[field] == expected, f"invalid {field}")
    require(type(meta.get("timed_out")) is bool and type(meta.get("callback_pointer_mismatch")) is bool,
            "invalid boolean fields")
    require(integer(meta.get("first_frame"), 1), "invalid first frame")
    for field in ("submit_begin_ticks", "submit_return_ticks", "callback_arrival_ticks"):
        require(integer(meta.get(field)), f"invalid {field}")
    require(0 < meta["submit_begin_ticks"] <= meta["submit_return_ticks"], "invalid submit times")
    require(integer(meta.get("owner_state"), 4, 5) and
            integer(meta.get("callback_count_at_save")), "invalid owner state/callback count")
    rejected = meta["owner_state"] == 5
    if rejected:
        require("overall_u32" not in meta and meta["callback_arrival_ticks"] == 0 and
                meta["callback_count_at_save"] == 0, "rejection fabricated a callback")
    else:
        require(integer(meta.get("overall_u32"), 0, 2**32 - 1) and
                meta["callback_count_at_save"] >= 1 and
                meta["callback_arrival_ticks"] >= meta["submit_begin_ticks"] and
                "submission_error" not in meta, "invalid completion metadata")
        # Inline completion may arrive before submit returns: do not invent an ordering.
    scenario = meta.get("scenario")
    require(type(scenario) is dict and scenario.get("kind") in {"single_burst", "no_td"}, "invalid scenario")
    raw = data["raw.bin"]
    rows = list(ROW.iter_unpack(data["transactions.bin"]))
    active = []
    statuses = Counter()
    for i, (status, requested, offset, actual, ticks, options) in enumerate(rows):
        require(requested == 192 and offset == i * 192 and options == 0 and actual <= requested,
                f"invalid transaction layout at {i}")
        statuses[f"0x{status:08x}"] += 1
        if actual:
            active.append(i)
    unused_zero = all(raw[i*192:(i+1)*192] == bytes(192) for i in range(960) if i not in active)
    if scenario["kind"] == "single_burst":
        require(integer(scenario.get("first_sequence"), 0, 65535), "invalid first sequence")
        content = len(active) == 16 and active == list(range(active[0], active[0] + 16)) and unused_zero
        for ordinal, i in enumerate(active):
            sequence = (scenario["first_sequence"] + ordinal) & 65535
            expected = b"ISO1" + struct.pack("<H", sequence) + bytes(
                (j ^ sequence ^ (sequence >> 8)) & 255 for j in range(6, 192))
            content = content and rows[i][3] == 192 and raw[i*192:(i+1)*192] == expected
    else:
        content = not active and raw == bytes(184320)
    active_clean = all(rows[i][0] == 0 for i in active)
    finalized = not any(row[0] == 0xe0000001 for row in rows)
    callback_clean = (not rejected and meta.get("overall_u32") == 0 and
                      meta["callback_count_at_save"] == 1 and not meta["callback_pointer_mismatch"] and
                      not meta["timed_out"] and "abort_error" not in meta)
    return {"schema": "A23-transaction-analysis-1", "backend": meta["backend"],
            "evidence_integrity_verified": True, "execution_mode": 'hardware' if observation else "simulation",
            "hardware_verified": False, "usb_strict_pass": False,
            "device_evidence_verified": False, "empty_status_policy_verified": False,
            "submission_rejected": rejected, "overall_u32": meta.get("overall_u32"),
            "timed_out": meta["timed_out"], "callback_count_at_save": meta["callback_count_at_save"],
            "active_indices": active, "status_counts": dict(sorted(statuses.items())),
            "payload_matches": bool(content), "active_native_clean": active_clean,
            "transactions_finalized": finalized, "callback_clean": callback_clean,
            "host_transaction_candidate": bool(content and active_clean and finalized and callback_clean),
            "simulation_logic_pass": bool(not burst and content and active_clean and finalized and callback_clean)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        result = analyze(args.directory)
    except (ValueError, OSError, UnicodeError, TypeError, KeyError) as error:
        print(json.dumps({"evidence_integrity_verified": False, "usb_strict_pass": False,
                          "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["simulation_logic_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
