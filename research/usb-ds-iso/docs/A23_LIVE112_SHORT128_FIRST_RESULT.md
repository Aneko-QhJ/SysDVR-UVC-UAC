# 112件基线固定128项三轮首个传输结果（2026-10-25）

本次在用户新授权及关机/装卡/USB就绪确认后完成321..368三轮，主机严格分析及独立重读接受，共9216正确字节。用户在实际WAITING提示后报告进入CFW/HOME，接收器exit0并由创建者直接wait，无abort、未观察到interest。本次设备日志现已只读回收：唯一216条execution与三轮一致，关联27条生命周期确认约30秒正常到期返回。持续流、回调排空及旧故障根因仍未知。

| 项目 | 第一轮 | 第二轮 | 第三轮 |
| --- | --- | --- | --- |
| 序号 | 321..336 | 337..352 | 353..368 |
| 正确字节 | 3072 | 3072 | 3072 |
| 有效槽 | 5..20 | 2..17 | 8..23 |
| 新URB | 387 | 403 | 419 |
| ISO提交至回调 | 47.175542 ms | 47.736250 ms | 47.388709 ms |
| BURST至控制回调 | 3.234292 ms | 3.663125 ms | 2.642209 ms |

每轮完整保存raw24576字节和128项transaction3584字节，仍严格验证16个192字节包、全部transaction、前后STATUS及ISO7。三次ISO、三次BURST、六次STATUS，ISO/control回调各[1,1,1]，三轮共享同一session和接口。实际SDK链、导出前后完整检查、接受回执与独立收集器一致。interest为完整空观察前缀，pending0/overflow=false/latch=false，不证明未来无消息或回调排空。

## 接收时长与间隔

此前225..272的960项三轮ISO提交至回调为151.958792、151.886167、151.834417 ms；本次为47–48 ms，约减少104 ms，与128项名义48 ms预测相容。两次采集基线、来源数量、序号和负载不同，未随机化，不能把所有性能差异都单独归因于窗口缩短。

本次首轮保存至第二轮before_intent为492.662917 ms，第二轮保存至第三轮为438.797917 ms；两次实际触发间隔546.624084和502.107917 ms。每轮arm前的完整校验仍保留，因此回调提前不等于连续流。各区间来自同一Mach时钟域；不把另一时钟域的绝对数值直接相减，callback_drain_verified、continuous_streaming_verified和广义hardware_verified均保持false。

## 新基线接线及检查

新增4份独立来源：build_a23_live112_short128.py、a23_live112_short128_workflow.py、audit_a23_live112_short128.py与test_a23_live112_short128.py，总640份，旧636保持。绑定最后回收的112份原件、完整49..320消费历史和六个旧namespace。273..320虽然零提交，仍整段进入已耗尽历史。

相对已封存109件候选，owner/evidence实现逐字节相同；adapter/driver只把首序号保护first!=273改为first!=321。固定128项、存储尺寸、lead32、16 ms控制及2 s ISO期限、单次abort、任意interest停止、每轮完整检查均保持。scope新增spent273现场保护，新schema拒绝旧273 scope。

最终r2通过11个原生接线场景和6项专项检查：新三轮成功、spent273改写/增加/缺失、新来源/112基线变化、旧scope及32计数、第三轮前来源变化、interest关机后前缀、坏封存历史；还检查960尺寸归档和旧消费者拒绝。未重复扩大原128项传输矩阵。r1也完成11原生场景，但末尾“实现字节相同”断言漏掉预期的首序号保护变化而失败；修正比较口径后形成r2。两版4编译作业/22fixture均创建者wait；两次只读环境核验通过，不代表USB打开权限。

112件是最后只读回收的档案基线，不是本次开机前重新读卡的证明。之后用户曾报告No HOC和默认入口均不卡，可能有尚未回收的设备日志。助手未写卡或改部署；现已回收120件并确认四项部署匹配；新增记录中仍有未关联上下文，不能把112件档案当成本次开机前的全部内容。

## 启动脚本失败、修正与新授权

最初launch-plan-r1误导入a23_live109_short128_workflow，而构建为live112。此前review与缺授权拒绝没有执行到工作流issue，漏掉了这项版本不一致。实际执行在outer一次性记录创建后，被旧工作流以descriptor differs拒绝；未创建job、namespace或run，未启动接收器、未访问USB，也没有进入WAITING。该接线错误及失败记录完整保留，未重置或自动重试。

修正后的launch-plan-r2显式导入live112工作流，并在创建outer记录前检查flow.builder、生成workflow.builder及native preview/build/scope都与计划一致。加入把旧109工作流代入的回归反例，确认在claim前拒绝；正常review与缺新授权拒绝通过，formal namespace仍未创建。

用户获知该失败和修正后，另行明确同意使用修正入口、三项仍就绪；新人工授权和actual record使用r2文件名。此后仅启动一个真实接收器，发行并消费一次321..368，实际WAITING后才提示开机。旧r1是未发行的软件启动失败，不是第二次USB采集；同一未保留范围没有被重复消费。

新build采用review-20261025-r2，构建manifest46566911e04baa6fccd1f77d0ca84d32e3ee7a7714f2561cfd18adde52821a3d，receiver摘要a0720c188c50a58207bae0e33ca00a48d7db646ba2943c2957d9eb5974a1c89b。最终启动计划为private/analysis/A23-live112-short128-launch-plan-20261025-r2；实际记录为A23-live112-short128-once-20261025-r2.json，原r1失败保持。

## 只读回收与设备关联

SD UUID核对、只读挂载、原件复制及哈希回读通过，120份原件已封存并安全弹出。四项实验部署匹配；相对112件基线，新增8件，只有logfile.txt改写，111件旧非日志不变，无删除。此次“读卡”未另获人类关机确认，回执如实记录false；物理卡身份和只读状态已核实。无写卡、额外USB请求或追加采集。

