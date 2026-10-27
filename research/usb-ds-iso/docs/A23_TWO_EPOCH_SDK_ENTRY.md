# 两轮SDK等待入口、构建绑定与最终检查点（2026-10-19）

后续：[最新69基线与32序号一次流程模型](A23_TWO_EPOCH_BASELINE69_WORKFLOW.md)已完成只读采用和隔离文件验证；生产共享账本及permit尚未接入。以下保留入口阶段结果。

独立入口库 `A23TwoEpochEntry` 已将进程环境、两次许可声明、被动等待、SDK准备/启动及最终检查点串联；专用构建生成文件检查程序，并编译全部休眠原生实现。33个原生注入场景、18份坏归档及13项专项检查通过ASan/UBSan，搬移后两个程序重新编译、完整/拒绝分类一致。

本轮用假等待operations、假SDK operations及文件副本验证。文件检查程序仅提供describe、check-build、inspect-context，任何acquire参数均返回2；**生产许可、正式消费流程和现场执行模式尚未实现**。没有启动真实等待器、创建SDK客户端、发USB请求、访问SD、构建固件、部署、发行或保留序号。

## 入口与先后顺序

新增 `host/a23_two_epoch_entry.h/.m`，使用已冻结的两轮SDK驱动、资源层、执行环境检查器及被动等待适配器。旧336份来源不修改，新增9份后共345。

构造时冻结context和binding副本、校验32序号范围及三个摘要格式，排他创建entry journal。begin只能尝试一次：

1. 排他保存context原始字节及摘要，验证既有环境策略、binary摘要、采样期限；不能从未来采样。默认策略要求OS build 26A434、指定IOUSBHost UUID和sandbox_check结果0。
2. 外部permit持久消费进程许可后返回YES，再排他保存process-claim，绑定context摘要、pid、binary/build/authorization receipt摘要和81..112范围。保存及journal通过后才能创建等待器。
3. 被动适配器先注册再排空初始iterator；已有设备、歧义到达、120s期限、退出或通知均停止。WAITING后选择唯一HS接口，take时再检查身份，外部permit消费选择许可后排他保存sdk-claim，才能调用provider。
4. provider独立retain借用service、安装通知、准备四块存储；随后关闭被动等待器。关闭失败或release失败即停止，不开始STATUS/ISO/BURST，保留SDK资源及失败引用。
5. 构造驱动与prepared事件处于本轮tick；下一轮tick再次检查退出/断连及等待器关闭状态，才开始驱动。之后使用上一阶段的逐轮保存、原生入口时钟、两轮上限及250ms观察窗口。

入口转发等待operations时保留原context，journal与时钟使用协调器context，避免覆盖context后错误调用。tick禁止重入，准备与启动分开，许可回调中途requestExit也立即拦截。退出与断连不会转成自动重试。

许可接口没有生产默认实现。其契约要求调用者重新核验当前/冻结构建、最新卡基线、正式消费回执并持久烧掉对应机会。模型permit只计数和检查顺序，不创建正式消费记录；模型context、pid、摘要及序号均为注入材料，不能把claim文件当成真实发行或物理来源认证。

## 最终检查点与保留

`finalizeOnce` 只允许在驱动完成观察或入口停止后尝试一次；待定观察不消费机会。先保存驱动的单次SDK回执，再记录final_checkpoint，排他创建 `entry-final`，保存entry/driver/receipt-status原始JSON字节，写manifest/COMMITTED、fsync并读回。碰撞/部分失败不覆盖或重试。

`entry-current.json` 和 `entry-final-status.json` 表示调用方最后一次读取的当前状态；测试fixture负责导出这些文件及SDK层result/receipt-status。`finalStatus` 比较当前结果与已提交entry快照，迟到回调会使两层回执都stale/saved=false。失败检查点即使保存成功也不代表完整；独立分析器仍拒绝stopped或不匹配链。

该方法是检查点，没有自动exit、kill、active destroy或释放SDK映射；资源保留至进程结束。250ms窗口及磁盘提交不证明回调排空或未来稳定。真正现场程序如何处理未决I/O、最后导出与进程退出，仍须随生产入口审查。

## 专用构建与文件模式

