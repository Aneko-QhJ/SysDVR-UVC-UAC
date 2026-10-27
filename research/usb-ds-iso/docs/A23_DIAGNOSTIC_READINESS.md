# A23诊断候选的会话容量与分支证据审查（2026-10-15）

本轮得到一个具体阻塞：**现有128条trace候选只能在最多两次普通GET_INTERFACE查询后
完整记录STATUS/BURST/STATUS。三次查询后会拒绝后置STATUS，四次查询后会拒绝BURST。**
这是新诊断候选的容量保护行为，原A23在相同注入服务条件下可以继续处理；不能用它解释
首次SDK burst实机失败。下一候选先修订有限容量及版本化导出，再核对诊断时间窗。

## 方法与绑定范围

[审查工具](../tools/audit_a23_diagnostic_readiness.py)读取GetSize保护候选的dormant与
window-30s两个完整封存树，核验manifest、ELF及recipe；从最终候选源码逐字提取实际
poll、控制helper、ISO handler、dispatcher、ProcessRequests及wrapper。owner/guard/
admission使用同一封存树的实际实现和头文件，不再从较早候选拼接handler。

编译四个电脑程序：两个配置各有原A23与候选，均使用ASan/UBSan。USB、事件、时间、
速度、report与join是注入服务；LOG也只是计数/虚拟耗时。没有运行HOS或ARM机器码，
没有执行真实SD服务、线程、初始化或VC/VS class处理。普通GET_INTERFACE、SET_INTERFACE(0)
及vendor请求使用实际dispatcher和helper，class stub在所列输入上不可达。

124组回放包含：0..8次普通GET_INTERFACE；0..8次SET_INTERFACE(0)/断开；从历史日志
选择的9次SET_INTERFACE/8次断开形状；以及正常、替换、速度错误/Full/Super、post失败、
ACK timeout、前置STATUS timeout、读取SETUP失败、ISO事件不就绪、ISO pending和两类
join失败。请求替换场景只注入三次目标SETUP，后置STATUS在BURST处理过程中到达，
不再额外注入第四次STATUS。两种配置只复用各自EP0实现；30秒计时器没有在请求fixture中执行。

## 容量结果

下表为候选的实际native回放。GET_INTERFACE交替发往接口0/1，每个请求广播给三个接口；
前置查询每次消耗23条记录、两个永久身份槽。标准三步目标会话为66条、六个槽。

| 目标会话之前的GET_INTERFACE数 | 最终记录/身份槽 | 目标行为 |
| --- | --- | --- |
| 0 | 66 / 6 | 三步完成，证据可导出 |
| 1 | 89 / 8 | 三步完成 |
| 2 | 112 / 10 | 三步完成 |
| 3 | 112 / 10 | BURST已提交；后置STATUS在clear/GetSetup之前被拒绝 |
| 4 | 115 / 10 | 前置STATUS完成；BURST在clear/GetSetup之前被拒绝，seq0/post0 |
| 5 | 115 / 10 | 前置STATUS已被拒绝 |
| 6..8 | 115 / 10 | 前置查询阶段就停止，无法进入目标会话 |

拒绝时仍有三个SetupEvent置位；dropped/invalid/bound_violations均为0。原因是每个已就绪
接口处理前必须预留17条，而不是等记录数组完全写满。身份槽仍有剩余，这些例子的直接
限制是trace容量。停止后拒绝正常ownership导出，但双join成功时可导出独立诊断。

SET_INTERFACE(0)本身消耗18条/一个槽，每次断开再增加一条；断开不重置trace和身份历史。
四次SET_INTERFACE/断开后，目标BURST能提交但后置STATUS被拒绝（119条）；五次之后
BURST已被拒绝（118条、seq0/post0）。这些结果也没有模拟设备物理枚举或HOS调度。

历史6041字节日志中，首个BURST接口0记录之前有9个connected通知、8个disconnected通知，
接口0与1各9条SET_INTERFACE(0, interface1)标签。它们不是18次总线请求的证明，也不能
还原全部请求、时间或来源。在“9次设置、间隔8次断开”的显式注入模型中，当前候选在
第7次设置时容量拒绝，114条/六个槽，尚未进入测试目标；原A23模型完成目标BURST。
因此容量问题与已有日志形状直接相关，仍不能据此声称重演了原实机过程。

## 分支证据是否够用

| 注入条件 | 从序列化证据可以区分的观察 | 仍不能推出 |
| --- | --- | --- |
| 四次广播日志各8ms，后置STATUS在约30.565ms到达 | 0/1读BURST、2读STATUS，52条、seq0/post0 | 本次实机已经发生覆盖；SD真实耗时等于注入值 |
| GetSpeed错误、Full或Super | 接口2读到BURST，有SPEED/guard记录；错误与非HS可区分 | 当时实机的速度查询结果 |
| ISO post失败 | seq1、post失败记录，候选fault并保留诊断 | 它能单独解释原实机前后seq0 |
| ACK timeout | seq1、post记录及ACK失败；后续共享buffer复用被候选拒绝 | 已完成排空或可以强制清理 |
| 前置STATUS timeout | 旧控制占用导致候选在BURST写seq前拒绝 | 原A23也存在这个新增拒绝分支 |
| 接口2读取SETUP失败 | 独立setup_read_failed记录 | 失败读取对应的8字节内容 |
| 接口2事件未就绪 | 0/1有BURST，2没有对应读取 | 该事件在整个窗口从未到达 |
| 任一join失败 | 正常及诊断字节均不导出 | 从调试用内存读取补成可信设备文件 |

