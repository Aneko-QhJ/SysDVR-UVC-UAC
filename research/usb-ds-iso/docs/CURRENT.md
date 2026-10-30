# 当前状态（2026-10-30 10:35，Asia/Shanghai）

> 本文件是唯一“当前状态”。历史细节见 [STATUS.md](STATUS.md)、[PROGRESS_HANDOFF.md](PROGRESS_HANDOFF.md)
> 和 `A23_*.md` 专题；那些文件不再作为入口。
> 最后一次实机是 2026-10-30 01:55 的 U1b；U1a/U1b 均通过，卡已恢复
> `52069a44…` 并安全弹出。此后只做 U2 离线：基础 26 条与 producer 30 条
> payload 均已构建，**未部署**。

## 当前进度（2026-10-30 10:35）

| 阶段 | 状态 | 证据 |
| --- | --- | --- |
| U0 枚举 | **通过**（257B/4 接口，音频设备） | `private/runs/UAC-u0d-20261030` |
| U1a 控制 | **通过**（13/13，SET_CUR ACK） | `private/runs/UAC-u1a-r7-20261030` |
| U1b alt | **通过**（alt 0→1→0，无 NOP） | `private/runs/UAC-u1b-20261030` |
| U2 基础 | 已构建（26 条），被 producer payload 取代 | `private/analysis/UAC-u2-base-20261030` |
| U2 producer | **已构建，未部署**（30 条，cave 684B） | `private/analysis/UAC-u2-producer-20261030` |
| 卡 | 安全 `52069a44…`，已弹出 | `private/card-cycles/20261030-u1b-alt` |

- U1a/U1b 使用 r7 NSP `01c6ff26…`（87321B）。U2 基础在其上追加 8 条
  alt0-filter NOP，共 26 条编辑，NSP `abdaff61…`（87461B）；该基础已被
  U2 producer 取代。producer 工作使源码行号变化，重建后的基础 NSP 为
  `4e112f7b…`（87461B）：用 HEAD 源码重建作对照，text 段逐字节相同，
  只有 GNU build-id note 随源码行号变化。
- U2 producer payload：30 条编辑 = 684B cave（`0x68d54..0x69000`，正好填满）
  + 3 条分支（`0x30364`/`0x30898`/`0x2cbe0`）+ 18 描述符 + 8 NOP。
  NSP `703e7795…`（88676B），`-DUAC_HOST_PROBE -DUAC_U2_PATCH -DFILE_LOGGING`；
  编译出的 `uacU2Edits` 表 30 条与 manifest 一致。
- **端点是 `0x00C00584`，不是 `0x00C00184`**：U0d 的 `usb-config.txt` 已从设备
  读到 `ep 84 attr=05 mps=192 interval=4`（原始 `07 05 84 05 c0 00 04`）；驱动在
  `0x2fd80` 把 8 字节描述符原样拷进 endpoint 对象，A23 vendor 端点是
  `0x01000183`（attrs 0x01）。若按旧文档写 `0x00C00184`，hook 会走
  `reject_original`（返回 `0x1908c`），不会崩但拿不到数据。
- **Unicorn 回放（离线）**：`tools/replay_uac_u2_cave.py` 用合成 endpoint 对象执行
  两个 cave 的 `iso_enter`：EP0x83 接受 vendor、拒绝 UAC；EP0x84 反之；两次接受生成的
  16 Isoch + 16 ED TRB、mailbox 与 producer 指针**逐字节相同**（ring `d50a3872…`）。
  报告 `private/analysis/UAC-u2-producer-20261030/replay.json`。
- `uac-control` 支持 `--set-rate` 与 `--alt-only`；`uac-burst` 已改为
  **先提交 ISO transfer、再发 SET_CUR 触发**（原来顺序相反，TD 会落在宿主窗口外）。
- 应用侧 `UAC_U2_PATCH` 在 `usbDsEnable()` 前应用 30 条，失败即拒绝启用；
  alt1 后的 SET_CUR 向 EP `0x84` post 一次 3072B，并等一次完成（100ms 上限，不重试）。
- 下一步：一次有界 U2 burst（需新的明确授权）。详见
  [UAC_U2_BURST.md](UAC_U2_BURST.md)。

## 一句话

