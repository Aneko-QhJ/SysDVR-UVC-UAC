# A23 完整会话预算与拒绝诊断（2026-10-14）

封存guard候选的实际VideoStreamThread已完成28项native回放。完整STATUS→BURST→STATUS
使用6个永久身份槽和66条trace记录；**trace会先于16槽身份容量写满**。同时发现前置STATUS
超时后，候选仍可先提交独立ISO buffer，再在ACK buffer门槛处拒绝；当前保护不等于整个
BURST提交前的统一预检。16项新Python检查及312项相关回归通过，无跳过。

新增独立诊断内存格式EP0DIA1，在冻结、停止、双join成功及身份交接后保留失败状态。
19份诊断和10份正常ownership捕获独立解码通过；诊断不能成为正常导出或清理授权。
这次只审查封存候选并实现离线序列化，**没有把诊断sink接入ARM候选**。生产/旧runtime/
三份票据与旧封存不变，USB/SD0，remaining0，根因未知。

## 完整会话和停止交接

[工具](../tools/audit_a23_guard_session.py)读取上一阶段
`private/analysis/A23-guarded-candidate-review-20261014`的guard-buffers.c、两配置main和recipe，
先逐文件核验manifest及生产/票据hash，不重新生成或修改旧候选。
[回放fixture](../tests/a23_guard_session.c)提取实际VideoStreamThread，仅将其中一次
ProcessRequests调用包进native请求投递hook；hook仍调用封存的实际dispatcher、helper、
ISO poll、trace、账本及buffer门槛。WaitReady、nonce、身份、线程与USB结果为注入。

正常回放逐步投递STATUS、BURST、STATUS；最后通过native本地请求stop结束。两个完整
STATUS各用IN数据及OUT状态两个ID，BURST用ISO及IN零长ACK两个ID，依次通道4/5/8/4/4/5。
在第三步的原有ISO poll注入终结3时，pending0；不注入终结则仍pending1，即使两次join成功
也拒绝正常导出。没有新USB查询来排空。

- ACK timeout/report错误后，后STATUS在共享buffer copy之前拒绝并请求stop；ISO的原有
  poll可解除ISO ID，但旧ACK身份仍pending。late-ack-report的迟到控制报告没有被新请求
  查询，两份冻结诊断字节相同，不把可到达的假设报告当作已观察终结。
- 处理内部IN wait注入stop：提前Ep0CandidateStop返回false，实际视频函数等处理返回后
  才退出并冻结，后STATUS未投递；ISO仍pending1。仅证明该注入条件的返回边界顺序。
- 失败ISO post、ACK post、重复report或重用control ID都会保留fault/未知身份；失败post
  返回时的所有权不可信，即使已记录pending0也不证明服务没有其他借用。
- identity错误/全零nonce使Start失败，dispatch0/stopped0/joined0，正常和诊断导出都拒绝。
  ready-stop及30秒窗口样例注入31秒WaitReady返回，则dispatch0/stopped1/joined1，可正常
  导出空trace；**空导出不证明执行过三步会话**。真实等待、阻塞与停止延迟仍未知。
- 任一join错误时不进行Finish交接，也无诊断输出；结果模型没有执行实际threadWaitForExit。
  全部28项回放控制copy重叠0/同地址repost0、invalid记录0。

### BURST 的局部预检缺口

prestatus-timeout先让168byte STATUS IN超时。下一BURST检查的是独立g_isoBuffer范围，
虽然预留两个身份槽，却没有同时预检后续ACK所用的g_controlBuffer。于是seq1/ISO post1
已发生，ACK门槛随后拒绝，最终两个已记录身份pending、fault1。没有未知范围改写或重提交，
但**不能宣称未知控制占用会在ISO提交前拒绝整个BURST**。上一阶段的范围保护结论保持，
更强的整请求预检尚未实现，也不能据此解释首次实机前后seq0。

## 两个独立容量预算

以下为本fixture的实际记录计数，事件广播与STATUS内容均为模型条件；真实主机额外
enumeration/VC/VS请求也会占预算。时间窗口不回收身份，也不阻止trace溢出。

| 输入序列 | 使用身份槽 | 保留记录 | 丢失记录 | 原候选正常导出 |
| --- | ---: | ---: | ---: | --- |
| 完整三步会话 | 6 | 66 | 0 | 放行，前提为已观察ISO终结 |
| 三步会话再2次STATUS | 10 | 112 | 0 | 放行 |
| 三步会话再3次STATUS | 12 | 128 | 7 | 放行但trace有丢失 |
| 三步会话再5次STATUS | 16 | 128 | 53 | 放行但trace有丢失 |
| 三步会话再6次STATUS | 16 | 128 | 64 | 容量拒绝，后续data/status未post |
| 连续5次STATUS | 10 | 115 | 0 | 放行 |
| 连续6次STATUS | 12 | 128 | 10 | 放行但trace有丢失 |
| 连续8次STATUS | 16 | 128 | 56 | 放行但trace有丢失 |
| 连续9次STATUS | 16 | 128 | 67 | 容量拒绝，IN/OUT仍各8次post |

