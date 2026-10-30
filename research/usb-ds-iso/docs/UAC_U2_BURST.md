# UAC U2：alt1 端点安装与一次 ISO burst（离线准备）

> 目标：验证 AS alt1 EP `0x84` 的端点安装和一次 16×192B ISO burst。
> **payload、应用侧触发与 host 入口均已构建（2026-10-30）；未部署、未实机。**

## 现状

- **30 条 runtime payload**（`-DUAC_U2_PATCH`，在 `usbDsEnable()` 前应用，失败即拒绝启用）：
  - 684B cave（`0x68d54..0x69000`，正好填满 RX padding）；
  - 3 条分支：`iso_enter`（`0x30364`）、`iso_event`（`0x30898`）、`iso_report`（`0x2cbe0`）；
  - 18 条配置长度 u16 描述符编辑；
  - 8 条 alt0-filter NOP（安装 alt1 端点）。
  - header：`private/analysis/UAC-u2-producer-20261030/uac_u2_payload.h`
  - NSP：`private/analysis/UAC-u2-producer-20261030/build/outputs/exefs.nsp`
    89174 B，SHA256 `cbfbedbba6c3047eea74bc20c9a5d20ec7ada30f2ab0e70cee6f69f372582518`
    （实机用过 `703e7795…`/88676B、`db97b6e7…`/88669B 与 `81625cab…`/89178B；
    本版修正 precheck 的 manager 偏移，见下节）
  - defines：`-DUAC_HOST_PROBE -DUAC_U2_PATCH -DFILE_LOGGING`
  - 生成工具：[tools/build_uac_u2_producer.py](../tools/build_uac_u2_producer.py)；组装源
    [patches/iso_burst_uac84.S](../patches/iso_burst_uac84.S)。`--check` 可在不组装的情况下
    复核 header/manifest 与 ELF。
  - 构建工具：[tools/build_uac_u2_probe.py](../tools/build_uac_u2_probe.py)。
- 应用侧触发：alt1 后的 `SET_CUR(48000)` 里，`_ctrlAck` 之后向 EP `0x84` post 一次
  3072B（`g_audioEndpointBuffer`，4KB 对齐，flush cache），等一次完成（100ms 上限），
  日志 `UAC U2 post` / `UAC U2 complete`；`burstPosted` 保证每次 boot 只 post 一次。
- host 入口：[uac-burst.c](../host/uac-burst.c)
  - claim interface 3，alt1，**先提交 16×192B ISO transfer，10ms 后再发 SET_CUR 触发**。
    顺序不能反：producer 在 post 时才排 TD，触发早于 submit 会让 TD 落在宿主轮询窗口外
    （A23 的 `iso-probe` 一直是先 submit 再 trigger）。
  - `--trigger-delay-ms 1..500`（默认 10）、`--packets`、`--transfers`（默认 1）。

## 端点字：`0x00C00584`，不是 `0x00C00184`

A23 的 vendor 端点检查字是 `0x01000183`（address `0x83`、`bmAttributes=0x01`、
MPS256）。UAC AS 描述符由 `UacBuildAsConfiguration` 写成 `bmAttributes=0x05`
（`ISOCHRONOUS | async sync`）、MPS192，因此检查字必须是 `0x00C00584`。

U0d 的主机 dump 已直接读到这个端点描述符：`usb-config.txt` 里
`interface 3 alt 1 ... endpoints=1`、`ep 84 attr=05 mps=192 interval=4`
（原始 7 字节为 `07 05 84 05 c0 00 04`，即 `[desc+2]=0x00C00584`）；
证据 `private/runs/UAC-u0d-20261030/usb-config.txt`。

驱动侧已离线确认 8 字节描述符是**原样**拷贝进 endpoint 对象的
（`usb.elf` 的 `0x2fd80`：`ldur w10,[x1,#3]; str w?,[x19,#3]; str w?,[x19]`，
对象就是 `iso_enter` 的 `x1`，`+3` 处即 attributes）。若仍按旧文档的
`0x00C00184`，hook 会走 `reject_original` 返回 `0x1908c`：不会崩，但拿不到任何数据。

## 离线验证

