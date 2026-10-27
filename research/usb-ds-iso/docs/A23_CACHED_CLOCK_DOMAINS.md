# 缓存时钟域与模型时限算术

后续：[缓存来源准入、verifier与静态收集关联](A23_CACHED_COLLECTION_LINKS.md)已完成45场景及49测试；静态收集、外层退出及verifier执行声明分别处理，完整运行认证仍未完成。以下保留原阶段。

2026-10-20，承接[模拟许可/context关联](A23_CACHED_PERMIT_CONTEXT.md)。新增三个来源文件，总数431；原428项、23项保护记录、真实49/65及账本保持原字节。

已明确三个独立时钟域，并从缓存核对注入driver时钟内的预算、回调到达、记录顺序及最小观察间隔。30个场景中7个满足模型算术子集、23个拒绝；新增16及旧permit16/session15项共47测试无跳过通过。结果为`consistent_injected_driver_clock_arithmetic_subset`，不升级现场时限、时钟来源、回调排空或完整SDK链认证。

## 时钟域合同

外部固定的clock profile绑定receiver构建清单、日志清单和三份冻结来源摘要：BrokerClock fixture、transaction owner、SDK driver。profile只适用于已审查的step100注入模型，要求driver时间基准为1/1。消费者先复核既有构建、session、模拟发行和context子集，再从分组缓存复核来源摘要。

| 域 | 可用信息 | 本层用途 |
| --- | --- | --- |
| injected_driver | fixture每次查询增加100，可显式advance；声明1/1基准 | driver入口、控制观察、SDK journal、预算与quiet数值计算 |
| native_owner | 原生owner直接采样mach_absolute_time；没有保存可用时间基准/跨域映射 | 原值保留，duration为null，不参与driver减法 |
| supervisor_ns | 上游独立核对的监督器ns声明 | 不参与本层driver时长计算 |

相同起点外观或数值接近不构成域等同。跨域减法、owner无基准换算、伪造跨域mapping、角色替换、布尔ratio、来源漂移及权限声明提升均拒绝。旧原件没有新加clock标签；profile是受限离线解释合同，不能证明运行时真实使用了该时钟。

`sample.frame_time`仅核对正整数声明，不把它当作driver时长端点，也不据此认证总线微帧相位或物理服务时间。

## driver域内规则

| 指标 | 上限或下限 |
| --- | ---: |
| 帧查询时间 | ≤2 ms |
| 帧样本至入队检查年龄 | ≤16 ms |
| 入队调用时间 | ≤8 ms |
| 入队返回至触发间隔 | ≤8 ms |
| 帧样本至触发年龄 | ≤32 ms |
| ISO入口到达距submit | ≤2 s |
| control入口到达距trigger | ≤16 ms |
| 两轮保存后的模型quiet间隔 | ≥250 ms |

回调上限使用driver入口保存的到达时间，等于上限可通过；本阶段只分析已有到达记录，未实现pending无到达时的超时状态机。queued handler的journal时间只用于因果顺序和排队延迟，不替代入口到达时间。25 ms排队场景因此仍能满足control入口200 ns的模型算术。

预算中的query/age/call、trigger-return中的gap/age均独立重算，不能只信任budget_pass。按driver时钟核对before观察、sample、submit/check/return、trigger、callback入口/日志、after观察、save及下一轮顺序；quiet必须在两轮保存记录之后开始，结束值不得晚于声称观察完成的journal时间。

正常历史注入记录两轮均为ISO到达800 ns、control到达200 ns，quiet为250000101 ns。这些是fixture数值，不是设备性能或真实墙钟时长。owner的真实ticks原值保持，整体偏移不改变driver计算，也不会获得跨域认证。

## 最小等待的舍入反例

冻结的`A23TicksToNanoseconds`用向上取整转换ns，SDK quiet代码再比较`ns>=250000000`。向上取整用于整数最大时限可以保守检查；对于最小等待，分数不足量可能被补成已达标。

独立数学反例：numerator=2、denominator=3、ticks=374999999，真实分数为`749999998/3 ns`，小于250000000 ns，但ceil为250000000 ns。当前1/1 profile没有分数余量，不受该反例影响；这里没有观察到设备故障或证明真实USB根因。

新的离线`minimum_elapsed`使用精确交叉乘法：`ticks*numerator >= minimum_ns*denominator`。该反例拒绝，375000000 ticks的精确边界通过。一般转换仍执行严格uint64端点、uint32 ratio、无逆序及转换结果溢出检查，不用浮点。

本轮没有修改或执行原生C/Objective-C代码。反例只验证数学规则，新最小等待规则只进入离线校验器；原生候选修正及其执行验证不在本轮完成范围。冻结源码片段、摘要和反例另保存在验证归档的`clock-rule-evidence.json`。

## 场景与复核

7个满足模型算术的场景是历史正常、owner偏移、独立生成正常时序、25 ms排队、两种callback恰好上限、全部预算恰好上限和quiet恰好250 ms。

23个拒绝场景涵盖六种预算/回调超限、预算和trigger算术不符、callback晚于自身日志、after观察早于callback、保存早于观察结束、反向sample、布尔check、quiet少1 ns/逆序/早于保存/晚于完成记录、五种profile错误和前置receipt损坏。

生成场景同时更新metadata、SDK事件、driver/snapshot/receipt、entry/report副本、业务摘要及全部嵌套封存；时序坏件通过旧关联子集后由本层拒绝。反例是确定性文件模型，未执行新的原生fixture。profile来源摘要符合冻结源码也不证明模型记录曾按该代码执行。

431项来源和完整材料搬移后，全30场景、数学反例及三种CLI结果一致。消费者文件打开0，搬移复核进程对原仓库及`/Volumes`文件打开0；CLI子进程不继承Python审计钩子，不提供OS隔离。

r1封存为最初1/1模型算术版本，r2增加精确分数最小等待规则和反例测试；两份均保留，以r2为最终审查。原始1/1数据的分类不变。

## 下一步和现场边界

继续离线补齐来源准入、verifier结果及最终收集元数据与当前缓存链的关联；为原生候选单独设计最小等待规则修正和时钟域声明，再验证实际时钟来源。不能从本轮数值一致性推出OS进程来源、真实wall-clock等待、现场SDK时限或设备状态。

本轮USB、SD、真实SDK、原生执行、固件构建、context刷新、正式发行及序号保留均0。23保护项、失败修复owner和实际账本保持；65已回收、remaining=0，81..112未保留，生产32序号目录未创建，生产采集仍关闭。

最终审查：`private/analysis/A23-clock-domains-review-20261020-r2`，SHA256SUMS摘要`b0b9d5b6c09f882d98adbed75c8d51416dcfabd62522738b54bc90c9f69c63cc`。

验证与交接：`A23-clock-domains-validation-20261020-r1`、`A23-clock-domains-closeout-20261020`，以各自SHA256SUMS和COMMITTED为准。

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.14 research/usb-ds-iso/tools/audit_a23_cached_clock_domains.py \
  --check "$PWD/research/usb-ds-iso/private/analysis/A23-clock-domains-review-20261020-r2" \
  --expected-sha256 b0b9d5b6c09f882d98adbed75c8d51416dcfabd62522738b54bc90c9f69c63cc
```
