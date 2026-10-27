# 最终导出之后的故障检测边界（2026-10-26）

已在冻结[132件接收器](A23_LIVE132_TERMINAL_OFFLINE.md)中复现一个明确的末端缺口：最后一次live状态比较之后，接受回执写入和loop成功之间没有再次健康检查。此时已经进入provider/driver的故障，可以使loop仍报success，而稍后的entry getter报告stopped。finished后的loop tick又在调用target之前返回，因此该成功标志不会自行撤销。

本轮只做边界审查，没有修补接收器或产生新候选。旧662来源和接收器build保持，新增tools/audit_a23_postexport_boundary.py，研究来源总663。1次ASan/UBSan原生编译、8个原生诊断进程均创建者直接wait；8个临时模拟namespace，无真实SDK对象、USB/SD访问、新正式范围或授权。

## 源码中的切点

冻结build的generated/live_export.m在以下顺序执行：

```mermaid
flowchart LR
    A[导出payload] --> B[第二次完整export guard]
    B --> C[读取latest及final状态]
    C --> D[重读payload并比较快照]
    D --> E[after_postcheck切点]
    E --> F[写接受回执并封存]
    F --> G[after_receipt切点]
    G --> H[success和finished置true]
    H --> I[后续tick直接返回]
```

latest/final读取位于117行，after_postcheck位于121行，回执写入127行，after_receipt位于129行，success/finished赋值130行。源摘要为f3fa97ab4bb406dd98009410bd49ea64e5dad39a97985f18d545b3219d8311d1。行号只针对冻结build，不指向可变模板。

after_postcheck和after_receipt是已存在的fixture切点；正常编译时这些测试hook为空，但对应的检查、IO和赋值顺序仍在。loop.status只返回控制器字段，退出门只检查loop finished及verifier/worker归还，不读取SDK故障标志。entry.result会调用driver.result及guard，因而可能在成功赋值之后才首次把已到达的故障写成停止事件。

provider入口先原子锁存interest并保存消息，再把pin/外层通知排入owner queue。因此“已进入provider的通知、只剩pin排队”和“整个provider入口尚未执行”必须区分。前一种可被新的健康读取发现；后一种在入口执行前尚没有该锁存值。

## 服务窗口结束后的既有成本

以下来自上轮冻结r4的正常样本，只比较同一个RAW时钟域，不使用本轮带诊断copy的进程作性能比较：

| 窗口之后的完整检查 | 耗时 |
| --- | ---: |
| terminal_final | 463.069 ms |
| before_finalize | 456.214 ms |
| after_finalize | 449.774 ms |
| 导出前export_boundary | 451.397 ms |
| 导出后export_boundary | 460.379 ms |

五次检查合计2280.833ms，最后一次结束距服务窗口最后采样2307.841ms，之后仍要读payload和写接受回执。这些时间均未被250ms服务窗口覆盖，不能解释为连续服务或SDK drain证据。

## 诊断方法与结果

完整receiver生成代码、原SDK/entry/export消费者和132件scope均使用上轮冻结版本。只修改fixture注入hook、期望结果及诊断捕获，不修改exporter或放宽验收。诊断fixture另以摘要绑定，不冒充冻结receiver的原始fixture。

对于会返回success的场景，在同一个owner queue工作块内、loop.tick刚返回后，先读取控制器自身字段，并复制host为at-return。复制前不调用live entry/driver getter，避免探测先追加停止日志。之后仍执行原fixture的live getter，得到after-probe材料。两份材料分别交给原完整消费者和服务窗口消费者。

at-return只是诊断模型中的顺序复制；不是实际设备目录的原子快照。这里所有文件写入和注入都受同一模型队列安排，且相关worker已返回。复制会增加返回后的阻塞，不能用它推算真实SDK回调延迟或发生概率。

| 场景与注入点 | loop success | 返回前磁盘副本验收 | live探测后entry | 探测后磁盘验收 |
| --- | --- | --- | --- | --- |
| normal | true | 通过 | complete | 通过 |
| before_precheck直接interest | false | 无成功副本 | stopped | 拒绝 |
| after_payload直接interest | false | 无成功副本 | stopped | 拒绝 |
| after_postcheck直接interest | true | 通过 | stopped | 拒绝 |
| after_receipt直接interest | true | 通过 | stopped | 拒绝 |
| after_payload排队整个interest入口 | true | 通过；入口尚未执行 | stopped | 拒绝 |
| after_postcheck旧ISO回调 | true | 通过 | stopped | 拒绝 |
| after_postcheck改写模型来源 | true | 通过 | complete | 通过 |

