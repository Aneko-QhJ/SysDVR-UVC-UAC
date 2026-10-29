# UAC1 标准层（离线 P0）

日期：2026-10-27。范围：只做电脑上的离线实现与测试；**没有启用 UAC、没有调用
`_setupAudioInterfaces5x`、没有 USB/SD/实机操作**。

## 做了什么

新增 [uac_standard.h](../../../source/uvc/uac_standard.h) 与
[uac_standard.c](../../../source/uvc/uac_standard.c)：

- **描述符字节构建器**：`UacBuildAcConfiguration` / `UacBuildAsConfiguration`
  生成 AC（IAD + AC 接口 + Header/IT/OT）和 AS（alt0/alt1 + General/Format/EP/Class-EP
  + SS companion）的完整字节；长度固定为 47 / 50 / 56。
- **描述符 lint**：`UacLintConfiguration` 解析两组字节，检查长度、接口号、
  `baInterfaceNr1`、终端 ID/类型/连接、alt0/alt1、格式、端点属性/MPS/interval、
  SS companion；测试里对每个字段做单字节破坏并确认拒绝。
- **控制状态机**：`UacStandardHandle` 处理
  - `SET_INTERFACE(0/1)`、`GET_INTERFACE`（AS；AC 的 alt0 也接受）；
  - `SAMPLING_FREQ` 的 `SET_CUR`（仅 48000）、`GET_CUR/MIN/MAX/RES/LEN`；
  - 端点 recipient 与接口 recipient 两种寻址；其他请求 stall。
- **接线**：`uvc_device.c` 的 UAC 路径改用构建器，新增专用 `g_uacControlBuffer`
  和 `_handleUacSetup` 路由；`_setupAudioInterfaces5x` 仍保持不调用。

## 修掉的旧问题

| 旧行为 | 现在 |
| --- | --- |
| `baInterfaceNr1 = 3` 写死 | 构建器写入实际 AS 接口号，lint 交叉检查 |
| EP 地址 `IN | (asIfaceNum + 1)` 推导 | 固定 `0x84`，与接口号解耦 |
| `SET_INTERFACE` 只接受 alt0 | AS 接受 alt0/alt1，AC 接受 alt0 |
| UAC class request 落到 `_handleVcSetup` | `_handleUacSetup` 先按接口路由 |
| UAC 与 VS 共用控制缓冲 | 独立 `g_uacControlBuffer` |
| 逐包补零的发送器 | 未改；仍禁用，属于后续 PCM 工作 |

## 验证

| 检查 | 结果 |
| --- | --- |
| 设备构建 `make -j4 OUTPUT_DIR=research/usb-ds-iso/private/tmp-import-20261029/builds/sysdvr-uac-build` | 通过（`uac_standard.c`、`uvc_device.c`） |
| host `clang -std=c11 -Wall -Wextra -Werror -DUAC_STANDALONE` | 通过 |
| `tests/test_uac_standard.c` | 描述符/lint/状态机全部断言通过 |
| `make -C research/usb-ds-iso check` | 6 个文件，全绿 |
| 描述符长度 | AC 47、AS HS 50、AS SS 56 |

## 仍然未知

- **alt1 安装**：已用 runtime NOP patch 打通 bulk alt1（见
  [A23_ALT1_ENDPOINT_PATCH.md](A23_ALT1_ENDPOINT_PATCH.md)）；UAC 的 ISO alt1
  仍缺 ISO producer 与标准宿主验证。
- 配置数据 append 后不可回退，所以启用前必须做能力判断，不能“失败再退回”。
- PCM 发送器、时钟/反馈、跨块余量仍未设计；UAC 仍禁用。
- 没有标准宿主枚举、没有硬件结论。

## 接口预算（2026-10-27 补充）

[libnx `usbds.c`](https://github.com/switchbrew/libnx/blob/master/nx/source/services/usbds.c)
的 `TOTAL_INTERFACES` 是 4；[Switchbrew usb:ds](https://switchbrew.org/wiki/USB_services)
也写明“Up to 4 interfaces can be used and enabled”。当前设备：

- UVC 占 VC + VS = 2；
- UAC 需要 AC + AS = 2；
- 合计正好 4。

因此 **UAC 不能与 `ISO_PROBE` 的 vendor 接口共存**：第 5 个
`usbDsRegisterInterface` 会失败。`_setupAudioInterfaces5x` 已在 `ISO_PROBE` 下
直接拒绝，避免注册到一半。alt1 探针也不能另加接口——要么直接用 AC+AS，
要么在无 UVC 的专用 build 里做。

## alt1 探针问题卡（未授权）

| 字段 | 内容 |
| --- | --- |
| 问题 | AS alt1 上注册的 `0x84` 端点，能否在 `SET_INTERFACE(1)` 后完成一次 post？ |
| 变化 | 无 `ISO_PROBE`；UVC 2 + AC/AS 2 = 4 个接口；AS alt0 无端点、alt1 有 `0x84`；只发一个诊断 buffer |
| 判别 | `usbDsInterface_RegisterEndpoint` 返回值；`SET_INTERFACE(1)` 是否 ACK；post 的 completion/urb_status；host 是否收到预期字节 |
| 上限 | 一次 boot、一个 buffer、不重试 |
| 停止 | 注册失败、enable/stall、post 超时、未知所有权、证据容量不足 |

## 备选路线

| 方案 | 前提 | 风险 |
| --- | --- | --- |
| A. 当前 P0：显式 `RegisterEndpoint` + 客户端处理 `SET_INTERFACE` | alt1 端点也能被安装 | 未验证 |
| B. 端点同时放进 alt0 | 宿主接受 alt0 带端点 | 非标准；宿主可能选错 alt |
| C. patch `usb:ds` descriptor walk | 接受每个 Build-ID 的补丁 | 风险高、维护重 |
| D. 放弃标准 UAC，走 vendor/bulk 伴生通道 | 允许专用客户端 | 不再是免客户端产品 |

## 下一步

1. **ISO alt1**：把 ALT1 NOP patch 与 A23 的 ISO producer 合并，先验证 vendor
   ISO `0x84`/alt1，再验证 UAC AS 的 ISO alt1。
2. **标准宿主**：用 AC/AS + NOP + ISO producer 接 Linux `snd-usb-audio`，看枚举、
   alt1 选择和 PCM。
3. **收窄 patch**：全局 NOP 只用于实验；产品化应收窄到目标接口或 `SET_INTERFACE`。
4. `_setupAudioInterfaces5x` 继续保持不调用，直到 ISO/UAC 都通过。
