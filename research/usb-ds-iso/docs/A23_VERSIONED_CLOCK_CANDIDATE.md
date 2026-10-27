# A23 参与式版本时钟快照候选（2026-10-20）

后续：[版本快照接入主机端隔离模型](A23_VERSIONED_DRIVER_MODEL.md)完成59场景与61测试；C候选未改，模型引入store owner与提交票据，生产集成仍false。以下保留独立C阶段。

接续[完整driver故障回放](A23_DRIVER_FAULT_MODEL.md)的两个ABA反例，本阶段新增独立C候选，以版本号绑定profile/ticks样本。43场景在优化、UBSan和467来源搬移重建中一致；新增20、旧driver故障20及旧算术18项，共58测试无跳过通过。

候选尚未接入Objective-C桥或完整driver。旧driver的ABA反例继续保留；此次只验证所有写入方遵守契约时的C模型，`versioned_driver_integrated=false`、`writer_contract_enforced=false`。

## 契约与实现

`host/a23_versioned_clock_candidate.h/.c` 定义store、profile/ticks样本和Begin/Finish/Abort接口。store在发布前初始化一次，incarnation为非零调用方声明；调用者必须维持对象生命周期，禁止并发重新初始化、复用身份或重置版本。

- generation从2开始；偶数表示稳定，Begin以一次CAS获得奇数写票据。票据只属于该writer，不得转交其他writer、伪造或并发完成。
- Finish发布profile后推进到下一个偶数；Abort及相同profile的no-op发布也推进版本。已Begin却提交无效profile会毒化store，后续采样拒绝。
- Profile字段、版本及poison均采用C11顺序一致原子操作。ReadProfile不调用ticks reader；Capture在读取profile与ticks之后要求版本未变且未poison。接口没有显式自旋或自动重试，不声称底层原子实现无锁。
- Capture只调用一次注入reader；失败清空样本。Evaluate要求同一store地址、incarnation及同一非零偶数版本，再复用既有精确算术。反向、溢出和分数最短等待规则保持。
- 最后一个稳定偶数版本为UINT64_MAX-1；后续Begin毒化store并返回Exhausted，不回绕。此边界由fixture直接设置计数器模拟，不是生产版本重置入口。

所有profile写入必须经这些接口参与，包括变化后恢复。C结构可见，调用者仍能绕过接口；契约与标签不认证写入方、对象身份唯一性或真实时钟来源。ticks仍由外部注入reader提供，没有实际时钟API。

## 结果及能力边界

| 场景 | 结果 |
| --- | --- |
| Capture起点/终点reader内部ABA | 版本2变6，拒绝该Capture |
| 两次Capture之间ABA，最终profile恢复 | 两个Capture各自成功，Evaluate因版本2/6不同拒绝 |
| 两个对应ABA的pthread场景 | 同样拒绝；是指定交错，不是全部线程调度证明 |
| 无变化发布或Abort | 版本推进，旧起点与新终点不能配对 |
| 写入未完成、嵌套writer或指定线程争用 | Busy/Changed，reader不自动重试 |
| profile非法、reader失败、空指针、损坏版本、错票据/重放票据 | 拒绝并按接口规则清空输出或保留原writer资格 |
| store对象或incarnation不同 | 端点不能配对 |
| 2/3比例差一个tick | ceil报告250ms，但minimum仍false；精确等号才true |
| 非参与写入直接改字段后恢复 | 两个负对照仍通过，明确展示无法强制契约 |
| 结束Capture后再发布新profile | 历史样本仍可评价；此接口不撤销过去样本，也不授予当前driver提交资格 |

5个参与式ABA场景拒绝，2个绕过版本的ABA负对照通过。tick0在算术上允许，未来driver桥仍须保留生命周期起始0的独立拒绝规则。preflight只读profile、原始tick来源和写入契约仍不能构成现场quiet证明。

新候选使用原子字段以避免合规调用间普通C字段的数据竞争；只执行了3种指定pthread安排。未运行TSan，未证明所有交错、内存回收或恶意票据安全，`all_thread_interleavings_verified=false`。

## 封存与重现

review：`private/analysis/A23-versioned-clock-candidate-review-20261020-r1`，481成员，摘要 `5092cf770ca73f8df1f72379b7072ca6cbcefd987587b11ec7f27d76cc2bad9e`。

验证：`private/analysis/A23-versioned-clock-candidate-validation-20261020-r1`。收口：`private/analysis/A23-versioned-clock-candidate-closeout-20261020`。

原位置及搬移合计4份独立C fixture、4个compiler jobs、4次有效fixture进程和4次无参数之外的未知模式拒绝，合计创建12个fixture线程。编译使用-Werror及UBSan，执行前检查链接库与符号，仅依赖系统运行库；没有Foundation、driver或SDK模型链接/执行。

正确/错误/缺失pin的只读CLI返回0/2/2，不执行原生程序。搬移回放的Python审计钩子记录原checkout与/Volumes打开0；编译器和原生子进程不继承钩子，其命令使用搬移来源。不是OS能力隔离证明。

原462来源、旧driver/桥/fixture、23保护项、真实49/65、账本及失败修复owner保持；仅新增5份候选/fixture/audit/测试来源。65已回收、remaining0，81..112未保留或发行。USB/SD/真实SDK对象/实际context刷新/设备包改动均0，生产采集关闭。

下一步离线准备拥有store生命周期的Objective-C桥，把所有数字mock profile写入接入协议，再在隔离driver副本中重放起止ABA及既有故障。必须另行定义结束采样后到事件append/post-guard的版本检查，以及sidecar如何表达版本/身份；真实clock来源、域映射、现场quiet/drain和生产permit仍未认证。