视频可用；UAC 枚举与控制平面可用，数据路径仍不可用。U0 已通过（U0d）：
257B/4 接口的复合配置可读，macOS 绑定 AppleUSBAudio 并出现
`SysDVR-UVC Capture` 2ch/48k 输入；U1a 已通过（r7，13/13 控制请求），
U1b 已通过（alt 0→1→0，无 NOP）；U2 producer（30 条，cave 684B，
NSP `703e7795…`）已构建未部署。AS alt1 尚未 post 数据，PCM 未测试。
UAC 默认仍禁用（仅 `UAC_HOST_PROBE`）。卡已恢复安全 `52069a44…` 并安全弹出。
最近一次短包实机（2026-10-27）主机侧通过、设备侧保存失败；路径修正版已存在，
未打包/未部署。

## 最近一次 U1a 实机（2026-10-30，通过）

| 项 | 结果 |
| --- | --- |
| 构建 | U1a-r7 `01c6ff26…`（87321B，`UAC_HOST_PROBE + UAC_DESCRIPTOR_PATCH`） |
| 部署 | 一次 boot，无重试；卡记录 `private/card-cycles/20261030-u1a-r7` |
| 主机 | 13/13：`GET_INTERFACE=0`；接口/endpoint 的 CUR/MIN/MAX/RES=48000；LEN=3；`SET_CUR` 成功并回读 48000 |
| 设备 | `UAC setup[2] type=22 ... action=1`；AS 重复投递 `0x25c8c` 但未 STALL；后续 GET 正常 |
| 判定 | **U1a 通过**；未选 alt1、无 PCM |
| 证据 | `private/runs/UAC-u1a-r7-20261030` |
| 收尾 | 已恢复 `52069a44…` 并安全弹出 |

## 最近一次 UAC 实机（2026-10-30，U0 通过）

| 项 | 结果 |
| --- | --- |
| 构建 | `UAC_HOST_PROBE + UAC_DESCRIPTOR_PATCH`，NSP `48c872f1…`（86780B） |
| 部署 | `atmosphere/contents/00FF0000A53BB666/exefs.nsp`；一次 boot，无重试 |
| 主机 | 配置 `wTotalLength=257`、`bNumInterfaces=4`；AC/AS 可见，AS alt1 EP `0x84` ISO MPS192/interval4 |
| 驱动 | AC → `AppleUSBAudioControlNub`；AS → `AppleUSBAudio`；`usbaudiod` 独占 |
| 音频 | `SysDVR-UVC Capture`，2 声道输入，48 kHz，USB，Nintendo Switch |
| 设备 | `UAC descriptor patch result=0 record=17`；`UAC initialized: AC=2 AS=3 EP=0x84` |
| 判定 | **U0 通过**；未选 alt1、无 PCM、未测 U1/U2 |
| 证据 | `private/runs/UAC-u0d-20261030`、`private/card-cycles/20261030-uac-descriptor-probe` |
| 收尾 | 已恢复 `52069a44…` 并安全弹出；无重试 |

## 最近一次短包实机（2026-10-27）

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
  （seal `d5f18629…`）
  - 14 对象 ELF；5 个已链接静态路径对象各 769B；短包控制器与 runtime 载荷逐字节不变。
  - 7 个 CPU/ASan 专项场景通过；未复现 Switch 内核错误。
- 审计：`private/analysis/A23-short24-path-span-audit-20261027-r2`。
- **配套包已生成（2026-10-30）**：`private/analysis/A23-short24-path-span-package-20261030-r1`
  - seal `c236e895…`；recipe `279586c4…`；NSP `49ec1582…`；IPS `b2151be8…`
    （与首测短包包相同，控制器未变）；回滚基线 `67ec8288…`（2026-10-26 卡快照）。
  - 部署只替换 `exefs.nsp` 与 IPS；`boot2.flag`/`toolbox.json` 不变。
- **新 recipe 入口**：`private/analysis/A23-short24-path-span-entry-20261030-r1`
  （seal `0dc5ea00…`，receiver `275dcf0e…`）；`--describe` 绑定 513..528、16×24B、
  recipe/NSP/IPS/基线，`max_bursts=1`。
- **SDK 模型**：`private/analysis/A23-short24-path-span-sdk-20261030-r1`
  （seal `3205ee3e…`；recipe `279586c4…`；21 原生场景 + 7 关系检查）。
