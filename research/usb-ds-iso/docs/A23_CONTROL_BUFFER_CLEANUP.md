# A23 控制 buffer 复用与退出路径审查（2026-10-13）

本轮用实际 A23 源码确认两个候选边界：**账本最后排空不证明此前没有复用未知 buffer；
正常退出保护不覆盖当前保留的 __appExit 回调。** 19 个控制场景各编译原版与候选，共
38 次 native 回放，已记录的 USB 调用计数与 CPU 复用观察一致；11 个退出场景及 285 项相关 Python
回归通过 ASan/UBSan，无跳过。

本轮只审查，没有修改生产源码、候选 runtime、协议/timeout、部署或三份凭据。USB/SD0，
remaining0，根因仍未知；没有新增 ARM 构建、NSO/NSP 或执行入口。上一阶段的
[文件 sink 与停止窗口](A23_EP0_CANDIDATE_SINK.md)及其封存材料保持原样。

## 控制 buffer 的实际使用

[uvc_device.c](../../../source/uvc/uvc_device.c#L1322)的 _ctrlBufferFor 只区分 VC 与其他接口：
接口0使用 g_vcControlBuffer，接口1(VS)/2(ISO)共用 g_controlBuffer，都是4096bytes。
_ctrlWrite 在调用 _ctrlInXfer **之前** memcpy；后者的 post/wait/report/parse 错误直接返回。
_ctrlWrite 随后 stall，不保留“该范围仍可能被旧请求使用”的复用门槛。_ctrlRead 的非零
OUT 也可在 wait/report 错误后返回；下一次 IN/OUT 仍使用同一地址。单一 CPU owner 只排除
另一 CPU 调用者的并发，不能证明异步服务已经不再使用该范围。

[工具](../tools/audit_a23_control_buffers.py)提取实际控制/ISO/dispatch/_pollIsoProbe 源码，
分别编译原版与既有插桩候选。只在生成的 native 副本中给实际 memcpy 前后加观察 hook，
并在 modeled Post/GetReportData 中保存地址、长度、ID、通道和接受时字节；已有匹配
status3/4/5 才解除 span，wait/stall/cancel/断开不解除。

这是**显式的所有权假设**：CPU 在旧 post 使用过的同一范围写入可在源码重现，但 HOS
是否一直借用原内存、是否复制、DMA何时读取/写入都没有运行或测量。不能把 modeled
active span 直接称为实机仍在 DMA，也不能宣称已经观察到真实传输数据损坏。

| 原请求与后续调用 | 模型中的 CPU 复用结果 | 候选账本结束时 |
| --- | --- | --- |
| STATUS IN168 timeout/report错误/错ID/status1、2、未知，再次STATUS | memcpy覆盖168bytes旧范围，注入的不同STATUS使部分字节变化 | pending1，拒绝导出 |
| 非零OUT32 timeout/report错误，再次STATUS | memcpy覆盖旧OUT前32bytes | pending1，拒绝导出 |
| ISO2的非零IN未知后，VS1 GET_INTERFACE | 共用地址覆盖1byte；VC0对照不重叠 | 旧ID仍pending |
| BURST零长IN ACK或STATUS零长OUT timeout，再次STATUS | 同地址再post两次，**零长旧请求覆盖的数据字节为0** | pending1，拒绝导出 |
| 匹配终结status4/5或正常3先被原有report观察，再次STATUS | 模型无未知范围重叠；parse失败不等于仍持有 | pending0 |
| memcpy/post之后的既有IN report才带回旧/新不同终结ID | 旧范围已经被写过，迟到report不能撤销历史 | pending0，仍允许导出 |

最后一行的 late-report-after-copy 是新发现的证明缺口：独立账本准确反映当前终结状态，
但没有保存/阻止先前的 buffer 复用。原版与候选都发生相同的 memcpy/post 顺序；因此
Finish/CRC/解码成功只能支持记录与最终账本一致，不能给整个传输路径背书。

19个场景中17个经实际 ProcessRequests/dispatcher，两个非零OUT场景直接调用实际
_ctrlRead helper（ISO burst协议本身没有该非零OUT）。服务、终结状态、迟到报告及STATUS
内容改变都是注入；没有重标旧capture或改变wire。计数对照范围为ISO post、控制IN/OUT
post、控制report和stall，未声称全部IPC时序/调度相同。本轮仅输出分析JSON，不把这些回放
导出为新候选capture。BURST ACK在原源码的seq/post之后，ACK错误或零长地址复用本身
仍不能解释首次前后seq0。

ISO CANCEL场景只调用原有ISO cancel/ACK路径，不解除旧控制IN；断开再连接也不清旧
控制占用。两种情况下后续控制请求仍可进入；目前trace账本只阻止导出，不阻止这些复用。

## 正常与回调退出

[main.c](../../../source/sysmodule/main.c#L209)的 __appExit 设置 g_running=false，随后直接
UvcDeviceExit/CoreExit/smExit。最新隔离 sink 候选保留了完全相同的回调，提取时逐字比较。
[UvcDeviceExit](../../../source/uvc/uvc_device.c#L1101)先close ISO接口，再检查initialized；
关闭VS/VC并usbDsExit。静态buffer没有在这里free，**观察到的是资源关闭调用，不是已证明
的内存释放或HOS终结**。UAC接口在A23禁用/null；模型共有3次接口close。

[退出fixture](../tests/a23_exit_paths_fixture.c)编译原始JoinThread、UvcDeviceExit、__appExit，
以及生产和封存候选main的正常退出片段。join/线程存活/URB/sink Result均注入；在保留
路径的第一次sleep用native longjmp截获，真实候选仍会保留并sleep，不会正常返回。

- 原JoinThread忽略wait Result：注入视频join失败，仍threadClose，再关3个USB接口。
  两次join成功也不等于服务请求终结：注入pending1仍会进入USB/Core清理。
- 候选正常路径检查视频/音频join、Finish和save。pending、任一join失败或sink失败时，
  threadClose/USB/Core/sm清理都未调用；只有sink失败场景尝试save。
- 候选正常排空、save成功后执行清理，随后回调再次UvcDeviceExit不会重复关闭NULL接口，
  共3次接口close、一次usbDsExit和一次CoreExit；仅在这个注入条件下符合预期。
- **直接调用原样回调**且注入线程仍运行，join0而close3/CoreExit1；注入线程停止但pending1
  也直接清理。这证明回调没有同样的门槛，不证明它在本次实机异常中已发生。

callback-live等是诊断性的直接调用。正常runtime约定在main返回后调用回调；fatalThrow、
SVC异常、进程终止是否进入它，以及实际线程/服务的退出语义，本轮未查证。不能将该缺口
写成已发生的异常清理竞态，也不能把正常路径sleep当作已保护所有退出方式。

## 封存与下一步

[10项Python检查](../tests/test_a23_control_buffers.py)核验原/候选观察一致、非零范围/零长
地址区别、VS/VC隔离、终结4/5、迟到终结后的历史、回调门槛缺口及正常资源保留。
[span模型](../tests/a23_control_buffer_model.c)与[场景](../tests/a23_control_buffer_session.c)
都是native限定；没有被放入ARM候选或生产。

- `private/analysis/A23-control-buffer-cleanup-review-20261013`：3份生成源码/native二进制、
  38次控制回放、11个退出结果、编译命令、输入hash、audit、SHA256SUMS。
- `private/analysis/A23-control-buffer-cleanup-validation-20261013`：285项回归、源码快照、
  旧封存材料/生产hash/三份票据/文档链接检查及独立validation。

下一步只在电脑设计并回放**按实际buffer范围禁止未知占用复用**的隔离候选，门槛必须在
memcpy/非零post之前，覆盖共享VS/ISO、IN/OUT及零长请求身份。还需区分owner未启动、
已停止、join失败、未排空和已保存等清理阶段，统一正常与回调退出的可审查策略。
不能靠新增查询、清账本、强制cancel/close或扩大timeout使检查通过；额外USB命令/实机
采集仍无次数。严格终结、ID/槽容量、停止成本、DMA/来源与断电持久性仍未验证。
