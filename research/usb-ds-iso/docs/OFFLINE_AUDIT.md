# A23离线研究：代码差异、完成路径与证据缺口

2026-10-12，Asia/Shanghai。本轮不访问USB或SD，不准备新的实机入口，不修改部署包、历史run、collection或采集状态。
当前设备仍A23；serial-clock-1两次独立启动各16轮完整验收通过，原backend失败保持有效。
本轮未确认根因、修复或长期稳定性。

## 1. 成功与失败工具到底差在哪里

对照native-guard-serial-2与serial-clock-1的冻结源码、静态库和实际C结构布局：

- receiver-source.c、native_file_guard.h、serial_ring_guard.h、iso_probe_protocol.h和preflight.c逐字节一致。
- 两个静态库成员列表相同，只有darwin_usb.o的内容变化，其余成员逐字节一致。
- darwin_usb.c的7处差异全部是插入；原有帧号计算、ReadIsochPipeAsync参数、原生状态保存和公开错误映射未被替换。
- 新增5处mach_absolute_time调用：帧查询前后、ISO提交前后和异步callback入口。callback入口的新增调用没有ISO类型条件，因此控制传输等共用callback也会执行。
- 完成处理新增mach_timebase_info及一条Mach记录输出。这些输出发生在IOKit已完成之后，但可能影响后续串行轮次。

临时编译独立布局探针，得到本机实际ABI：

| darwin_transfer_priv | 原匹配backend | Mach观察backend |
| --- | ---: | ---: |
| sizeof | 104 | 176 |
| isoc_framelist偏移 | 48 | 120 |
| req偏移 | 64 | 136 |
| result偏移 | 96 | 168 |

私有结构增加72bytes，也改变分配大小和后续字段位置。这是libusb内部布局，两边各自编译一致，
不能仅凭偏移变化判为ABI错误；它与计时调用都是潜在观测扰动。当前成功并不证明新增代码修复了旧错误。
也不能把完成后新增打印解释成同一轮原生错误被清除：该轮IOKit结果已经收到，原映射代码保持。

## 2. 固件与主机完成逻辑的核对结果

原始NSO的BuildID为AD8D36F2029822A4C498F055ADBDAA789EB913C6000000000000000000000000，
SHA256为08e0c60a2879e59bb7ace77a17418f7fc0d18058e90a2f12516ff8b1ebe62dfb。
归档原模块与当前输入相同；归档ELF与该NSO重新转换的字节相同。
在临时目录以A23参数重建，680byte inject.bin和IPS均与冻结部署包逐字节一致，未写回包目录。

| 路径 | 本轮确认的静态事实 | 不能由此推出的结论 |
| --- | --- | --- |
| FUN_000302e0，原提交 | 传输类型低两位为1时进入拒绝分支；0x30364原指令跳到0x30394。补丁把这个条件分支接到iso_enter | 原固件存在可直接启用的完整device ISO producer |
| FUN_00031ab0，原producer | 原路径构造Normal TRB及ED，尾部0x31c74继续原检查与门铃写入；A23自己构造16个ISO TD/ED | 原Normal producer能自动安排ISO |
| iso_event，A23 | 检查EP7和当前burst范围；16个不同ordinal的ED须CC1且actual192才能累计至3072。重复事件不重复计数，错误保存terminal高位并保留所有权 | 设备成功等于主机接受了全部总线事务 |
| FUN_0002a980 → FUN_0002c690 | A23累计完成后向原URB完成函数传递3072；原函数累计transferred，写status3并发完成事件。它不读取macOS结果 | status3能覆盖主机原生错误 |
| darwin_async_io_callback | IOKit传入overall result，直接保存到tpriv->result，再通知libusb完成。frStatus/frActCount来自IOKit帧列表，诊断没有写这些状态字段 | 错误由接收器guard或离线分析器生成 |
| darwin_handle_transfer_completion | 保留overall和逐槽原生状态，映射公开结果；旧版与Mach版映射相同 | 更下层究竟由主机调度、控制器或设备协议行为导致错误 |

设备完成路径和主机完成路径是两套独立判断，所以“raw正确、设备status3、主机报错”在逻辑上并不矛盾。
本轮审计范围内未发现一个已证实、能解释这些原生失败的确定性软件缺陷；这是有界审计结论，不是完整固件正确性证明。