- `make -C research/usb-ds-iso check` 绿（14 个文件，含新增 `test_uac_u2_producer.py`）。
- cave 逐条 before word 与 `usb.elf`/NSO 校验；分支目标 = `0x68d54`/`0x68e9c`/`0x68fb4`。
- cave 反汇编检查：`mov w10,#0x584` + `movk w10,#0xc0,lsl16`、`mov w1,#0x84`、
  `cmp w8,#0x84`；与 EP0x83 版本只差这 4 个字。
- **Unicorn 回放**（[replay_uac_u2_cave.py](../tools/replay_uac_u2_cave.py)）：用合成的
  usb:ds endpoint 对象执行两个 cave 的 `iso_enter`，并跑完整拒绝矩阵：端点字、
  长度、interval、速度、环非空五类输入都以真实 `reject_original` 返回 `0x1908c`
  且不写环；接受路径生成
  16 个 Isoch + 16 个 ED TRB（地址 `DMA+192*i`、长度 192、控制字按 MFI 公式）、
  mailbox `ISO2` 与 producer 指针 `ring+0x200`，且**两个 cave 的结果逐字节相同**
  （ring `d50a3872…`）。依赖 unicorn（不入库）：
  `python3 -m venv private/venv-unicorn && private/venv-unicorn/bin/pip install unicorn &&
  private/venv-unicorn/bin/python tools/replay_uac_u2_cave.py --out
  private/analysis/UAC-u2-producer-20261030/replay.json`。报告
  `private/analysis/UAC-u2-producer-20261030/replay.json`（`check_passed=true`）。
- 编译出的 `uacU2Edits`（30×24B @ `0x20010`）逐条与 manifest 相同；cave before 为
  684 个零。
- 完成路径静态审计：`complete_original`（`0x2a980`）先用 `0x3a30(address)` 求
  endpoint 表索引（IN 端点 = `0x10|num`，EP0x84 → `0x14`），再查
  `manager+0x14c8+index*16`；安装器（`0x295d0`）用同一函数写同一张表。因此
  `mov w1,#0x84` 与 A23 的 `0x83` 走同一通用路径，driver 里没有硬编码 `0x83`。
- 默认 / descriptor / U2 基础 / U2 producer 四种配置均构建通过；基础 NSP 重建后
  text 段与 HEAD 版本逐字节相同（只有 GNU build-id note 随源码行号变化）。
- **没有 USB/SD 操作。**

## U2 实机计划（需新授权）

- 一次 boot、一次 alt1、一次 16×192B 读；不做 PCM、不混 alt1 探针/路径修正版。
- 通过条件：
  - host：`done transfers=1 packets=16 bad=0`（16/16 个 192B 包）；
  - 设备：日志 `UAC U2 post rc=0x0 urb=...` 与 `UAC U2 complete rc=0x0
    requested=3072 transferred=3072`，无 usb fatal；
  - `SET_INTERFACE(0)` 恢复成功，卡恢复 `52069a44…`。
- 停止条件：无数据、post 返回 `0x1908c` 或其他错误、无完成、fatal、断连；
  读卡并恢复安全 NSP，**不重试**。

## 2026-10-30 15:08–15:12 precheck 实机（安全跳过）

- 部署 `81625cab…`（89178B）一次 boot；`UAC u2 patch result=0 record=29`，
  枚举 257B/4 接口正常；无 usb fatal、无新 crash report。
- 宿主按名字解析音频设备为 `[0]`，ffmpeg 采集 5s（无游戏，只有 ~0.6s 有效帧），
  `uac-control --set-rate --repeat=100 --interval-ms=20` 全部成功。
- 设备：100× SET_CUR，36× `skip alt=0`，64× precheck，**64× `post skipped`**。
- precheck 读到 `word=0x00c00584`、`int=4`、`ring=prod=cons=0x2d1d7d000`
  → **EP `0x84` 已安装、环为空**，cave 的接受条件成立。
- 但 `speed=2835697652`、`installed=97`、`table=0x7100051f…` 是代码字：这三项
  偏移漏加 manager 基址 `0xDA000`。修正为 `0xFCA58`/`0xDB610`/`0xDB608` 后
  重建 `cbfbedbb…`（89174B）。
