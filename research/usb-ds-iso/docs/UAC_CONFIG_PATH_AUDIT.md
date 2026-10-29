# UAC 配置描述符路径审计（2026-10-29/30，离线）

> 目标：解释 U0/U0b/U0c 的复合配置 `GET_DESCRIPTOR(config)` 失败
> （`0xE00002CD`）和 UAC-only 的“主机无设备”。本轮做静态审计、descriptor-only
> payload 生成、指令级仿真与 build 接入，**没有 USB/SD/实机操作**。

## 结论

1. **复合 UVC+UAC 的 HS 配置正好 257 字节**（SS 269 字节）。usb:ds 在组装
   配置描述符时把运行长度存在 **u8** 字段：`wTotalLength` 最终写成
   `len & 0xff`；读取路径也按同一个 u8 字段截断。257 → `wTotalLength = 1`，
   主机读 9 字节配置头后按 1 字节继续，`0xE00002CD` 与这个结果一致。
2. **修复已经存在**：A23 的 runtime payload 里有 18 条把
   `strb/ldrb/uxtb/and #0xff` 改成 `strh/ldrh/uxtw/mov` 的编辑
   （`0x2bf1c…0x2bdb8`），并有 281 字节组装 + `GET_DESCRIPTOR` 的仿真验证。
   UAC build 没有带 `ISO_RUNTIME_PATCH`，所以 257 字节必然失败。
3. **UAC-only 的 97 字节不触发 u8 截断**；它的问题在别处：`UAC_ONLY` 跳过了
   `_setupDescriptors5x`，而这是唯一设置设备描述符、字符串和 BOS 的地方；
   libnx 的 `usbDsInitialize` 不会补默认描述符。该轮的“主机无设备”是构建
   缺陷，**不能**作为 usb:ds 配置路径的证据。

## 输入

- `private/module/usb.elf`（`0100000000000006`，BuildID `AD8D36F2…`），
  SHA256 `10b280d446daf116f139dbc8301968e899587a6b7dab229d5e4af6214078da29`。
- Ghidra 12.1.4 工程
  `private/analysis/A23-iova-free-list-audit-20261029-r1/ghidra-project`
  （`UsbDs`）；程序自报 `executableSHA256` 与上面的文件一致。
- `source/uvc/uvc_device.c`、`source/uvc/uac_standard.h`；
  `build/uvc_device.o` 的符号尺寸（`nm -S`）。
- runtime payload 样本：
  `private/analysis/A23-urb-trace-v4-20261029-r4/build-source/source/uvc/iso_runtime_payload.h`。

复现命令：

```sh
cd research/usb-ds-iso/private/analysis/A23-iova-free-list-audit-20261029-r1
JAVA_TOOL_OPTIONS="-Duser.home=$PWD/home" \
  /opt/homebrew/Cellar/ghidra/12.1.4/libexec/support/analyzeHeadless \
  "$PWD/ghidra-project" UsbDs -process usb.elf -noanalysis \
  -scriptPath ../UAC-config-path-audit-20261029 \
  -postScript AuditUacConfig.java ../UAC-config-path-audit-20261029/usbds-config-decomp.txt
```

## 1. 配置描述符的组装

`FUN_0002bee0` 按 speed 组装配置描述符（反编译摘录，完整文本在
[证据目录](../private/analysis/UAC-config-path-audit-20261029/usbds-config-decomp.txt)）：

```c
puVar1 = (undefined8 *)(param_1 + 0x1054);    // config descriptor buffer
uVar7 = 9;
*(undefined1 *)(param_1 + 0x1454) = 9;        // running length = 9, stored as u8
*puVar1 = *(undefined8 *)(param_1 + 0x5e);    // 9-byte header template
...
iVar3 = *(int *)(size_table + ...);           // per-interface block size
memcpy(param_1 + 0x105d, block, iVar3);       // append after the header
iVar3 = (uint)*(byte *)(param_1 + 0x1454) + iVar3;
*(char *)(param_1 + 0x1454) = (char)iVar3;    // store truncated u8
...
*(char *)(param_1 + 0x1058) = cVar8;          // bNumInterfaces
*(ushort *)(param_1 + 0x1056) = uVar7 & 0xff; // wTotalLength <- low 8 bits
```