`tools/build_a23_two_epoch_entry.py` 生成冻结345来源、静态嵌入metadata字节的header、构建manifest、binary摘要回执、编译命令及文件模式回执，并持久封存。只构建主机程序，不构建设备包。

`entry-inspector --check-build PATH` 核对自身位置、嵌入metadata原始字节、派生header、每份冻结来源和自身binary摘要回执；拒绝源文件、manifest、header篡改以及重复JSON键的binary回执。Python verify_build还核对当前来源、完整封存和确切文件清单。摘要一致性不是二进制来源认证或签名。

`--inspect-context` 仅观测本进程身份、OS、框架UUID、沙箱及自身binary，stdout返回policy_pass。本轮在默认沙箱观察到sandbox_query_result=1、policy_pass=false；结果如实保留，没有提权或改变策略。它不测试USB打开权限。

程序包含休眠原生SDK/IOKit代码，但没有生产permit实例或capture入口；describe、check-build、inspect-context均不创建通知端口或真实SDK对象。acquire及无效参数返回2。

## 联合分析与验证

`tools/analyze_a23_two_epoch_entry.py` 同时核验context原始字节摘要、严格类型、进程/SDK claim、WAITING前无设备、唯一选择与handoff、关闭→准备→启动顺序、最终检查点当前性，以及上一阶段完整SDK归档。保留SDK观测来源及注入标记。

结论为 `supplied_entry_chain_complete`；production_permit_authenticated、process_origin_authenticated、physical_run_authenticated、hardware_verified、hardware_entry_enabled和callback_drain_verified均false。外部build/授权摘要在模型中是显式占位，分析器仅核对供应材料间的一致性，不验证真实发行或环境来源。正式许可还须调用完整构建/基线/消费核验，不能仅凭此分析结果启动测试。

33场景中，正常与排队25ms两个模型完整，另外31个拒绝，其中观察未满者保持待定。覆盖环境五种错误、进程/选择许可拒绝及其回调中途退出、claim碰撞、已有/歧义设备、等待超时/退出、准备后退出/断连、等待器release失败、provider失败/部分分配/通知、模拟资源错接、payload/控制期限、运行中退出、观察/回执/最终检查点故障及最后检查点后的迟到回调。正常模型只open一次、retain一次、四存储、ISO/BURST各两次；活跃SDK资源destroy0，限制保持。

18份坏归档在重算检查点哈希和相关绑定后，分别命中沙箱、布尔pid、context摘要、claim binding/pid、选择身份、等待顺序/初始已有设备、release失败、启动顺序、序号范围、过期/不一致检查点、硬件/释放声明、缺失提交、重复JSON键和部分journal。13项检查逐项断言预期拒绝原因；另验证claim碰撞不覆盖原文件及4种构建篡改拒绝。

初稿有两类验证错误，旧材料保留：驱动构造时就写prepared，分析器最初误要求其在入口start之后；坏归档生成器先因清单未排序、再因无修改也重编码context而提前拒绝。最终版保留未修改context的原始字节、排序清单，并逐项核对具体拒绝原因。旧r1/r2审查不作为最终语义验证依据。

正式Python搬移重放不读取原checkout或/Volumes；从冻结函数重建文件检查程序和ASan/UBSan fixture，复现33场景、18坏件及两份完整链。比较排除session UUID和观察绝对时钟，仍分别核验≥250ms；context摘要及状态/计数继续比较。

- 最终审查：`private/analysis/A23-sdk-entry-review-20261019-r3`。
- 验证：`private/analysis/A23-sdk-entry-validation-20261019-r1`。
- 初稿材料：`private/analysis/A23-sdk-entry-draft-materials-20261019`。
- 收尾：`private/analysis/A23-sdk-entry-closeout-20261019`。

## 续接

336旧来源、23保护项、旧49/65记录和失败修复owner/状态保持。65仍已回收、remaining0；81..112未保留。沿用上次设备关机及SD于2026-10-18 14:41:59+08弹出的记录，本轮未核验当前现场状态。

下一项离线实现/审查最新69基线、原子32序号预览/保留/消费及生产permit绑定，再接真正的现场CLI与收尾导出。正式流程当前不可用。真实SDK映射、设备双轮、完整trace/URB代际、现有设备包复用及连续稳定性仍未验证。继续优先采用文件副本、编译及注入模型；不据此新增现场操作。
