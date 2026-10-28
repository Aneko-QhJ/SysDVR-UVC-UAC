# 当前状态（2026-10-27 19:20，Asia/Shanghai）

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
- UAC1 标准层离线 P0 已完成：[UAC_STANDARD_LAYER.md](UAC_STANDARD_LAYER.md)。
  - 描述符构建器 + lint + alt0/alt1/类请求状态机；`make check` 覆盖。
  - 设备构建通过；UAC 仍禁用，`_setupAudioInterfaces5x` 仍未调用。
  - 未验证 `usb:ds` 的 alt1 端点安装；这是下一个问题。
  - 接口预算：usb:ds/libnx 最多 4 个接口；UVC 2 + UAC 2 = 4，因此 UAC 不能与
    `ISO_PROBE` 的 vendor 接口同 build；`_setupAudioInterfaces5x` 已加拒绝。

## 授权与边界

- `remaining=0`、`acquisition_enabled=false`、`device_log_pending=false`、
  `next_hardware_authorized=false`。
- SD 最后已安全弹出；当前设备现场状态不推定仍就绪。
- 旧票据、actual465、消费 namespace 保持；不恢复旧次数。

## ALT1 探针（bulk alt1 已通过）

- 目的：只回答“alt1 上的 bulk 端点能否安装/被宿主选中”，不引入 UAC、ISO 或 IPS。
- NSP：`/tmp/alt1-probe-log/exefs.nsp`，SHA256 `7fa38c98…`；NPDM 与卡上一致。
- Host：[alt1-probe](../host/alt1-probe)，libusb，SHA256 `a7e4ca89…`。
- 卡操作：完全关机后插入 SD；备份 `exefs.nsp`/`logfile.txt`/旧 `.ips`，只替换 `exefs.nsp`，
  移除旧 IPS，回读并安全弹出。
- 本轮独立计一次：一次 boot、一次 `set_alt(1)`、一次 trigger、一次 64B 读；不重试，
  不恢复 short24 的旧次数。
- **首次结果（20:45）**：`set_alt(1)`/trigger 成功；bulk `LIBUSB_ERROR_IO`；
  status `alt=1 state=3 post=0x0002628c triggers=1`。控制路径接受，端点 post 失败，
  数据路径未建立；不通过、不重试。证据 `private/runs/A-alt1-probe-20261027/`。
- 设备日志（`/logfile.txt`，`e09ad931…`）确认：`ALT1 probe iface=2`、
  `ALT1 SET_INTERFACE 1` 均成功；`ALT1 trigger rc=0x2628c urb=0`。即 alt1 注册/控制可用，
  数据路径在 `PostBufferAsync` 失败。`0x2628c` 的 base `0x628C` 是
  Usb(140)/49 `ResultUsbEndpointAlreadyOpen`，额外 bit17 的具体名称未知。
- alt0 对照（同一 NSP，不 `set_alt`）：同样 `post=0x2628c`、bulk `NOT_FOUND`；
  说明不是 alt 切换导致，而是 alt1-only 描述符注册的端点从未成为可用的控制器上下文。
- `ALT1_PROBE_ENDPOINT_ALT0` 变体（端点同时在 alt0/alt1）结果：
  - alt0：post 0、urb 388、64B、bulk 收到 `ALT1`，**通过**。
  - alt1：`set_alt(1)` 成功、设备 post 0/urb 404/64B/urb_status 3，但 host bulk 读超时、0B。
  - 结论：alt0 端点可用；alt1 切换后端点仍停在 alt0 上下文，host alt1 pipe 收不到数据。
- **runtime NOP patch（21:42）成功**：把 `FUN_000295d0` 的 8 个 alt0 endpoint
  filter 改成 NOP 后，alt1-only 端点 `post=0`、urb 388、64B、urb_status 3；
  host bulk 收到 `ALT1`。设备日志 `ISO runtime patch result=0 record=7`。
  根因/地址/边界见 [A23_ALT1_ENDPOINT_PATCH.md](A23_ALT1_ENDPOINT_PATCH.md)。
  证据 `private/runs/A-alt1-runtime-nop-20261027/`。
- 这证明 **bulk alt1 的安装/选择/传输** 已打通；UAC 的 ISO alt1、ISO producer、
  标准宿主仍未验证。IPS 版本未生效，runtime patch 是当前可用机制。
- **ISO alt1（22:12）通过**：vendor alt1 `EP0x83` ISO/MPS256/interval4 +
  A23 burst producer + NOP；host 收到 16/16 个 192B 包，payload/completion 均 verified；
  设备日志 `ISO runtime patch result=0 record=29`、`ISO seq=1 URB=387 requested=raw=3072
  status=3`。仍是 16×192 的一次性 burst，不是连续 PCM；UAC 标准宿主未验证。
- **3 URB in flight 已验证（10-27 23:4x）**：START 握手 + b0/b1/b2 各自 4K 对齐、
  各用一次；设备 `posts=3 completes=3 errors=0`，host **48/48 包、bad=0**。
- **完成缓冲复用失败（10-28 00:23）**：复用 b0 的第二次提交返回 `0xf601`，usb 再次
  在 DMA map `base+0x2c584` 崩；host 只有 16 valid。结论：3 个不同缓冲可行，但完成
  后的 DMA 缓冲不能直接复用。证据
  `private/runs/A-alt1-stream-hs2-20261027/`、
  `private/runs/A-alt1-stream-reuse-crash-20261028/`。
