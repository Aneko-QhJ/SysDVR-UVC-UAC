# 当前109件基线的固定128项三轮候选（2026-10-25）

固定128 transaction候选已实现、编译并封存，最终r4通过34个原生注入场景和12项专项检查。绑定636来源、当前109原件、完整49..272消费历史及五个旧namespace；仅允许新范围273..320。新授权、actual record、正式namespace和保留均未创建，USB/SD/真实SDK对象操作为0。

本次完成的是接线和拒绝验证。旧960项实测的约152 ms ISO回调不能作为128项结果；名义48 ms回调及每轮减少104 ms仍待实测，轮间完整校验仍保留，不宣称持续流。

## 实现与约束

| 项目 | 候选 |
| --- | --- |
| transaction | 固定128项，每项请求192字节，SDK结构28字节 |
| 三组互不重叠存储 | 每组raw24576字节、transaction3584字节 |
| 每轮载荷 | 严格16包、3072正确字节，三轮合计9216字节 |
| 序号 | 273..288、289..304、305..320 |
| 保持的策略 | lead32、BURST16 ms、ISO2 s、单次abort、任意interest停止、每轮完整校验、保存后下一次poll再arm |
| 设备 | 同一部署、16包、30秒窗口、trace256/owner32；本次未写卡或改固件 |

新增4份来源：build_a23_live109_short128.py、a23_live109_short128_workflow.py、audit_a23_live109_short128.py和test_a23_live109_short128.py。旧632份保持。构建生成独立live_owner.m/live_evidence.m并显式链接，原960源码不变；同步缩小lease、driver及独立payload消费者的固定尺寸。driver在接受快照前还要求transaction_count为整数128。

新scope/schema与candidate binding隔离旧960入口，candidate binding显式包含transaction_count128。109件只读快照、49..272完整消费历史以及spent225现场文件均进入原生完整检查；新增来源在首轮提交前和轮间变化也会拒绝。历史225..272实测记录和五个namespace逐字节保持，旧177失败不升级。

## 验证结果

| 场景 | 观察 |
| --- | --- |
| normal、queued-delay | 新三轮独立收集器接受9216正确字节与双边检查回执；合成时钟不能作为真实SDK输入接受 |
| tail128 | 每轮16包占112..127槽，末槽127完整保存并验收 |
| owner raw/rows分别127、129、960项 | 构造拒绝，没有提交；对应模拟open为0 |
| lease enqueue count127、129、960 | 每场景实际创建1个模拟open，随后拒绝错误计数、置故障，底层提交为0 |
| 15/17包、末项错误、重复回调、外来回调指针 | 首轮即失败，提交数1，不启动下一轮 |
| 第三轮STATUS错误、新来源在第三轮前变化 | 前者在第三轮失败，后者保持提交数2 |
| spent225改写/增加/缺失、新来源/基线变化 | 在下一ISO提交前拒绝 |
| 旧225 scope、错误32计数、坏源码/历史/生成物/binary | 门禁拒绝，不调用模拟open |
| interest-close/open/overflow | 保持停止；准备期无driver消息和关机后补充前缀保存，溢出只作不完整诊断 |
| 重新封存后改写补充消息前缀 | 独立消费者拒绝 |
| raw960/rows960坏归档、新build送入旧103消费者 | 尺寸或descriptor拒绝 |
| 回执后载荷变化、重复consume/他job接管、缺授权issue | 独立收集器或许可引擎拒绝 |

最终34个fixture均exit0、由创建者直接wait，ASan/UBSan stderr为空；12专项检查通过。原生CLI仅运行describe、归档/当前文件检查及不存在job的拒绝，没有创建真实IOUSBHost对象。模拟时钟只验证接线，不用于预测实际回调时长。

开发材料全部保留：r1在CLI已编译后发现缺少render_engine入口而停止；r2的34原生场景通过，但专项测试存在类执行顺序依赖；修正并补新增来源变化覆盖后r3通过34场景/12检查。随后复核发现尺寸探针把模拟open计数固定写0，r4改为读取实际计数，并增加相应断言，最终34/12通过。r2/r3已被r4取代，不能用其探针open字段作为最终结论。

四个构建版本共7个编译作业、102个fixture进程均由创建者wait。三个完整review各执行4个原生文件模式，共12个；两次只读环境检查均直接wait。没有因开发重建而追加实机尝试。

## 当前环境与一次计划

r4沙箱外只读--inspect-context通过：arm64、OS26A434、指定IOUSBHost框架UUID与sandbox查询结果0匹配。记录绑定r4 receiver摘要，不能据此证明USB打开权限。r3对应环境检查保持归档，不替代r4。

最终一次计划在private/analysis/A23-live109-short128-launch-plan-20261025-r2，选择review-r4/build。无参数只review；缺授权execute返回2，actual record与namespace仍不存在。新人工授权须绑定此build/receiver及transaction_count128，明确一次最多三轮273..320、失败即停、不重试，并确认本次完全关机、SD装回、USB已连接。实际WAITING后才提示开机CFW。

授权文件和actual record计划路径分别为private/analysis/A23-live109-short128-human-authorization-20261025-r1.json与A23-live109-short128-once-20261025-r1.json；目前均不存在。sequence-reservations48-273尚不存在，remaining0。旧225..272已经耗尽，SD最后已安全弹出，当前现场状态未确认，不自动启动。

未来实测分别报告各轮ISO提交至回调、保存至下一轮意图及完整检查耗时，完整核对STATUS/ISO7/新URB/三组载荷和设备生命周期；不能单凭触发间隔或更短回调判为持续流。漏包、多包、错误、interest、超时或留证/新鲜度/容量拒绝立即停止；未决资源由创建者保留，用户确认关机后正常失败退出并wait，结束另行只读回收日志。

## 封存索引

以下相对private/analysis，摘要为SHA256SUMS的SHA256。

| 材料 | 摘要 |
| --- | --- |
| A23-live109-short128-review-20261025-r4 | 5744722bd799792b47e3b5bbb5f8960f93bf93d32121dee5f23b6259caa60e5c |
| A23-live109-short128-validation-20261025-r4 | ceb0ae4e5cdd3d4dbf616de0c6b025105f55b3f6e39d37949e8e7da18a79bd07 |
| A23-live109-short128-context-20261025-r2 | db30aa2c1cf85988986b284e5556564b75ce1b437deec02c538cdccab3cc779a |
| A23-live109-short128-launch-plan-20261025-r2 | eaf258f4d7bb44855ef8287b70e97cb1295d82b7a63d2ece69a858966f6cc2ce |

最终636来源、保护项、actual225、五个namespace、ticket与交接副本见private/analysis/A23-live109-short128-closeout-20261025。范围依据见[A23_SHORT_WINDOW_SCOPE.md](A23_SHORT_WINDOW_SCOPE.md)，此前实测及读卡见[A23_LIVE103_INTEREST_FIRST_RESULT.md](A23_LIVE103_INTEREST_FIRST_RESULT.md)。