- **包/入口审计**：`private/analysis/A23-short24-path-span-entry-audit-20261030-r2`
  （seal `0ef9c47c…`；7 原生运行场景、5 持久化检查、10 项授权拒绝；0 SDK 对象/USB/SD）。
  若沿用旧 SDK 模型（recipe `53560611…`），审计以 execution recipe mismatch
  拒绝，失败样本保留在 `...-audit-20261030-r1-OLDSDK-FAILED`。
- **未部署、未实测**；短包复测仍需新的明确授权。
- UAC1 标准层离线 P0 已完成：[UAC_STANDARD_LAYER.md](UAC_STANDARD_LAYER.md)。
  - 描述符构建器 + lint + alt0/alt1/类请求状态机；`make check` 覆盖。
  - 设备构建通过；UAC 默认仍禁用，`_setupAudioInterfaces5x` 在默认构建未调用。
  - alt1 端点安装已由 runtime NOP patch 证明（vendor `0x83`）；UAC 的 AS `0x84`
    alt1 已在 U0d 描述符/枚举中出现（MPS192/interval4），但未被选择、无 producer，
    数据路径未验证。
  - 接口预算：usb:ds/libnx 最多 4 个接口；UVC 2 + UAC 2 = 4，因此 UAC 不能与
    `ISO_PROBE` 的 vendor 接口同 build；`_setupAudioInterfaces5x` 已加拒绝。
- UAC 配置路径审计已完成：[UAC_CONFIG_PATH_AUDIT.md](UAC_CONFIG_PATH_AUDIT.md)。
  复合 HS 257B/SS 269B 被 usb:ds 的 u8 长度截断；UAC-only 只 97B，但跳过了
  设备描述符设置。descriptor-only payload（18 条）、Unicorn 仿真与 build 接入
  已完成：未修补 HS `wTotalLength=1`、SS=13，修补后 257/269；补丁 NSP
  `48c872f1…`（86780B）已在 U0d 实机一次并恢复。

## 授权与边界

- `remaining=0`、`acquisition_enabled=false`、`device_log_pending=false`、
  `next_hardware_authorized=false`。
- SD 最后已安全弹出；当前设备现场状态不推定仍就绪。
- 旧票据、actual465、消费 namespace 保持；不恢复旧次数。
- UAC 四轮实机（2026-10-29 18:13–18:40）只留下部署/恢复记录，没有书面 authorization
  票据，相关 scope 仍写 `hardware_authorized: false`；按 RESEARCH_RULES 属于记录缺口，
  不构成后续实机授权。见 [UAC_HOST_10S.md](UAC_HOST_10S.md) 末尾的记录缺口。
- U0d 实机（2026-10-30 01:00）由用户“部署”明确授权，一次 boot；已读卡确认补丁、
  恢复 `52069a44…` 并安全弹出；原始日志
  `private/runs/UAC-u0d-20261030/device-log-u0d.txt`（`520afc3b…`）。
- U1a 的 r4–r7 与 U1b 在用户“如果还要部署，无需另外授权”下连续执行；
  每次一次 boot，U1a-r7/U1b 通过后均恢复 `52069a44…` 并安全弹出。
  r1–r3 的日志与恢复记录保留在 `private/runs/UAC-u1a*`。

## ALT1 探针（bulk alt1 已通过）

- 目的：只回答“alt1 上的 bulk 端点能否安装/被宿主选中”，不引入 UAC、ISO 或 IPS。
- NSP：`../private/tmp-import-20261029/builds/alt1-probe-log/exefs.nsp`，SHA256 `7fa38c98…`；NPDM 与卡上一致。
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
  栈同 busy-map leak（`+0x2c584` DMA map）。当时的结论是 one-in-flight 不能解决
  A23 完成/URB 释放缺失，**serial640 不是稳定基线**、A23 约 5 个 URB 到顶；
  这个“5 URB 墙”已被 2026-10-29 的 v5 320 包推翻，见下。
- 2026-10-28 的当时结论是“唯一稳定的是 base A23 3-URB 短 burst，A23 约 5 个
  URB 到顶”。2026-10-29 的 v5 320 包已推翻这个硬限制（8 post、两页复用、无
  fatal），见下；serial640 的旧崩溃仍需复测解释，不能再直接当作当前 build 的
  稳定边界。
