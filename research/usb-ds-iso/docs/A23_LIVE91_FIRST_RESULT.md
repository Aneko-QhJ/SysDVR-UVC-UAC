# 91件基线候选首次实测结果（2026-10-23）

本次已完成一次授权采集：同接口两轮145..160、161..176均通过主机严格分析，合计6144正确字节；真实SDK路径的导出前后检查与接受回执完整。设备记录唯一对应这两轮，关联生命周期报告正常返回。SD已只读回收、安全弹出，145..176整段消费、remaining0，不补次。

| 项目 | 第一轮 | 第二轮 |
| --- | --- | --- |
| 序号 | 145..160 | 161..176 |
| 有效槽 | 0..15 | 6..21 |
| 正确字节 | 3072 | 3072 |
| 新URB | 387 | 403 |
| 终态report_count | 0 | 0 |
| ISO提交至回调 | 152.077 ms | 151.755 ms |
| BURST至控制回调 | 1.964 ms | 2.203 ms |

每轮960项transaction结构、16个有效载荷槽、前后STATUS及ISO7均由冻结收集器核对；两次ISO/两次BURST、各两个回调，无abort。接收器exit0，实际创建者直接wait；无重试、无固件或来源修改。双边回执只证明所记录检查边界，不证明检查后的永久新鲜度；纯回执消费者也不独立证明进程wait，wait证据来自外层创建者。

## 设备关联和回收

对SD副本中20份execution逐一比较，只有新增`ep0-123d03f5fd75a234ee74d025871400739e505914d4dcd0e6baaa167a93169f83.execution.bin`匹配四次STATUS与两次BURST的顺序、状态/序号、两次3072字节Post和URB387/403 status3。该trace150条、无丢失或无效记录；外部primary与内嵌副本一致，设备报告primary commit已确认。

同boot/session唯一关联`ep0-life-a8ef1579de55142c42c0b5e0f5b98083.bin`：27条有效生命周期记录，末条`main_return/result0`，closed且zero tail，writer/频率一致、joined_context在execution窗口之后。关联是请求/状态/序号/URB链一致性，未逐字节绑定设备端完整STATUS，也未认证物理来源标签或跨时钟对齐。

另新增一份execution/capture及其27条正常返回生命周期：该execution无ISO trace或URB，不匹配本次两轮，保留为独立上下文；不据文件数量推断用户开机次数。历史两份recipe不匹配的生命周期仍保留并排除，不追认；此前未归因记录也不因本次成功得到解释。

回收验证卷UUID`37614F76-3E12-3470-B5C8-52B5A449C213`，只读挂载一次，保存97份原件并哈希后安全弹出。相对91件基线新增6件，仅`logfile.txt`变化，90件既有非日志原件不变；8件既有ERPT不变、无新增ERPT，四项部署文件匹配。未写SD，未追加USB测试。

## 实测节奏和边界

| 主机同一时钟域区间 | 上次113..144 | 本次145..176 |
| --- | --- | --- |
| 首轮保存至第二轮STATUS意图 | 1476.301 ms | 293.376 ms |
| 两次BURST触发间隔 | 1638.889 ms | 453.402 ms |

本次导出前后完整检查分别记录275、276次，含开机前WAITING轮询；不能把这些总数当作轮间次数。轮间调用链保留一次完整检查，导出前/后的最后检查耗时分别268.615/268.541 ms。主机SDK时钟标记为非synthetic；两个主机时钟域的绝对值尚未校准，不直接相减。

两次实测未随机化，来源数量和主机负载等可能不同，不能证明差异完全由去重导致。293.588 ms观察窗口也不证明quiet drain。本次证明有限两轮串行复用与真实checked-export接线；持续流、长期稳定、所有回调排空、来源认证、跨时钟及旧81失败字段/根因仍未确认，广义`hardware_verified`保持false。

## 续研入口

下一项先用封存调用链和计时界定当前轮间关键路径，明确持续采集仍缺的实验问题与停止条件，不继续扩大通用模拟框架。若实机能增加信息，再准备当前97件基线、完整49..176消费继承和新范围的独立候选，审查后取得新的单次授权。当前91件build只可归档验证，不能重启；新SD快照已使其current91新鲜度前提失效。

## 封存材料

路径相对`research/usb-ds-iso`；摘要为目录内SHA256SUMS的SHA256。

| 材料 | 摘要 |
| --- | --- |
| `private/runs/A-two-epoch-a36f6a3f-db83-4a7e-8c57-96f9c666700d` | `5831f133593e471a3af683f154a8176b8e7bd2f913e014fa0de1832970ccf296` |
| `private/analysis/A23-live91-first-live-host-20261023` | `3ad3e9eb18f31a495d841d844cd6435131816d95900964ba6d68a296f38b11a9` |
| `private/analysis/A23-live91-first-live-analysis-20261023-r1` | `ae9fa64e5e49ecae60030166ac64c97fe98ef7936d50f2203bb6f2839053108d` |
| `private/card-cycles/20261023-live91-first-read` | `2dc75e0848b4dfa4ce4c50764cc4a85f64cfb1376a85840182ae9affada15ee8` |
| `private/analysis/A23-live91-first-live-read-20261023-r1` | `22613de65defb9c3ef5d7bca32b51b18d4a8a96c88a0bfd2c53b5dce1a983ebc` |

最终交接与保护摘要见`private/analysis/A23-live91-first-live-closeout-20261023`。人工授权及actual record沿用准备时固定的20261022文件名，实际执行、回收时间为2026-10-23。