- 配置缓冲区 `ctx+0x1054`（9 字节头从 `ctx+0x5e` 的模板复制）。
- 运行长度 `ctx+0x1454`；`wTotalLength` 在 `ctx+0x1056`；`bNumInterfaces`
  在 `ctx+0x1058`。
- 四个接口块按 `ctx+0x67..0x6a` 的标志依次追加；UVC 的 VC/VS 和 UAC 的
  AC/AS 走同一条路径（`iso_burst`/UAC 没有各自的描述符组装器）。

## 2. 配置描述符的读取

`FUN_00028210` 是 EP0 标准请求分发；`wValue >> 8 == 2`（configuration）时
调用 `FUN_0002bd80`：

```c
if (uVar3 == 2)
    uVar9 = FUN_0002bd80(param_1 + 0x10, PTR_DAT_00092120, uVar2, uVar13);

uint FUN_0002bd80(long ctx, u64 dst, char index, uint req) {
    if (index == 0) {
        if (*(byte *)(ctx + 0x1454) <= req) req = *(byte *)(ctx + 0x1454);
        memcpy(dst, ctx + 0x1054, req);
    } else req = 0xffffffff;
    return req;
}
```

- 读取端**再次**用 u8 长度；即使组装端是 u16，这里也会截断
  （补丁同时改 `0x2bdb8` 的 `ldrb` → `ldrh`）。
- 257 字节时：`wTotalLength = 1`，且 getter 最多返回 1 字节；主机请求
  9 字节配置头只能得到 1 字节 → 主机侧报 `0xE00002CD`
  （`kIOReturnNotReadable`，与 `run.json` 记录一致）。

## 3. 257 字节的构成

HS 配置（不含 UAC）的 UVC 块：

| 块 | 字节 | 依据 |
| --- | ---: | --- |
| config 头 | 9 | 组装器初始化 |
| IAD | 8 | `g_iadDescriptor`（`nm -S`） |
| VC 接口 | 9 | `g_vcInterfaceDesc` |
| VC class-specific | 40 | `g_vcDescriptors` |
| VS 接口 alt0 | 9 | `g_vsInterfaceDesc0` |
| VS class-specific | 78 | `g_vsDescriptors` |
| VS bulk EP | 7 | `g_videoEndpointDesc` |
| **UVC HS 合计** | **160** | |

UAC 块（`uac_standard.h`）：AC 47，AS HS 50，AS SS 56。

| 配置 | HS | SS |
| --- | ---: | ---: |
| UVC（SS 另加 6 字节 companion） | 160 | 166 |
| UAC（AC + AS） | 97 | 103 |
| **合计** | **257** | **269** |

校验：UAC safe build（`52069a44…`）读出 185B/3 接口 = UVC 160 + vendor
alt0/alt1 接口 25；185 < 256，所以未修补的 usb:ds 能正常服务。复合 UAC
的 257 正好越过 u8 边界，与早先记录的“u8 configuration length/offset wrap
at 257 bytes”一致。UAC-only 只有 97 字节，长度本身没有问题。

## 4. 修复的范围与覆盖缺口

`tools/build_patch.py` 的 22 条 runtime edits 中，前 4 条是 ISO producer/
event/report hook，后 18 条是描述符修复：

```text
strb w21,[x22,#0x454] @ 0x2bf1c,0x2bf94,0x2c028,0x2c0a0,0x2c11c
ldrb w8, [x22,#0x454] @ 0x2bf8c,0x2c020,0x2c098,0x2c114
ldrb w21,[x22,#0x454] @ 0x2bfb8,0x2c0b0,0x2c138,0x2c148
add  x0, x23, w21, uxtb @ 0x2bfec,0x2c064,0x2c0e0
and  w8, w21, #0xff    @ 0x2c158
ldrb w8, [x19, x8]     @ 0x2bdb8   （config getter）
```

补丁后分别变成 `strh/ldrh/uxtw/mov/ldrh`。payload 里能直接看到
`0x2bf1c: 0x391152d5 → 0x7908aad5`、`0x2bdb8: 0x38686a68 → 0x78686a68`。

覆盖缺口：

- A23 诊断/流 build 定义 `ISO_RUNTIME_PATCH`，启动时应用这 22 条编辑。
- UAC build 只定义 `-DUAC_HOST_PROBE [-DUAC_ONLY] -DFILE_LOGGING`，没有
  `ISO_RUNTIME_PATCH`，也没有 `_logIsoTarget()` 调用点，所以 usb:ds 是
  未修补的原始模块。
