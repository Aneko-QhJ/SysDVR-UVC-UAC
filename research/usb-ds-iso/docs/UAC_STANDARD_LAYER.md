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
| 设备构建 `make -j4 OUTPUT_DIR=/tmp/sysdvr-uac-build` | 通过（`uac_standard.c`、`uvc_device.c`） |
| host `clang -std=c11 -Wall -Wextra -Werror -DUAC_STANDALONE` | 通过 |
| `tests/test_uac_standard.c` | 描述符/lint/状态机全部断言通过 |
| `make -C research/usb-ds-iso check` | 6 个文件，全绿 |
| 描述符长度 | AC 47、AS HS 50、AS SS 56 |

## 仍然未知

- **alt1 安装**：`usb:ds` 是否把新端点关联到 alt1、宿主 `SET_INTERFACE(1)` 后
  端点是否可用，仍未验证；这是下一个要回答的问题。
- 配置数据 append 后不可回退，所以启用前必须做能力判断，不能“失败再退回”。
- PCM 发送器、时钟/反馈、跨块余量仍未设计；UAC 仍禁用。
- 没有标准宿主枚举、没有硬件结论。

## 下一步

1. 离线回答 alt1：做一个最小 vendor alt0/alt1 探针，或直接读 `usb:ds` 的
   descriptor walk，确认端点安装条件。
2. 若 alt1 不可用，再评估 patch 安装路径；不要先启用 UAC。
3. `_setupAudioInterfaces5x` 继续保持不调用，直到 alt1 与 ISO 都通过。
