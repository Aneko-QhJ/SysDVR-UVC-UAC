# 固定三轮主机离线核心（2026-10-23）

后续接线已完成：[当前97件三轮候选](A23_LIVE97_THREE_READY.md)已编译封存，等待新单次授权和现场状态确认。下文保留此前离线核心阶段的历史语境。

三轮SDK资源与driver已在独立生成副本中编译并通过19个原生注入场景，正常路径保存三组、9216正确字节。独立分析器接受三轮并拒绝两轮、四轮、坏载荷和复用任意先前URB；固定48序号模型验证一次消费和完整49..176历史要求。尚未接入当前97件现场scope、真实入口控制器、第三轮失败快照导出及checked export，因此完整实测候选未就绪。

新增4来源，总619；旧615逐字节保持：

- `tools/a23_three_epoch_candidate.py`：固定三轮生成规则，生成独立Triple provider/resource与ThreeEpoch driver、严格分析器和仅临时目录运行的48序号模型。
- `tools/audit_a23_three_epoch.py`：封存输入核对、原生编译/注入、独立归档验收及模型消费检查。
- `tests/a23_three_epoch_fixture.inc`：仅注入SDK形状操作的原生场景。
- `tests/test_a23_three_epoch.py`：48序号模型的6项行为测试。

实际91件build的生成driver和STATUS分析器作为语义父本，先核对完整封存清单再派生；paired adapter由旧615中固定的源码派生。生成代码只写新审查目录；现有双轮源码、真实入口、部署和实测build不改。每个生成替换核对锚点数，数组只扩指定声明，保持SHA256、接口2、lead32、960 transaction、192字节及单轮截止时间。

## 完成的接线

独立SDK lease一次准备六块互不重叠的存储，分别保留三组data/transaction地址、ISO/控制回调计数和进入标记；最多6次STATUS、3次frame查询、3次ISO和3次BURST。下轮STATUS/查询/ISO前核对所有先前轮的终态；任意重复旧回调污染lease，停止继续。活跃资源仍保留到进程结束，未添加运行中destroy或自动重试。

driver只接177起始序号，三组owner和原子状态分别保存；前轮保存并ack后，由后续串行poll进入下一轮。第三轮before比较第二轮after，沿用仅report_count0/1可变化的政策；第三轮after与全部先前URB比较。STATUS原件、观察及失败字段仍在判断前独立封存，三轮保存后保持原250ms观察及单次回执。观察和回执都不认证回调排空。

分析器有独立三轮schema，要求3个epoch目录、36个有序事件、三组回调、6份STATUS留证及9216正确字节；每轮前置STATUS与前轮after相符，新URB不得与任意旧轮重复。两轮/四轮目录、重新封存的第三轮坏载荷、协调重写after及STATUS副本/摘要后复用第一或第二轮URB均拒绝。有效数据保留`injected_fixture`标签，不当作真实SDK或设备成功。

固定48模型采用独立schema/class，拟177..224且要求完整49..176消费历史集合。只允许simulation=True和规范/private/tmp子目录，formal分支在创建目录前拒绝。一次issue/consume烧完整48段，不可重复消费、重发或由第二job接管。模型消费只发生在临时目录；模型不是正式授权或真实入口许可。完整历史的摘要仍由调用方提供，本阶段没有认证物理来源。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| 原生正常三轮 | 3个不同URB、3次提交/触发、9216正确字节，独立验收通过 |
| 第0/1/2轮状态失败 | 分别止于1/2/3次提交，无补轮 |
| 第三轮before错误回取首轮 | 2次提交后拒绝，第三轮未提交 |
| 第三轮复用首轮或第二轮URB | 留下失败STATUS原件并拒绝 |
| 第三组data/transaction别名 | 准备拒绝，无ISO/BURST |
| 第三组存储改变、旧第一/第二轮回调晚到、第三轮前detach | 2次提交后停止 |
| 第三轮保存冲突、STATUS留证冲突、控制超时 | 停止；不重试，未决资源不destroy |
| 完成后第4次STATUS/ISO，旧回调晚到 | lease/driver拒绝，不增加第4次SDK提交 |
| 重新封存坏归档 | 5份分别拒绝两轮、四轮、第三轮载荷、复用首轮/第二轮URB |
| 48序号模型 | 正常消费与4项拒绝通过，完整历史来自现有49..176消费记录 |
| 模型单元测试 | 6项通过，包括重新计算摘要后的缺失历史仍拒绝 |

最终19个原生进程全部exit0，由Python创建者直接wait；编译启用ASan/UBSan，运行stderr为空。链接Foundation/IOUSBHost/IOKit只为编译类型与接口；未创建真实SDK对象、打开USB或访问SD。二进制是单场景fixture，没有真实采集CLI。

开发r1因替换锚点数量不符，在编译前失败；r2编译成功，但normal第三次ISO未进入adapter，暴露driver transport中遗漏的`n>=2`限制，原生断言失败并wait。补齐为3后r3的19场景通过。随后补完整历史集合要求及重新封存URB归档反例，r4的19场景及6单元检查通过。四版材料全部保留，不追认失败；共3个编译作业和39个原生进程均完成创建者wait，其中1个原生失败、38个exit0。

## 尚未接入与下一项

下一项只补同一三轮候选的真实入口和证据链：绑定当前97原件、619及后续新增来源、完整49..176历史，建立新的固定48 scope/原生一次许可；接入三组失败owner快照、checked export双边校验/接受回执和独立收集器。完成来源闭包与必要拒绝验证后才有可审查的真实build。现有双轮entry/permit/controller不能与新driver直接混接，fixture回执不替代checked export或外层进程wait证明。

当前177..224未保留、未授权，145..176仍耗尽，remaining0；SD最后回收记录为已弹出，当前现场状态未经本轮确认。没有USB/SD/真实SDK/部署/新正式记录或保留操作。持续流、长期稳定、设备实际第三轮容量与窗口、物理来源、跨时钟对齐、quiet drain和旧失败根因均未新增实机结论。

## 封存索引

以下相对`private/analysis`，摘要为各SHA256SUMS的SHA256。

| 材料 | 摘要 |
| --- | --- |
| `A23-three-epoch-offline-review-20261023-r4` | `e62a7ad30d2d1b261f9d65c91ebc1a100d9cb883910cd094be040fc01dc55bed` |
| `A23-three-epoch-offline-review-20261023-r3` | `3a2c9c8bc80fdddc51eee7bb088dd337e9fe557448de0d5c430c8517c12d8b33` |

失败r1/r2与最终单元/语义复核、票据和文档快照见`A23-three-epoch-offline-closeout-20261023`。此前容量设计见[三轮范围审查](A23_THREE_EPOCH_SCOPE.md)。
