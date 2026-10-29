#!/usr/bin/env python3
"""Run the offline test suite. No USB, SD, SDK or hardware access.

Default is one `unittest discover` process (fast).  `--per-file` isolates each
test file so a crash or import error in one file does not hide the others.
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUICK = [
    "test_current_tools.py",
    "test_uac_standard.py",
    "test_uac_pcm_ring.py",
    "test_a23_audio_cadence.py",
    "test_research_storage.py",
    "test_a23_q2_epoch_lease_model.py",
    "test_a23_q2_generation_model.py",
    "test_urb_accounting.py",
    "test_a23_urb_trace_decode.py",
]


def test_files(pattern):
    return sorted(p for p in (ROOT / "tests").glob(pattern) if p.is_file())


def run(cmd, timeout):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "tools"), str(ROOT), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    try:
        return subprocess.run(
            cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            cmd, 124, exc.stdout or "", (exc.stderr or "") + f"\nTIMEOUT after {timeout}s"
        )


def tail(result, lines=25):
    text = (result.stdout or "") + (result.stderr or "")
    return "\n".join(text.strip().splitlines()[-lines:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-file", action="store_true", help="run each test file separately")
    parser.add_argument("--quick", action="store_true", help="run only the current-topic tests")
    parser.add_argument("--pattern", default="test_*.py", help="test filename glob")
    parser.add_argument("--filter", default="", help="only files whose name contains this")
    parser.add_argument("--timeout", type=int, default=1800, help="seconds per process")
    parser.add_argument("--list", action="store_true", help="list matching files and exit")
    parser.add_argument("-q", "--quiet", action="store_true", help="only print failures and summary")
    args = parser.parse_args()

    if sys.version_info < (3, 10) and not args.quick:
        print(
            "warning: Python < 3.10; some historical modules use 3.10+ syntax. "
            "Use PYTHON=python3.13 for a full run.",
            file=sys.stderr,
        )

    files = test_files(args.pattern)
    if args.quick:
        files = [ROOT / "tests" / name for name in QUICK if (ROOT / "tests" / name).is_file()]
    if args.filter:
        files = [p for p in files if args.filter in p.name]
    if args.list:
        for path in files:
            print(path.relative_to(ROOT))
        return 0
    if not files:
        print(f"no tests matched {args.pattern!r}", file=sys.stderr)
        return 2

    print(f"{len(files)} test files under {ROOT / 'tests'}")
    failures = []

    if args.per_file:
        for path in files:
            module = f"tests.{path.stem}"
            result = run([sys.executable, "-m", "unittest", module], args.timeout)
            status = "ok" if result.returncode == 0 else "FAIL"
            if result.returncode != 0:
                failures.append((path.name, result))
            if not args.quiet or result.returncode != 0:
                print(f"  {status:4}  {path.name}")
    else:
        all_files = test_files(args.pattern)
        if not args.quick and len(files) == len(all_files):
            cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", args.pattern]
        else:
            cmd = [sys.executable, "-m", "unittest", *[f"tests.{p.stem}" for p in files]]
        result = run(cmd, args.timeout)
        if result.returncode != 0:
            failures.append(("discover", result))

    if failures:
        print(f"\n{len(failures)} failure group(s):")
        log = Path(tempfile.gettempdir()) / f"dsh-research-tests-{os.getpid()}.log"
        chunks = []
        for name, result in failures:
            print(f"\n--- {name} (exit {result.returncode}) ---")
            print(tail(result))
            chunks.append(f"===== {name} (exit {result.returncode}) =====\n")
            chunks.append((result.stdout or "") + (result.stderr or ""))
        log.write_text("\n".join(chunks))
        print(f"\nfull output: {log}")
        return 1

    print("\nall tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
