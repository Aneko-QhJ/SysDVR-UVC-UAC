# 缓存中的entry、receipt与SDK session关联

后续：[缓存中的模拟发行、原生许可与context关联](A23_CACHED_PERMIT_CONTEXT.md)已核对内部许可与外层实际/注入context关系；生产许可和时限仍未认证。以下保留原阶段。

2026-10-20，承接[缓存构建结构与日志引用关联](A23_CACHED_BUILD_RELATIONS.md)。新增三个来源文件，总数425；原422来源、23项保护记录和真实账本保持原字节。

已从原有构建分组和92份日志/事务缓存建立entry→driver/receipt→SDK session→epoch的数据关联。30个场景中3个满足定义的关联子集、27个反例拒绝。结果为`consistent_cached_session_link_subset`；完整SDK链、原生许可、时限、观察窗口和现场认证继续false。

## 本轮关联范围

新消费者先调用上一阶段纯缓存构建检查，再复核原日志字节合同。它不打开嵌入路径、不运行旧路径分析器，也不直接采用旧材料的`complete`结论。

- entry-current与entry-final完整JSON内容对应；entry的driver副本、最终driver、result、SDK snapshot及receipt内嵌snapshot一致；receipt的snapshot摘要对应保存的原始字节。
- entry最终状态、SDK receipt状态及其全部副本必须为attempted/saved、非stale；driver与lease的次数、保留状态和权限字段按类型检查，布尔不能替代整数。
- 25条SDK事件和12条entry事件完整、无重复，索引及时间数值类型有效；SDK事件的session ID、prepared binding与receipt匹配。这里只检查声明顺序和数值关系，不认证时钟来源或deadline。
- entry日志的构建绑定、context字节摘要及process/SDK claim副本一致；选择的device/interface对应SDK prepared identity，六步adapter声明及entry→SDK日志交接顺序一致。没有认证原生permit、进程身份或context执行策略。
- 两轮epoch绑定与SDK prepared/receipt绑定一致；before与metadata原始字节摘要、frame sample及budget副本、trigger序号及callback声明匹配。既有STATUS/URB/ISO7与有效载荷子集继续复核。
- quiet记录中的起止数值与snapshot副本一致，但本轮不据此计算或认证250ms观察窗口。

## 确认的模型时钟边界

冻结来源中的`BrokerClock`从`mach_absolute_time()+100`起步，随后每次查询只增加100，并声明1/1 timebase；driver日志和driver callback入口使用该注入时钟。底层`A23TransactionOwner`回调则直接记录真实`mach_absolute_time()`。driver日志把owner事件内容原样嵌入，因此同一JSON中保留两类时钟值。

正常历史模型的两个ISO callback记录为：

| epoch | driver arrival ticks | owner arrival ticks | journal ticks |
| --- | ---: | ---: | ---: |
| 0 | 18552314646335 | 18552444284008 | 18552314646535 |
| 1 | 18552314648835 | 18552484517267 | 18552314649035 |

直接比较会得到owner到达晚于记录事件；这不构成真实USB时序倒置证据。源码显示它们取自不同的模型时钟路径，本轮没有建立共同的时间映射、误差界限或单位关系。结果逐项保留这些数值，`owner_driver_clock_domain_relation_verified`始终false。

另一个构造场景把owner到达值整体增加1000000，session/receipt/epoch的数据关联仍成立。它明确展示关联子集不能证明时钟语义。另一个正向场景交换两种callback的日志先后，验证消费者不把特定回调先后固定为唯一合法顺序。

冻结源码片段、来源摘要和上述数值另保存于本轮验证归档的`clock-source-evidence.json`。原始模型及其旧分析原件没有改写。本轮未重新编译或执行原生模型；旧模型通过的结论不能升级为新时限认证。

## 反例、测试与复核

27个拒绝场景覆盖driver/receipt副本、stale状态、snapshot摘要/嵌入内容、driver session、布尔次数与数值complete、事件索引/时间类型、重复或半截日志、session及descriptor绑定拼接、claim/选择身份/context摘要、entry事件错误、epoch session拼接、sample/budget/metadata摘要、callback次数、control字节数、quiet记录和前置构建引用错误。

反例重新生成日志原清单和外部链接摘要，并重建全部嵌套封存。修改epoch metadata的场景同时更新saved事件的原字节摘要；结果按指定的关联类别拒绝，避免仅依靠过期摘要失败。反例由冻结函数和保留的正常缓存确定性重建，保存每场景输入摘要和新分析。

新增15项及旧构建15项、旧日志/事务15项共45项测试通过，无跳过。425项来源和完整材料搬移后，全30场景及三种CLI复核一致；消费者文件打开0，搬移复核进程对原仓库和`/Volumes`文件打开0。CLI子进程不继承Python审计钩子，这不构成OS能力隔离。

初稿r1在最后一个前置构建坏件使用了错误的fixture配置相对路径，审查未提交；失败来源、材料和日志独立保留。r2修正坏件构造路径后，全部场景通过预期分类，作为最终审查。

## 下一步

继续从缓存核对共享序号的发行/消费、authorization receipt与原生permit、process/SDK context及外层监督关联。随后为注入时钟和owner真实时钟明确独立域或建立有界映射，再检查callback deadline与250ms观察窗口；不能直接混合这两类ticks。

本轮USB、SD、真实SDK、原生执行、固件构建、正式发行和序号保留均0。真实49/65、失败修复owner和23保护项保持；65已回收、remaining=0，81..112未保留，生产32序号目录未创建，生产采集仍关闭。模型时钟边界不解释真实设备故障根因。

最终审查：`private/analysis/A23-session-links-review-20261020-r2`，SHA256SUMS摘要`b350df05a0a347c8613e4b85928037a566a4d8ed9cb3e09218283ce1f35f5f24`。

验证与交接：`A23-session-links-validation-20261020-r1`、`A23-session-links-closeout-20261020`，以各自SHA256SUMS和COMMITTED为准。

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.14 research/usb-ds-iso/tools/audit_a23_cached_session_links.py \
  --check "$PWD/research/usb-ds-iso/private/analysis/A23-session-links-review-20261020-r2" \
  --expected-sha256 b350df05a0a347c8613e4b85928037a566a4d8ed9cb3e09218283ce1f35f5f24
```
