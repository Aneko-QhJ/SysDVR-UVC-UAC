# U1 控制请求验证准备（2026-10-30，离线）

> 目标：在标准宿主上验证 AC/AS 控制平面（U1a）：`GET_INTERFACE`、
> SAMPLING_FREQ 的 `GET_CUR/MIN/MAX/RES/LEN` 与 `SET_CUR(48000)`。
> **不碰 alt1 数据路径**；`SET_INTERFACE(1)` 归 U1b，单独授权。
> 首次与 r2 已实机（分别失败/部分通过，见下）；r3 已构建未部署。

## 现状与边界

- U0 已通过（257B/4 接口，macOS `AppleUSBAudio` 绑定，见
  [UAC_HOST_10S.md](UAC_HOST_10S.md)）。
- UAC 仍只在 `UAC_HOST_PROBE` 下启用；默认构建禁用。
- `UacStandardHandle` 已实现 U1a 的请求；`_handleUacSetup` 在
  `UAC_HOST_PROBE` 下轮询 AC/AS SetupEvent。
- U1b 的 `SET_INTERFACE(1)` 仍可能受 usb:ds 的 alt1 端点安装限制影响，
  不能与 U1a 混在同一轮。

## 设备构建（U1a）

- 首次构建（已实机失败）：`private/analysis/UAC-u1a-20261030/build/outputs/exefs.nsp`
  - 86883 B，SHA256 `2f7b5f57…`
- r2（已实机部分通过）：`private/analysis/UAC-u1a-r2-20261030/build/outputs/exefs.nsp`
  - 87102 B，SHA256 `40b55391…`
- r3（**未部署**）：`private/analysis/UAC-u1a-r3-20261030/build/outputs/exefs.nsp`
  - 86994 B，SHA256 `c1e91c1124dc802cffc45f8d6412f5769788ecbf9b05092e0084a9b90c89e69e`
- 两者 defines 相同：`-DUAC_HOST_PROBE -DUAC_DESCRIPTOR_PATCH -DFILE_LOGGING`
  - 复用 18 条 descriptor-only payload，无 ISO cave/hook。
- 新增请求日志（`UAC_HOST_PROBE`）：

  ```text
  UAC setup type=%02x req=%02x val=%04x idx=%04x len=%u action=%d rate=%u
  ```

  `action`：0 STALL、1 ACK、2 WRITE、3 START、4 STOP。

## 主机工具

`research/usb-ds-iso/host/uac-control`（libusb；不 claim 接口、不启动 streaming）：

```sh
# U1a 只读：GET_INTERFACE + endpoint/interface 的 CUR/MIN/MAX/RES/LEN
research/usb-ds-iso/host/uac-control

# U1a 额外 SET_CUR(48000) 并回读
research/usb-ds-iso/host/uac-control --set-rate
```

- 默认退出码 0 表示全部预期通过，1 表示有失败。
- 端点寻址用 `wIndex=0x84`，接口寻址用 `wIndex=3`。
- **不要**在 U1a 使用 `--alt=1`；它属于 U1b。

## U1a 第一次实机（2026-10-30 01:17，未通过）

- 部署 `2f7b5f57…` 一次 boot；主机 `uac-control --set-rate` 结果：
  - `GET_INTERFACE(AS)` 通过（alt=0）；
  - 所有 sampling-frequency 类请求（CUR/MIN/MAX/RES/LEN、SET_CUR）返回
    `LIBUSB_ERROR_PIPE`；`GET_CUR (ep)` 只回 1 字节。
- 设备日志（3463B，`8c854c46…`）显示请求确实到达 `_handleUacSetup`：
  `val=0100 idx=0084/0003 action=0`，即被设备 STALL。
- 根因：
  1. `UacStandardHandle` 要求 `wValue` 低字节为 `0x01`，而 UAC1 规范与真实
     宿主发送 `0x0100`；
  2. usb:ds 会把同一个 setup 广播到多个接口的 SetupEvent，UAC 处理器没有
     按 `wIndex` 过滤，误 STALL 了发往 UVC 接口 1 的 `SET_INTERFACE` 和
     设备 recipient 的 `GET_DESCRIPTOR`。
- 修复：
  - 接受低字节 `0x00`（规范）与 `0x01`（旧测试约定），其余仍 STALL；
  - 新增 `_uacOwnsSetup()`：只处理 AC/AS 接口或 EP `0x84` 的请求，其他
    直接返回，不再应答/STALL；
  - 测试改用 `0x0100`，保留 `0x0101` 兼容用例，并断言 `0x0102` stall。
- 收尾：读卡后恢复 `52069a44…` 并安全弹出；未重试。
- 证据：`private/runs/UAC-u1a-20261030/`、
  `private/card-cycles/20261030-u1a-control/`。

## U1a-r2 实机（2026-10-30 01:24，部分通过）

- 部署 `40b55391…` 一次 boot；`uac-control --set-rate`：
  - `GET_INTERFACE(AS)` 通过；
  - **接口 recipient** 的 CUR/MIN/MAX/RES 全部 48000（3 字节），LEN=3；
  - **endpoint recipient**（EP `0x84`）的 GET 超时/PIPE，SET_CUR PIPE。
- 设备日志（3761B，`935ce949…`）：endpoint 请求全部
  `UAC setup ignored`——主机工具把 `bmRequestType` 写成 `0xA1/0x21`
  （interface recipient），却把 `wIndex` 写成 `0x84`；r2 的过滤按接口
  recipient 正确忽略了它。
- 同时看到接口 recipient 请求被 AC/AS 各应答一次（两条 `action=2`）。
- 修复：
  - 主机工具：endpoint 请求改用 `0xA2`（GET）/`0x22`（SET）；interface
    请求保持 `0xA1/0x21`；
  - 设备：`_uacOwnsSetup(iface, setup)` 增加 `iface` 归属判断——endpoint
    只由 AS 应答，AC/AS 接口只由对应接口应答。
- r3 NSP `c1e91c11…`（86994B）已构建未部署；重测需新的授权。

## U1a 判定

| 请求 | 期望 |
| --- | --- |
| `GET_INTERFACE(AS)` | 1 字节 `00` |
| `GET_CUR/MIN/MAX/RES`（ep `0x84` 与 if 3） | 3 字节 `80 BB 00`（48000） |
| `GET_LEN` | 2 字节 `03 00` |
| `SET_CUR(48000)`（ep） | ACK，回读 48000 |
| 设备日志 | 每条请求出现且 `action` 与期望一致；无 STALL |
| 链路 | 无 usb fatal、无断连 |

## 停止条件

- 任一 GET stall、超时或返回长度不符；
- `SET_CUR` 非 ACK 或回读不是 48000；
- usb fatal、断连、设备日志缺失；
- 失败即停，读卡并恢复 `52069a44…`；不自动重试。

## U1b（未准备、未授权）

- `--alt=1` 会让 AS 选择 alt1；UAC alt1 端点安装可能仍受 alt0-only 端点
  filter 影响（vendor alt1 需要 NOP patch）。需要单独的离线评估和有界实机，
  不与 U1a 混。