- **URB/IOVA 记账模型（离线，历史容量边界）**：`tests/test_urb_accounting.py`
  证明——unmap 正常时 5 页可复用；unmap 缺失或地址错误才会得到“5 个完成后第 6 次
  map 失败”；8 项 URB 表解释不了 5。它仍是有用的边界模型，但 v5 实机已经显示
  unmap/复用连续成立，不能再拿它断言“5 页墙”。见
  [A23_URB_ACCOUNTING_MODEL.md](A23_URB_ACCOUNTING_MODEL.md)。
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
- **v5 全条目 trace 已实机两次（10-29）**：magic `0x394f5349`（ISO9），
  diagnostics +8 起写 8 组 `{IOVA 低32, size}`；680/684B，NSP `11d5e9eb…`。
  - 160 包：`posts=4 completes=3`，4 个非零条目两页交替；
  - 320 包 + `caffeinate`：host **96/320、bad=0**，设备
    `posts=8 completes=7 errors=0 late=6`，**无 usb fatal**；8 个条目全部非零，
    仍只在 `0x80030000`/`0x80040000` 两页间交替。
  **one-in-flight 下第 6/7/8 次 map 均成功，两页连续复用**；本 build 不存在
  固有“5 URB/5 页”硬限制。见 [A23_URB_TRACE.md](A23_URB_TRACE.md)。
- **serial640 10s 复测通过（10-29 18:01）**：同 v5 build、640 缓冲、
  `posts == completes` 单飞，host `caffeinate -dimsu iso-stream --transfers 1
  --packets 10000` → `packets=3392 bad=0 zero=6608`；设备
  `posts=214 completes=213 errors=0 late=212 attempts=214`，**无 usb fatal**；
  8 条目仍两页交替。**原始 serial640 的 5 URB 崩溃未复现**；主机休眠/USB
  调度或当时运行状态成为首要解释，不再是固有 5 页墙。见
  [A23_SERIAL640_RETEST.md](A23_SERIAL640_RETEST.md)。
- **UAC 标准宿主入口与 U0 已实机一次（10-29，未通过）**：Linux
  `tools/uac_host_10s.sh`、`tools/check_uac_wav.py`、U0–U4 检查清单已备。
  U0 NSP `3c3bf145…`（`UAC_HOST_PROBE`，83942B）已实机一次：
  设备日志 `UAC initialized: AC=2 AS=3 EP=0x84`，但 macOS 只看到 USB 设备，
  没有音频设备，也没有 `USB host connected`/EP0 记录 → **U0 未通过**。
  **U0b/U0c 均未通过**：U0b 的 IAD/enable 修正没有改变 host 不 configure；
  U0c 用 `host/usb-config-dump` 和 macOS 内核日志定位到
  `GET_DESCRIPTOR(config)` 返回 `0xE00002CD`（`kIOReturnNotReadable`），
  即**设备/usb:ds 无法提供新的 UAC 复合配置描述符**。safe build 的 config
  可正常读出（185B/3 接口），工具与链路正常。
  **UAC-only 隔离 NSP 已实机一次，结果更严重**（`7ffdf733…`，仅 AC/AS）：
  设备日志仍写 `UAC initialized: AC=0 AS=1 EP=0x84`，但主机**完全枚举不到
  USB 设备**（不是无音频设备），也没有 `USB host connected`。该构建已标为
  **dangerous，不再部署**，卡已恢复 `52069a44…`。下一步停止 UAC 变体试验，
  先离线审计 usb:ds 的 `AppendConfigurationData`/配置状态、接口数/描述符长度
  约束，解释“复合能枚举但 config 读失败、纯 AC/AS 连设备都不出现”。
  UAC 默认仍禁用，AS `0x84` 仍无 ISO producer，10s PCM 未就绪。
  见 [UAC_HOST_10S.md](UAC_HOST_10S.md)。
