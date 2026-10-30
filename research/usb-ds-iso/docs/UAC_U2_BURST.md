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
    88676 B，SHA256 `703e779587b0c9d84fc8a7ae1abe9361b8896a6eea1b8bcfcc11904be09ca43b`
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

驱动侧已离线确认 8 字节描述符是**原样**拷贝进 endpoint 对象的
（`usb.elf` 的 `0x2fd80`：`ldur w10,[x1,#3]; str w?,[x19,#3]; str w?,[x19]`，
对象就是 `iso_enter` 的 `x1`，`+3` 处即 attributes）。若仍按旧文档的
`0x00C00184`，hook 会走 `reject_original` 返回 `0x1908c`：不会崩，但拿不到任何数据。

## 离线验证

- `make -C research/usb-ds-iso check` 绿（14 个文件，含新增 `test_uac_u2_producer.py`）。
- cave 逐条 before word 与 `usb.elf`/NSO 校验；分支目标 = `0x68d54`/`0x68e9c`/`0x68fb4`。
- cave 反汇编检查：`mov w10,#0x584` + `movk w10,#0xc0,lsl16`、`mov w1,#0x84`、
  `cmp w8,#0x84`；与 EP0x83 版本只差这 4 个字。
- 编译出的 `uacU2Edits`（30×24B @ `0x20010`）逐条与 manifest 相同；cave before 为
  684 个零。
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

## 风险与边界

- 8 条 NOP 是全局的：Configured 时所有接口/速度的 alt 端点都会安装。UAC build 只有
  VS alt0 bulk `0x82` 与 AS alt1 ISO `0x84`，没有重复端点，当前风险可控；产品化应把
  NOP 收窄到目标接口/端点，或改为 `SET_INTERFACE` 时按需安装。
- cave 正好 684B（0 余量）：任何新增诊断都会超出 RX padding，需要先腾空间。
- 一次 post 只证明“端点安装 + 一包 16 TD 的 burst”；不证明持续 PCM、时钟/反馈、
  跨块连续性或 UAC 互操作。NOP 收窄与 PCM 都在 U2 通过后再定。
- 未部署、未实机；本文不把任何离线通过当作数据路径证据。
