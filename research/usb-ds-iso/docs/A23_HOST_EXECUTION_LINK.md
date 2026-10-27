# A23主机通知适配与EXE3收集对接（2026-10-15）

后续实施见[隔离等待入口与SDK启动分离](A23_WAITING_ENTRY.md)：32组完整入口注入及
58项相关回归通过；新组件已对接，真实采集启动器和完整构建校验门禁仍待接入。
本页保留上一阶段记录。

本轮实现了[执行V3候选](A23_EXECUTION_V3_CANDIDATE.md)之后的两个电脑组件：**可编译链接的
真实IOKit通知绑定及同步适配器；直接保存、解码和比较EXE3的离线收集器。** 旧接收器和
采集入口未接入新组件，不能据此按“已经支持提前等待”使用旧入口。没有调用真实IOKit
操作、SDK、接收器或USB/SD，原SDK超时根因仍未知。

新增[审查工具](../tools/audit_a23_host_execution_link.py)，113组native适配器回放、230个
独立消息格式边界及六组收集样例完成；15项新检查与原29项回归共44项通过、0跳过。

## 通知适配器及对象寿命

- [adapter接口](../host/a23_passive_wait_adapter.h)：调用者在同一串行队列内使用，结构体
  及ops/context保持到回调之外的close完成；take返回借用的service，使用者需自行retain。
- [实际adapter实现](../host/a23_passive_wait_adapter.c)：复用既有C等待策略，处理注册、
  初始排空、唯一新到达、身份复核、终止观察、一次交接、停止和资源释放。
- [真实IOKit绑定](../host/a23_passive_wait_iokit.c)：构造固定VID/PID、接口2/vendor class/
  HS匹配，读IORegistry身份/父设备/速度，注册first-match和general-interest通知。

同步收取通知消息后调用IODispatchCalloutFromMessage；不创建dispatch或runloop通知源。
因此回调只在显式pump内分派，回调里请求停止只改变状态，notifier/iterator/port/service
的清理延迟到pump返回。close后的队列消息不再分派，不留下指向已释放adapter的异步任务。
这仍依赖调用者遵守同队列及寿命契约，不是可并发调用的线程安全对象。

