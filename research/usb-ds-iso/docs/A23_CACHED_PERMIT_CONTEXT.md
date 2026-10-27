# 缓存中的模拟发行、原生许可与context关联

后续：[缓存时钟域与模型时限算术](A23_CACHED_CLOCK_DOMAINS.md)已建立driver独立域内预算/到达/quiet算术规则，并给出分数最小等待反例；原生与现场时钟认证仍未完成。以下保留原阶段。

2026-10-20，承接[entry/receipt/session关联](A23_CACHED_SESSION_LINKS.md)。新增三个来源文件，总数428；原425项和23项保护记录保持原字节。

从缓存核对模拟共享序号的发行/消费、授权摘要、原生process/selection claim、entry context和外层监督。33个场景中3个满足定义的模拟关联子集、30个反例拒绝；新增16及旧session15/构建15项共46测试无跳过通过。结果为`consistent_cached_simulated_permit_context_subset`；生产许可、真实进程身份、完整SDK链、时限和现场认证继续false。

## 本轮核对范围

- 共享namespace只有模型scope、既定49..64/65..80历史、一个81..112模型记录和唯一作业的完整文件集合。历史reservation及record摘要与receiver缓存中的冻结历史成员相符；不打开历史材料声明的路径。
- job、authorization、32序号模型reservation、issue和consumed逐字段重建，并核对issue/consume提交标记和尝试标记。simulation必须true、硬件授权false、invocations整数1；consumed为remaining整数0且receiver_launched=false。
- entry binding中的授权回执摘要对应原始consumed字节；原生process claim对应job、scope、consumed、原始native-context摘要和PID。selection对应原始process字节摘要、context、PID及HS设备身份。
- native-context与entry context的JSON值一致；逐项执行既有纯context策略检查。host与native保存使用不同JSON编码，各自摘要继续绑定原字节。
- entry process/SDK claim的PID与context相符；两种选择声明的device/interface一致。原生permit报告必须simulation、两次claim成立、非stale、无硬件或进程来源认证；计数按整数检查。
- fixture report的execution context、entry副本及原始report副本一致。外层hello、handoff、nonce、owner、命令、作业路径、父子身份、collection PID及actual context相互匹配。
- 监督器自己的5秒hello/30秒执行预算和保存的ns数值按固定合同核对，不与SDK ticks或owner ticks混用。这只是已提供记录中的数值一致性，不证明现场退出或时限。

所有输入继续先经过缓存构建、entry/receipt/session与两轮epoch子集复核。消费者只接收缓存及字节参数，没有发行器、实际账本写入、进程查询、启动或USB接口。

## 实际与注入context的区别

历史hello、命令及report的actual_context均记录`sandbox_query_result=1`，既有执行策略检查不接受它。fixture声明`inject_policy=true`，只允许把`sandbox_query_available/result/errno`改成`true/0/0`，再与native、entry及report的execution_context逐项比较。

正常结果保留：

```json
{"actual_context_policy_accepted":false,"injected_policy_declared":true,"actual_sandbox_query_result":1,"supplied_execution_sandbox_query_result":0}
```

这属于2026-10-19历史模型的记录，本轮没有刷新当前进程context。模型记录一致不表示实际环境策略通过，更不授予现场USB权限。

两个关键反例都先把内部关联改到一致，再由外层拒绝：

- PID拼接同时更新native/host context、process/SDK claim、原始字节摘要、entry checkpoint、entry事件及report。内部许可关联一致，但外层监督的child PID仍不匹配。
- context额外字段替换同时更新全部内部副本和摘要。内部策略及关联可一致，但与actual context相比多改了euid，违反仅允许三项sandbox字段的注入声明。

worker和历史plan/context中可以保留不同搬移阶段的逻辑路径。构建角色由外部清单和二进制摘要关联，路径只在相应声明之间作词法比较；本轮没有把逻辑别名当作实际执行路径或OS来源证明。

## 原始JSON编码兼容

历史host context由Foundation保存，含`\/`转义且无末尾换行；native-context为不转义斜杠的规范JSON并有末尾换行。二者解析值一致，原始SHA256不同。新读取器仅对这两类context接受规范JSON的斜杠转义/不转义及有/无末尾换行四种编码；重复键、额外空白、字段类型与context策略检查保持。

初稿r1因只接受不转义编码而拒绝正常材料，失败来源、材料和日志独立保留。r2接受上述确切编码，始终使用各自原始字节核对摘要，没有改写或重序列化原件。

## 反例和复核

30个拒绝场景覆盖：授权布尔次数/硬件声明，reservation计数/job摘要，issue/consume标记和consumed布尔值；native PID/sandbox/回执/HS身份/尝试/stale/计数，entry回执/PID；命令nonce、监督PID、注入声明、actual副本、策略结论、完整内部PID拼接、额外context替换、owner、hello预算/迟到、作业路径、collection PID及前置session回执错误。

每场景重算原清单、外部链接和嵌套封存；上下游业务摘要本身是检查对象，不自动“修正”被故意破坏的关联。正常、owner时钟偏移和监督记录中仍在预算内的hello观察值偏移三个场景满足本轮子集，但不认证实际时钟或进程。

428项来源及材料搬移后，全33场景与保存分析逐字节一致；正确/错误/缺失外部摘要的CLI分别退出0/2/2。消费者文件打开0，搬移复核进程对原仓库和`/Volumes`文件打开0；CLI子进程不继承Python审计钩子，不提供OS能力隔离。

## 下一步和现场边界

继续离线明确driver注入时钟与owner真实时钟的独立域或有界映射，制定不混用ticks的callback deadline及250ms观察窗口核验规则，并保留旧模型原件。完整来源准入/verifier/final收集叙述仍需逐项关联；本轮没有认证整条SDK链。

本轮USB、SD、真实SDK、原生执行、固件构建、context刷新、正式发行及序号保留均0。真实49/65、实际账本、失败修复owner和23保护项保持；65已回收、remaining=0，81..112未保留，生产32序号目录未创建，生产采集仍关闭。结果中的32仅为历史临时模型声明。

最终审查：`private/analysis/A23-permit-context-review-20261020-r2`，SHA256SUMS摘要`5f843197e793bcbcf4ce1f0e3265d052d155eebbcdc2c15080841db9e4e3fda2`。

验证与交接：`A23-permit-context-validation-20261020-r1`、`A23-permit-context-closeout-20261020`，以各自SHA256SUMS和COMMITTED为准。

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.14 research/usb-ds-iso/tools/audit_a23_cached_permit_context.py \
  --check "$PWD/research/usb-ds-iso/private/analysis/A23-permit-context-review-20261020-r2" \
  --expected-sha256 5f843197e793bcbcf4ce1f0e3265d052d155eebbcdc2c15080841db9e4e3fda2
```
