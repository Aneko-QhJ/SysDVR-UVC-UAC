# 当前 macOS USB 主机驱动离线审计（2026-10-12）

已定位本机内核集合并追到兼容层错误转换。最重要的结果是：日志中的 `frStatus` 虽然来自
IOKit，却未必是逐帧原始控制器结果；某些分支用整次请求结果填写它。
这解释了正确 raw 与有效槽 `NotResponding` 可以同时出现，但没有确定旧失败的根因，
也没有把失败改判为通过。本轮 USB0、SD0，未执行接收器、写卡或修改采集阶段。

## 1. 材料及身份边界

当前系统为 macOS27.0.1 / 26A434、ARM64；`uname -v` 与解压镜像内的
Darwin27.0.0 / xnu-13432.1.9 / RELEASE_ARM64_T8112 字符串一致。
常规 kext 可执行目录不含独立内核驱动，但 Preboot 的 IMG4 kernelcache 可读。
从 IM4P 的 LZFSE payload 解压得到125026304bytes的 ARM64 `MH_FILESET`，包含完整驱动符号。

| 输入 | 身份 |
| --- | --- |
| IMG4 kernelcache | SHA256 dfe76b2a4f4f44e05f8e54d3ccec55b5a37ce49a72dcf76e4638efce25061caa |
| 解压 kernelcache.macho | SHA256 06846c718a67715f540c7f5a5d5a183da6185d94b6fc01f1ce57a30b601be44d |
| 根 fileset | UUID dc19e614344391f3e0636dd78da31217 |
| AppleUSBXHCI | UUID f697a29d53603e1795ac9bec1055f3d7 |
| IOUSBLib | 本机 IOUSBHostFamily 内的 bundle，分析 arm64e slice；完整文件哈希见 provenance.json |

未取得运行内核 UUID 的独立确认；未查询当前 USB 拓扑，也未证明历史失败时运行的镜像与
此镜像逐字节相同。因此以下是**当前本机二进制的静态事实**，对历史日志的应用标为兼容解释。
不能据机器型号就指定当时端口使用哪个平台控制器或其覆写路径。

Mach-O member 的 segment/section/symtab 文件偏移属于整个 fileset，不能加 member header
偏移。工具按原地址导出代码，保留每个目标函数的文件偏移、字节哈希和符号；反汇编是核对依据。
Ghidra 仅导入导出的代码段，未加载完整数据段或全部外部调用签名；伪代码中的类型、间接调用
参数和日志分支可能不准确，关键判断均另用机器指令核验。

## 2. IOKit 兼容路径确实会重写状态

`IOUSBInterfaceClass::ReadIsochPipeAsync`（IOUSBLib arm64e，0x6e20）读取用户帧请求长度，
调用 `IOConnectCallAsyncScalarMethod` selector20，传入 buffer、startFrame、numFrames 和帧列表。
它使用8byte `IOUSBIsocFrame`；low-latency 路径使用16byte结构，两者在内核完成函数中分开处理。

内核 `AppleUSBHostInterfaceUserClient::isochronousRequestCompletion` 位于
`0xfffffe000b361720`。参数 x2 为整次请求结果，入口保存到 x22；内部帧数组按24bytes递增，
状态位于+0、requested位于+4、actual位于+8。

| 当前镜像中的判断 | 写给旧 IOKit API 的状态 | 指令位置 |
| --- | --- | --- |
| 普通帧：内部状态0、特定模式判定为真，且actual < requested | E00002E7，Underrun | 0xb361bf0..0xb361c18 |
| 普通帧：内部状态为E00002BE（NoResources）或E00002ED（NotResponding） | E000400E，NotSent1 | 0xb361c1c..0xb361c2c |
| 普通帧：其他分支，包括上述模式下状态0且actual >= requested | `translateIOReturnToLegacy(整次请求结果)` | 0xb361c30..0xb361c38 |
| low-latency帧：内部状态为NoResources或NotResponding | E000400E | 0xb3617c8..0xb3617dc |
| low-latency帧：其余内部状态 | `translateIOReturnToLegacy(整次请求结果)` | 0xb3617e0..0xb3617e8 |
| 整次回调结果为NoResources或NotResponding | E000400E | 0xb361964..0xb3619a8 |

表内短地址均在 `0xfffffe0000000000` 地址空间；完整地址见导出的 `.asm`。
后续[请求与分派审计](HOST_DRIVER_FLOW_AUDIT.md)已确认该模式值是内存描述符方向是否恰为In，
并追到首个非零CC汇总规则及直接IOUSBHost transaction API候选。

普通路径在0xb361c58写frStatus，并在0xb361c5c..0xb361c60把**内部actual**写入frActCount，
不会因为传播整体错误而清零这个长度。
low-latency 路径另保留时间戳；对象类型与方向判定的后续核对见上述补充报告。

`translateIOReturnToLegacy`（0xfffffe000b3ec7c4）只转换3个特定值：
E0005000→E000404F、E0005001→E000405D、E00002D6→E0004051；其余值原样返回，
包括E00002ED。同步提交包装函数 `io` 也把NoResources/NotResponding转换成NotSent，
但保存日志来自异步完成，不能混淆提交失败与回调失败。

这是一项明确的信息损失：兼容层把两种错误合并，部分逐帧状态又继承整体错误。
此前“libusb未造出错误”的结论保持；“IOKit原生逐槽状态等于控制器逐槽原始状态”则不成立。
没有修改 macOS 驱动，也未认定其实现为已证实的驱动缺陷。

## 3. xHCI 完成码再向下追了一层