该设计依据Apple的[取回通知端口说明](https://developer.apple.com/documentation/iokit/1514875-ionotificationportgetmachport)
及[显式分派接口](https://developer.apple.com/documentation/iokit/1514775-iodispatchcalloutfrommessage)。
另对照[公开IOKit实现](https://github.com/apple-oss-distributions/IOKitUser/blob/main/IOKitLib.c)：
正常分派已处理消息携带的notifier/service权利，本组件不再重复destroy该消息。公开实现
是设计参考，不能代替当前系统二进制及真实消息ABI运行验证。

| 处理阶段 | 行为及失败边界 |
| --- | --- |
| 开始/注册 | 日志回执成功后才创建通知端口；先注册，再排空初始iterator |
| 初始排空 | 有旧匹配实例就停止；不把已存在的接口冒充新启动 |
| 新到达 | 只接受唯一候选，检查iterator有效性、非零/不同的interface/device ID及HS |
| 终止观察 | 保留IOIteratorNext交给调用者的一份service引用，先注册interest，再复核身份 |
| 交接 | 再排空当前消息、复核身份/期限；交接事件保存失败或回调请求停止，不返回service |
| 停止 | 不重新选择；notifier和iterator先释放，接收端销毁，最后释放本组件的service引用 |

新到达一次最多取65个对象（第65个用于识别超过64的上限），每个已取对象有释放路径；
每次poll最多分派16条消息，未见空队列就按积压停止，不带着未知积压交接。消息本身使用
8KiB局部缓冲，核验长度、消息类型、port descriptor及interest内容下界。230项格式检查
针对当前64位SDK的matched/interest形状，不是对任意消息或全部系统ABI的证明。

等待期限在调用返回边界检查，不能中断阻塞的IORegistry调用；交接后也不以等待期限替代
SDK的传输/退出期限。事件ticks是最近一次核验的本机时钟，不是清理完成或总线到达时刻。

事件记录涵盖BEGIN/REGISTERED/WAITING/SELECTED/HANDOFF/STOP，原生注册错误保持数值。
emit的“已持久化并读回”由调用者提供的sink回执表示；本轮使用注入回执，没有新增真实
等待日志写入器。HANDOFF表示一次策略交接已消耗，不能当作SDK请求已经发出；必须同时
看take返回值及后续SDK记录。STOP日志失败可被报告，但不能撤销之前已完成的交接。

释放失败的token保存在unreleased列表且不重试。复核补齐了额外到达叠加释放失败时的
五份引用记录：两个正在排空的service，以及既有selected、iterator、interest均保留；
对应组合回放为未交接、五次释放失败、五份引用仍可追踪。closed表示通知接收端已关闭，不能推定
所有引用均已释放。使用者另行持有的service引用不随adapter关闭而释放；这也不涉及释放
任何SDK传输缓冲区。

## 模型验证范围

实际adapter、真实绑定及fixture一起严格编译链接，真实绑定函数未执行；fixture只调用
注入ops表。ASan/UBSan下113组native进程执行包括：

- 0..66个新候选、已有实例/初始积压、注册/创建失败、早到回调及错误iterator；
- 排空前后iterator失效、身份/速度错误、watch或take前身份变化、interest失败；
- 排空/注册后/交接前过期、反向时钟、消息错误/积压、拔出和requesting-close；
- 等待/选择/交接回调内停止、回调重入、交接后拔出、二次交接；
- 每一日志阶段的失败及service/iterator/interest释放失败。

引用计数fixture验证本组件最多交接一次、正常路径无未释放引用、失败token不丢失；
destroy不得在pump/回调内发生。回调之外关闭后再注入迟到回调不改变状态，也不能重启。
这些是同步ops契约下的模型结果，未验证真实IORegistry时序、硬件稳定性或多线程调用。

## EXE3离线收集与比较

新增[collect_a23_execution_v3.py](../tools/collect_a23_execution_v3.py)，与旧V2收集器分离。
输入是电脑上已静止的host目录、EXE3文件、明确的预期recipe及可选的原始OWN2/DIA2文件；
不挂载/读取SD、不查票据、不启动接收器。它不会为了“能解析”而修复或丢弃失败字节。

收集器独占创建新目录，逐文件fsync/读回，保存原始库存、分析和manifest/COMMITTED；
限定目录层数、文件数及大小，拒绝符号链接、特殊文件、非规范路径和输出覆盖/嵌套原host。
完成前再次读取源库存，源变化时留下未提交的新目录及已复制材料，不声称收集成功。
回执表示这些文件系统调用和读回已确认，不认证断电后的持久性。

比较由原严格SDK host审查、独立EXE3/INI1/OWN2/DIA2解析器与原三步SETUP比较函数组成：

1. EXE3格式/CRC/recipe/本地窗口/内嵌身份及原文件保存receipt保持原判定。
2. 可选原文件逐字节对照内嵌材料。receipt声称commit成功而给定原文件不同，标为矛盾；
   receipt失败且给定文件是部分写入则保留两份，不将其“修正”为完整文件。
3. 主机STATUS仍绑定原journal字节，检查接口2三步SETUP顺序及两次state/seq。
4. 主机材料不完整、EXE3损坏或recipe错误成为分析错误；收集本身仍可完整保存这些材料。

收集完整性、封装有效性和材料关系分别报告。原文件commit失败、EXE3自身保存未知、
host失败均不会被解析成功洗成通过。全部物理来源、同一实机run、跨时钟、USB通过、资源
清理及下一轮权限字段保持false；没有把Mac和Switch的原始tick相减。

六组样例刻意将**原SDK失败host**与**封存模拟EXE3（recipe03开头）**组合，用于否定对照，
不是新的采集或同run证据：正常、原文件commit失败、原文件部分写入、EXE3部分写入、
错误recipe、主机journal不完整。六组均完整保存库存，全部不接受为一致的诊断会话。
另检查篡改文件/COMMITTED、重算manifest后的权限或分析篡改、错误原文件、符号链接、
已有输出、源在收集中变化；该拒绝的仍拒绝，失败材料保持。

## 封存、操作方式及下一项

本轮44项相关检查通过（新增15、原29），0跳过；不是全库测试。最终封存257条、原V3候选
504条、其验证9条及历史run17条核验；60个源输入、七个生产输入和三份票据哈希保持。
绑定本轮实际clang、显式SDK及六份SDK头；未重建或执行ARM，V3设备候选及旧格式未改。

- [审查及全部回放](../private/analysis/A23-host-execution-link-final-review-20261015/audit.json)
- [正常通知/借用交接模型](../private/analysis/A23-host-execution-link-final-review-20261015/notifications/ok-batch1.json)
- [五份引用同时释放失败](../private/analysis/A23-host-execution-link-final-review-20261015/notifications/release-all-extra-arrival-batch1.json)
- [原文件部分写入的收集样例](../private/analysis/A23-host-execution-link-final-review-20261015/collections/primary-partial/analysis.json)
- [EXE3损坏但材料完整保存的样例](../private/analysis/A23-host-execution-link-final-review-20261015/collections/execution-partial/analysis.json)
- [独立验证](../private/analysis/A23-host-execution-link-final-validation-20261015/validation.json)
- [44项回归记录](../private/analysis/A23-host-execution-link-final-validation-20261015/regression.txt)

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 \
  research/usb-ds-iso/tools/audit_a23_host_execution_link.py --output /private/tmp/a23-host-link-new
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/usb-ds-iso/tests /opt/homebrew/bin/python3.12 \
  -m unittest test_a23_host_execution_link test_a23_execution_v3_candidate test_a23_execution_readiness -v
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 \
  research/usb-ds-iso/tools/collect_a23_execution_v3.py analyze \
  research/usb-ds-iso/private/analysis/A23-host-execution-link-final-review-20261015/collections/execution-partial
```

审查输出必须为新目录；freeze子命令只接受给定静止文件，绝不是设备采集命令。
下一项形成隔离主机入口，拆开SDK准备与start：先让provider持有独立service引用并建立
终止观察，再关闭等待器、确认无未解决释放，最后开始原控制请求，避免通知pump插入
16ms控制阶段。其等待/交接日志、原SDK journal、失败/退出及一次性门禁须一起回放。
单次许可必须在首次SDK open或descriptor访问可能触发USB之前核验并消耗，不能只守住
BURST；被动等待不自行签发许可，准备失败也不自动重选或重试。
新的构建/门禁源库存还须显式覆盖a23_*.c/h，不能直接移用旧io_usb_host*扫描和旧receipt。
完成这层对接后再核对可达线程/TLS/栈及运行成本；不扩大通用formatter主线。

当前旧入口仍单次发现，真实等待journal写入与capture门禁尚未接入，三票据remaining0。
本轮没有IOKit操作、SDK/接收器调用、USB/SD访问、设备包或部署，也没有新增实机结论。
