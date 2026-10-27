# 126件基线的轮间后台校验候选（2026-10-25）

独立候选已编译封存，原生与Python校验通过。651来源、126件当前回收快照、完整49..416消费历史和spent369现已绑定；软件描述范围为417..464，尚未保留或授权。实际许可remaining0，未启动接收器或连接USB/SD。

本轮将[临时轮间接线](A23_INTEREPOCH_GUARD_WIRING.md)固化为独立生成器和工作流，不覆盖旧120件入口、647来源或旧namespace。新候选允许固定三轮，每轮128项、16包/3072字节；设备部署未改，持续流、吞吐提升、回调排空及存储复用仍未证。

## 固化内容

新增4来源：tools/build_a23_live126_interepoch.py、tools/a23_live126_interepoch_workflow.py、tools/audit_a23_live126_interepoch.py、tests/test_a23_live126_interepoch.py；来源总数647→651。前一阶段的控制器及fixture3来源原字节保持。

新生成器基于已核验的120件build生成新内容，加入第12个根spent369和对应实际记录；新scope/schema、417..464序号、namespace路径、固定48模型、原生许可、传输首序号门、SDK/entry/导出消费者和工作流同步更新。旧scope及旧工作流在打开SDK之前拒绝新build。owner/evidence/adapter/driver逐字节与旧版比较，除driver/adapter首序号保护369→417外保持。

126件快照来自20261025-live120-lstat-first-read：身份/只读回执、部署摘要、哈希和安全弹出均复核。完整49..416历史包含前一轮369/385/401三段及其已闭合actual369，新增来源、spent369和实际记录均纳入每轮完整检查。旧369..416不会恢复使用；417..464只是软件绑定的未来范围，不是已发行的权限。

## 工作队列与退出门

仅两次轮间边界使用唯一worker。期间不自动arm或访问可变verifier；group实际返回后归还独占权，再复核job/permit和边界，最多恢复一次poll。首次WAITING、原STATUS/frame/ISO/BURST期限、lead32、末轮观察和最终导出继续沿用原路径。新增10秒guard期限只锁存停止，不取消或提前释放阻塞文件调用。

固化入口时补上一个旧fixture未直接验证的退出条件：loop即使因模型关机确认标记finished，后台校验未返回时也不能退出进程。生成的interepoch_exit.h提供同一个退出谓词，由真实入口与fixture共同使用，要求finished、guard非busy且verifier已归还串行队列。校验中exportEvidence只返回verification_pending，finalize/最终校验拒绝进入，不读取verifier可变字段。退出门/主入口/控制器/生成scope均纳入候选绑定与文件清单。

这只等待本次校验工作块，不证明SDK回调排空；退出前仍可能存在原合同保留的SDK资源。原子故障最后读取至SDK调用之间的窗口也未闭合。

## 必要的新接线检查

| 原生场景 | 实际结果 |
| --- | --- |
| normal | 417/433/449三轮，9216正确字节；两次worker返回/复核/poll，独立新消费者接受 |
| spent369改写/额外/缺失 | 三项均在初始完整检查拒绝，opens0 |
| 新控制器来源改写 | 初始完整检查拒绝，opens0 |
| baseline126-pre | 临时基线变化，ISO提交0；此前模型准备曾open1，不说成零open |
| old369-scope / count32-reservation | 旧scope或错误许可计数拒绝，opens0 |
| between-third-source | 新生成器来源变化，第三轮前停止；ISO/BURST均2 |
| exit-worker-ack | 第一轮后，worker开始时处理模型退出与关机确认；loop已finished但退出谓词false，export pending，finalize拒绝；worker返回后才允许退出，未恢复下一轮poll |
| frozen-spent369 / archive-new-main | 冻结历史或新入口改写均在初始完整检查拒绝，opens0 |

共12个原生场景通过。先前12项worker交错矩阵及旧三轮传输/interest故障矩阵保持封存，不在本轮重复；normal用于验证新范围、新基线和新绑定，exit-worker-ack专门覆盖新增退出门。

6项Python专项检查通过：新范围载荷/绑定、spent369与来源拒绝、旧scope/计数/基线/晚变、模型关机不跳过worker、旧工作流/伪实机拒绝、文件模式及零物理变更。缺新授权issue拒绝；旧120消费者和旧工作流均以descriptor不同拒绝；simulation=true结果不能按真实时钟验收。

候选编译1次、ASan/UBSan fixture编译1次、12 fixture进程、4文件模式进程（describe/archive/current成功，缺消费票据入口exit2）以及Python单元进程均由创建者直接wait。文件模式不打开SDK；fixture provider全注入，真实SDK对象/USB/SD均0。12个临时模型namespace/授权已留证，正式namespace/授权/范围新增均0。未检查本轮沙箱外执行上下文或USB打开权限，不把软件准备通过称为实机就绪。

最初一次审计调用使用相对路径，被canonical参数检查在创建输出前拒绝；改为绝对路径后r1通过，无额外编译、模型或发行。构建后生成工作流的builder/consumer接线也核对为新版本，未残留旧120工作流导入或旧首序号门。

## 候选与边界

候选目录：private/analysis/A23-live126-interepoch-review-20261025-r1/build。SHA256SUMS摘要abd21e277165bac7aca7145a968459ef004803de234488f63428188404338324；包含原生入口、新生成工作流与源代码，归档可复核。当前文件检查通过不代表设备现场未变、实际部署来源已获物理认证或未来文件不会变化。

下一项仅离线准备/审查这一版本的一次性启动计划，核对launcher→专用工作流→新scope和实际执行上下文；缺授权不得保留417..464或启动接收器。未来实测须新的单次最多三轮授权与当前关机/装卡/USB就绪确认，先实际WAITING后提示开机；失败即停、不补轮。它应回答“后台校验下严格三轮链和退出保留能否工作”，不能把无故障三轮当成回调排空、真实故障竞争或连续音视频证明。

## 封存

| 材料（相对private/analysis） | SHA256SUMS摘要 |
| --- | --- |
| A23-live126-interepoch-review-20261025-r1 | ed8f8a57954c004d5945dafacb4f95d7d5548b7426139d946399d72617306c77 |
| A23-live126-interepoch-validation-20261025 | 88e81cdf6d82b25d6f8f9345a0fde802cdb02f8890edb13266438fbee3c8deae |

最终交接private/analysis/A23-live126-interepoch-preparation-closeout-20261025保留651来源、八个namespace及actual369不变、票据前后副本和文档。日志仍pending=false、SD最后已弹出，当前现场状态未重新推定；remaining0、采集关闭。