`AppleUSBXHCIRequest::translateCompletionCode` 位于0xfffffe000b578ba8：

| 输入主机CC | 返回值 |
| --- | --- |
| 1、13 | 0 |
| 2 | E00002CA |
| 3 | E00002E8 |
| 4、36 | E00002ED，NotResponding |
| 6 | E0005000 |
| 23 | E00002BE，NoResources |
| 26、27 | E00002EB，Aborted |
| 其他（此通用函数） | E00002C9，InternalError，并进入诊断分支 |

主机CC4、23、36的标准名称分别为USB Transaction Error、Missed Service Error、Split Transaction Error；
名称对照使用 [Linux xhci.h](https://raw.githubusercontent.com/torvalds/linux/master/drivers/usb/host/xhci.h)。
**Apple的返回值表来自本机机器码**，没有用Linux实现替代Apple实现，也没有把Switch设备CC23
当成这里的主机CC23。旧SDK USB.h 的NotSent备注讲的是OHCI，不能套用其编号到xHCI。

ISO `update` 在0xb59b7c4提取event CC，在0xb59c960..0xb59c9f4通过虚表槽+0x308
调用转换并写入交易记录。`AppleUSBXHCIRequest` 与 `AppleUSBXHCIIsochronousRequest`
两张虚表该槽均为kernel-cache chained pointer `8011bf4f04574ba8`：cacheLevel0、target04574ba8，
按根映射基址0xfffffe0007004000解析到上述函数。SDK fixup-chains.h 的30bit target布局及
虚表原始字节另存vtable-check.json，避免把PAC/链编码当作普通地址。
根LC_DYLD_CHAINED_FIXUPS位于文件0x7738000；含虚表的根segment声明pointer_format8，
与SDK的DYLD_CHAINED_PTR_64_KERNEL_CACHE一致，未仅凭指针外观猜测编码格式。

ISO `finish(int)` 还会把传入非零结果填入尚未处理的交易并清零其actual。
因此仍须区分“事件CC转换”“剩余交易收尾”和“整体请求汇总”。本轮已导出并查看这些路径，
尚未完成平台覆写、所有调度分支及汇总规则的完整审计；不能反向断言一次NotSent必然来自某个CC。

## 4. 对三次冻结失败的影响

三份失败run重新核验原manifest，逐槽形状如下；完整记录见native-remap-review.json：

| run时刻 | 空NotSent前缀 | 16个actual192有效槽 | 其他空槽 |
| --- | ---: | --- | --- |
| 10-08 00:39:52 | 271 | indices522..537，E00002ED | E00002E7 |
| 10-09 16:44:28 | 314 | indices566..581，E00002ED | E00002E7 |
| 10-11 22:12:15 | 293 | indices543..558，E00002ED | E00002E7 |

三次overall均E000400E，raw的16包和设备终结正确，严格验收仍失败。
这组形状与当前普通兼容路径完全相容：例如整体内部结果为NotResponding，前缀内部状态为
NoResources或NotResponding，其余内部状态0，短包判定启用，就会输出“前缀NotSent、
空槽Underrun、完整包NotResponding、整体NotSent”。这是**一组可能的内部状态**，不是恢复出的历史记录。

现在可以确定两条解释边界：

- 有效槽NotResponding不独立证明这16个包发生过16次总线事务错误；它可能继承整体结果。
- NotSent前缀长度仍是已观察到的现象，但不能仅从这些兼容码推出实际内核入队过晚，
  也不能用前缀×125µs重建控制器错过的服务时间。

CC23/14包的设备不完整仍单独分类，与上述三次native/raw分歧没有合并。
这项审计缩小了错误解释范围，没有证明根因、修复或长期稳定性。

## 5. 后续工作的分界

电脑上仍可继续：审计整体结果如何选取、普通API mode的来源、主机交易到帧的汇总，
以及平台控制器的ISO调度覆写；对照已部署A23机器码检查协议和错误恢复。
这些任务现在已有当前版本二进制，无需为了读逻辑连接Switch。

历史日志无法恢复丢失的内部帧状态或原始host event。若要区分主机missed service、事务错误、
整次请求收尾与设备时序，应先准备能保留这些区别的新证据入口，再做有界实机验证。
用户态atTime本身不能补足event CC或总线DATA PID；若该假设依赖它们，还需要相应内核/总线证据。
当前不准备新的采集入口，不安排第三次同样串行复核，不修改FrameID/SIA或音频范围。

## 复现与保存

工具：[audit_host_driver.py](../tools/audit_host_driver.py)，检查：[test_host_driver_audit.py](../tests/test_host_driver_audit.py)。
默认只输出JSON；输入是已有解压fileset，输出必须是不存在的新目录。
导出当前两模块的代码、符号、目标函数机器码哈希和反汇编：

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 research/usb-ds-iso/tools/audit_host_driver.py \
  --output /tmp/a23-host-driver-new \
  --objdump /opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump
```

本轮产物为private/analysis/A23-host-driver-review-20261012/，28份文件及SHA256SUMS，
包含反汇编、近似伪代码、Ghidra脚本/日志、输入身份、虚表核对及冻结失败再核对。
其中DumpHost.java按导出的tsv标记创建目标函数，Ghidra12.1.4以
`BinaryLoader / AARCH64:LE:64:v8A / -noanalysis`导入代码，基址使用audit.json中的text.addr。
导出的tsv是两组审计目标的并集；本轮部分伪代码分别存在decompiled.c和completion.c，
后续一次运行也可输出到同一份新文件。程序类型和伪代码不能取代机器码核对。
