# A23独立V2容量候选（2026-10-15）

已将[上一轮设计](A23_DIAGNOSTIC_READINESS.md)实现为独立V2候选：**256条trace、32个永久
身份槽，配套TRC2/OWN2/DIA2/REL2格式、独立分析器及文件容量。** 八次GET_INTERFACE后
目标三步完整完成，250条/22槽；历史选取的九次设置与八次断开形状为236条/15槽。
旧候选在这些模型中提前拒绝的容量限制已经消除，原实机故障根因仍未知。

## 实现与隔离

[构建工具](../tools/build_a23_capacity_v2_candidate.py)核验原GetSize保护候选、上一轮审查和
设计封存后，复制两配置完整源码到新目录；所有替换要求唯一源码锚点。只改变八个容量/
格式/文件策略源文件和recipe头，共九个文件。生产源码、原device目录及全部V1工具保持。

| 修改范围 | V2行为 |
| --- | --- |
| trace与owner | 256条、32槽；终结身份仍占槽，未知范围与迟到请求不清账 |
| TRC/OWN/DIA/REL | magic及外层版本号均为2；INI1启动记录和USB STATUS ABI保持原格式 |
| 正常sink | 将旧6640硬编码替换为该候选的EP0_CAPTURE_MAX |
| 诊断/关联保存 | 容量随新常量增长；关联receipt与文件入口核验DIA2/REL2 |
| 原服务路径 | 接口顺序、同步日志、HOS补丁、FrameID/SIA/interval、控制期限与等待实现保持 |

V2分析器为独立文件：[trace](../tools/analyze_ep0_trace_v2.py)、
[ownership](../tools/analyze_ep0_candidate_capture_v2.py)、
[diagnostic](../tools/analyze_ep0_diagnostic_v2.py)、[session](../tools/analyze_ep0_session_v2.py)。
解析器固定核验新版本及256/32布局，不在解码时修改旧数据。V1/V2互相拒绝；修复外层CRC
后混入旧/新内层trace的样例也被拒绝。所有新格式仍标为simulation，不认证实际来源。

## 真实客户端函数回放与边界

用上一轮同一124组矩阵，重新编译两配置及原A23对照。实际poll/helper/handler/dispatch/
ProcessRequests来自本轮生成树；USB、事件、时间、速度与join仍由电脑服务模型注入。

| 前置普通接口查询数 | V1候选 | V2候选 |
| --- | --- | --- |
| 0..2 | 目标三步完成 | 同样完成，原服务调用观察保持 |
| 3 | 拒绝后置STATUS | 完成，135条/12槽 |
| 4 | 拒绝BURST，seq0 | 完成，158条/14槽 |
| 8 | 查询阶段即停止 | 完成，250条/22槽 |
| 九次设置/八次断开形状 | 第7次设置时停止 | 完成，236条/15槽 |

查询与断开历史均保留，未增加USB请求或通过重置账本绕过容量。速度失败、请求替换、post
失败、ACK timeout、前置STATUS timeout、无接口2事件、pending和join失败的证据判别与
原124组矩阵相应场景一致。normal_export仍只表示可导出ownership封装，不表示USB通过。

额外259组实际admission边界检查：

- 对0..256个已用记录逐一回放；已用239条时单接口STATUS恰好到256，240条起在clear/
  GetSetup之前拒绝。事件保留，没有dropped/invalid。
- 剩两个身份槽时允许BURST/ACK，最终32槽；只剩一个时在seq/payload改写及post之前拒绝，
  payload保持原字节。此前已终结的31个身份没有被回收。

以上只覆盖声明的模型会话，不能推定真实枚举总请求上界、任意会话容量或持续串流稳定。
请求fixture不执行30秒计时器，也不执行真实VC/VS class、SD、HOS或线程调度。

## 序列化与真实文件adapter

| 封装 | 最大字节数 | 对应工作区/文件检查 |
| --- | --- | --- |
| OWN2 | 13040 | 32身份及256条有效结构记录，正常文件逐字节读回 |
| DIA2 | 13056 | 最大fault元数据、独立诊断与receipt绑定 |
| REL2 | 14368 | 1120字节INI1、DIA2及192字节关联头 |

