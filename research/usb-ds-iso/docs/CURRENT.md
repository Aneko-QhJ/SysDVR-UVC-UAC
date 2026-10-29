# 当前状态（2026-10-29 17:30，Asia/Shanghai）

> 本文件是唯一“当前状态”。历史细节见 [STATUS.md](STATUS.md)、[PROGRESS_HANDOFF.md](PROGRESS_HANDOFF.md)
> 和 `A23_*.md` 专题；那些文件不再作为入口。
> 本轮只做 usb:ds 的离线静态审计，没有新的 USB/SD/实机操作。

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
- **per-URB fixed2 仍在 UVC init 崩（22:24）**：`71ca5b1a…` 日志
  `UvcDeviceInitialize failed: 0xf601`，同一 Data Abort `advance` x13=0。
  8B report 抑制没解决；per-URB 的 enter/event selector 改变了 init 路径。
  **per-URB 不能作为 boot-time 全局 hook 直接部署**，需要 dormant guard 或 init 后
  才启用。卡已恢复安全 `52069a44…`；per-URB 候选不可部署。见
  [A23_PER_URB_ASSEMBLY.md](A23_PER_URB_ASSEMBLY.md)。
- **serial640 也崩（08:10）**：host 80 包后，usb `User Break`、fatal `0x4A2`，
  栈同 busy-map leak（`+0x2c584` DMA map）。one-in-flight 不能解决 A23 完成/URB
  释放缺失。**serial640 不是稳定基线**；A23 只能在约 5 个 URB 内工作。
- 当前唯一稳定的是 base A23 3-URB 短 burst（`52069a44…`）；持续流需要修
  A23 完成/URB 释放或写新 producer，不能再靠 in-flight/buffer/mailbox 调整。
- **URB/IOVA 记账模型（离线）**：`tests/test_urb_accounting.py` 证明——unmap 正常时
  5 页可复用；unmap 缺失或地址错误才精确得到“5 个完成后第 6 次 map 失败”；8 项 URB
  表解释不了 5。host 已收到 5 个完成，说明 `complete_original` 被调用了，问题在
  **unmap 没释放**（条目/地址/domain/free-list），不是完成没发生。见
  [A23_URB_ACCOUNTING_MODEL.md](A23_URB_ACCOUNTING_MODEL.md)。
  下一步：usb:ds 侧记账 trace（`+0/+4/+8`、`[URB+0x10]/[+0x20]`、domain、unmap
  返回值），trace 出来前不再部署 A23 长流。
- **A23 endpoint trace 已构建（离线）**：[patches/iso_burst_trace.S](../patches/iso_burst_trace.S)
  把 report 诊断换成 endpoint 指针 + producer/consumer/count（680/684B）；
  `iso-stream-trace3.nsp`（`9e8fc035…`）用 safe stream 源码 + trace payload 构建，
  `iso-probe --status` 的 `diagnostics_hex` 由
  [tools/decode_a23_trace.py](../tools/decode_a23_trace.py) 解码。未部署。
  见 [A23_URB_TRACE.md](A23_URB_TRACE.md)。trace3 第一次实机：stream 48/208 正常，
  但 `iso-probe --status` 读到 diagnostics 全 0——trace 没有写 `ISO_PROBE_DIAG_MAGIC`，
  `_pollIsoProbe` 的 magic 检查丢弃了它。v2 (`c237f250…`) 补了 magic，但仍用
  manager+0x14c8+0x830 查 endpoint，status 还是全 0；v3 (`6fe2ec15…`) 直接用 x19
  作为 endpoint 对象，读 `+0/+4/+8`，668/684B。`iso-probe --status` 和
  `--report` 模式已加；`--report` 的 GET_REPORT 是 PIPE，A23 trace 走 NSP status。
  **v3 实机读到了 3 URB 计数**：magic `0x314f5349`、endpoint `0x172f79560`、
  producer=3、consumer=3、count=0——3 个 URB 的 complete/consumer/count 正常。
  **serial5 实机结果**：设备 stop 日志 `posts=5 completes=4 errors=0 attempts=5`；
  stop 后 endpoint `producer=5/consumer=5/count=0`；host 48/112（one-in-flight 下
  只有 3 个 URB 的数据到达 host）。**URB 表是干净的**；serial640 的第 6 次 map
  仍失败，说明不是表/count。卡已恢复安全 `52069a44…`。
  见 [A23_URB_TRACE.md](A23_URB_TRACE.md)。