唯一匹配321/337/353序号、六次STATUS、三次BURST与Post(3072, URB387/403/419)的新增execution为ep0-ebf5a1ee5ab93ac6ae84743b30762d420a699463cf602d9ddb9bdf35cd67ce8e.execution.bin，共216条trace、丢失0、无效0，外部capture与嵌入primary逐字节相同。通过boot/session身份关联ep0-life-a2a9cc87da2170baa972531d59d9924c.bin：27条有效记录、闭合标志、零尾、无解析错误，writer/frequency一致，末条main_return/result0。设备窗口expired，30.000295573秒；首条序号至停止29.193941979秒。主机与设备时钟未做跨域校准。

另一个新增execution为ep0-19a68c3b790fdb7025290739d175e642ff47a136cda3428add3a0186ba6ca7c8.execution.bin，37条trace、无本次序号或ISO URB；其关联生命周期ep0-life-c1f1fdcb6051838504e591b11450c464.bin也以27条main_return/result0闭合。第三份新增生命周期ep0-life-51ab8f654cafb6d05c84434c205fa716.bin只有4条有效前缀，末条quiet_enter，未报告闭合；不能推定其退出原因。现有证据不能把这些额外上下文分配到此前No HOC、默认入口观察或确定的开机顺序。

新增一份870字节ERPT：atmosphere/erpt_reports/96833172-806f-cb4e-552d-b67d9124c6c0。完整MessagePack解析为28字段，ErrorCode为2162-0004，没有进程/模块标识；报告已保留，但未建立与本次三轮或未闭合前缀的身份关联，不能据此认定本次sysmodule崩溃。完整解码含敏感字段，仅在private封存。启动配置文件哈希、缺失项及boot2标记清单与前次相同，标记不证明模块实际执行，也不认证实际选择的入口。

## 当前状态与续研

321..368整段耗尽，remaining0，不补轮、不重复启动；接收器exit0且创建者直接wait。640来源、旧actual273、旧六个及新321共七个namespace保持。设备日志pending=false、recovered=true，SD已弹出；当前现场开机/装卡状态不作推定。

本次9216字节三轮传输与关联设备正常返回均已核对，固定128项回调约47–48 ms。持续流、长期稳定、回调排空、额外记录归属、旧卡logo及旧interest根因仍未证明；hardware_verified、continuous_streaming_verified、callback_drain_verified和root_cause_confirmed保持false。下一项只做额外记录的离线关联审查；未来采集需120件新基线、新范围及新授权。用户按默认入口开机提示后报告“已进入 CFW／HOME”，未单独重复入口名称，保留原话。

## 封存材料

路径相对research/usb-ds-iso；摘要为SHA256SUMS的SHA256。

| 材料 | 摘要 |
| --- | --- |
| private/runs/A-three-epoch-e47d0bd7-882a-4524-b781-de6b79d96b7e | d2a30e8fd020ce7ab1bb1cad1f72d9186b831d866864e598bfb6fae1ddef6b50 |
| private/analysis/A23-live112-short128-first-host-20261025 | 6191159f4bbab6f08005e9e6ef1b844209834c26e0eb7e2163e04a23e1ea398c |
| private/analysis/A23-live112-short128-review-20261025-r2 | e4ed25c0988f4567af59c568c07215bed5e4f1d73a7123c3ba3099bf9d115d88 |
| private/analysis/A23-live112-short128-validation-20261025-r2 | 3c15de7f05e36e758ef225df45d7b9e0e4e349d4e22b080cb4ef9b338ab23105 |
| private/analysis/A23-live112-short128-launch-plan-20261025-r2 | 7b5c61461467ca2f3dd9b60ba1391684f8fd5de8150b5e756d36f0fda1e6a1d8 |

最终授权、旧启动失败、640来源、七个namespace、ticket和交接副本见private/analysis/A23-live112-short128-first-result-closeout-20261025。前次273失败和默认/No HOC恢复观察继续保留，见[A23_LIVE109_SHORT128_FIRST_RESULT.md](A23_LIVE109_SHORT128_FIRST_RESULT.md)。

本次回收、设备分析和补充审查分别见private/analysis/A23-live112-short128-first-read-20261025-r1、A23-live112-short128-first-analysis-20261025-r1及A23-live112-short128-first-supplement-20261025；摘要依次为de06994b8db74412e094fd7f771e534bc85f69713336e2d685749171787053f5、a87603c3d5b46d325eca9e293193f5b21f2a0a8f162400754406d2f2ce725f12、6f461628fa7e5ea2d02c119286fe2da31272dba87376fb1fd75ccbf699569922。120件卡快照摘要94feade6120cbc10cf1136268bce1801be7871d2c9138f229be89691a0731875。最终回收closeout为private/analysis/A23-live112-short128-first-recovered-closeout-20261025；旧主机阶段closeout保持原封存，pending描述仅为当时历史。

后续离线核对见[A23_ERPT_PREFIX_CORRELATION.md](A23_ERPT_PREFIX_CORRELATION.md)：9份ERPT均为官方ForcedShutdownDetected类；quiet_enter前缀位于worker启动之前、窗口内刻意不记账，不能定位崩溃；ERPT与前缀仍无身份连接，本次正常三轮结论保持。

后续性能核对见[A23_LIVE112_GUARD_METADATA.md](A23_LIVE112_GUARD_METADATA.md)：文件属性查询是新的本地热点，隔离lstat候选完整检查均值628→341 ms，尚未绑定120件或进行实机对照。本次原三轮结果不作修改。