这里还确认两个验收边界：

- `normal_export=true`仅表示ownership封装允许导出。例如速度查询失败和请求替换场景也能
  导出合法文件。独立分析始终保留usb_strict_pass=false、root_cause_confirmed=false。
- quiet poll只保留累计计数和最后结果，没有逐时刻历史。缺少接口2的BURST记录只能标为
  “未观察到”，不能升级为“事件从未发生”。

独立DIA1中的reason4同时覆盖trace与身份容量。native admission计数能区分本轮例子；
真实候选的REL1另有admitted/trace_refusals/bound_violations等字段，只有取得并关联REL1
时才可使用。不能把native输出的计数当作已包含在独立DIA1中。

## 时间窗与下一候选设计

静态审查确认30秒窗口在VideoStreamThread启动、等待USB ready之前开始，停机检查在
同步ProcessRequests返回之后。它既不是“主机开始诊断后30秒”，也不能中断正在等待的
控制helper。dormant的0表示没有时间到期，容量和资源拒绝仍生效。此次未测真实运行耗时。

下一项电脑实现选择**独立的第二版有限容量格式：256条trace、32个身份槽**，继续保留
全部已观察身份、不回收或清空未知请求，不增加USB查询。先用本轮同一矩阵验证容量扩展，
再完整链接候选并核对成本；不直接改旧头文件常量后沿用旧decoder或文件策略。

按当前分支成本推算，八次GET_INTERFACE加目标三步需要250条/22槽；历史选取形状需要
236条/15槽。它们是设计预算，尚未在新容量候选上执行，不构成任意枚举或长期会话上界。
预算之外仍明确停止并保留诊断，不能为延长窗口清账本。

冻结构建方案要求：

1. 新TRC/OWN/DIA/REL版本及独立decoder；保留旧版本和封存。若保持原头部尺寸，新最大
   OWN=13040、DIA=13056、REL=14368字节。同步核对原正常sink硬编码6640、诊断sink、
   receipt校验、关联工作区和文件读回容量，逐一覆盖边界与部分失败。
2. 保留现有SETUP服务顺序、16ms主机期限、A23 FrameID/SIA/interval和同步日志行为。
   候选已包含的保护单列；容量扩大不是原故障修复。新ELF重新绑定改动涉及的调用、
   常量、格式、BSS及可达栈成本，旧ELF绝对地址或formatter结果不自动成为新ELF验收。
3. 时间窗先保留现有语义，主机执行方案须提前等待fresh设备并记录实际时间关系；
   启动延迟与到期本身都归为诊断条件不满足。若必须改变起点，作为单独变更验证。
4. 仅在完整取得请求、阶段结果、身份与失败保存关系时判别分支；无法join、保存失败或
   丢关键记录仍为不可判定。实际logger/TLS/reent、完整线程栈、设备映射、停止时延及
   SD持久性继续作为明确缺口，按候选可达需求处理。

方案参数与原候选身份另存
[design-plan.json](../private/analysis/A23-diagnostic-readiness-validation-20261015/design-plan.json)。
第二版尚未实现、链接或生成设备包；这是下一项电脑任务，不是新的采集凭据。

## 验证与续接

14项新增回归全部通过、0跳过，包括容量两侧、原A23对照、断开不重置、替换不多发请求、
分支区分、候选拒绝来源、证据缺失、join失败、CRC/recipe损坏拒绝、旧输出保留及输入哈希。
124组ASan/UBSan native回放全部无dropped/invalid/bound violation。没有扩大为全库测试声明。

- [审查结果及124组回放](../private/analysis/A23-diagnostic-readiness-review-20261015/audit.json)
- [源快照、native程序与封存](../private/analysis/A23-diagnostic-readiness-review-20261015/SHA256SUMS)
- [14项回归日志](../private/analysis/A23-diagnostic-readiness-validation-20261015/regression.txt)
- [独立核验](../private/analysis/A23-diagnostic-readiness-validation-20261015/validation.json)

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 \
  research/usb-ds-iso/tools/audit_a23_diagnostic_readiness.py --output /private/tmp/a23-readiness-new
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -m unittest discover \
  -s research/usb-ds-iso/tests -p test_a23_diagnostic_readiness.py -v
```

输出必须是新目录。七个生产输入（含协议头）及三票据与基线哈希保持，原封存未修改。
SDK burst仍failed_no_retry/remaining0、采集禁用，日志已回收。本轮只运行电脑native模型，
没有新ARM构建/执行、打包、USB测试、SD访问或部署；原实机根因仍未知。