- 证据：`private/runs/UAC-u2-precheck-20261030`（`run.json`、设备日志
  `ec66d049…`）、`private/card-cycles/20261030-u2-precheck`。

## 2026-10-30 15:19–15:22 precheck2 实机（post 被接受后崩溃）

- 部署 `cbfbedbb…`（89174B）一次 boot；补丁 `record=29`，枚举正常。
- 预检四项全过：`word=0x00c00584`、`int=4`、`speed=3`、
  `ring=prod=cons=0x712cd7d000`（`installed=144`、`table=0x800501000003`）。
- `UAC U2 post rc=0x0 urb=388 size=3072` —— **cave 接受了提交**，没有 `post skipped`。
- 随后 usb 崩溃（Data Abort `0x4A8`）：PC `0x2a980`、LR `0x302c4`、`x1=0x84`、
  `x2=0x1908c`，栈 `0x2c84c→0x2a9fc→0x302c4` 递归。即崩溃发生在
  **完成/重提路径**：`0x2c690` 的 vtable 回调（`[obj]+136`）再次进入 `0x302e0`，
  被只认 3072 的 cave 拒绝，错误完成再次递归。
- 宿主无游戏，流反复重启/abort；崩溃后 97 次 SET_CUR `NO_DEVICE`。
- 证据：`private/runs/UAC-u2-precheck2-20261030`（设备日志 `99e84785…`、
  `crash-usb-2.log` `c014c780…`）、`private/card-cycles/20261030-u2-precheck2`。
- 下一步候选：
  1. 离线解码 `0x2c690` 传给 vtable 的提交参数（大小/缓冲），确认重提为什么被拒；
  2. 断路器：把 `0x302c0` 的 `bl 0x2a980` 改成 `nop`，让被拒的重提只返回错误、
     不再进入递归；
  3. 实机在**有游戏/稳定音频流**时进行，避免主机反复 abort 触发重提。

## 断路器候选（已实机，无效）

> 2026-10-30 15:27–15:30 实机一次：`f92ce7a5…`（31 条）在 alt0 的第一次 SET_CUR
> 后触发 usb `User Break`（svcBreak）：`0x302c0` 是**通用** submit 的错误完成，
> EP0 控制传输也走它；跳过它会让失败的 control submit 永不完成并断言。
> 该方案作废，改用下面的“安全接受 cave”。

## 安全接受 cave（离线就绪，待实机）

ISO 提交被拒时，cave 直接返回 0（不建 TRB、不跳 `reject_original`）；调用方
`cbz w0` 跳过错误完成，而 EP0 控制传输根本不经过 cave，所以两条路径都不受影响。

- 汇编 `patches/iso_burst_uac84_safe.S`：所有入口检查失败都跳到 `fail_accept`
  （`ldp x29,x30,[sp],#16; mov w0,#0; ret`）；删除 `iso_event` 的 `error:`
  诊断以腾出空间；cave **668/684B**；
- payload 仍 30 条（cave + 3 分支 + 18 描述符 + 8 NOP），不含 `0x302c0`；
- NSP `6a27d4c8…`（89166B），工作目录 `private/analysis/UAC-u2-safecave-20261030`；
- Unicorn 回放（`tools/replay_uac_u2_cave.py --safe`）：五类拒绝都返回 0、
  不写环；接受路径与 A23 逐字节相同（`d50a3872…`）；
- `tests/test_uac_u2_safecave.py` 覆盖 payload/汇编/回放；
- 边界：被拒的提交对 app 表现为“已接受但无完成”；driver 的请求项仍在队列里，
  上层是否会重试仍需实机观察。

## 旧断路器候选（已被上面替代）

precheck2 已经证明 cave 接受首次 3072B 提交；崩溃来自完成后的重提。静态解码
`0x2c690`（URB 完成）可以看到它按队列项重新提交：

```
ldr  x0, [x20, #96]     ; controller
ldrb w1, [x20, #112]    ; endpoint address (0x84)
ldr  w9, [x8,  #32]     ; entry.size
ldr  x2, [x8,  #16]     ; entry.buffer
ldr  w10,[x20, #116]    ; endpoint limit
csel w3, w9, w10, cc    ; w3 = min(entry.size, limit)
blr  [vtable + 136]     ; 再次进入 0x302e0
```

