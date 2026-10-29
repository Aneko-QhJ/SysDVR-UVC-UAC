# U1 控制请求验证准备（2026-10-30，离线）

> 目标：在标准宿主上验证 AC/AS 控制平面（U1a）：`GET_INTERFACE`、
> SAMPLING_FREQ 的 `GET_CUR/MIN/MAX/RES/LEN` 与 `SET_CUR(48000)`。
> **不碰 alt1 数据路径**；`SET_INTERFACE(1)` 归 U1b，单独授权。
> U1a（r7，13/13）与 U1b（alt 0→1→0）均已实机通过；U2 未开始。

## 现状与边界

- U0 已通过（257B/4 接口，macOS `AppleUSBAudio` 绑定，见
  [UAC_HOST_10S.md](UAC_HOST_10S.md)）。
- UAC 仍只在 `UAC_HOST_PROBE` 下启用；默认构建禁用。
- `UacStandardHandle` 已实现 U1a 的请求；`_handleUacSetup` 在
  `UAC_HOST_PROBE` 下轮询 AC/AS SetupEvent。
- U1a 与 U1b 均已通过；U2 的端点安装/数据路径仍受 alt0-only filter 影响，
  需要 8 条 NOP。

## 设备构建（U1a）

- 首次构建（已实机失败）：`private/analysis/UAC-u1a-20261030/build/outputs/exefs.nsp`
  - 86883 B，SHA256 `2f7b5f57…`
- r2（已实机部分通过）：`private/analysis/UAC-u1a-r2-20261030/build/outputs/exefs.nsp`
  - 87102 B，SHA256 `40b55391…`
- r3–r6（迭代，均未通过）：`c1e91c11…`、`1a77894b…`、`a7c1d9dc…`、`ed52fee0…`。
- r7（**通过，已实机**）：`private/analysis/UAC-u1a-r7-20261030/build/outputs/exefs.nsp`
  - 87321 B，SHA256 `01c6ff262f286ddbb27442c4cf907926d9fbdcc23873ac913ec3725178671bec`
- 全部 defines 相同：`-DUAC_HOST_PROBE -DUAC_DESCRIPTOR_PATCH -DFILE_LOGGING`
  - 复用 18 条 descriptor-only payload，无 ISO cave/hook。
- 新增请求日志（`UAC_HOST_PROBE`）：

  ```text
  UAC setup[%u] type=%02x req=%02x val=%04x idx=%04x len=%u action=%d rate=%u
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

## U1a 通过（2026-10-30 01:46，r7）

- 部署 `01c6ff26…` 一次 boot；`uac-control --set-rate` **13/13** 通过：
  `GET_INTERFACE=0`；接口 3 与 EP `0x84` 的 CUR/MIN/MAX/RES 均为 `80 BB 00`；
  `GET_LEN=3`；`SET_CUR(48000)` 成功并回读 48000。
- 设备日志：`UAC setup[2] type=22 ... action=1`（AC 读取数据阶段并 ACK）；
  AS 的重复投递 `rc=0x25c8c` 失败但未 STALL；随后 GET 正常。
- 关键修复链：
  1. `wValue` 低字节 `0x0100`（兼容 `0x0101`）；
  2. UAC setup 按接口/endpoint 归属，不误应答其他接口；
  3. UVC VC/VS 不再 STALL 非自己的 endpoint 请求；
  4. SET_CUR 数据阶段改用 4KB 对齐的 `g_uacControlBuffer`；
  5. 重复投递的数据阶段失败不 STALL，避免污染控制管道。
- 收尾：恢复 `52069a44…` 并安全弹出。

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

## U1b 离线评估与准备（2026-10-30）

- vendor alt1 的根因是 `FUN_000295d0` 在 bus Configured 时只安装 alt0 端点：
  8 个 `cbnz w9`（`35ffff09`）需要 NOP 成 `d503201f`，地址
  `0x29694/0x29ad4/0x29ba4/0x29c88/0x29d54/0x29e38/0x29f04/0x29fe8`
  （本机 usb.elf 已逐条核对）。
- UAC AS 的 EP `0x84` 也是 alt1-only：alt0 无端点、alt1 一个端点，所以同样
  受该 filter 影响。
- 但 **U1b 只验证 `SET_INTERFACE(1)/0` 的控制与状态，不 post 数据**，因此
  phase 1 **不需要 NOP**；NOP 只在 U2 需要端点 `entry+8=1` 时才必要。
- phase 1（已备）：复用 r7 NSP `01c6ff26…`；`uac-control --alt-only`
  依次 `GET_INTERFACE(0) → SET_INTERFACE(1) → GET_INTERFACE(1) →
  SET_INTERFACE(0) → GET_INTERFACE(0)`，不 post、不 PCM。
- phase 2/U2：加 8 条 NOP 后再做一次 PostBuffer；全局 NOP 会影响所有
  接口的 alt 端点安装，需评估后再决定是否收窄。
- 用户已表示后续部署无需另行授权；U1b 仍需一次 boot 的有界范围，失败即停。

## U1b 通过（2026-10-30 01:55）

- 复用 r7 NSP `01c6ff26…`，无 NOP、无数据 post，一次 boot。
- 主机：`GET_INTERFACE` 0 → `SET_INTERFACE(1)` ACK → `GET_INTERFACE` 1 →
  `SET_INTERFACE(0)` ACK → `GET_INTERFACE` 0；failures=0。
- 设备日志：`UAC setup[3] type=01 req=0b val=0001 ... action=3`；
  `... val=0000 ... action=4`；无 usb fatal。alt 切换期间 macOS 有
  disconnect/connect 重枚举，但控制请求全部完成。
- 结论：**alt-setting 控制生命周期可用**；端点安装未被验证（未 post），
  U2 才需要 8 条 NOP 让 `entry+8=1`。
