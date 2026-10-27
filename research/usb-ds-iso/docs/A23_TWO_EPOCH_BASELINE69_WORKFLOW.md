# 69份基线与32序号一次流程模型（2026-10-19）

后续：[共享账本引擎与原生文件permit](A23_SHARED_SEQUENCE32_NATIVE_PERMIT.md)已完成临时命名空间/原生注入验证；生产fresh verifier与现场CLI未接通。以下保留独立模型阶段结果。

最新69份已保存原件已接入独立的只读预览；32序号保留、消费、进程声明和选择声明完成文件模型验证。23个场景、15份坏件、17项专项检查通过，搬移后从冻结来源独立重放一致，包括四组跨进程竞争。

本轮仅读取已封存文件，在 `/private/tmp` 创建可丢弃模型；没有读写SD、访问USB/SDK、启动接收器、构建固件、正式发行或保留81..112。真实账本仍只有49..64和65..80，两份记录及 `.lock` 字节保持。生产共享账本适配、生产permit和现场CLI仍待实现，预览固定remaining0且formal_issuance_available=false。

## 保存69份的独立采用

新增 `tools/a23_two_epoch_baseline69.py`，固定上次SDK入口收尾哈希、真实65收尾哈希与最新69快照manifest。逐份核对原件清单和字节、四项部署文件、空boot2.flag、device/recipe绑定、卡UUID、只读恢复、已弹出及严格布尔/整数；不能把旧63份或更早快照当成当前基线。

核对最新已保存recovery仍是2026-10-18 14:41:59的69份，真实65已回收/remaining0、device_log_pending=false、81尚未保留。核对旧63引用与真实65封存分析中的引用完全一致，再重算63→69差异：新增6份EXE3/primary/LCP1原件，仅logfile变化，其余62份保持，8份ERPT不变。失败修复owner及失败状态保持原哈希。

四个部署文件与已审阅包匹配，并不证明该包适合设备双轮。基线中的hardware_verified、physical_run_authenticated和根因声明继续false。这里采用的是保存材料，没有重新检查当前设备、卡或接线状态。

`tools/prepare_a23_two_epoch.py` 只有只读预览，不支持issue/acquire/reserve参数。它绑定351来源摘要、69清单摘要、先前文件检查构建及binary摘要、历史49/65两份保留和记录摘要，生成明确model_only的81..112材料。前一构建仍是文件检查程序；没有把它称为已具备采集模式。

## 原子32保留与失败保留

新增 `tools/a23_sequence32_model.py`。每个模型根目录代表一个独立假账本及单次调用胶囊，根目录必须是新建且规范的 `/private/tmp` 子目录。胶囊冻结原始位置、UUID、材料及历史摘要；副本可只读分析，但不允许在副本继续消费。正式目录没有写入实现。

一次排他锁下创建**一个**reservation.json，表示81..112全部32个序号。没有分别写两份16序号的中间状态。任何已存在、空或部分reservation都阻止整个区间重用；不会自动补写、释放、删除或恢复半成品。文件排他创建后先fsync空文件及父目录，再写完整内容、fsync和读回，使写入失败也保留占用。

issue在同一锁内先持久保留，再排他写issue.json。issue失败保留全部32；只有reserve没有issue的模型也不能再补发。历史49..64/65..80保持，历史若占到81..96或97..112任一半，都拒绝整个32区间。

这些竞争规则限定在同一个假账本根目录。不同测试根目录是彼此隔离的模型；它们不构成生产全局分配器。生产流程未来必须使用同一受控共享命名空间，验证无关历史、正式记录和32序号schema兼容，不能直接复制本模型到真实账本。

## 消费与两次声明

消费在持久consume-attempt后排他写consumed.json，remaining变为0，receiver_launched=false。原issue保留为不可变历史，不能仅凭其remaining1判断仍可用；任何后续消费均受永久attempt门禁阻止。本模块没有runner、Popen接收器或硬件入口。

process-attempt先持久创建，再保存context并执行已有环境策略检查，process-claim绑定消费回执、context原始字节、pid及材料摘要。即使context错误或保存失败，这次尝试也不会续命。selection-attempt同样一次，要求context与进程声明完全一致，并核验唯一、不同的device/interface ID和HS速度3，再写sdk-claim。

所有模型context都是合成字节，未核验真实pid或进程来源。上述文件不会转化为生产 `A23TwoEpochEntryPermit`。与原生入口的生产permit、正式消费格式和选择时重新核验仍需独立实现；不能把文件模型成功视为可发USB请求。

## 独立分析和测试

`tools/analyze_a23_sequence32.py` 必须提供预览材料。它核对模型材料/历史与预览一致、严格schema/数值/布尔、材料→32保留→发行→消费→context→进程→选择的摘要链、三份永久attempt及完整文件清单。复制归档可以只读分析，写入仍要求胶囊原位置。

结论为supplied_model_chain_complete；formal_issuance_available、process_origin_authenticated、hardware_entry_enabled、hardware_verified、receiver_launched均false。hash与模型文件一致性不认证外部预览来源、物理同次、生产许可或全局分配。

23场景中正常及四种竞争模型完整，另18个待定/故障模型拒绝：仅保留/仅发行/仅消费、错误context/布尔pid、选择时context变更、错误身份/布尔速度、空/部分保留、发行/消费/context/声明保存失败及永久attempt冲突。所有场景都验证保留后重试不改变文件；完整链再次消费或声明也不改变字节。

四组竞争分别同时启动两个独立Python进程争夺issue、consume、process和selection，每组只一个成功。使用真实排他文件创建和flock，未模拟锁的结果。并发失败可来自锁竞争或已存在标记，不依赖两者的具体先后。

15份坏件分别覆盖拆为16、布尔计数、旧基线、来源/历史scope、消费remaining、pid/身份/context摘要、硬件声明、重复JSON键、未知文件、缺attempt、部分issue及lock内容变化。scope修改时同步重算胶囊输入摘要，确保进入材料/历史匹配检查；关键拒绝原因逐项断言。另独立验证7种69基线语义错误、正式路径拒绝、软链拒绝、模型副本拒绝，以及两半区间重叠。

17项专项检查通过。本阶段是Python文件/并发测试，未将其称为新的ASan/UBSan原生测试；旧345来源和先前原生结果保持。搬移351来源及69原件后，新进程不读取原checkout或/Volumes，重建69 manifest并匹配固定哈希，提取冻结纯函数重放23场景和15坏件，五份完整结果一致；四组跨进程竞争再次各一成功。移动检查脚本初稿将清理时的dir_fd相对打开解析到了原cwd，误报原目录访问；改在移动目录运行后重放通过，原始错误与脚本保留，模型来源和结果未因此修改。

- 审查：`private/analysis/A23-workflow32-review-20261019-r1`。
- 验证：`private/analysis/A23-workflow32-validation-20261019-r1`。
- 收尾：`private/analysis/A23-workflow32-closeout-20261019`。

## 续接

345旧来源不变，新增6项共351；23保护项、实际49/65记录、真实保留文件和失败修复owner/状态保持。65仍已消费并回收，remaining0；81..112只在隔离模型中出现，实际未保留。沿用2026-10-18关机/弹卡记录，本轮没有现场核验。

下一项离线接入生产共享账本/预览/发行/消费及原生permit绑定，重新审查历史排除边界、跨作业竞争、失效材料和最终收集格式；之后才考虑实现现场CLI与收尾进程策略。当前生产发行仍不可用。真实映射、设备双轮/trace/URB代际、包复用及持续稳定性未验证；继续优先采用文件副本和注入模型替代现场操作。