只有 app 的第一次提交携带 3072；后续重提用的是请求项自己的 size，cave 的
`cmp w3, #3072` 会拒绝，随后 `0x302c0` 的错误完成进入递归。

断路器候选 = 在 payload 里再加一条编辑：

| 地址 | before | after | 作用 |
| --- | --- | --- | --- |
| `0x302c0` | `bl 0x2a980`（`b0e9ff97`） | `nop`（`1f2003d5`） | 跳过错误完成，不再递归 |

- 31 条 payload（30 + 断路器），cave 不变；
- NSP `f92ce7a5…`（89175B），工作目录
  `private/analysis/UAC-u2-breaker-20261030`；
- `tests/test_uac_u2_breaker.py`：断言断路器只改这一条、错误路径其余指令不变，
  并从 `usb.elf` 解码上面的重提参数；
- 边界：这是诊断用断路器——被拒的重提不再触发完成，driver 的请求项不会被完成/
  上报，调用方忽略返回值；目的是先避免 usb 崩溃并观察首次 URB 是否完成。

## 风险与边界

- 8 条 NOP 是全局的：Configured 时所有接口/速度的 alt 端点都会安装。UAC build 只有
  VS alt0 bulk `0x82` 与 AS alt1 ISO `0x84`，没有重复端点，当前风险可控；产品化应把
  NOP 收窄到目标接口/端点，或改为 `SET_INTERFACE` 时按需安装。
- cave 正好 684B（0 余量）：任何新增诊断都会超出 RX padding，需要先腾空间。
- 一次 post 只证明“端点安装 + 一包 16 TD 的 burst”；不证明持续 PCM、时钟/反馈、
  跨块连续性或 UAC 互操作。NOP 收窄与 PCM 都在 U2 通过后再定。
- 未部署、未实机；本文不把任何离线通过当作数据路径证据。

## 2026-10-30 实机结果（一次 boot，未通过）

- 构建 `703e7795…`（88676B），一次 boot；设备日志 `UAC u2 patch result=0
  record=29`、`UAC initialized: AC=2 AS=3 EP=0x84`，无 usb fatal。
- 枚举 `wTotalLength=257`、4 接口；AS alt1 `ep 84 attr=05 mps=192 interval=4`。
- 宿主：`uac-burst` 在 `libusb_claim_interface(3)` 失败（四个接口均 `-3`，
  macOS 系统驱动持有）；改用标准宿主 ffmpeg 采集 `:2` + `uac-control --set-rate`。
- 设备侧 13×`SET_INTERFACE(1)`（action=3）、14×`SET_INTERFACE(0)`（action=4）、
  2×SET_CUR ACK；**0× `UAC U2 post`、0× completion**。两次触发时设备端 alt 都是 0，
  `_postUacBurst` 在 post 之前返回。主机内核日志显示 endpoint 0x84 停止时
  abort 了 30 个请求（流确实开过）。
- 判定：**未通过**；producer 未被触发，不能评价 EP `0x84` 的数据路径。
- 下一轮（已离线就绪）：设备用 `db97b6e7…`，`_postUacBurst` 在 `alt != 1` 时记
  `UAC U2 skip alt=… ep=…`；宿主在采集期间循环触发：
  `host/uac-control --set-rate --repeat=100 --interval-ms=20`
  （`burstPosted` 保证每 boot 最多一次 post）。设备日志里 skip 的行数与
  `UAC setup[...] action=1` 的行数可直接对比，判断触发落在哪个 alt。
- 证据：`private/runs/UAC-u2-burst-20261030`（`run.json`、`device-log-u2.txt`、
  `host-audio-log.txt`、`host-claim-failure.json`）、
  `private/card-cycles/20261030-u2-burst`。卡已恢复 `52069a44…` 并安全弹出。

## 2026-10-30 14:39–14:41 retrigger 实机：usb 崩溃（dangerous）

- 部署 `db97b6e7…`（88669B，含 skip 日志）一次 boot；补丁 `record=29`、初始化
  `AC=2 AS=3 EP=0x84`、配置 257B/4 接口均正常。
