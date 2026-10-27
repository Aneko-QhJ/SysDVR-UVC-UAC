# USB ISO / UAC 研究

本目录研究 Switch `usb:ds` 的设备侧 ISO 传输、vendor 诊断路径与标准 UAC 音频。
当前入口不是本文，而是：

1. [START_HERE.md](START_HERE.md) — 60 秒上手与当前边界
2. [docs/CURRENT.md](docs/CURRENT.md) — 唯一当前状态
3. [WORKFLOW.md](WORKFLOW.md) — 最小研究流程

## 现在做什么

- 最近一次实机（2026-10-27）：短包 16×24B 的主机观察通过；设备 `capture`/`EXE3`
  保存失败 `0xD401`，未严格通过，本次范围已耗尽，不补试。
- 离线路径修正版已存在，但未打包、未绑定接收器、未部署、未实测。
- UAC1 标准层离线 P0 已完成：[UAC_STANDARD_LAYER.md](docs/UAC_STANDARD_LAYER.md)；
  alt1 数据路径已被首次探针否定，UAC 仍禁用。
- ALT1 runtime NOP patch 成功：[A23_ALT1_ENDPOINT_PATCH.md](docs/A23_ALT1_ENDPOINT_PATCH.md)；
  bulk alt1 收到 64B，ISO alt1 收到 16/16 包。**3 URB in flight 已验证**（START +
  3 个各自 4K 对齐的不同缓冲；host 48/48 包）；但**完成缓冲复用会崩 usb**。
  连续 PCM 需要安全 DMA unmap/recycle 或每 URB 新缓冲：
  [A23_REARM_BOUNDARY.md](docs/A23_REARM_BOUNDARY.md)。
- 下一步是修正版配套包/入口，以及 alt1 安装探针/标准宿主验证。

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
| `README_HISTORY.md` | 2026-10-09 → 2026-10-27 逐轮时间线（历史） |

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

流程与安全边界以 [docs/RESEARCH_RULES.md](docs/RESEARCH_RULES.md) 为准。
`private/` 中的原始日志、失败样本和封存材料不覆盖、不移动；未交还的 I/O 存储不释放、
不覆盖、不复用。实机操作需要新的明确授权。
