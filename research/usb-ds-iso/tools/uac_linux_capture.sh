#!/bin/sh
# Capture one Linux (ALSA/snd-usb-audio) round of the Switch UAC device.
#
#   uac_linux_capture.sh OUTDIR [SECONDS] [ALSA_DEVICE]
#
# Records arecord, the ALSA card/stream snapshot, dmesg and - when debugfs is
# available - the usbmon text stream for bus 1, which is the Linux host's
# per-URB view of endpoint 0x84.  Run as root.  No USB or SD writes.
set -eu

out=${1:?usage: uac_linux_capture.sh OUTDIR [SECONDS] [DEVICE]}
secs=${2:-20}
dev=${3:-plughw:0,0}

mkdir -p "$out"
date -Is > "$out/started.txt"
uname -a > "$out/uname.txt"
arecord -l > "$out/arecord-l.txt" 2>&1 || true
aplay -l > "$out/aplay-l.txt" 2>&1 || true
cat /proc/asound/card0/stream0 > "$out/stream0.txt" 2>&1 || true
cat /proc/asound/cards > "$out/cards.txt" 2>&1 || true
lsusb -t > "$out/lsusb-t.txt" 2>&1 || true

mon=
if [ ! -e /sys/kernel/debug/usb/usbmon ]; then
    mount -t debugfs none /sys/kernel/debug 2>/dev/null || true
fi
if [ -e /sys/kernel/debug/usb/usbmon/1u ]; then
    timeout $((secs + 3)) cat /sys/kernel/debug/usb/usbmon/1u \
        > "$out/usbmon.txt" 2>/dev/null &
    mon=$!
fi

if arecord -D "$dev" -f S16_LE -r 48000 -c 2 -d "$secs" "$out/capture.wav" \
        > "$out/arecord.stdout.txt" 2> "$out/arecord.stderr.txt"; then
    echo "arecord rc=0" > "$out/arecord.rc.txt"
else
    echo "arecord rc=$?" > "$out/arecord.rc.txt"
fi

[ -n "$mon" ] && wait "$mon" 2>/dev/null || true
dmesg -T > "$out/dmesg.txt" 2>&1 || true
date -Is > "$out/stopped.txt"
ls -l "$out/capture.wav" 2>/dev/null || echo "no capture.wav"