原owner导出只核验fault/pending/join等条件，**不会因dropped>0拒绝**；原main在这种导出
成功且save成功后仍能授权清理。本轮没有改变这个行为。独立decoder报告丢失，不能把文件
可解码或已commit说成lossless。Stop冻结reason为stopped，旧trace_window_complete规则始终
不将它标为finished完整窗口；这里的无丢失与会话路径是分别核对的事实。

## 独立失败诊断

[序列化器](../device/ep0_diagnostic_capture.h)只拷贝冻结CPU元数据，**不读取仍可能被服务
借用的control/ISO payload**。两次join Result失败会在读取owner/guard之前直接拒绝；随后要求
stopped/joined、非processing、exporter身份匹配、冻结reason stopped和有失败或记录丢失。
caller必须在实际join成功后才传入状态；模拟的Result和身份不认证真实线程状态。

格式为128byte header、最多16×16byte身份行和原EP0TRC1 trace，最大6656bytes。
header包含simulation+diagnostic-only标记、source recipe关联、writer/exporter、fault、已记录
pending、拒绝计数/原因、unmatched计数、双join结果和stopped/joined标记；三组CRC保护header、
身份行及inner trace。身份行保留active/nonterminal，不要求所有请求终结。

[独立decoder](../tools/analyze_ep0_diagnostic.py)核对布局/CRC、身份去重、active/终结一致、
pending计数、拒绝与fault关系，以及可见post与账本的对应。它始终输出diagnostic_only=true、
ownership_export_accepted=false、cleanup_authorized=false；已有正常EP0OWN1 decoder拒绝
EP0DIA1，包括只有trace丢失而原正常导出放行的情况。完整干净快照不能重标为失败诊断。

序列化不修改owner、guard、fault、pending、normal bytes或清理授权，也不执行join/USB/FS。
[边界fixture](../tests/ep0_diagnostic_policy_test.c)用不可读地址验证失败join先拒绝、短输出及输出与owner/guard/recipe重叠都拒绝，
保持原字节，检查live/未交接/错身份/非法行/干净快照拒绝，以及输出后账本不变。
Python补CRC后的字段篡改、三段损坏和正常格式误用也被拒绝。

native fixture在上述条件成立后写电脑新目录，共19份诊断；其中5份同时有原正常导出
但trace丢失。只有诊断格式头文件另用真实Switch头文件编译为AArch64.o，未链接新的完整ELF，
未执行。recipe取封存候选配置用于关联回放上下文；新增native/诊断源码另外绑定audit hash，
**这个recipe不覆盖新增诊断代码，也不认证来源或运行时**。

当前封存main在Finish失败处仍sleep，诊断API未接main或SD文件adapter；因此尚无实机失败
诊断文件路径。没有保存buffer地址映射或完整raw report batch，也没有恢复未知URB的机制。
join失败、Start失败无法安全读取/导出，所有未授权资源保持；不能用诊断文件解除unknown。

## 封存与下一步

- `private/analysis/A23-guard-session-review-20261014-final`：28项真实视频函数回放、19份diagnostic、
  10份原正常ownership捕获及独立JSON、两份生成native源码/二进制、边界fixture结果、
  诊断AArch64.o、编译命令、输入hash、audit和SHA256SUMS。
- `private/analysis/A23-guard-session-validation-20261014`：312项相关回归、源码/生产快照、
  旧封存/三份票据/本地链接检查、独立validation和SHA256SUMS。

```sh
python3 research/usb-ds-iso/tools/audit_a23_guard_session.py --output /private/tmp/A23-session-review-new
```

无final的初步review及首次312项回归保留；交付以final和最终regression.txt为准。

输出必须为新目录。下一步电脑隔离准备整个BURST的ISO+ACK范围联合预检、trace记录预算
门槛，以及双join成功但Finish拒绝后的独立诊断sink；保存诊断必须仍保留资源，不能走正常
capture或清理授权。初始化失败阶段需另核对Core/USB/LaunchThread已取得的资源后再设计
回滚，不能凭owner未启动断言设备无借用；异常/fatal退出的可达性仍未验证。

生产协议/timeout、原候选/旧wire和凭据保持。无NSO/NSP、部署或新次数；DMA终结、真实线程/
调度、SD commit成本与持久性、ID重用和来源认证尚未验证，根因仍未知。