- 因此 U0/U0b/U0c 的 257 字节配置在组装和读取两端都会被截断；这不是
  新的 usb:ds 限制，而是“已知修复没有随 UAC build 生效”。

## 5. UAC-only 为什么不能算配置路径实验

`UvcDeviceInitialize` 里的条件：

```c
#if !(defined(UAC_HOST_PROBE) && defined(UAC_ONLY))
    _setupDescriptors5x(config);   // 设备描述符、字符串、BOS
    _setupInterfaces5x();          // UVC VC/VS
#else
    (void)_setupDescriptors5x;     // UAC_ONLY: 跳过
    (void)_setupInterfaces5x;
#endif
```

- `_setupDescriptors5x` 是 `usbDsSetUsbDeviceDescriptor`、
  `usbDsAddUsbStringDescriptor`、`usbDsSetBinaryObjectStore` 的唯一调用点
  （源码 grep）。
- libnx 侧没有默认描述符：`usbDsInitialize` 的反汇编里没有这些调用
  （`usbDsEnable` 只发 IPC 命令，成功不代表描述符有效）。
- 故 UAC-only 从未向 usb:ds 提供 18 字节设备描述符。主机在
  `GET_DESCRIPTOR(device)` 阶段拿不到有效描述符，失败发生在枚举早期，
  不是 AC/AS 配置。
- 该轮“主机完全无设备”只有用户观察，没有主机侧 dump；即使设备以无
  字符串/默认身份出现，也没有记录可区分。**该构建不应原样重试**；如果
  仍要做隔离实验，必须先调用 `_setupDescriptors5x`。

## 6. descriptor-only payload 与仿真（2026-10-29 22:55）

`tools/build_uac_descriptor_payload.py` 从 usb.elf 生成只含 18 条描述符编辑的
runtime payload：校验 BuildID、ELF SHA256 和每条 before word，并明确排除 4 条
ISO cave/hook 地址。输出：

- `private/analysis/UAC-descriptor-patch-20261029/uac_descriptor_payload.h`
  （SHA256 `cbed1b66…`）：`uacRuntimeBuildId` + 18 对 before/after +
  `uacRuntimeEdits[]`，可直接配 `isoApplyRuntimePatch`。
- `manifest.json`（SHA256 `54bcf31d…`）：地址、字节、哈希、`edit_count=18`。

`tools/emulate_uac_config_assembly.py` 用 Unicorn 2.1.4 直接执行 usb.elf 的
`FUN_0002bee0`（组装器）与 `FUN_0002bd80`（config getter）。ctx 里放 4 个接口块
（VC 57、VS 94/100、AC 47、AS 50/56），对照组应用 `uacRuntimeEdits`：

| 配置 | 未修补 wTotalLength | getter(9) | getter(257) | 修补后 wTotalLength | getter(9) | getter(257) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HS | 1 | 1 | 1 | 257 | 9 | 257 |
| SS | 13 | 9 | 13 | 269 | 9 | 257（请求钳制） |

- HS：主机请求 9 字节配置头只得到 1 字节；修补后得到 9，再按 257 读完。
- SS：未修补时 9 字节头自称 13 字节，随后只能读 13 字节，配置在第一个接口
  中间截断；修补后为 269。
- 仿真覆盖组装器与 getter，不含 EP0 传输和主机栈；互斥/清理调用被短路。
- 结果：[emulation.json](../private/analysis/UAC-descriptor-patch-20261029/emulation.json)
  （`failures=[]`）。

`tests/test_uac_descriptor_payload.py`（quick）验证 18 条编辑、排除 ISO 地址、
before 字节与 ELF 一致；`tests/test_uac_config_assembly.py`（需 unicorn）复现上表。
payload 只改 usb 模块代码，不改本应用；下一步需要把它接到 UAC build 的启动路径
（`usbDsEnable()` 之前）。

## 7. UAC build 接入（2026-10-30）

`UAC_DESCRIPTOR_PATCH` 把 payload 接到应用启动路径：

- `uvc_device.c` 在 `UAC_DESCRIPTOR_PATCH` 下包含 `uac_descriptor_payload.h`；
- `UvcDeviceInitialize` 的 5.0+ 分支最前面调用 `_applyUacDescriptorPatch()`，
  早于 `usbDsEnable()`；失败时 `goto cleanup` 并返回 `LibnxError_BadInput`，
  不会以未修补的 257B 配置启动（fail closed）；
