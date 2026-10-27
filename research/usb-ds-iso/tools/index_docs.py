#!/usr/bin/env python3
"""Generate docs/INDEX.md from the markdown files in docs/ and the repo entry files.

The index is generated, not hand-edited. Run from anywhere:
    python3 research/usb-ds-iso/tools/index_docs.py
"""
import datetime
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = DOCS / "INDEX.md"
TOP = ["README.md", "START_HERE.md", "WORKFLOW.md", "AGENTS.md", "README_HISTORY.md", "STORAGE.md"]
TITLE = re.compile(r"^#\s+(.+?)\s*$")


def summarize(path):
    title = path.stem
    summary = ""
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        match = TITLE.match(line)
        if match and title == path.stem:
            title = match.group(1)
            continue
        if line.startswith(("---", "```", "|", ">", "#")):
            continue
        summary = re.sub(r"^[-*]\s+", "", line)
        break
    summary = summary.replace("|", "\\|")
    if len(summary) > 110:
        summary = summary[:109] + "…"
    stamp = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    size = max(1, path.stat().st_size // 1024)
    return title.replace("|", "\\|"), summary, stamp, f"{size}K"


def main():
    files = [p for p in DOCS.glob("*.md") if p.name not in {"INDEX.md", "ARCHIVE_INDEX.md"}]
    rows = []
    for path in files:
        title, summary, stamp, size = summarize(path)
        rows.append((path.name, title, stamp, size, summary, path))
    rows.sort(key=lambda row: row[0].lower())

    by_time = sorted(rows, key=lambda row: row[2], reverse=True)[:15]

    lines = [
        "# 文档索引",
        "",
        "> 自动生成，勿手改。重生成：`python3 research/usb-ds-iso/tools/index_docs.py`。",
        "> 当前状态见 [CURRENT.md](CURRENT.md)；历史阶段见 [ARCHIVE_INDEX.md](ARCHIVE_INDEX.md)。",
        "",
        "## 当前入口",
        "",
        "| 文件 | 说明 |",
        "| --- | --- |",
        "| [CURRENT.md](CURRENT.md) | 唯一当前状态 |",
        "| [../START_HERE.md](../START_HERE.md) | 60 秒上手 |",
        "| [../WORKFLOW.md](../WORKFLOW.md) | 最小研究流程 |",
        "| [../README.md](../README.md) | 研究目录入口 |",
        "| [../README_HISTORY.md](../README_HISTORY.md) | 逐轮时间线（历史） |",
        "",
        "## 最近修改",
        "",
        "| 文件 | 日期 | 大小 | 摘要 |",
        "| --- | --- | --- | --- |",
    ]
    for name, title, stamp, size, summary, _ in by_time:
        lines.append(f"| [{name}]({name}) | {stamp} | {size} | {summary} |")

    lines += [
        "",
        f"## 全部文档（{len(rows)}）",
        "",
        "| 文件 | 日期 | 大小 | 标题 / 摘要 |",
        "| --- | --- | --- | --- |",
    ]
    for name, title, stamp, size, summary, _ in rows:
        text = title if not summary else f"{title} — {summary}"
        lines.append(f"| [{name}]({name}) | {stamp} | {size} | {text} |")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(ROOT.parent.parent)} ({len(rows)} docs)")


if __name__ == "__main__":
    main()
