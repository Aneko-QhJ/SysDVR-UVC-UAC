# A23 初始化与启动失败审查（2026-10-14）

本轮核对实际Core/Capture/grc:d、顶层USB初始化和线程启动代码，确认三个调用顺序边界：
**Capture第二次open失败未关闭第一次会话；Core初始化成功标志尚未置位时CoreExit不进入
清理主体；音频启动失败可以发生在视频threadStart成功之后。** 假设重试CoreInit，模型还会
重复取得FS引用并覆盖旧挂载句柄。旧清理gate只约束回调，不覆盖USB初始化内部cleanup。

40项实际函数副本native回放通过ASan/UBSan，13项新增Python检查、356项相关回归无跳过。
服务结果/句柄/线程状态均注入；没有执行真实服务、线程、HOS或fatal。本轮未新增ARM构建/
执行/打包、USB/SD访问或初始化回滚；生产/旧候选/封存/三票据保持，remaining0，根因未知。

## 实际源码和模型边界

[审查工具](../tools/audit_a23_startup.py)先核验最新[诊断sink](A23_DIAGNOSTIC_SINK.md)封存与
其独立validation、三票据和生产源码。Core/Capture/grc:d/core.h与冻结完整ARM树对应，生产
UVC/main与独立生产快照对应；新生成的回放只在电脑执行。

[fixture](../tests/a23_startup_fixture.c)插入原样函数：

- [grcdServiceOpen/Close](../../../source/grcd.c)：service已active则不重复smGetService；失败
  close的是本次输出service，不会关闭前一次成功的video service。
- [CaptureInitialize/Finalize](../../../source/capture.c)：mutex初始化，依次open video、audio；
  `R_RET_ON_FAIL`直接返回；Finalize则依次close两者。
- [CoreInit/Exit和LaunchThread](../../../source/core.c)：原FileLogging mount/delete/create、
  serial helper、Core初始化分支和threadCreate/threadStart。只有CoreExit成功主体额外增加
  native计数；运行期LOG设为no-op，不执行日志追加/格式化或测量延迟。
- [UvcDeviceInitialize](../../../source/uvc/uvc_device.c)：原顶层init/setup/enable与cleanup。
  描述符、VC/VS及ISO setup helper的内部服务调用以部分取得资源的模型替代，未把这些helper
  称为实际完整源码回放。原函数源码另封存，helper取得顺序供静态核对。
- 最新候选的__appInit、实际两次LaunchThread调用段及__appExit；线程函数不执行，
  threadStart成功仅在模型中标为live。fatalThrow用longjmp表示不返回；随后明确强制调用
  __appExit观察gate，不推断实机fatal会经过回调。

安装的libnx usbds.h说明usbDsExit会自动关闭剩余接口/端点；头文件快照与hash入封存。
native用这一接口约定模拟auto-close，不执行libnx库机器码，不证明设备DMA终结或跨服务
所有权已解除。FS引用、挂载、grc:d active状态也只表示模型中的API取得/释放次数，实际进程
终止可能有系统回收；本轮不能据此宣称实机资源泄漏或故障根因。

## Core/Capture部分初始化

| 注入路径 | 实际函数返回/调用 | 模型结束观察 |
| --- | --- | --- |
| Capture video open失败 | 返回71，不调用audio open | 两service未active |
| Capture audio open失败 | 返回72，未调用video close | video active、audio inactive |
| Core video open失败（FS/mount成功） | 返回71，g_coreInitialized仍false；两次CoreExit均早退 | FS引用1、挂载1，无fsExit |
| Core audio open失败（FS/mount成功） | 返回72，同样不进入CoreExit主体 | FS引用1、挂载1、video active |
| FS初始化失败而capture成功 | FS错误不导致CoreInit失败，随后仍可置初始化标志 | CoreExit调用fsExit；该无引用exit在模型中no-op |
| FS成功、挂载失败、audio失败 | Core返回72；CoreExit早退 | FS引用1、挂载0、video active |
| 完整CoreInit、再次CoreInit、两次CoreExit | 已初始化直接成功；清理主体只执行一次 | 各service关闭1次，FS/挂载模型归零 |
| audio失败后假设再调用CoreInit并成功，再CoreExit | 前一次video已active，第二次跳过其smGetService；FS/mount再次取得 | FS init2/exit1，旧挂载1；两capture service已关闭 |

最后一行是**手工注入的假设重试**，当前__appInit在Core失败时走fatalThrow，没有自动重试。
`g_sdCard`第二次赋值覆盖旧句柄，正常清理只关闭当前挂载；FS引用模型也只减一次。这个
结果要求未来回滚/重试设计分别记录资源成功步骤，不能依赖一个最终initialized位。

