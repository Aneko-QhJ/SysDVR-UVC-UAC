#!/usr/bin/env python3
"""Read-only Q1 cadence analysis. No SDK, device, acquisition or ticket imports.

PCM durations are byte equivalents of diagnostic patterns, never captured audio.
The fixed Q1 input layout is deliberate; this is not a replacement validator.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct


Q1_MANIFEST = "9f0b5ad5cf94f8cb6a99d42680176086d7bcd1a56956819e55259737c50b0271"
TRANSACTION = struct.Struct("<iIIIQI")
PCM_BYTES_PER_SECOND = 48000 * 2 * 2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ceil_fraction(value):
    return -(-value.numerator // value.denominator)


def packet_budget(packet_bytes, interval_us, packets=16):
    require(all(type(n) is int and n > 0 for n in (packet_bytes, interval_us, packets)),
            "positive integer packet budget required")
    require(packet_bytes % 4 == 0, "packet splits stereo sample frame")
    return dict(packet_bytes=packet_bytes, service_interval_us=interval_us,
                samples_per_packet=packet_bytes // 4,
                nominal_bytes_per_second=packet_bytes * 1000000 / interval_us,
                pcm_rate_multiple=float(Fraction(packet_bytes * 1000000,
                                                interval_us * PCM_BYTES_PER_SECOND)),
                burst_bytes=packet_bytes * packets,
                pcm_equivalent_ms=float(Fraction(packet_bytes * packets * 1000,
                                                PCM_BYTES_PER_SECOND)),
                service_slots_ms=interval_us * packets / 1000,
                first_to_last_slot_ms=interval_us * (packets - 1) / 1000)


def chunk_residues(packet_bytes, chunks=3, chunk_bytes=4096):
    """Conditional full-buffer arithmetic; grc:d may return other lengths."""
    require(all(type(n) is int and n > 0 for n in (packet_bytes, chunks, chunk_bytes))
            and packet_bytes % 4 == chunk_bytes % 4 == 0, "sample-aligned sizes required")
    rows = []
    remainder = 0
    for n in range(chunks):
        emitted, remainder = divmod(remainder + chunk_bytes, packet_bytes)
        rows.append(dict(chunk=n, emitted_packets=emitted, carried_bytes=remainder))
    return rows


def legacy_padding_budget(chunk_bytes=4096, packet_bytes=192):
    require(all(type(n) is int and n > 0 and n % 4 == 0
                for n in (chunk_bytes, packet_bytes)), "sample-aligned sizes required")
    emitted = ((chunk_bytes + packet_bytes - 1) // packet_bytes) * packet_bytes
    return dict(input_bytes=chunk_bytes, emitted_bytes=emitted,
                inserted_silence_bytes=emitted - chunk_bytes,
                inserted_stereo_sample_frames=(emitted - chunk_bytes) // 4,
                sample_count_increase_percent=100 * (emitted - chunk_bytes) / chunk_bytes,
                conditional_on="every successful input chunk has this size; dormant sender only")


def source_facts():
    root = Path(__file__).resolve().parents[3]
    anchors = {
        "source/uvc/uac_descriptors.h": ["#define UAC_SAMPLE_RATE         48000",
            "#define UAC_CHANNELS            2", "#define UAC_SUBFRAME_SIZE       2"],
        "source/capture.h": ["#define AbufSz 0x1000"],
        "source/capture.c": ["frame->DataSize = dataSize;"],
        "source/uvc/uvc_device.c": ["if (!g_uacCtx.initialized || !g_uacCtx.streaming) {",
            "isoProbeByte((uint16_t)(setup->wValue + packet), i);",
            "size_t chunkSize = remaining >= isoPacketSize ? isoPacketSize : remaining;",
            "memset(g_audioEndpointBuffer, 0, isoPacketSize);",
            "g_audioEndpointBuffer, isoPacketSize, &urbId);"],
        "research/usb-ds-iso/patches/iso_burst_context.S": ["cmp w3, #3072",
            "mov w10, #192", "add x2, x2, #192", "cmp w4, #192"],
    }
    facts = []
    for name, needles in anchors.items():
        raw = (root / name).read_bytes()
        lines = raw.decode().splitlines()
        locations = {needle: [i + 1 for i, line in enumerate(lines) if needle in line]
                     for needle in needles}
        require(all(locations.values()), "source anchor changed: " + name)
        facts.append(dict(path=name, sha256=sha(raw), anchors=locations,
                          scope="current checkout static source; not a new device build"))
    return facts


def decode_payload(raw, transactions, first):
    require(len(raw) == 128 * 192 and len(transactions) == 128 * TRANSACTION.size,
            "Q1 fixed128 snapshot sizes differ")
    slots = []
    for i in range(128):
        rc, requested, offset, count, timestamp, options = TRANSACTION.unpack_from(
            transactions, i * TRANSACTION.size)
        require(rc == 0 and requested == 192 and offset == i * 192 and
                options == 0 and count in (0, 192), "invalid transaction")
        if count:
            sequence = first + len(slots)
            require(sequence <= 65535 and len(slots) < 16, "sequence/packet overflow")
            expected = b"ISO1" + struct.pack("<H", sequence) + bytes(
                (j ^ sequence ^ (sequence >> 8)) & 255 for j in range(6, 192))
            require(raw[offset:offset + count] == expected, "diagnostic payload mismatch")
            slots.append(i)
    require(len(slots) == 16 and slots == list(range(slots[0], slots[0] + 16)),
            "16 consecutive diagnostic packets required")
    return slots


def sealed_inputs(run):
    manifest = (run / "SHA256SUMS").read_bytes()
    require(sha(manifest) == Q1_MANIFEST and
            (run / "COMMITTED").read_text() == Q1_MANIFEST + "\n", "Q1 seal differs")
    files = {}
    # Read the sealed run once. Only these in-memory bytes feed the analysis.
    for line in manifest.decode().splitlines():
        digest, name = line.split("  ", 1)
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts and name not in files,
                "invalid manifest path")
        path = run / relative
        require(path.resolve().is_relative_to(run.resolve()) and not path.is_symlink(),
                "input outside run")
        raw = path.read_bytes()
        require(sha(raw) == digest, "sealed input drift: " + name)
        files[name] = raw
    return files


def analyze(run):
    files = sealed_inputs(run)
    journal = [json.loads(line) for line in files["host/session.jsonl"].splitlines()]
    require([r["index"] for r in journal] == list(range(1, len(journal) + 1)) and
            all(a["ticks"] <= b["ticks"] for a, b in zip(journal, journal[1:])),
            "journal order differs")
    require(journal[0]["event"] == "prepared", "prepared event missing")
    prepared = journal[0]["details"]
    require(prepared["max_epochs"] == 3 and prepared["lead_frames"] == 32,
            "Q1 schedule differs")
    numerator, denominator = prepared["timebase_numerator"], prepared["timebase_denominator"]
    require(type(numerator) is int and type(denominator) is int and numerator > 0 and denominator > 0,
            "invalid Mach timebase")
    scale = Fraction(numerator, denominator)

    def duration(end, begin):
        require(end >= begin, "negative tick duration")
        return ceil_fraction((end - begin) * scale)

    def event(name, epoch):
        matches = [r for r in journal if r["event"] == name and r["details"].get("epoch") == epoch]
        require(len(matches) == 1, "missing/duplicate event: " + name)
        return matches[0]["ticks"]

    rows, metadata = [], []
    for n in range(3):
        prefix = f"host/epoch-{n}/"
        m = json.loads(files[prefix + "metadata.json"])
        require(m["epoch"] == n and m["first_sequence"] == 465 + n * 16 and
                m["execution_mode"] == "sdk_observation" and m["overall_u32"] == 0 and
                m["callback_count"] == m["control_count"] == 1 and
                m["budget"]["timebase_numerator"] == numerator and
                m["budget"]["timebase_denominator"] == denominator and
                m["binding"]["session_id"] == journal[0]["session_id"], "Q1 metadata differs")
        require(event("iso_callback", n) >= m["iso_arrival_ticks"] and
                event("trigger_intent", n) <= m["trigger_ticks"] and
                event("iso_intent", n) <= m["submit_ticks"] <= event("iso_return", n) and
                m["sample"]["current_frame"] + 32 == m["first_frame"], "timestamp binding differs")
        slots = decode_payload(files[prefix + "raw.bin"], files[prefix + "transactions.bin"],
                               m["first_sequence"])
        after = files[prefix + "after.bin"]
        require(len(after) == 168, "STATUS size differs")
        status = struct.unpack_from("<14I", after)
        require(status[0] == 0x31505349 and status[2] == m["first_sequence"] and
                status[3] == 2 and status[4] == 0 and status[7:10] == (3072, 3072, 3) and
                status[10:14] == (3, 0x83, 0, 0) and
                struct.unpack_from("<I", after, 56)[0] == 0x374f5349,
                "Q1 completed HS ISO7 STATUS differs")
        if n:
            require(files[prefix + "before.bin"] == files[f"host/epoch-{n-1}/after.bin"],
                    "interepoch STATUS differs")
        rows.append(dict(epoch=n, first_sequence=m["first_sequence"], effective_slots=slots,
                         iso_submit_to_callback_ns=duration(m["iso_arrival_ticks"], m["submit_ticks"]),
                         trigger_to_saved_ns=duration(event("saved", n), m["trigger_ticks"])))
        metadata.append(m)
    for n in range(2):
        m, following = metadata[n:n + 2]
        interval_ticks = following["trigger_ticks"] - m["trigger_ticks"]
        interval = interval_ticks * scale
        rows[n].update(
            trigger_interval_ns=ceil_fraction(interval),
            saved_to_next_before_ns=duration(event("before_intent", n + 1), event("saved", n)),
            next_before_to_trigger_ns=duration(following["trigger_ticks"], event("before_intent", n + 1)),
            pcm_supply_fraction=float(Fraction(16000000, 1) / interval),
            pcm_byte_equivalent_deficit=ceil_fraction(interval * PCM_BYTES_PER_SECOND / 1000000000 - 3072))
    reference_raw = (run.parent.parent / "analysis" /
        "A23-live132-q1-first-host-20261026-r1/report.json").read_bytes()
    reference = json.loads(reference_raw)
    require(reference["run_manifest_sha256"] == Q1_MANIFEST, "reference run mismatch")
    require(len(reference["timing"]) == len(rows), "reference epoch count differs")
    for row, previous in zip(rows, reference["timing"]):
        for key in ("iso_submit_to_callback_ns", "trigger_to_saved_ns", "trigger_interval_ns",
                    "saved_to_next_before_ns", "next_before_to_trigger_ns"):
            if key in row:
                require(row[key] == previous[key], "independent timing mismatch: " + key)
    return dict(schema="A23-audio-cadence-offline-1", run=str(run.resolve()),
                run_manifest_sha256=Q1_MANIFEST, run_files_verified=len(files),
                clock_domain="mach_absolute_time", timebase=[numerator, denominator], epochs=rows,
                reference_report_sha256=sha(reference_raw), source_facts=source_facts(),
                pcm_target=dict(sample_rate=48000, channels=2, bytes_per_sample=2,
                                bytes_per_second=PCM_BYTES_PER_SECOND),
                diagnostic_packet_budget=packet_budget(192, 125),
                rate_matched_arithmetic=[packet_budget(24, 125), packet_budget(192, 1000)],
                full4096_chunk_residues={str(size): chunk_residues(size) for size in (192, 24)},
                dormant_sender_full4096_padding=legacy_padding_budget(),
                same_schedule_zero_between_work=dict(
                    assumption="unchanged observed receive schedule; next submit only after prior callback",
                    iso_wait_ns=[r["iso_submit_to_callback_ns"] for r in rows],
                    pcm_equivalent_per_burst_ns=16000000,
                    all_observed_waits_exceed_pcm_duration=all(r["iso_submit_to_callback_ns"] > 16000000 for r in rows)),
                new_usb_operations=0, captured_pcm=False, continuous_audio_verified=False,
                buffer_reuse_verified=False,
                limitation="Host intents/arrivals are not calibrated bus timestamps; rate alternatives are arithmetic only")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.run.resolve()), "output must be outside sealed run")
    report = analyze(args.run)
    # Exclusive creation protects previous analyses as well as the raw input.
    with args.output.open("x") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(dict(output=str(args.output), epochs=len(report["epochs"]),
                          continuous_audio_verified=False)))


if __name__ == "__main__":
    main()
