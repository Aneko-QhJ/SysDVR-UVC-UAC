# 关联发布/中断与最终ELF栈审查（2026-10-14）

上一轮REL1候选的并发与中断边界已补验：未release的context/receipt不会成为已发布数据；runtime capture未返回或中断时不会输出成功文件，第一份快照完成后也不能升级或覆盖。所有生产、候选runtime、旧格式、ELF与历史封存保持原样，remaining=0，USB/SD访问0，根因未知。

10项核心发布策略与11项实际runtime策略，各通过ASan/UBSan和TSan，共42次场景检查；14项新增与429项相关Python回归无跳过。三线程核心竞争与四线程runtime竞争发生在电脑pthread，发布中断使用测试边界的协作退出；没有运行Switch线程、DMA、真实USB/FS。本阶段未新增ARM候选，相关回归会在临时目录复建旧实现。

## 并发与首次快照语义

| 场景 | 核验结果 |
| --- | --- |
| 两个context发布者与一个读取者 | 32份独立存储各仅1个winner；writer与boot/session字段完整一致 |
| 两个receipt发布者与一个读取者 | 32份各仅1个winner；输入长度/CRC一致，ack或commit错误字段不混合 |
| release前context/receipt已填字段 | phase=1时读不到这些字段，context仍unbound、receipt省略；poison EP0/sink旁路通过 |
| release前发布者协作退出 | phase保持1，不重置、不认证完成、不自动恢复 |
| runtime capture占用工作区 | Bytes返回NULL/长度0，第二个capture在CAS门槛拒绝，不读取poison recipe |
| runtime capture占用后协作退出 | phase保持1，Bytes始终未发布；第二次调用不能补写 |
| recipe不一致导致capture拒绝 | phase=3，无伪造metadata；不再次尝试 |
| 三个runtime capture与一个Bytes读取者 | capture只成功1次，EP0/receipt getter各只被winner读取一次；完整输出不可变 |
| StartupOnly与Bind并发 | 输出可有或没有已发布context，但始终只含startup，不读owner/receipt |
| context尚未发布时先完成快照 | 随后Bind不修改该快照，后续Joined无法将它升级成完整诊断 |
| 启动尚未尝试时Bind | 拒绝且无SID查询，StartupOnly仅192byte状态信息 |

两个核心race先读至少32份未发布状态，再释放发布者竞争，并在所有发布者返回后再读32份完整状态；竞争期间的读取次数取决于电脑调度，不作为性能指标。发布者/读取者使用同一session生命周期、有效输入和独立只读owner；reader的工作区归单个reader，不共享可变scratch。所有最终context/receipt样例另存REL1并独立解码，owner/guard内容不变。

核心测试使用封存header的新副本，仅在两个最终release之前增加测试hook；hook暂停或pthread_exit，使“字段已写但phase仍1”的状态可确定重现。正常竞争时hook不做同步。runtime测试直接嵌入封存startup/session源码，用startup状态getter的测试wrapper暂停capture claim后的执行；callback、实际候选源码与ELF均未修改。这些hook和host退出仅模拟边界，不证明Switch异常、fatal回调或中断可达性。

读取后的别名、对象销毁/重用、修改已经发布的字段、伪造join或在owner仍可变时读取均不在允许的生命周期内。TSan无报告覆盖本次受测调度，不认证SID，也不证明任意程序或真实DMA安全。原startup与joined读取契约保持：StartupOnly可与VideoThread绑定并发；真实Joined仍要求两个worker已经退出，不能把仍在发布的VideoThread伪称已join。

第一份快照优先是既有单次设计的结果：启动失败的早期记录不会随后自动补成完整会话，capture中断也不会恢复。如果将来需要多阶段文件，须独立存储/发布代次与格式设计，不能在当前immutable输出或phase上原地重置。当前不增加重试、sidecar、启动失败写卡或清理授权。

## 最终ELF的调用链与SP

对上一轮两配置完整ELF做只读反汇编，以名称和地址区分同名SDK内部函数，按函数内分支传播SP、核对项目静态.su记录，再沿直接call/tail边累计调用时尚未释放的用户态栈。分支不一致、未知SP写入、动态分配、间接目标、递归和无法识别的函数终止均保留为未闭合；不会把未知callee当0再发布上界。模拟负例另外核验recursive call与.su/机器码不一致均拒绝给出上界。

| 入口 | 结论 |
| --- | --- |
| session_capture | 两配置直接调用图闭合，累计用户态SP上界352byte |
| Ep0SessionStartupOnly / Ep0SessionJoined | wrapper尾调用到capture，入口累计上界同为352byte |
| Ep0SessionSaveJoined | 自身560byte已核对，完整上界未闭合：snprintf进入_svfprintf_r间接调用/跳转，另有异常终止边界 |
| VideoStreamThread | 完整上界未闭合：SDK waitObjects按寄存器动态调整SP，并有间接调用/跳转；旧logger格式化与异常路径也未闭合 |
| AudioStreamThread / __appInit / main / __appExit | 有logger/SDK格式化或异常路径未闭合，不发布线程栈上界 |

352byte从上述入口开始计数，已包含其直接SDK memcpy/memset/memcmp等静态路径；不包括调用它时main/LaunchThread等caller已占用的栈，也不包括内核/异常上下文。它与上一轮单函数报告相同，是调用图核验后的局部上界，不是完整线程栈或实际峰值。

分析同时保存结构上可见的已知路径和值，未按常量format、TLS有效性或noreturn语义裁剪。含未解析边的这些数值不能当作真实运行峰值、完整上界或实测下界。waitObjects的动态SP尤其需要把实际调用参数/事件数与SDK机器码关联；不会凭视频/音频线程栈配置或最大单函数.su数值推断足够。

## 证据与续接

- [发布竞争/中断fixture](../tests/ep0_session_concurrent_publish_test.c)、[runtime竞争fixture](../tests/ep0_session_runtime_concurrency_test.c)、[回放审查工具](../tools/audit_a23_session_concurrency.py)、[最终ELF SP分析](../tools/analyze_a23_session_stack.py)、[交叉检查](../tests/test_a23_session_concurrency.py)。
- [审查audit](../private/analysis/A23-session-concurrency-review-20261014-final/audit.json)、[manifest](../private/analysis/A23-session-concurrency-review-20261014-final/SHA256SUMS)：两sanitizer的源码/程序/独立REL1解码、42次策略检查、两完整ELF反汇编及逐函数/调用图/未闭合位置。
- [验证摘要](../private/analysis/A23-session-concurrency-validation-20261014/validation.json)、[manifest](../private/analysis/A23-session-concurrency-validation-20261014/SHA256SUMS)：429项回归、源码与生产快照、三票据、历史封存及文档链接核验。

下一步电脑把SDK waitObjects的参数与动态SP/间接路径核对，审查固定REL1路径拼接是否需要通用格式化，明确TLS/异常终止前提后再计算更完整的保存/线程栈；不改旧候选来凑上界。启动helper细阶段与64条记录预算、失败时FS/部分线程/借用条件仍待审；任何回滚或失败导出都需单独设计。当前真实DMA、join、停止时序、实际栈/运行成本、文件持久性与来源认证未测，不能将此次模型或局部上界当作首次SDK burst的原因或修复。