- **完成 unmap 静态审计（10-29）**：`2c690` 只在 `[URB+0x20] != 0` 时调用
  `4c70(domain, [URB+0x10])`，且**不检查** `4c70` 的返回值；`4c70` 地址 miss
  返回 `0x19a8c`、不 assert。所以“size 为 0”和“IOVA 不匹配”都会静默泄漏，
  而 `+0/+4/+8` 仍归零。`40e0` 以基址作 free-tree key、分配按 size 阈值搜索，
  这个不对称暂标可疑，但不能单独解释 5。下一步 trace 必须读
  `[URB+0x10]/[+0x20]` 或记录 `4c70` miss 计数；在此之前不再上硬件。见
  [A23_URB_UNMAP_AUDIT.md](A23_URB_UNMAP_AUDIT.md)。
- **v4 URB 字段 trace 已实机一次（10-29 17:28）**：magic `0x384f5349`（ISO8），
  diagnostics 写 consumer、最后完成 URB 的 `+0x10` IOVA、`+0x20` size。
  r5 NSP `b0cbe1ed…`，30 条 runtime edits（22 + 8 alt1 NOP），680/684B。
  host 48/160；设备 `posts=5 completes=4 errors=0`；status `consumer=5`、
  `last_iova=0x80030000`、`last_size=3072` → `last_entry_present`。
  **最后一条没有走 size=0 跳过**；本轮只到 5 URB，未尝试第 6 次 map，
  所以不复现也不排除复用。r2–r4 分别修 magic gate/alt1/NOP；卡已恢复
  `52069a44…`。见 [A23_URB_TRACE.md](A23_URB_TRACE.md)。
  下一步是 v5 全条目摘要或 6-URB 复现，需新授权。
- **v5 全条目 trace 已离线构建（10-29）**：magic `0x394f5349`（ISO9），
  diagnostics +8 起写 8 组 `{IOVA 低32, size}`；680/684B。NSP
  `11d5e9eb…`，payload `049c47c4…`，IPS `275bd67c…`，30 条 edits。
  **未部署**；用于确认 `0x80030000` 属于哪个条目、5 个完成是否各有不同 IOVA，
  只需一次 5-URB 单飞授权。见 [A23_URB_TRACE.md](A23_URB_TRACE.md)。
- **两阶段 patch 已实现**：boot base A23；START 时 `_applyIsoStreamPatch()` 应用
  per-URB delta（injection 684B + report branch）。候选
  `iso-stream-twostage3.nsp`（`e33b7237…`，256 包）和
  `iso-stream-twostage-reuse.nsp`（`631dac7f…`，10000 包）已归档未部署；卡安全
  `52069a44…`。见 [A23_PER_URB_TWO_STAGE.md](A23_PER_URB_TWO_STAGE.md)。
  **boot-only 已过；START-before-submit 仍崩**：delta result=0 后立即
  `post 0xf601`，同一 Data Abort `advance` x13=0。说明不是 host 时序，而是
  per-URB enter/event 对真实上下文不成立。**停止 per-URB 部署**，卡恢复安全
  `52069a44…`；下一步先抓 base A23 的真实 x1/x8/x10/ring-slot/event trace。
- 下一步：离线设计 **per-URB mailbox** 或 one-in-flight 基线；3-mailbox 最小布局
  0x60 可放进 ring 尾部，但 cave 684B 已满，主要风险是代码空间。见
  [A23_PER_URB_MAILBOX_DESIGN.md](A23_PER_URB_MAILBOX_DESIGN.md)。
- 离线分析 `entry+4/+8`/8 项 URB 表/A23 完成释放，设计新的 producer；
  当前 A23 诊断 producer 不支持 10s 连续流，UAC 标准宿主还不能接。汇总见
  [A23_SUSTAINED_STREAM_LIMIT.md](A23_SUSTAINED_STREAM_LIMIT.md)。

## 工程状态（2026-10-27）

- 入口/索引已整理：[START_HERE.md](../START_HERE.md)、[WORKFLOW.md](../WORKFLOW.md)、
  [docs/INDEX.md](INDEX.md)、[tools/INDEX.md](../tools/INDEX.md)。
- `make check` 绿：10 个文件，约 2 秒。
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