- 宿主音频索引在重启后变成 `[0]`；第一次采集误用 `:2`（华为手机麦），100 次
  SET_CUR 都在 alt0，设备无 post。第二次 `:0` 采集启动后 `GET_INTERFACE` 超时，
  SET_CUR 全部 `LIBUSB_ERROR_NO_DEVICE`，设备掉线。
- 设备崩溃：`usb` 进程（`0100000000000006`）Data Abort `0x4A8`（2162-0004）。
  PC `0x2a980`（`complete_original`）、LR `0x302c4`（ISO 提交错误路径），
  `x1=0x84`、`x2=x20=x23=0x1908c`；栈为 `0x2c84c→0x2a9fc→0x302c4` 循环，
  即 cave 以 `reject_original` 的 `0x1908c` 拒绝提交后，驱动错误完成路径无限
  递归到栈溢出。设备日志没有 `type=22`/`UAC U2 skip`/`UAC U2 post`。
- 主机内核：`14:40:39 ep0x84 abort 16 requests`、`14:40:40–52 ep0x00
  status 0xe00002d6`、`14:40:52 hardware connection lost`、`14:41:25` 重新枚举。
- **结论**：`db97b6e7…` 标 dangerous，不再部署；cave 拒绝原因（端点字/interval/
  环非空/长度）与 EP `0x84` 的 endpoint 对象是否安装都还未确定。读卡后恢复
  `52069a44…` 并安全弹出，无重试。
- 安装路径补充（静态）：安装器 `0x295d0..0x2a04c` 共有 **8 条** endpoint 安装
  循环（4 个接口 × SS/请求速度）。用每条 `bl 0x2b520` 前的 `w1`（接口号）与
  `w2`（`4`=SS，`w20`=请求速度）可以把它们逐一映射：

  | 接口 | SS 循环 | 请求速度（HS）循环 |
  | --- | --- | --- |
  | 0 VC | `0x29694` | `0x29AD4` |
  | 1 VS | `0x29BA4` | `0x29C88` |
  | 2 AC | `0x29D54` | `0x29E38` |
  | 3 AS | `0x29F04` | **`0x29FE8`** |

  8 条循环的 alt 过滤（`cbnz w9`）正好是 payload 的 8 条 NOP；
  `tests/test_a23_alt1_nop_coverage.py` 从 `usb.elf` 重新推导这张表，并断言
  AS 的两个循环就是 `0x29F04`/`0x29FE8`、都在 NOP 列表里。SS 循环要求端点后跟
  SS companion（`[desc+8]==0x30`），HS 循环没有该检查。因此 HS 下 AS alt1 的
  EP `0x84` 由 `0x29FE8` 安装，NOP 覆盖没有问题；若 precheck 仍读到 `word=0`，
  要查的是这条 pass 是否执行、AS 的配置数据是否被 `0x2b520` 取到，而不是 NOP。

- 下一次尝试前必须先离线解决：
  1. **已完成**：post 前用 dmnt 短暂 attach 读 endpoint 对象（`base+0xFC300`）
     的端点字/interval/环指针、HS 速度，以及安装器 flag（`base+0x1610`）和
     `complete_original` 的表项指针（`base+0x1608`）；不满足条件就只记
     `UAC U2 post skipped`、不 post。所有地址都由 `usb.elf` 指令推导，
     `tests/test_uac_u2_precheck.py` 重新算出 `0xFC300`/`0x1610`/`0x1608`。
  2. **已确认（静态）**：`reject_original`（`0x30394/0x30398`）返回 `0x1908c`，
     提交调用方（`0x30290` 的 `cbz w0`、`0x302c0` 的 `bl 0x2a980`）对任何非零
     结果都会调用 `complete_original`——即拒绝必然进入崩溃报告里那条递归路径。
     `tests/test_uac_u2_precheck.py::test_reject_path_is_the_fatal_one` 从 ELF
     指令解码确认。递归内部（`complete_original → 0x2c690 → vtable`）仍未知，
     但只要不拒绝就不再进入，precheck 是当前唯一的安全阀。
  3. 证据：`private/runs/UAC-u2-burst2-20261030`（`run.json`、`device-log-u2b.txt`
     `b457421d…`、`crash-usb-0100000000000006.log` `ead11166…`、`erpt-a0311816.txt`）。