- 下一步：正常完成路径确实会 unmap（`FUN_0002c690` -> `FUN_00004c70`），但 A23
  完成选中的 URB 可能不对齐，导致旧映射未释放；见
  [A23_BUFFER_RECYCLE.md](A23_BUFFER_RECYCLE.md)。
- **640-buffer 有限池实测：仍崩（14:15）**：640 个不同、4K 对齐、每个只用一次；
  host 10000 包窗口只收到 **80 包（5 个 URB）**，其余为空；设备 b0/b1/b2 成功，
  之后 usb 在 DMA map `+0x2c584` 再次 `svcBreak`。所以持续流的限制不是 buffer
  复用，而是 A23 producer 的 URB/ring 完成/再提交状态。证据
  `private/runs/A-alt1-stream-pool640-crash-20261028/`。
- 卡已恢复安全的 3-URB NSP `52069a44…`；640 池归档为危险构建。
- **诊断构建 `iso-stream-diag8…` 已编译，未部署**：8 个不同缓冲、每次 post/complete
  都写日志，用来拿第 5/6 轮崩溃前的最后计数；实机需新的明确授权。
- 进一步：`FUN_0002c520` 先 map 后检查 8 项表；busy 分支不 unmap，会泄漏 IOVA。
  如果 A23 完成没有按 URB 递减 `entry+8`，表满后的重试就会把 usb 带崩；见
  [A23_BUSY_MAP_LEAK.md](A23_BUSY_MAP_LEAK.md)。
- 更上层根因：A23 mailbox 是 per-endpoint 单实例，`iso_enter` 每次重置，没有 URB
  ID/代际；3 个 in-flight 时后一个 URB 会覆盖前一个的事件归属，完成调用可能缺失/
  错位。**离线 replay 已证实**：3 个 submit 只有最后一个完成，slot 0/32 的 16 个
  ED 全部丢失。见 [A23_SINGLE_MAILBOX_MULTI_URB.md](A23_SINGLE_MAILBOX_MULTI_URB.md)、
  [A23_MAILBOX_REPLAY.md](A23_MAILBOX_REPLAY.md)。
- **one-in-flight 串行基线已构建，未部署**：`iso-stream-serial640.nsp`（`c129dce7…`），
  一次一个 URB、640 个不同 buffer；预期 ~208 轮、~3328 个有效包、errors=0、无 fatal。
  见 [A23_SERIAL_BASELINE.md](A23_SERIAL_BASELINE.md)。
- **per-URB mailbox 实现草案已出**：3 个 0x20 mailbox，按 `slot/32%3` 选择；删除
  report/error 诊断后净余约 24B。见
  [A23_PER_URB_IMPLEMENTATION.md](A23_PER_URB_IMPLEMENTATION.md)。
- 下一步：离线设计 **per-URB mailbox** 或 one-in-flight 基线；3-mailbox 最小布局
  0x60 可放进 ring 尾部，但 cave 684B 已满，主要风险是代码空间。见
  [A23_PER_URB_MAILBOX_DESIGN.md](A23_PER_URB_MAILBOX_DESIGN.md)。
- 离线分析 `entry+4/+8`/8 项 URB 表/A23 完成释放，设计新的 producer；
  当前 A23 诊断 producer 不支持 10s 连续流，UAC 标准宿主还不能接。汇总见
  [A23_SUSTAINED_STREAM_LIMIT.md](A23_SUSTAINED_STREAM_LIMIT.md)。

## 工程状态（2026-10-27）

- 入口/索引已整理：[START_HERE.md](../START_HERE.md)、[WORKFLOW.md](../WORKFLOW.md)、
  [docs/INDEX.md](INDEX.md)、[tools/INDEX.md](../tools/INDEX.md)。
- `make check` 绿：7 个文件，约 3 秒。
- `make check-all` 基线：1074 tests / 499 秒 / 95 errors / 22 skipped；类别见
  [tests/README.md](../tests/README.md)。当前不是门禁，非零不等于本轮改动回归。

## 开放问题（按优先级）

1. **路径修正版**：能否通过配套包/入口检查，并做一次短包复测？需要新的明确授权。
2. **标准 UAC 层**：描述符/控制状态机离线已完成；alt1 bulk 与 ISO 一次性 burst 都已
   打通；连续 PCM 的 3-URB 方案已被硬件否决（usb assert）。剩下单 URB 长传输/低 lead、
   标准宿主枚举、时钟/反馈与跨块样本连续性。
   接口预算 4 已确认：UAC 与 `ISO_PROBE` 不能同 build，探针须用 AC+AS 或专用 build。
3. **持续供给**：在标准宿主（Linux `snd-usb-audio`）下测重挂延迟，再定 ring 深度；
   当前自定义接收器的 47ms 不作为产品下限。
4. **失败分类**：主机 `E00002ED/E000400E` 空前缀（raw 正确）与设备 `CC23/bitmap000F`
   （14 包）是否同源；目前没有被证明同源。

## 下一步（未授权）

- 离线：修正版打包 + 新 recipe 入口 + 包/入口审计；alt1 安装探针或读 `usb:ds`
  descriptor walk。仓库里没有 usb NSO（Build-ID `AD8D36F2…`）；若要读 descriptor
  walk，需要该 dump 或对应 Ghidra 工程。UAC 标准层 P0 已完成，不再重复描述符 lint。
- 实机：另定范围与授权；alt1 探针必须用无 `ISO_PROBE` 的 build（AC+AS 占满 4 个接口）；
  或先做路径修正版短包。两者不要混在同一轮变量里。

## 不证明

持续 PCM、UAC 互操作、时钟同步、缓冲复用、SDK 排空、旧超时根因、未来无事件。