- applier 复用 `isoApplyRuntimePatch` 与 `_logIsoTarget` 的 dmnt 流程：校验
  usb 模块 `count==1`、`size==0x369000`、`build_id==uacRuntimeBuildId`，暂停
  usb、应用 18 条编辑、失败回滚；`-4`（回滚未验证）保持 usb 暂停；
- payload 不含 ISO cave/hook，`ISO_RUNTIME_PATCH` 仍未定义。

构建矩阵（`make -B`，全部离线通过）：

| 配置 | 结果 |
| --- | --- |
| 默认（无 flag） | 通过 |
| `UAC_HOST_PROBE` | 通过 |
| `UAC_HOST_PROBE + UAC_ONLY` | 通过 |
| `UAC_HOST_PROBE + UAC_DESCRIPTOR_PATCH` | 通过；NSP 86780B，SHA256 `48c872f1…` |
| A23 `ISO_PROBE_STREAM + ISO_RUNTIME_PATCH`（回归） | 通过（用归档的 ISO payload 头编译） |

复现：`python3 research/usb-ds-iso/tools/build_uac_descriptor_probe.py`；记录
`private/analysis/UAC-descriptor-patch-20261029/build-result.json`。该 NSP
**未部署、未上卡、未实机**；按记录卡上仍是安全 `52069a44…`，本轮没有接触硬件。

## 8. 限制与未证明

- `0xE00002CD` 的 host 侧映射是按“配置头长度 1 字节”推断的，未在主机
  侧逐包验证。
- 257B + 补丁尚未实机；本审计不对硬件行为作保证。
- 仿真短路了 mutex/cleanup，只覆盖组装器与 getter，不是 EP0/主机栈的端到端测试。
- NSP 未部署；dmnt 附加/恢复与 fail-closed 只在 A23 上验证过，UAC 变体未实机。
- usb:ds 对“从未设置设备描述符”的默认对象状态没有完整追踪。
- runtime edits 只对 BuildID `AD8D36F2…` / size `0x369000` 的 usb 模块有效；
  其他固件版本需要重新定位。
- 记录：`A23-iova-free-list-audit-20261029-r1/README.md` 里的 usb.elf
  SHA256 写成 `…309688e8…`，实际文件与 Ghidra 程序都是 `…3019688e…`；
  本审计以实际文件为准，旧 README 的摘要待单独校正。

## 9. 下一步（离线优先）

1. **已完成**：descriptor-only 的 18 条 payload（`uac_descriptor_payload.h`）。
2. **已完成**：HS 257B / SS 269B 的组装与 getter 仿真（1/13 → 257/269）。
3. **已完成**：UAC build 接入（`UAC_DESCRIPTOR_PATCH`），四种配置均构建通过；
   产物 NSP `48c872f1…`（未部署）。若保留 UAC-only 隔离实验，仍需把
   `_setupDescriptors5x(config)` 移到它也会执行的路径。
4. 实机（需要新的明确授权）：复合 UAC + descriptor-only 补丁，
   一次 boot，`usb-config-dump` 期望 4 接口/257B，`SPAudioDataType` 或
   `arecord -l` 出现音频设备；本轮不做 PCM。

## 证据

- [usbds-config-decomp.txt](../private/analysis/UAC-config-path-audit-20261029/usbds-config-decomp.txt)
  —— 4 个函数的反编译与关键指令窗口。
- [AuditUacConfig.java](../private/analysis/UAC-config-path-audit-20261029/AuditUacConfig.java)
  —— 只读反编译脚本。
- [result.json](../private/analysis/UAC-config-path-audit-20261029/result.json)
  —— 输入哈希、结论摘要与审计边界。
- [uac_descriptor_payload.h](../private/analysis/UAC-descriptor-patch-20261029/uac_descriptor_payload.h)
  与 [manifest.json](../private/analysis/UAC-descriptor-patch-20261029/manifest.json)
  —— 18 条 descriptor-only 编辑。
- [emulation.json](../private/analysis/UAC-descriptor-patch-20261029/emulation.json)
  —— Unicorn 组装器/getter 结果。
- [build-result.json](../private/analysis/UAC-descriptor-patch-20261029/build-result.json)
  —— `UAC_DESCRIPTOR_PATCH` NSP 的构建参数与哈希。