- **UAC 配置路径审计完成（10-29 22:50，离线）**：
  [UAC_CONFIG_PATH_AUDIT.md](UAC_CONFIG_PATH_AUDIT.md)。
  - 复合 HS 配置 = 160（UVC）+ 97（AC+AS）= **257B**，SS = 269B；usb:ds 的
    组装器把运行长度存 u8（`ctx+0x1454`），`wTotalLength` 写成 `len & 0xff`，
    getter 也按 u8 截断 → HS `wTotalLength=1`，与主机 `0xE00002CD` 一致。
  - 修复已存在：22 条 runtime edits 的后 18 条把 `strb/ldrb/uxtb/and` 改成
    `strh/ldrh/uxtw/mov`（`0x2bf1c…0x2bdb8`），A23 流 build 已带；UAC build
    没有 `ISO_RUNTIME_PATCH`，所以 257B 必然失败；281B 组装/读取曾仿真通过。
  - UAC-only 的 97B 不触发 u8 截断；它跳过了 `_setupDescriptors5x`，从未设置
    设备描述符/字符串/BOS，libnx 也不补默认；该轮“无设备”是构建缺陷，不是
    usb:ds 配置路径的证据。
  - **descriptor-only payload 已生成并仿真**：18 条编辑（无 ISO cave/hook），
    payload SHA256 `cbed1b66…`；Unicorn 执行组装器/getter，未修补 HS 1/SS 13，
    修补后 257/269，`getter(9)=9`。详见审计文档第 6 节。
  - **build 接入完成（10-30）**：`UAC_DESCRIPTOR_PATCH` 在 `usbDsEnable()` 前由
    dmnt 应用 18 条编辑，校验 BuildID/size，失败即拒绝启用；四种配置（默认/
    UAC probe/UAC-only/probe+patch）均构建通过。补丁 NSP `48c872f1…`
    （86780B）随后在 U0d 部署一次。详见审计文档第 7 节。
  - **U1b 通过（10-30 01:55）**：复用 r7 NSP，无 NOP、无数据 post；
    `GET_INTERFACE` 0→1→0，两条 `SET_INTERFACE` ACK；设备日志
    `action=3`（START）后 `action=4`（STOP），无 usb fatal；切换期间有
    host 重枚举。端点安装未验证，U2 才需要 NOP。
  - **U1a 通过（10-30 01:46，r7）**：NSP `01c6ff26…`（87321B）一次 boot；
    13/13 控制请求通过；设备日志 `UAC setup[2] type=22 ... action=1`，AS 的
    重复投递 `0x25c8c` 但未 STALL；后续 GET 正常。修复链：wValue 0x0100、
    setup 归属、UVC endpoint 过滤、4KB 对齐 CtrlOut、重复投递不 STALL。
    卡已恢复 `52069a44…` 并安全弹出。
  - **U1a-r2 部分通过（10-30 01:24）**：接口 recipient 的
    CUR/MIN/MAX/RES=48000、LEN=3；endpoint recipient 全被忽略，原因是主机
    工具的 `bmRequestType` 用了 interface recipient（`0xA1/0x21`）却把
    `wIndex` 写成 `0x84`。工具改 `0xA2/0x22`，设备补 `iface` 归属判断；
    r3 NSP `c1e91c11…`（86994B，未部署）。卡已恢复 `52069a44…` 并安全弹出。
  - **U1a 第一次实机未通过（10-30 01:17）**：部署 `2f7b5f57…` 一次；
    `GET_INTERFACE` 通过，所有 sampling-frequency 请求 `LIBUSB_ERROR_PIPE`。
    设备日志 `val=0100 ... action=0`，根因是 `UacStandardHandle` 要求 wValue
    低字节 0x01（应 0x00）；另发现 usb:ds 广播 setup，UAC 处理器误应答其他
    接口请求。已修复（接受 0/1 + `_uacOwnsSetup` 过滤）并更新测试；r2 NSP
    `40b55391…`（87102B，未部署）。卡已恢复 `52069a44…`。
  - **U0d 实机通过（10-30 01:00）**：部署 `48c872f1…` 一次 boot；
    `usb-config-dump` 读出 `wTotalLength=257`、4 接口；AC/AS 绑定
    `AppleUSBAudio`，音频设备 `SysDVR-UVC Capture` 2ch/48k/USB；设备日志
    `UAC descriptor patch result=0 record=17`、`UAC initialized: AC=2 AS=3 EP=0x84`。
    **U0 通过**；未选 alt1、无 PCM。卡已恢复 `52069a44…`。证据
    `private/runs/UAC-u0d-20261030`、
    `private/card-cycles/20261030-uac-descriptor-probe`。
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
  A23 诊断 producer 尚未验证 10s 连续流（v5 只到 8 post/320 包），UAC 标准宿主
  还不能接。汇总见 [A23_SUSTAINED_STREAM_LIMIT.md](A23_SUSTAINED_STREAM_LIMIT.md)。

## 工作区留存（2026-10-29）

