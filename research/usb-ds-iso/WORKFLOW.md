# 最小研究流程

一轮只回答一个问题；先离线，后实机；失败即停；证据与推断分开。
本文件只规定流程；安全边界、证据定义和验收标准仍以
[RESEARCH_RULES.md](docs/RESEARCH_RULES.md) 为准。

## 一轮 = 5 步

1. **问题卡（5 行）**：问题 / 变化 / 判别条件 / 次数或时长上限 / 停止条件。
2. **离线**：只读分析、构建、测试。产物写 `private/analysis/<id>/`，不覆盖旧目录。
3. **检查**：`make -C research/usb-ds-iso check`（快速，必须绿）；需要时跑 `check-all`。
   测试分层与当前全量基线见 [tests/README.md](tests/README.md)。失败先修，不申请实机。
4. **实机**：需要新的明确授权；一次只改一个变量；实际打印 `WAITING` 后再提示开机；
   失败不重试、不补轮。
5. **收尾**：更新 [docs/CURRENT.md](docs/CURRENT.md)（事实、证据路径、未证明项），
   专题细节写 `docs/<topic>.md`；不把整段状态复制到多个文档。

## 文档规则

- `docs/CURRENT.md` 是唯一“当前状态”。其他文档不要再写“最新状态”。
- `STATUS.md`、`PROGRESS_HANDOFF.md`、`RESEARCH_DIRECTION.md`、`TEST_PLAN.md` 是历史快照：
  保留原文，顶部已标注；不再作为入口。
- 文档里的“下一项仅……”只描述当时计划，不自动成为当前指令。
- 超过一页的细节放专题文档；CURRENT 只放结论和链接。

## 工具规则

- 新工具放 `tools/`，带 `--help` 和至少一个 `tests/test_*.py`。
- 同类逻辑优先复用已有函数；不要复制 manifest/hash/verify。
- 一次性脚本用完移到 `tools/archive/`；迁移前先跑 `make links`。
- 生成物（`docs/INDEX.md`、`tools/INDEX.md`、JSON 报告）不手改，用脚本重生成。

## 提交规则

- 每个候选/每次实机至少一个 commit 或 tag，提交信息写清 `build` / `run` 标识。
- `private/` 不入库；工具、文档、补丁、host/device 源码入库。
- 不把未验证的候选标成 `current` 或 `passed`。

## 停止条件（任一）

- 设备状态未知、存在未决 I/O、所有权不明或证据容量不足。
- 结果与预期不符且无法区分分支。
- 需要新的硬件授权或范围变化。
