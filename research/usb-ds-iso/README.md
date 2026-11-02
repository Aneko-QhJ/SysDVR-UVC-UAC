# USB ISO / UAC 研究

本目录研究 Switch `usb:ds` 的设备侧 ISO 传输、vendor 诊断路径与标准 UAC 音频。
当前入口不是本文，而是：

1. [START_HERE.md](START_HERE.md) — 60 秒上手与当前边界
2. [docs/CURRENT.md](docs/CURRENT.md) — 唯一当前状态
3. [WORKFLOW.md](WORKFLOW.md) — 最小研究流程

## 现在做什么

- **UAC 目标**：让 Switch 输出标准 48 kHz / 2ch / 16 bit 音频（192 B/ms）。
- **已通过**：U0 枚举（257 B / 4 接口，macOS `AppleUSBAudio`）、U1a 控制
  （13/13）、U1b alt 0→1→0；U2 单 burst（v14，3072 B，2/2）与顺序 4-burst
  （v23，12288 B）。
- **2 在飞已成立**：v29a 的驱动队列补丁让第二个请求进入 cave，v29b 的
  per-set mailbox 修好完成账本——8/8 全部 `3072/3`，host = 设备 = 24576 B。
- **滚动流**：v29c 用 8 槽复用跑 64 个 post，host 187968 B、61 个完整
  3072 B 片段、持续 ~2.1 s；收尾在 **TD 环 wrap** 失败（cave link `+0xf70`
  vs 驱动 `+0xff0`，一套 16-TD 被拆到环首）。
- **下一步 v29d**：对齐 link 槽（首选 patch 驱动常量 `0xff0→0xf70`），或在
  wrap 前 rearm/复位；修好后重跑 64/128 post 看 100%，再谈 lead 32→16 与
  3 在飞。
- **边界**：占空比仍约 47%（16 ms 音频 / ~34 ms 墙钟），48 kHz 连续不成立；
  UAC 默认禁用（仅 `UAC_HOST_PROBE`）。收尾 `SET_INTERFACE(0)` 的 usb
  `svcBreak`、DCI-9 `ISO_ENTRY=0x270`、8 个 descriptor NOP 仍未隔离。
- **A23 线**（vendor alt1、short24、标准宿主 10s PCM）已挂起；其逐轮记录在
  [README_HISTORY.md](README_HISTORY.md)，专题分组见
  [docs/ARCHIVE_INDEX.md](docs/ARCHIVE_INDEX.md)；UAC 层概要见
  [UAC_STANDARD_LAYER.md](docs/UAC_STANDARD_LAYER.md)。

## 目录

| 路径 | 用途 |
| --- | --- |
| `docs/` | 专题记录；`CURRENT.md` 是当前状态，其余是历史 |
| `tools/` | Python 工具；[tools/README.md](tools/README.md) 是分类索引 |
| `tests/` | 离线测试；[tests/run_all.py](tests/run_all.py) 是统一 runner，分层见 [tests/README.md](tests/README.md) |
| `host/` | macOS IOUSBHost 接收器与主机侧实验 |
| `device/` | 设备侧候选与 C 头文件 |
| `patches/` | 汇编 patch 与部署材料 |
| `private/` | 原始证据（不入库，只读） |
| `README_HISTORY.md` | 2026-10-09 → 2026-11-02 逐轮时间线（历史） |

## 检查

```sh
make -C research/usb-ds-iso check      # 当前专题的快速检查
make -C research/usb-ds-iso check-all  # 全部离线测试（较慢）
make -C research/usb-ds-iso index      # 重生成 docs/INDEX.md 与 tools/INDEX.md
make -C research/usb-ds-iso links      # 检查公开文档的相对链接
```

## 历史与索引

- [README_HISTORY.md](README_HISTORY.md) — 逐轮时间线
- [docs/INDEX.md](docs/INDEX.md) — 全部专题文档索引（生成）
- [docs/ARCHIVE_INDEX.md](docs/ARCHIVE_INDEX.md) — 历史阶段分组
- [docs/STATUS.md](docs/STATUS.md)、[docs/PROGRESS_HANDOFF.md](docs/PROGRESS_HANDOFF.md)、
  [docs/RESEARCH_DIRECTION.md](docs/RESEARCH_DIRECTION.md)、[docs/TEST_PLAN.md](docs/TEST_PLAN.md)
  — 历史快照，保留原文，不再作为入口

## 边界

流程与安全边界以 [docs/RESEARCH_RULES.md](docs/RESEARCH_RULES.md) 和
[START_HERE.md](START_HERE.md) 的“当前边界”为准。2026-11-01 16:19 起为常设
实机授权：部署/测试不再逐轮申请，插卡与开机前通知用户；一次 boot、失败即停、
不重试。`private/` 中的原始日志、失败样本和封存材料不覆盖、不移动；未交还的
I/O 存储不释放、不覆盖、不复用。
