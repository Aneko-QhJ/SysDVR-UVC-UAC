# A23 独立 worker 失败与材料完整性模型（2026-10-20）

后续：[完整隔离driver的worker故障与收集边界](A23_DRIVER_WORKER_FAILURE_MODEL.md)将15种安排接入Capture/BeginCommit/post-guard，87场景和60测试通过；保留3个driver无法感知worker失败的反例，收集器拒绝完成。以下保留原阶段。

本阶段在现有纯 C 版本时钟候选上完成13个指定 pthread 安排。driver、Objective-C 桥、C helper 和此前479个来源保持原字节；新增4个来源，总计483。结果限定于独立离线模型，尚未将本阶段 worker 故障接入完整 driver。

| 指定安排 | 观察结果 | 完成资格 |
| --- | --- | --- |
| normal-readonly | 同 store、同版本，两次采样达标，worker 正常返回 | 允许此离线模型声明 |
| normal-finish | 正常发布推进2→4；跨版本采样被拒绝 | 拒绝 |
| error-before-begin / exit-before-begin | 返回7 / pthread_exit 9；时钟采样仍有效 | worker 失败，拒绝 |
| unfinished-return / unfinished-exit | 获得票据3后返回7 / pthread_exit 9；store 保持奇数 | Busy，拒绝 |
| abort-error | worker 显式 Abort 后返回7，版本变4 | worker 失败且旧版本失效，拒绝 |
| invalid-finish | 无效 profile Finish 返回 Profile，store 毒化 | 拒绝 |
| wrong-ticket | Finish 错误票据返回 Changed；原票据未释放 | Busy，拒绝 |
| exhausted-begin | 测试注入最大偶数版本，Begin 返回 Exhausted | 毒化且不回绕，拒绝 |
| last-finish-exhausted | 最后一次合法 Finish 到最大偶数，再次 Begin 耗尽 | 毒化且不回绕，拒绝 |
| replacement-store | 两个仍存活 store 的 profile、incarnation、版本声明相同 | store 身份不同，拒绝 |
| explicit-abort-after-join | worker 结束并 join 后，由 fixture 显式 Abort | 版本2→4，旧样本拒绝 |

每个场景创建并 join 一个真实 pthread，共13线程；场景顺序执行。共享非原子诊断仅在 join 后读取。未完成写入不触发自动恢复或重试。显式 Abort 只演示调用后的版本效果，不构成恢复授权或自动恢复机制。对象替换测试保留两个 store 的生命周期，不证明释放后使用或回收安全。未测试 pthread_cancel、进程崩溃、失联或永不退出的 worker；父进程以30秒超时约束模型进程。

新增的纯字节消费者接收五个成员：worker.json、clock.json、manifest.json、SHA256SUMS、COMMITTED。它核对精确清单、摘要、schema/case 绑定、严格类型和各指定场景的完整预期字段。材料由外层从 native stdout 派生，消费者不打开文件。`evidence_complete`、`worker_success`、`clock_eligible`、`completion_eligible` 分别表达材料完整、worker 成功、时钟成立、两者共同成立；错误场景可作为完整失败证据保存，不能成为完成声明。校验只适用于这13种注入模型，不是通用运行收集器，也不认证来源。

优化与 UBSan 两版输出一致，搬移483个来源后再次编译并一致。新增20、此前并发20和纯 C20项测试，共60项无跳过通过。299次逐字段修改后重算全部摘要的材料被拒绝；另有65次成员缺失、5次截断、额外成员、跨场景、BOOL/整数混用及非法JSON拒绝测试。消费者在 open/io.open 均被阻断时仍验证全部13场景；外层收集与封存检查正常读文件。

原位置及搬移共4份独立 C fixture、4个 compiler jobs、4次有效进程及4次未知参数拒绝、52线程。执行前核对链接库与符号；Python 搬移回放阻止原 checkout 和 /Volumes 文件打开，未向 clang/原生子进程继承该 Python hook，不宣称 OS 能力隔离。三种只读 CLI 返回0/2/2；只读检查不执行模型。

证据目录：

- review：`private/analysis/A23-worker-failure-model-review-20261020-r1`
- validation：`private/analysis/A23-worker-failure-model-validation-20261020-r1`
- closeout：`private/analysis/A23-worker-failure-model-closeout-20261020`
- review SHA256SUMS：`9b064e431e7442d0a05a29dcd3e00074a5d13340b76efcdcbf5753302e6ea42e`

入口：`tools/audit_a23_worker_failure_model.py --check <review> --expected-sha256 <pin>`；缺少/错误 pin 拒绝。新增代码在 `tests/a23_worker_failure_fixture.c`、`tools/a23_worker_failure_materials.py` 与 `tests/test_a23_worker_failure_model.py`。

23项保护文件、实际49/65账本和失败修复 owner/state 保持；65已回收、remaining0，81..112未保留。USB/SD/真实 SDK/context 刷新/正式发行与保留均0，生产采集关闭。此前完整 driver 的72场景仅作为旧材料回归验证，本轮没有重新构建或执行完整 driver。

下一步：离线将 worker 未完成写入、异常退出、耗尽及对象替换安排接入完整 driver 的 Capture/BeginCommit/post-guard 窗口，明确 incomplete 材料在外层收集时的终止行为。仍需独立研究真实时钟域映射、SDK runtime、quiet/drain 与生产 permit；本阶段不解决这些现场缺口。

前序：[提交期间指定并发与缓存诊断关联](A23_COMMIT_CONCURRENCY_MODEL.md)。
