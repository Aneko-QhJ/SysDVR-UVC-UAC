# 当前状态（2026-10-27 18:10，Asia/Shanghai）

> 本文件是唯一“当前状态”。历史细节见 [STATUS.md](STATUS.md)、[PROGRESS_HANDOFF.md](PROGRESS_HANDOFF.md)
> 和 `A23_*.md` 专题；那些文件不再作为入口。
> 本轮只更新文档与流程，没有新的 USB/SD/实机操作。

## 一句话

视频可用；音频不可用。最近一次短包实机主机侧通过、设备侧保存失败；离线路径修正版已存在，
未打包/未部署。标准 UAC 层（alt1、类请求、时钟）尚未开始。

## 最近实机（2026-10-27）

| 项 | 结果 |
| --- | --- |
| 范围 | 513..528，一次，16×24B |
| 主机 | 384B 连续；IS24/STATUS/128 项原生状态通过；control/ISO 回调 0；abort 0 |
| 设备 | `capture` 4384B、`EXE3` 5440B 创建均返回 `0xD401`（InvalidMemoryState）；末态 retain(reason5)；无完整 trace |
| 判定 | 非严格通过；次数已耗尽；不补试 |
| 原因假设 | 候选从旧父树生成，漏带 769B 路径修正；尚未证明内核错误的确切根因 |
| 主机证据 | `private/runs/A-short24-513-20261027` |
| 设备证据 | `private/card-cycles/20261027-short24-513-read` |
| 收尾 | `private/analysis/A23-short24-first-live-20261027-r1` |

## 离线状态

- 路径修正版：`private/analysis/A23-short24-path-span-candidate-20261027-r1`
  - 14 对象 ELF；5 个已链接静态路径对象各 769B；短包控制器与 runtime 载荷逐字节不变。
  - 7 个 CPU/ASan 专项场景通过；未复现 Switch 内核错误。
- 审计：`private/analysis/A23-short24-path-span-audit-20261027-r2`。
- 未打包、未绑定接收器、未部署、未实测。

## 授权与边界

- `remaining=0`、`acquisition_enabled=false`、`device_log_pending=false`、
  `next_hardware_authorized=false`。
- SD 最后已安全弹出；当前设备现场状态不推定仍就绪。
- 旧票据、actual465、消费 namespace 保持；不恢复旧次数。

## 工程状态（2026-10-27）

- 入口/索引已整理：[START_HERE.md](../START_HERE.md)、[WORKFLOW.md](../WORKFLOW.md)、
  [docs/INDEX.md](INDEX.md)、[tools/INDEX.md](../tools/INDEX.md)。
- `make check` 绿：5 个文件，约 2 秒。
- `make check-all` 基线：1074 tests / 499 秒 / 95 errors / 22 skipped；类别见
  [tests/README.md](../tests/README.md)。当前不是门禁，非零不等于本轮改动回归。

## 开放问题（按优先级）

1. **路径修正版**：能否通过配套包/入口检查，并做一次短包复测？需要新的明确授权。
2. **标准 UAC 层**：alt1 端点安装、`SET_INTERFACE(1)`、`SAMPLING_FREQ` 类请求、
   时钟/反馈与跨块样本连续性。可完全离线推进。
3. **持续供给**：在标准宿主（Linux `snd-usb-audio`）下测重挂延迟，再定 ring 深度；
   当前自定义接收器的 47ms 不作为产品下限。
4. **失败分类**：主机 `E00002ED/E000400E` 空前缀（raw 正确）与设备 `CC23/bitmap000F`
   （14 包）是否同源；目前没有被证明同源。

## 下一步（未授权）

- 离线：修正版打包 + 新 recipe 入口 + 包/入口审计；UAC 描述符 lint 与 alt1 状态机。
- 实机：另定范围与授权；先做路径修正版短包，或直接做标准宿主 10s 流。
  两者不要混在同一轮变量里。

## 不证明

持续 PCM、UAC 互操作、时钟同步、缓冲复用、SDK 排空、旧超时根因、未来无事件。
