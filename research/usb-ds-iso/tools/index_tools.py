#!/usr/bin/env python3
"""Generate tools/INDEX.md grouped by filename prefix.

The index is generated, not hand-edited:
    python3 research/usb-ds-iso/tools/index_tools.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
OUT = TOOLS / "INDEX.md"
EXCLUDE = {"INDEX.md", "check_links.py", "index_docs.py", "index_tools.py"}
CURRENT = [
    "build_a23_short24_path_span_candidate.py",
    "audit_a23_short24_path_span.py",
    "build_a23_short24_candidate.py",
    "audit_a23_short24_entry.py",
    "build_a23_short24_entry.py",
    "package_a23_short24.py",
    "analyze_a23_short24_session.py",
    "audit_a23_short24_sdk.py",
    "analyze_a23_audio_cadence.py",
]


def docline(path):
    lines = path.read_text(errors="replace").splitlines()
    value = ""
    for index, line in enumerate(lines[:6]):
        stripped = line.strip()
        if not stripped.startswith(('"""', "'''")):
            continue
        quote = stripped[:3]
        first = stripped[3:]
        value = first if first and not first.startswith(quote) else (
            lines[index + 1].strip() if index + 1 < len(lines) else ""
        )
        break
    for marker in ('"""', "'''"):
        value = value.split(marker)[0]
    return value.strip().replace("|", "\\|")[:100]


def group(name):
    if name.startswith("a23_"):
        return "a23_*"
    return re.split(r"[_]", name, maxsplit=1)[0]


def main():
    files = sorted(
        p for p in TOOLS.glob("*.py") if p.name not in EXCLUDE and not p.name.startswith("__")
    )
    groups = {}
    for path in files:
        groups.setdefault(group(path.name), []).append(path)

    lines = [
        "# 工具索引",
        "",
        "> 自动生成，勿手改。重生成：`python3 research/usb-ds-iso/tools/index_tools.py`。",
        "> 使用约定见 [../WORKFLOW.md](../WORKFLOW.md)；分类说明见 [README.md](README.md)。",
        "",
        f"共 {len(files)} 个 Python 工具。",
        "",
        "## 当前使用",
        "",
        "| 工具 | 用途 |",
        "| --- | --- |",
    ]
    for name in CURRENT:
        path = TOOLS / name
        if path.exists():
            lines.append(f"| [{name}]({name}) | {docline(path) or '—'} |")

    lines += ["", "## 分组", "", "| 前缀 | 数量 |", "| --- | --- |"]
    for key in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        lines.append(f"| `{key}` | {len(groups[key])} |")

    for key in sorted(groups):
        lines += ["", f"## {key}（{len(groups[key])}）", "", "| 工具 | 说明 |", "| --- | --- |"]
        for path in groups[key]:
            lines.append(f"| [{path.name}]({path.name}) | {docline(path) or '—'} |")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(ROOT.parent.parent)} ({len(files)} tools)")


if __name__ == "__main__":
    main()
