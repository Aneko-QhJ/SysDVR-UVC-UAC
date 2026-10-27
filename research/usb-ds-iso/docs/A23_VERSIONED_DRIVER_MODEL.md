# A23 版本快照接入主机端隔离模型（2026-10-20）

后续：[指定并发与缓存诊断关联](A23_COMMIT_CONCURRENCY_MODEL.md)在driver/桥/C原字节保持下完成72场景与61测试；加入13种worker安排和字节消费关联，不认证全部交错或真实来源。以下保留原阶段。

接续[纯C版本快照候选](A23_VERSIONED_CLOCK_CANDIDATE.md)，本阶段把同一C实现接入现有macOS Objective-C driver的隔离副本。新增适配层负责对象/store生命周期、协议转接和提交票据；没有改写项目语言或改动Switch固件。

59场景在优化、UBSan和474来源搬移重建中一致；新增21、旧C候选20及旧driver故障20项，共61测试无跳过通过。结果仅适用于参与协议的注入模型，生产集成仍false。

## C候选与适配边界

`a23_versioned_clock_candidate.h/.c` 与父阶段逐字节相同。新增 `a23_versioned_driver_bridge.h/.m` 由对象持有内嵌store，数字mock的n/d/domain/instance setter全部转经C Begin/Finish。无效的已开始提交会毒化store；提交票据被占用时发布返回Busy，字段没有改变。ticks、计数器和步长在数字mock中使用原子字段。

driver新增独立强引用固定clock/store生命周期，采样绑定对象地址、store、声明incarnation和版本。bridge preflight不读ticks；base adapter没有raw reader时Capture失败，错误输出清空。fixture验证base adapter可随最后一个强引用释放；这不证明全部资源回收或恶意对象安全。

生成副本修改构造、quiet起止、guard与提交流程。deadline、emit/stop及receipt/result部分逐字节保持。guard明确新增对象绑定与live generation检查；原来的整段emit/stop/guard已不再整体相同。完整差异位于review的 `work/driver-versioned.diff`，候选摘要 `ed7166c37687df4349ade858bd72d5bb1ae8ea608e1372f2d335663a9ae3e89c`。原driver源码仍冻结未改。

## 从结束采样到提交

1. 精确minimum达标后，以结束样本申请C写票据，要求ticket对应样本版本的下一个奇数；采样后发生过变化就拒绝。
2. 持票据期间append observation_complete，执行post-guard，再设置settled。参与协议的其他profile发布只能返回Busy；这属于阻止写入，不是容忍发生过的ABA。
3. 通过最初固定的owner释放票据到下一偶数版本，记录expected generation，再运行guard。append失败、旧callback或clock被替换也释放原owner的票据。
4. 释放后的新版本变化由后续guard撤销完成资格；保存过的receipt通过原有结果比较变stale。历史quiet_end保留作诊断，不代表持续有效。

票据占用期间的方法归同一串行driver队列；所有写入方仍必须遵守C协议。此门控不认证真实时钟、阻止绕过接口的字段写入，或让receipt落盘与未来所有变更成为一个原子操作。

## 回放结果

原46个callback/deadline/profile场景仍覆盖，其中原先完整driver会接受的start/end ABA现在被拒绝。另加13个场景，共59项：正常、两次采样间ABA、Capture返回后ABA、append期间ABA/可见发布尝试、append期间callback/clock替换、journal失败、receipt后ABA、clock替换、起始0、分数short→equal及非参与式ABA负对照。

- 起止ABA以及结束Capture之后、拿票据之前的ABA均不能settle。
- append期间的两次ABA发布尝试均Busy且成功写入0；可见发布同样被阻止。事件在奇数版本3下append，正常释放后为4。
- append失败或post-guard拒绝不settle，票据释放。模型注入clock替换后也释放原owner；不会留下占用票据。
- receipt保存后发布ABA使版本4变8，guard终止并令receipt stale/saved=false。
- 2/3比例差1 tick仍等待，再加1 tick完成；24个arrival/poll deadline边界、排队25ms按原arrival判断、abort及晚callback保留存储的行为保持。
- 直接改字段后恢复的非参与式ABA仍通过，`commit_gate_bypass_writes_detected=false`，不声称强制所有写入方参与。

`version-profile.json` 记录构造/起止/append/释放/预期/当前版本、Busy及成功计数和对象绑定声明；严格限制字段及整数/布尔类型，关联quiet事件、最终状态和receipt。对象地址不写入sidecar。原事件及receipt schema保持；sidecar仍是fixture材料，不认证底层来源。

## 验证与封存

首次启动存在renderer的pin占位符导入错误，构建前修正，原日志保留。r1原生进程完成58场景，但严格sidecar校验拒绝整数1的object_bound；r2只显式转换BOOL，58场景两版通过。r3补入持票据时clock替换场景，并把Begin/End固定到原owner，59场景通过。r1/r2/r3及搬移共7份模型可执行文件、21个compiler jobs、7次有效模型进程和6次无参数拒绝入口；r1失败发生在审计，原生进程退出0。

每版执行前检查otool/nm，仅链接Foundation及系统运行库。真实SDK factory、Mach clock、实际context和生产broker实现继续排除。搬移回放Python审计钩子记录原checkout与/Volumes打开0，编译器和原生子进程不继承钩子，其命令使用搬移输入。三种只读CLI返回0/2/2，不执行模型。这不是OS能力隔离或全部线程交错证明。

review：`private/analysis/A23-versioned-driver-model-review-20261020-r3`，2559成员，摘要 `47a17bf2b9a9b31eb62b3cb59f8a6b9d68e1cbf581da0eb345dd4eadb9888ef0`。

验证：`private/analysis/A23-versioned-driver-model-validation-20261020-r1`。收口：`private/analysis/A23-versioned-driver-model-closeout-20261020`。

原467来源、C候选、旧driver/桥、23保护项、真实49/65、账本及失败修复owner保持；只新增7份主机端桥、fixture、renderer/audit/测试来源。65已回收、remaining0；81..112未正式保留或发行。USB/SD/真实SDK对象/实际context刷新/设备包改动均0，生产采集关闭。

下一步继续离线加入持票据期间的指定并发profile发布与callback交错，增强sidecar全部诊断字段及receipt失效关联。真实clock来源、owner/driver域映射、现场quiet/drain与生产permit仍未认证。
