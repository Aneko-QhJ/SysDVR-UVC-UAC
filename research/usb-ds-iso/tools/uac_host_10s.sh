#!/usr/bin/env bash
# Linux standard-host 10 s UAC capture for SysDVR-UVC.
#
# Usage:
#   tools/uac_host_10s.sh --out DIR [--device hw:1,0] [--seconds 10]
#
# Capture uses snd-usb-audio via arecord, then validates the WAV with
# check_uac_wav.py.  No USB commands are sent by this script beyond ALSA's
# normal open/close; the device sysmodule must already be running.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=""
DEVICE=""
SECONDS_LEN=10
while [ $# -gt 0 ]; do
    case "$1" in
        --out) OUT="${2:-}"; shift 2 ;;
        --device) DEVICE="${2:-}"; shift 2 ;;
        --seconds) SECONDS_LEN="${2:-}"; shift 2 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
if [ -z "$OUT" ]; then
    echo "--out DIR is required" >&2
    exit 2
fi
for tool in arecord; do
    command -v "$tool" >/dev/null || { echo "missing $tool" >&2; exit 2; }
done
mkdir -p "$OUT"
exec > >(tee "$OUT/host.log") 2>&1

echo "== arecord -l =="
arecord -l | tee "$OUT/arecord-list.txt" || true
if [ -z "$DEVICE" ]; then
    DEVICE="$(arecord -l | sed -nE 's/^card ([0-9]+):.*SysDVR.*device ([0-9]+):.*/hw:\1,\2/p' | head -1)"
fi
if [ -z "$DEVICE" ]; then
    echo "no SysDVR capture card found; pass --device hw:N,M" >&2
    exit 3
fi
echo "using $DEVICE"

if command -v lsusb >/dev/null; then
    lsusb -v -d 1209:ca57 > "$OUT/lsusb.txt" 2>&1 || true
fi
if command -v dmesg >/dev/null; then
    dmesg | tail -n 200 > "$OUT/dmesg.txt" 2>&1 || true
fi
cat /proc/asound/cards > "$OUT/asound-cards.txt" 2>&1 || true

set +e
timeout $((SECONDS_LEN + 10)) arecord \
    --format=S16_LE --rate=48000 --channels=2 \
    --duration="$SECONDS_LEN" --file-type=wav \
    --device="$DEVICE" "$OUT/uac.wav" 2> "$OUT/arecord.log"
ARECORD_RC=$?
set -e
echo "arecord rc=$ARECORD_RC"
tail -n 40 "$OUT/arecord.log" || true

if [ ! -s "$OUT/uac.wav" ]; then
    echo "no WAV captured" >&2
    exit 4
fi

set +e
python3 "$HERE/check_uac_wav.py" --seconds "$SECONDS_LEN" "$OUT/uac.wav" \
    | tee "$OUT/check.json"
CHECK_RC=${PIPESTATUS[0]}
set -e
echo "check rc=$CHECK_RC"
exit $(( ARECORD_RC != 0 || CHECK_RC != 0 ))
