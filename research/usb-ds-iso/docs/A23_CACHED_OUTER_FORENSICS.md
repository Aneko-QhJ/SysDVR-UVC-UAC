# A23 缓存外层取证与完整文件清单边界（2026-10-20）

后续：[原生精确等待与显式时钟域候选](A23_NATIVE_CLOCK_CANDIDATE.md)已完成2333向量及52测试；独立C候选尚未接入冻结driver，真实时钟和现场等待仍未认证。以下保留原阶段。

接续[静态收集关联](A23_CACHED_COLLECTION_LINKS.md)，本阶段从封存的历史first capture恢复4份外层原字节，联合已有92份raw缓存，精确覆盖同一SHA256SUMS的96个成员。新增分类是 `consistent_cached_outer_forensics_declarations_subset`；文件字节覆盖完整，不代表运行语义、worker来源或现场结果已认证。

## 发现与处理

外层四份材料为 `FORENSIC_ATTEMPT`、`analysis.json`、`capture.json` 和 `job.json`。恢复时验证原first capture封存摘要，要求其清单与现有缓存携带的origin清单逐字节一致；新消费者再核对96成员并集、所有摘要、COMMITTED、外层contract以及job原字节副本，拒绝遗漏或额外成员。

capture的历史目录声明含15项，其中 `journal/envelope/supervision/scratch` 是不含文件的历史空目录。后续detached缓存的contract另含人工创建的 `empty`，并不含该scratch。校验分别保留两份声明；文件清单只封存文件，不认证空目录来源或原始文件系统身份。

保存的source/marker/journal stat元组被检查为严格整数、对应目录/普通文件类型、marker字节长度及不同组件身份，stable必须为true且无skipped记录。inode整体偏移仍可满足内部一致性，`historical_stat_identity_authenticated=false`；没有执行stat查询，也没有将stat时间与driver/owner时钟相减。

历史bootstrap worker声明PID为84237，被监督的模型child PID为81936，两者承担不同角色。本层不将两者强行相等。worker PID变化、或明确改为静态bootstrap且删除退出声明，可保持内部一致；`bootstrap_worker_exit_authenticated=false`。

旧bootstrap schema只检查退出码为-255..255的整数，`derive` 的完整性结论不使用退出码。本层成功profile额外要求观察退出声明的returncode严格为整数0；退出7的重算封存模型会被拒绝。此处是源代码规则与离线反例，不是重新运行历史worker或旧完整分析器的结论，冻结旧代码未修改。

保存的bootstrap/journal摘要与已有子集关联：7个阶段、attempt摘要、journal/inner封存、成功声明及权限位。保存的 `complete_injected_model_chain=true` 仅记录为声明；消费者的完整链、真实SDK、实际时限、进程来源、原子快照、目录身份和生产permit认证仍false。

## 验证

47场景：正常、stat inode偏移、worker PID偏移、静态bootstrap共4种声明一致；43种坏件拒绝。其中10种范围/字节错误由outer_scope拒绝，32种语义坏件在完整文件字节覆盖和旧子集通过后被拒绝，1种receipt坏件由旧子集拒绝。

覆盖外部pin/COMMITTED/成员/复制job/标记/权限/大小边界、capture schema/构建引用/重复字段、raw清单/目录、stat类型/模式/大小/稳定性/别名、worker模式/PID/退出码/job摘要，以及保存摘要的阶段/attempt/权限/错误和完整链声明。

新增18项测试，旧静态收集17项及旧时钟16项，共51项无跳过通过。437份来源搬移后47场景结果逐字节一致；正确、错误和缺失外部pin的CLI分别返回0、2、2。纯消费者文件打开0；搬移主重放对原checkout和 `/Volumes` 的文件打开观测为0。CLI子进程不继承主进程的审计钩子，不能据此声称操作系统能力隔离。

## 封存

- 新审查：`private/analysis/A23-outer-forensics-review-20261020-r1`，2361清单成员，摘要 `e8e1991733d7ff9dcea4328666133f14ccb8892c7e474149d58903f5a11c85b4`。
- 验证：`private/analysis/A23-outer-forensics-validation-20261020-r1`，含测试、搬移结果/脚本、正常观察、旧规则证据及最终化脚本。
- 收口：`private/analysis/A23-outer-forensics-closeout-20261020`，含票据/文档前后快照、437来源、23保护项和真实账本摘要。
- 外层原字节：`private/analysis/A23-window-review-20261019-r3/models/normal/first`，96成员，摘要 `e915949e41941b5bbb909468a8ac4148c93f25c9fa1cdac7c03abf40794f581c`。
- 父收口：`private/analysis/A23-collection-links-closeout-20261020`，摘要 `d43d35caa5b255718b59df7954eb715d7e6c2c2c77ced19d246cb3161a406efa`。

原434来源保持，仅增加消费者、audit和测试三份。真实49/65、原账本、失败修复owner、保护票据及设备端代码不变。65已回收、remaining0，81..112未正式保留，生产采集关闭。本轮USB/SD/真实SDK/原生执行/context刷新/发行/保留均0。

## 后续

96成员的文件字节范围已补齐，后续不再把未读外层文件列为本scope的缺口。仍缺少的是运行来源、真实时钟/现场deadline/quiet/drain、live source新鲜度、原子读取和操作系统能力隔离等独立证据；窗口recheck/final-observation属于另一个外层archive，不包含在本first-capture的96成员中。

下一步可离线准备原生最小等待的精确比较及显式时钟域候选，复现2/3 timebase的ceil反例，验证整数/溢出和域边界；候选与冻结旧构建分离，不直接部署或开启采集。