- 按用户明确要求精简至约 **896 MiB / 1.93 万文件**（含 `.git` 和 `private/`）；
  淘汰 270 个历史离线目录、426 个过时 ZIP、74 个 Git 内旧构建/恢复副本。
- 当前源码、10-27 至 10-29 结果、short24 所需旧父树、固件/Ghidra/依赖、实机原件、
  启动/电源/收尾材料及现行票据保留；16,678 个保留文件/链接逐项核验未变。
  另 1 项未封存的 Finder 目录元数据被系统改写，差异单独记入收据。
- 精简后实际构建当前设备、4 个主机工具、v5 trace 和 short24 路径修正版通过；
  7 场景 short24 审计、Q1 时序重分析、快速测试及公开链接检查通过。没有 USB/SD 操作。
- 本次精简是一次性工作，不设置后续容量门禁；`make check` 只运行快速测试。
  旧离线流程不保证继续回放，详见 [存储策略](../STORAGE.md) 和
  [整理收据](../private/storage/trim-20261029/)；清单区分仍保留的证据与已永久退役的输入。

## 工程状态（2026-10-27 历史测试基线）

- 入口/索引已整理：[START_HERE.md](../START_HERE.md)、[WORKFLOW.md](../WORKFLOW.md)、
  [docs/INDEX.md](INDEX.md)、[tools/INDEX.md](../tools/INDEX.md)。
- `make check` 绿：13 个文件，约 2 秒。
- `make check-all` 基线：1074 tests / 499 秒 / 95 errors / 22 skipped；类别见
  [tests/README.md](../tests/README.md)。当前不是门禁，非零不等于本轮改动回归。

## 开放问题（按优先级）

1. **A23 10s 连续流**：serial640 复测已通过（214 post/213 complete/0 error，
   无 fatal）；下一步在标准宿主（Linux `snd-usb-audio`）接连续 PCM，验证
   跨块样本连续性、时钟/反馈和重挂；仍需新的明确授权。
2. **路径修正版**：配套包/新 recipe 入口/包与入口审计已通过离线检查
   （见 [A23_SHORT24_PACKAGE_AND_ENTRY.md](A23_SHORT24_PACKAGE_AND_ENTRY.md)）；
   剩余的是短包复测本身，需要新的明确授权。
3. **标准 UAC 层**：U0、U1a、U1b 均已通过（257B/4 接口、音频设备；
   13/13 控制请求；alt 0→1→0）。UAC 默认仍禁用（仅 `UAC_HOST_PROBE`）。
   U2 producer 已构建（30 条，EP `0x84`/MPS192/attrs0x05，cave 684B，
   NSP `703e7795…`）；host `uac-burst` 已改为先提交再触发。
   下一步是有界 ISO burst，验证 alt1 端点安装与 16×192B，需要新授权。
   接口预算 4 已确认（UVC 2 + AC/AS 2），UAC 与 `ISO_PROBE` 不能同 build。
   Linux 10s host 入口/检查器已备，但 10s PCM 仍未就绪（先过 U2）。
4. **持续供给**：在标准宿主（Linux `snd-usb-audio`）下测重挂延迟，再定 ring 深度；
   当前自定义接收器的 47ms 不作为产品下限。
5. **失败分类**：主机 `E00002ED/E000400E` 空前缀（raw 正确）与设备 `CC23/bitmap000F`
   （14 包）是否同源；目前没有被证明同源。

## 下一步（未授权）

- 实机（UAC 下一步）：一次有界 U2 burst——一次 boot、一次 alt1、一次
  16×192B 读；通过条件与停止条件见 [UAC_U2_BURST.md](UAC_U2_BURST.md)。
  需要新的明确授权，且不与 alt1 探针/路径修正版混在同一轮。
- 离线（U2 之后）：按 burst 结果决定是否收窄 8 条全局 NOP，再谈 10s PCM。
- 离线：标准宿主（Linux `snd-usb-audio`）10s PCM 入口与检查器已备；PCM producer
  模型已备，但接真实数据要等 U2 通过。
- 实机（短包复测）：路径修正版配套包已打包/绑定/审计，一次 513..528×16×24B
  需要新的明确授权，且不与 U2/alt1 探针混在同一轮。

## 不证明

10s 持续 PCM、完整 ring/长期缓冲复用、UAC 互操作、UAC 数据路径/alt1 选择、
U1b 的 alt1 端点安装与数据路径、时钟同步、SDK 排空、旧超时根因、未来无事件。