全部8个诊断场景按预期完成，包含成功对照和拒绝对照；不是8次接收器都成功。

直接interest和旧ISO在成功赋值之前已经执行入口并设置故障标志，故不能把这两种矛盾解释成“成功之后才发生的新故障”。排队场景则有不同边界：注入把整个provider入口排在当前串行工作块之后；at-return明确queued=true、delivered=false，后续事件才记录delivered。该安排证明模型代码不能提前看到尚未执行的入口，不证明真实SDK一定以此方式调度。

晚到SDK故障的after-probe消费者拒绝原因是额外停止事件破坏原entry事件清单。它没有实时询问SDK，也没有追溯修改先前已经写出的接受回执。隔离保留下来的at-return历史副本仍自洽，仍能被验收。因此磁盘材料完整不能等同于当前会话仍健康，单独loop.status也不能替代当前entry状态。

改写来源场景只修改临时模型repository中的a23_scope_verifier.m，改写字节已单独保存。最后完整检查之后没有再检查该来源，SDK健康getter也不检查文件，所以两份历史材料都通过。现有消费者已声明current_disk_freshness_verified=false；该结果验证了声明的实际限制，不是来源已经被重新认证。

## 当前能支持的结论

- 原始模拟传输、SDK状态/载荷和导出记录可按各自已记录的切点验收；不认证生产者或历史真实性。
- 服务窗口只证明提供记录中的250ms本地健康检查完成点符合候选间隔；不覆盖之后约2.31秒的串行收尾。
- 在最后一次live比较之前已经可见的故障，原路径能够拒绝；本轮两个提前注入对照验证了这一点。
- 最后live比较之后已经锁存的故障，当前loop仍可能置success；finished后的短路不会继续调用target来修正它。
- 整个入口尚未执行的排队通知、最后一次文件检查之后的来源变化，以及未来事件都不能被当前历史回执排除。

这些是冻结软件在模型中的边界，不改变真实417..464三轮及已回收设备日志的历史结论。不能据此推断旧实测中实际发生了晚到通知，也不能认定原硬件失效的根因。

## 下一项最小修补合同

下一项应先离线修补“已进入故障标志仍置success”的确定性软件缺口，硬件入口继续关闭：

1. 回执写完之后、授予loop success之前，再显式采样entry/driver健康与最终快照一致性。不能用loop.status、终态控制器的旧passed或磁盘回执代替。
2. 对本轮排队反例，考虑一次明确的owner queue交回/续接，再进行最后采样。退出门须等待这个终结步骤，不能在其pending时因loop或operator-ack结束。一次续接只覆盖该队列在该切点之前的可见前缀，不称为SDK drain。
3. 已写出的payload/接受回执保持不可变；若最终采样失败，追加绑定这些摘要的失败/撤销事实，保持loop失败。新消费者必须检查新的终结证据，不能仅凭旧接受文件完整即升级为新合同成功。
4. 固定检验本轮的提前/晚到/排队故障及正常对照，不扩大通用模型。不用反复重开观察窗口或不断追加完整文件校验来追求“未来无事件”。

这仍不能闭合最后采样到写终结事实之间的所有竞态，不能认证文件的持续新鲜度或尚未执行的SDK入口。新证据必须明示其采样切点、队列前缀与历史性质；SDK drain、存储释放/复用、真实通知交付和持续流仍需独立问题与证明。当前没有硬件测试问题、计划或授权。

## 封存

审计：private/analysis/A23-postexport-boundary-20261026-r1，SHA256SUMS摘要e698272afb3860b91960f24e62d0237271e832a2f4becc826df8195e681c81b0。内含fixture绑定、编译/运行原始输出及wait记录、静态切点、8个临时模型消耗记录、返回前后两套材料和16次消费者结果。

最终663研究来源、旧662保持、未改actual417、九个正式namespace清单、票据及交接见private/analysis/A23-postexport-boundary-closeout-20261026。原132件接收器build仍为上轮r4，未修补、未重新构建；硬件入口关闭，465..512未正式保留/授权，remaining=0、acquisition_enabled=false。SD最后已安全弹出，设备日志不待回收，当前现场未刷新。
