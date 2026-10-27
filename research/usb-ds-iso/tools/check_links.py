#!/usr/bin/env python3
"""Check relative links in the public markdown files.

`private/` targets are ignored by default: the raw evidence tree is large and
may be pruned. Use --include-private to check those links too.

Exit code 1 when a link target is missing.
"""
import argparse
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SKIP = ("http://", "https://", "mailto:", "#", "tel:")


def targets(text):
    for match in LINK.finditer(text):
        raw = match.group(1).strip()
        if raw.startswith("<") and ">" in raw:
            raw = raw[1 : raw.index(">")]
        else:
            raw = raw.split(" ", 1)[0]
        target = raw.split("#", 1)[0].split("?", 1)[0]
        if not target or target.startswith(SKIP):
            continue
        yield urllib.parse.unquote(target), text[: match.start()].count("\n") + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-private", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    files = sorted(ROOT.glob("*.md")) + sorted((ROOT / "docs").glob("*.md"))
    broken = []
    checked = 0
    for path in files:
        if path.name in {"INDEX.md", "ARCHIVE_INDEX.md"}:
            continue
        for target, line in targets(path.read_text(errors="replace")):
            if not args.include_private and "/private/" in f"/{target}/":
                continue
            if target.startswith("/"):
                resolved = ROOT / target.lstrip("/")
            else:
                resolved = path.parent / target
            checked += 1
            if not resolved.exists():
                broken.append((path.relative_to(ROOT), line, target))

    if broken:
        print(f"{len(broken)} broken link(s) of {checked} checked:")
        for path, line, target in broken:
            print(f"  {path}:{line}: {target}")
        return 1
    if not args.quiet:
        print(f"links ok: {checked} checked in {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
