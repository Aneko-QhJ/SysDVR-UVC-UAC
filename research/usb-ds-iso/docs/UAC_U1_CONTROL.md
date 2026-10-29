# U1 控制请求验证准备（2026-10-30，离线）

> 目标：在标准宿主上验证 AC/AS 控制平面（U1a）：`GET_INTERFACE`、
> SAMPLING_FREQ 的 `GET_CUR/MIN/MAX/RES/LEN` 与 `SET_CUR(48000)`。
> **不碰 alt1 数据路径**；`SET_INTERFACE(1)` 归 U1b，单独授权。
> 本文只记录离线准备；**未部署、未实机**。

## 现状与边界

- U0 已通过（257B/4 接口，macOS `AppleUSBAudio` 绑定，见
  [UAC_HOST_10S.md](UAC_HOST_10S.md)）。
- UAC 仍只在 `UAC_HOST_PROBE` 下启用；默认构建禁用。
- `UacStandardHandle` 已实现 U1a 的请求；`_handleUacSetup` 在
  `UAC_HOST_PROBE` 下轮询 AC/AS SetupEvent。
- U1b 的 `SET_INTERFACE(1)` 仍可能受 usb:ds 的 alt1 端点安装限制影响，
  不能与 U1a 混在同一轮。

## 设备构建（U1a）

- NSP：`private/analysis/UAC-u1a-20261030/build/outputs/exefs.nsp`
  - 86883 B，SHA256 `2f7b5f57697073d44304ceabedc3c461f1b1b22bcd8b71f8cbc9d06b6bd4fd7b`
  - defines：`-DUAC_HOST_PROBE -DUAC_DESCRIPTOR_PATCH -DFILE_LOGGING`
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