原FileLogging在mount成功后调用delete/create `/logfile.txt`，返回值被忽略，早于capture
初始化；delete/create失败仍可继续CoreInit成功。两错误场景均记录调用各1次；假设重试
各2次。**诊断sink的“不覆盖诊断文件”不覆盖这个原日志初始化行为。** 本轮仅模拟调用，
没有实际写卡/删除文件。serial初始化或获取失败也是非fatal；只有serial初始化成功才Exit。

## USB初始化内部cleanup

原顶层顺序是usbDsInitialize→描述符→VC/VS接口→ISO接口→usbDsEnable→initialized=true。
init本身失败直接return；其后各失败（含不支持的HOS路径）跳到`cleanup: usbDsExit()`。
因此候选回调gate为INITIAL并不能阻止这个内部exit调用。

40项回放覆盖descriptor、VC/VS注册、配置append、video endpoint、ISO注册/append/endpoint/
enable、全局enable、版本不支持以及成功/reentry。helper内部位置与部分成功资源均为注入，
模型显示后续失败即使已注册1..3接口也调用一次usbDsExit；成功重复初始化被拒绝，无第二次
注册。此处没有owner已启动的证据，也不能用“owner尚未启动”证明所有设备借用均安全释放。

当前无需把初始化失败接到EP0DIA1：它要求writer/trace已经启动、冻结、双join及正确交接。
USB初始化失败发生于owner启动前，强行伪造这些字段会破坏已有诊断语义。

## 线程启动和fatal边界

| 注入失败 | video create/start观察 | audio create/start观察 | 强制回调结果 |
| --- | --- | --- | --- |
| video threadCreate | 创建失败；未调用start | 未调用 | gate INITIAL，sleep |
| video threadStart | create成功、start失败，已有模型句柄 | 未调用 | 同上 |
| audio threadCreate | create/start已成功，可已有live video | create失败，未调用start | 同上 |
| audio threadStart | create/start已成功，可已有live video | create成功、start失败，已有模型句柄 | 同上 |

实际LaunchThread返回void，错误走`R_THROW→fatalThrow`，没有把错误Result返回给main，也
没有失败join/close或显式取消前一个线程。native保存原fatal Result81/82；强制回调调用0次
join/threadClose/Uvc/Core清理，phase仍INITIAL。两个create/start都成功的对照保留live2。
这些计数不证明真实线程在失败时的PC、EP0 processing或pending状态，也不证明fatal回调
可达/不可达。安全审查必须考虑音频失败时视频可能已经进入设备访问。

__appInit的sm初始化失败在Core之前fatal；Core失败则sm/FS或部分capture可能已取得。
setsys或firmware查询失败不fatal，可能没有设置HOS版本；回放仅观察appInit调用，不延伸
到真实HOS版本默认值或后续USB行为。

## 验证、封存与下一步

[13项Python检查](../tests/test_a23_startup.py)核对以上结果、正向/reentry、模型边界、依赖/
生产源码/票据和离线范围。40个native场景与356项相关回归全部通过，无跳过。

- `private/analysis/A23-startup-review-20261014`：生成的实际函数副本、native binary、40项
  结果、生产/依赖源码与SDK头文件快照、audit/manifest；没有新ARM产物。
- `private/analysis/A23-startup-validation-20261014`：356项回归、源码/生产快照、历史封存/
  三票据/文档链接复核及独立validation/manifest。

```sh
python3 research/usb-ds-iso/tools/audit_a23_startup.py --output /private/tmp/A23-startup-new
```

必须使用新输出目录。旧候选仍按成功join/Finish/save发布一次清理授权；此次未新增回滚、
thread stop入口、恢复/retry、设备查询、正常/诊断格式或文件写入路径。

下一步优先设计并验证**独立启动阶段记录**：区分FS初始化/挂载、capture两session、USB init/
接口/enable、video/audio created与started、原始失败Result和最终阶段。阶段记录应有明确
原子发布/读取边界；涉及可能live线程时不读取未join的owner或payload，不把“已启动”当作
已退出。再为admission/refusal及文件保存错误定义版本化诊断扩展，保留DIA1含义与旧recipe。
启动前没有owner的失败记录需独立语义，不能声称可正常导出或授权清理。

实机fatal/回调/线程、DMA终结、FS引用与持久性、启动/trace成本均未验证。当前remaining0，
USB/SD0，根因未知；不要将这些注入的初始化失败当作首次SDK burst seq0的实际原因。
