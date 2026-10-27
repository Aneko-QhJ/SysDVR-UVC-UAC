# 120件基线的lstat固定三轮候选（2026-10-25）

独立候选已编译、离线接线及环境核验通过，尚未实测。只将完整校验目录遍历中的文件类型查询改为lstat，绑定最近120件原件、完整49..368消费历史与七个旧namespace；拟新范围369..416，一次最多三轮、每轮128项，失败即停、不重试。新授权、actual record、正式namespace与许可消费均未创建，remaining0。

## 变更范围与绑定

新增4份来源，总644，原640逐字节保持：build_a23_live120_lstat.py、a23_live120_lstat_workflow.py、audit_a23_live120_lstat.py和test_a23_live120_lstat.py。旧112入口及其已消费321..368不改写。新scope为A23-live120-lstat-shared48-scope-1，旧scope和旧消费者拒绝混用。

lstat仅用于files()节点类型，错误或非普通文件/目录拒绝；原目录枚举、路径canonical、NOFOLLOW/NONBLOCK只读打开、fstat、大小/EOF/关闭、内容哈希、manifest和每轮完整检查保留。没有缓存现场内容或跨轮新鲜度。既有的非原子目录快照、瞬时变化观察范围仍存在，不声称所有并发交错等价。

新基线为private/card-cycles/20261025-live112-short128-first-read：120原件、只读/部署匹配/哈希/弹出回执通过。它是最后已回收的档案，不代表本次新增开机前重新读卡。history补入已成功且日志回收的321..368，并包含旧273..320零提交失败的整段消费，覆盖49..368，不恢复任何旧额度。spent321与actual321均进入现场保护。

owner/evidence与冻结112版本逐字节一致；adapter/driver仅将首序号保护first!=321改为first!=369。固定128项、raw24576/transaction3584、三组存储、lead32、16 ms控制及2 s ISO期限、单次abort、任意interest停止、STATUS/ISO7/URB唯一性、checked export双边检查保持。设备部署和30秒诊断窗口未改，不增加第四轮。

另修正新description继承的maximum_epochs/maximum_iso_submissions/maximum_burst_triggers=2，使三者及max_epochs均为3，与既有三轮逻辑一致；这是描述值修正，不扩大三轮上限。

上轮[文件重放](A23_LIVE112_GUARD_METADATA.md)测得628→341 ms仅属于冻结112版本的隔离对照；本次120件、644来源build尚无真实SDK性能对照，不转写为实机收益。

## 验证结果

16个原生注入场景通过：正常三轮369/385/401各3072字节，共9216字节；spent321改写/增加/缺失；新增来源与120件基线变化；旧321 scope、错误32项许可、冻结spent321改写；第三轮前来源变化；interest关闭消息；归档额外普通文件/空目录/符号链接/FIFO及基线额外空目录。

归档节点异常、旧scope或错误许可在模拟provider打开前拒绝；现场来源/基线/spent321变化安排在provider模拟打开之后、第一轮ISO之前，提交数0。第三轮前来源变化及interest安排只提交前两轮，第三轮不提交。这里的opens与ISO均是注入模型调用，真实SDK对象和USB请求为0。

原960尺寸raw/transactions归档、模拟时钟当真实结果、旧112消费者及关机后interest前缀改写均拒绝。正常作业重复消费和外来作业接管拒绝，模型namespace字节保持。7项专项检查通过，不重复扩大已封存的128项底层传输矩阵。

两次编译（真实候选、注入fixture）及16个fixture、4个文件模式、只读环境检查、2次启动计划native freshness检查均由创建者直接wait。原生执行共23个；测试runner及两次计划Python进程也已wait。原生文件模式describe/archive/current通过，缺作业acquire-once返回2且不访问USB。

沙箱外--inspect-context通过预期系统/框架/沙箱策略，usb_open_permission_proven=false；它不证明设备实际可打开。启动脚本显式校验launcher/workflow/generated-workflow同版和native preview/build/scope。review exit0，缺新人工授权的execute返回2；把旧112工作流代入在outer claim前拒绝。均未创建actual record、人工授权文件或正式369 namespace。

初次生成探测因嵌套binding_header助手层级错误而停止，未创建build、编译或硬件作业；源副本及失败封存于generation-probe-r1。修正后首个完整review通过，不覆盖失败。新脚本继续保留此前修正的claim前工作流版本核对，避免重现旧启动接线错误。

## 实测问题、停止与当前状态

候选只回答：保持每轮完整guard和严格三轮结果后，文件类型查询优化是否使真实轮间间隔下降。需分别报告完整guard耗时、saved至下一before和BURST间隔，保持不跨Mach/RAW绝对时间相减的边界。有限三轮仍不是持续流、长期稳定或回调排空证明，旧卡logo/interest及未闭合前缀原因不作升级。

当前没有新实测授权或当前关机/装卡/USB就绪确认。只有在新的单次最多三轮授权和就绪确认后才能执行；先真实WAITING，再提示开机CFW。任意interest、包数/载荷/URB/回调异常、超时、保存/来源/基线/许可失败立即停，整段369..416消费、不补轮、不重启重试。未决资源按既有保留策略等待正常失败退出和创建者wait；结束另行只读回收，不能拿本轮模拟生命周期作实机证明。

本轮未读写SD、未改部署、未打开USB或创建真实SDK对象。SD最后已弹出，现场状态不作推定；644来源、旧实际记录和七个namespace已复核保持。软件候选已就绪，不继续扩大通用文件/进程框架；下一项仅等待新的实测请求、授权与就绪。

## 封存材料

路径相对research/usb-ds-iso，摘要为SHA256SUMS摘要。

| 材料 | 摘要 |
| --- | --- |
| private/analysis/A23-live120-lstat-review-20261025-r1 | 8f71d86f548e6e569fec365c39af910438c09b98c7d88d770f44109ad00d7058 |
| 同目录build（944项） | 3ecfbead3207c7fab30e80102d694325030327d6c50fe05067c99d099e15cfb3 |
| private/analysis/A23-live120-lstat-validation-20261025-r1 | aaa5906f15c20ee664132a48a9945a99269d45aff706f22bbcc8a1427b29a1e2 |
| private/analysis/A23-live120-lstat-context-20261025-r1 | 2411abc159530cf64c0735fd777af629e9caf6a9e1d567d7517cf0d7f571bfd2 |
| private/analysis/A23-live120-lstat-launch-plan-20261025-r1 | ad60d24dadfc5a9347e1ee488cb34ae5db793001e483f5f82fe39f7358407f9f |
| private/analysis/A23-live120-lstat-generation-probe-20261025-r1 | ee1dea30ecc40a416c5c11e840fb59fac66151615daaf53bf01459be67de167c |

receiver摘要0b43277d070eae64f02ba2c6b174ec9e7a3775f5b373e5a9f563b1fd1bfcf2e3；descriptor摘要3fda27d2df2b0c786141e75aea34d8e830c6e7b0df1b200e5416bc6b861ddeb3。一次性计划launch-once.py默认仅review，--execute要求独立新人工回执。完整来源、七namespace、实际321与ticket/交接快照在private/analysis/A23-live120-lstat-preparation-closeout-20261025。