Linux的[Tegra XUDC驱动](https://code.googlesource.com/linux/torvalds/linux/+/9f7853d7609d59172eecfc5e7ccf503bc1b690bd/drivers/usb/gadget/udc/tegra-xudc.c)
在ISO构造中使用SIA1/FrameID0，可作设备侧参考。它不是本次HOS补丁的执行契约；本轮不把设备CC23直接套成主机xHCI错误语义。

## 3. 保存样本的分组复核

12个burst run的223个manifest条目全部核验；逐轮重查native、公开结果、raw和设备STATUS，合计60个burst。
分组按backend家族，接收器和启动方式可能不同，因此不计算跨组成功率，也不把逐轮成功当作独立启动或完整串行验收。

| backend家族 | burst数 | 严格逐轮成功 | raw/设备完成正确但native错误 | 设备完成不完整 | 有效Mach记录 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原host64 | 2 | 1 | 1 | 0 | 0 |
| microframe观察 | 3 | 2 | 1 | 0 | 0 |
| 匹配时序观察 | 22 | 20 | 1 | 1 | 0 |
| Mach观察 | 33 | 33 | 0 | 0 | 33 |

Mach组包含一次clock-audit-1单次及两次serial-clock-1各16轮。后两次完整设备日志collection各29项哈希通过，
记录关联到正确run、原始日志哈希匹配，各确认一次实际回绕；主机分析器仍只负责主机证据，不改写其历史pending字段。

三次native分歧分别有271、314、293个开头空槽NotSent，随后均收到16个连续且逐字节正确的包，设备正常终结。
另一次失败在第4轮：NotSent前缀0、主机overall0，但只收到14包，设备terminal为保留的CC23、bitmap000F。
必须保留这两类现象，不假定它们具有同一根因。

另行核验一次无TD基线的10项哈希：960个空槽均Underrun、overall0、raw全零，无NotSent。
它只说明那次空窗口正常，不能排除间歇性主机问题，也不能单独区分控制请求与设备TD的影响。

33条Mach记录全部来自成功轮，失败时刻的atTime样本为0。旧失败没有保存atTime，无法离线补造。
成功轮的软件余量不是内核入队时间或总线服务时间；软件耗时交叠也不能判为因果。

## 4. 哪些继续离线做，哪些需要实机

| 假设或目标 | 现有证据与离线工作 | 真正缺少的证据 |
| --- | --- | --- |
| 接收器错误映射造出错误 | 已查到IOKit完成边界；Mach版没有改写映射，也没有清零原生错误 | 对已确认的映射事实无需新实机；更下层来源还未确认 |
| 主机ISO窗口实际安排过晚，或与控制请求交互 | 原参数与调用未变；可继续定位本机IOKit/主机驱动的完成码产生路径 | 同backend失败轮的有效时钟记录，必要时内核安排或总线事务证据 |
| 新观察代码影响失败概率 | 已量出结构+72bytes及无ISO条件的callback计时调用；可离线准备结构扩容、计时调用分别受控的候选版本 | 相同设备/采集条件下有明确目标的实机对照；当前样本不能决定原因 |
| 设备FrameID/SIA、发布或协议时序参与错误 | 部署机器码可复现；可继续静态审计边界条件和错误恢复 | 实际125µs相位、总线服务和DATA PID；Switch连接本身不等于有总线证据 |
| CC23与14包不完整 | 已与三次native分歧分开；可审计对应event、retained及reset路径 | 相关完整设备失败日志（若历史未保存则无法恢复）或针对该现象的新诊断 |
| 持续串流、重连、视频共存、SS/reset、UAC | 实现和本地验证可以先做 | 分阶段实机验收；32轮成功不替代这些目标 |

本机已检查常规IOUSBHostFamily/AppleUSBXHCI kext可执行目录及常规KernelCollections路径，没有可直接读取的独立驱动二进制。
这不证明其他系统位置没有对应内核集合。随后10-12继续研究已从Preboot解压当前内核集合，
追到UserClient把NoResources/NotResponding合并成NotSent，部分frStatus继承整次请求结果。
详见[主机驱动审计](HOST_DRIVER_AUDIT.md)；这修正错误码解释，不恢复历史event或确认根因。
主机汇总/平台调度路径与固件其他路径仍可继续离线研究。

本轮不准备第三次相同串行复核，不调整FrameID/SIA，不把Mach记录成功视作修复，不解锁音频。
下一项实机必须先写清要区分的假设、变化变量、所需失败证据和停止条件；尚未取得这些证据时继续保留根因未知。

## 复现与产物

审计工具：[audit_a23_offline.py](../tools/audit_a23_offline.py)。使用Python>=3.10，当前主机可用python3.12。
它读取现有本地产物及只读归档，仅在临时目录编译布局探针和重建补丁，不运行接收器或任何capture入口。

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 research/usb-ds-iso/tools/audit_a23_offline.py
```

默认仅输出JSON；`--output`只能指定不存在的新目录，拒绝覆盖。固定本机SDK/devkitA64和冻结输入为复现前提。
本轮最终产物为`private/analysis/A23-offline-review-20261012-final/`：audit.json、两份backend差异及SHA256SUMS。
其中包含输入哈希、静态库成员差异、布局、逐轮分类、原函数摘录及补丁逐字节重建结果。
先前未包含补丁重建与无TD基线的初稿另存`A23-offline-review-20261012/`，不覆盖或作为最终报告使用。

检查：[test_offline_audit.py](../tests/test_offline_audit.py)，覆盖真实native分歧与CC23分类、损坏/越界输入拒绝、
既有输出保留，以及调度替换不能被报告为纯新增观察。采集阶段和所有入口次数保持原值。