最大格式样例由明确注入的元数据构造，单独独立解码，不标为实际handler或设备执行。
三个序列化输出少一个字节均拒绝且输出未修改；零长度、超过正常/诊断/关联各自上限、
过短REL头和旧REL magic共六项sink拒绝发生在create之前，旧DIA1 receipt也被拒绝。

58次文件场景直接编译本轮的正常/诊断/关联文件adapter函数体，FS由电脑内存模型替代：
成功、短读、打开/创建/冲突、部分写入、静默短写、损坏、flush/size/read、零读/超读和
commit错误，以及诊断/关联的两类join失败。一次性尝试不重试，源封装字节保持；失败
后的模型磁盘内容也封存。commit失败可保留完整可解码字节，但commit_acknowledged=false；
文件存在或能解码不能替代保存成功。join失败在任何owner/guard/session getter与FS前拒绝。

这一组检查覆盖字节和文件策略；没有运行真实SD、真实main退出、线程join或服务资源清理。

## 完整链接与可核验成本

两配置各13对象完整链接ARM ELF，26个编译单元严格格式检查通过；ARM未执行、未打包。
新recipe绑定记录的源码、原封存、SDK头、libnx.a、编译器和specs，并逐字节出现在最终
ELF只读段；ELF哈希另存。这些关联不认证实机来源。

| 项目 | dormant | window-30s |
| --- | --- | --- |
| text（size统计） | 153738 | 154050 |
| 相对V1 text | -3136 | -3136 |
| data | 13760 | 13760 |
| BSS | 1036208 | 1036208 |
| 相对V1 BSS | +28672 | +28672 |
| 最大项目函数自身栈 | 1376 | 1376 |

最终符号表核验：exported=13040、diagnostic_bytes=13056、session_bytes=14368、
session_work=14176、spans=768、storage=12816字节。不能以text减少推断执行更快或整体
资源缩小；BSS是实际增加。上述是函数自身栈，不包含完整SDK调用链、内核或异常栈。

最终ELF重新核验LogFunctionImpl的实际分支/调用/限长：GetSize失败只Close、正数写入最多
511字节、自身栈832字节。原core/worker/main正文未改。旧4080组完整formatter证书仍绑定
旧ELF，本轮未将旧绝对地址或旧回放记作新ELF验证；完整线程栈/TLS/reent等运行条件仍未知。

## 验证、封存与下一步

本轮442次native执行由124组会话、259组admission、58个文件场景与一组最大序列化组成，
均通过ASan/UBSan。15项新增V2测试和14项原readiness回归共29项通过、0跳过；不宣称
全库通过。V1格式、原封存、七个生产输入及三份票据保持，remaining0，采集仍禁用。

- [完整审查与构建结果](../private/analysis/A23-capacity-v2-candidate-review-20261015/audit.json)
- [dormant源码](../private/analysis/A23-capacity-v2-candidate-review-20261015/dormant/source/uvc/ep0_trace.h)
- [dormant完整ELF](../private/analysis/A23-capacity-v2-candidate-review-20261015/dormant/full.elf)
- [审查封存](../private/analysis/A23-capacity-v2-candidate-review-20261015/SHA256SUMS)
- [29项回归](../private/analysis/A23-capacity-v2-candidate-validation-20261015/regression.txt)
- [独立核验](../private/analysis/A23-capacity-v2-candidate-validation-20261015/validation.json)

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 \
  research/usb-ds-iso/tools/build_a23_capacity_v2_candidate.py --output /private/tmp/a23-v2-new
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/usb-ds-iso/tests /opt/homebrew/bin/python3.12 \
  -m unittest test_a23_capacity_v2_candidate test_a23_diagnostic_readiness -v
```

输出必须是新目录。下一项收敛30秒窗口与主机提前等待方案、V2主机/设备材料关联和失败
保存条件，再按实际可达路径核对线程/TLS与运行成本。保留窗口在USB ready之前启动、
只能在同步处理边界检查的语义，不把它当作硬停止时限。候选容量缺口已在模型中解决，
不据此认定原控制超时已修复。没有新USB/SD访问或设备部署。
