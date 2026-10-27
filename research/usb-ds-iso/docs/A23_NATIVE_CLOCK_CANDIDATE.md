# A23 原生精确等待与显式时钟域候选（2026-10-20）

后续：[独立quiet轮询与deadline适配候选](A23_QUIET_POLL_CANDIDATE.md)已验证完成事件/guard/失败撤销及arrival/poll边界；未接入冻结Objective-C driver，完整状态机和现场结果仍未认证。以下保留原阶段。

接续[完整文件清单边界](A23_CACHED_OUTER_FORENSICS.md)，新增独立C候选及stdio离线fixture，未替换冻结receiver的任何实现，也未接入真实driver、owner或supervisor。候选解决的是整数时间算术及声明一致性，不认证真实时钟、现场等待或回调排空。

## 精确比较

冻结 `io_usb_host_runtime_guard.m` 的转换规则为向上取整；冻结driver的quiet判断使用该结果与250000000比较。2/3 timebase下，374999999 ticks的真实有理数值为749999998/3 ns，小于250ms，但ceil得到250000000ns。

新 `host/a23_clock_candidate.c` 用128位整数分别比较：

```text
delta_ticks * numerator >= minimum_ns * denominator
delta_ticks * numerator <= maximum_ns * denominator
```

向上取整值只作为报告值，不能将不足最短等待的区间提升为达标。区间上下界均包含等号；最大允许时长的包含规则适用于本候选的区间API，不能不经适配就替换原driver的arrival/poll两种截止规则。

uint64 ticks和阈值乘uint32 timebase的中间结果小于2^96，使用 `__uint128_t`。转换为uint64纳秒时检查ceil是否溢出；即使floor仍为UINT64_MAX，只要ceil为UINT64_MAX+1也拒绝。所有失败清空输出标志，调用方必须同时检查status；短于minimum是有效测量但不满足区间，不应误报为测量错误。

## 域和接口

候选Stamp包含ticks、域、非零clock实例、numerator和denominator。支持当前离线分类的injected driver、native owner及supervisor-ns；只允许起止域、实例和timebase完全一致的计算。未知域、未知/零timebase、实例为0、跨域、实例变化和timebase变化均拒绝；等价但表示不同的2/3与4/6也拒绝。supervisor-ns要求规范1/1。

调用者提供的域和实例只是声明。为owner提供有效ratio并通过计算不意味着实际查询过其timebase；`actual_timebase_queried`、`clock_labels_authenticated`和现场来源字段仍false。新helper接受tick0作为算术值，原driver将 `_quietSince==0` 用作未开始状态，接入时必须保留该生命周期判断。

该候选支持分数ratio测试，比冻结step100的1/1文件模型profile更广；没有改变原缓存profile或为旧owner创建时钟映射。

## 验证结果

- 2333组输入：明确反例/域/实例/错误边界、极值组合及2048组固定种子的随机向量。
- Python oracle使用 `Fraction` 比较精确有理数，独立于C的交叉乘法实现。
- clang C11优化版和UBSan版均以 `-Werror -Wconversion -Wsign-conversion` 编译，无警告、无sanitizer输出，全部结果与oracle一致。
- 1642组测量有效；其余691组因参数/域/timebase/实例/倒退/溢出被拒绝。有效测量不一定满足等待区间。
- 每版执行批量向量、空指针/输出重置和8种错误输入协议；两版共20次fixture进程执行。完整搬移442来源后重新编译两版并重复20次，所有向量、结果、分类和错误协议结果一致。二进制不要求逐字节可复现。
- 新18项及旧时钟16项/外层取证18项，共52项测试无跳过通过；正确/错误/缺失外部pin的只读CLI分别返回0/2/2，只读检查不运行C二进制。

优化fixture只链接libSystem，未定义导入为stdio/字符串/栈保护和128位除法辅助。测试程序只接收数字stdin及固定的pointer-checks选项。构建和fixture子进程不继承Python文件审计钩子；主搬移流程对原checkout和 `/Volumes` 的打开观测为0，不能据此声称操作系统能力隔离。

## 材料与状态

- 头文件及实现：`host/a23_clock_candidate.h`、`host/a23_clock_candidate.c`。
- fixture：`tests/a23_clock_candidate_fixture.c`。
- audit及测试：`tools/audit_a23_clock_candidate.py`、`tests/test_a23_clock_candidate.py`。
- 审查：`private/analysis/A23-clock-candidate-review-20261020-r1`，447清单成员，摘要 `cb6839fa0a9f3a12046784419e65f0edf09dec3a3b7690665723cd91c4b5fc84`。
- 验证：`private/analysis/A23-clock-candidate-validation-20261020-r1`，含测试、搬移重编译封存、符号/依赖及旧规则和新算术对照。
- 收口：`private/analysis/A23-clock-candidate-closeout-20261020`，含源文件、票据/文档快照、保护项及引用。

原437来源字节不变，仅新增5份候选/fixture/audit/测试，当前442。冻结runtime guard和driver、实际49/65、账本、失败修复owner及23保护项保持。票据仍为65已回收、remaining0、81..112未正式保留，采集关闭。

本轮原位置及搬移位置合计构建4份离线C fixture、执行40次fixture进程。没有构建/启动生产receiver、刷新实际context、创建真实SDK对象、访问USB/SD、构建固件、改动设备包或正式发行/保留。原生产实现的minimum修复仍为未接入状态。

下一步在独立候选fixture中适配quiet轮询调用点，明确driver时钟域/实例与未开始sentinel，验证不足/达到阈值、停止/日志失败等状态转换，并保留arrival与poll的既有最大时限区别；不直接部署候选或运行旧receiver。
