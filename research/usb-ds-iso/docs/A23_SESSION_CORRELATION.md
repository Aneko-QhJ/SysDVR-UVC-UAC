# 启动与EP0会话关联原型（2026-10-14）

新增独立EP0REL1内存封装，关联当前启动journal、已停止且双join的EP0诊断、admission计数和已返回的旧DIA1保存结果。失败join/缺少context在读取owner、guard、admission或receipt之前旁路，只输出启动信息。原INI1、DIA1、OWN1及封存候选保持原样；生产与三票据不变，remaining=0，USB/SD访问0。

本阶段是电脑原型：28项已有实际视频函数副本回放结果逐项保持，24项策略检查通过ASan/UBSan；15项新增检查及400项相关Python回归无跳过。ARM只编译序列化核心.o，没有新完整ELF、实际启动hook关联或设备保存。视频回放的启动journal为两条合成SM记录，保存返回值为注入值，不能据此声称已串起真实启动与文件生命周期。

## 读取条件与失败旁路

| 条件 | 输出 | 不读取的状态 |
| --- | --- | --- |
| 仅请求启动信息 | 当前INI1已发布前缀，可未seal | 全部EP0与sink |
| 请求EP0，任一join失败 | 启动/状态信息，reason=1 | 全部EP0与sink |
| 两join成功但context未发布/发布中 | 启动/状态信息，reason=2 | 全部EP0与sink |
| context有效，旧DIA1 serializer拒绝 | 启动/状态信息，reason=3 | admission与sink内容 |
| 两join/context/旧DIA1门槛通过 | INI1+DIA1，可附admission与receipt | USB payload始终不读 |
| 启动SID失败禁记录，但EP0/context有效 | EP0-only；status=3与原始身份Result保留 | 不伪造INI1或启动writer |
| 没有journal或context | 192byte状态信息 | 不伪造writer/nonces/owner |

context采用单发布者CAS→不可变字段→release phase=2；reader acquire只接受完整发布，不重置或覆盖。同一存储生命周期中，context保存启动writer、EP0 writer、既有boot/session nonce与recipe；DIA1内的writer/exporter/nonces/recipe及INI1内writer/recipe必须一致。没有context的旧INI1文件不能仅凭recipe关联为同次启动；原型仅接受当前journal对象，不接受任意旧INI1文件作为输入。context匹配是调用方契约下的本地关联，SID、nonce、recipe与CRC均不认证来源。

启动前缀snapshot仍使用旧journal的acquire发布规则；seal不代替join。owner/guard与admission依赖停止、冻结、双join及旧DIA1的交接门槛；不增加USB查询，也不改变账本、fault、stop、服务Result或清理授权。admission必须不active，largest不超过128；超过17须有bound violation，refusal/violation须与owner fault一致。计数未提供与真实值全0分别标记，不能由拒绝计数推断实机根因。

## 文件结果的稳定读取

双join只约束视频/音频线程，main中的文件保存仍可能正在执行，因此不能立即读取可变sink。本原型另设单次不可变receipt：调用方声明保存调用已返回后，复制旧SinkState及该次DIA1输入长度/CRC，release发布。serializer只有在save_returned且receipt完整发布时才读取其内容，并要求长度/CRC对应此次嵌入的完整DIA1。未返回、未发布或发布中不附sink；错误输入CRC拒绝整个输出。

commit错误保留content_verified=true、commit_acknowledged=false及原始Result；读回验证与commit返回分别记录。receipt不认证真实文件操作，且针对嵌入的旧DIA1保存。REL1不能在自身保存之前记录自身最终commit结果，decoder恒标记envelope_own_save_result_recorded=false。本阶段不实现设备文件操作、初始化失败写卡、删除/覆写/重试或资源回滚。

## 独立格式与容量

EP0REL1为192byte header + 原INI1字节 + 原DIA1字节，最大192+1120+6656=7968byte。header含版本/flags、模式/旁路原因、组件长度、join Result、startup状态/身份Result、admission五计数、sink阶段/Result/flags/verified长度、writer/nonces/recipe和组件/header/receipt-input CRC。无相应组件时字段必须置零；独立decoder交叉核验布局、CRC及上述语义。旧三种decoder拒绝REL1，不重标记旧格式。

caller持有7776byte工作区，避免serializer新增约8KB自动数组；serializer通过全部门槛后才写输出，拒绝时输出保持原字节，scratch可变化。24项策略包含两种失败join和无context的poison指针、未返回receipt的poison指针、发布中context/receipt、live启动前缀、identity禁用、EP0-only、commit失败/成功、错误nonces/writers/recipe/receipt、active admission、短输出/别名以及64条INI/16槽/128条trace的最大样例。调用方必须保证对象有效、单次生命周期与指定发布/读取时序，原型不验证任意指针可访问性。

## 证据与复核

- [原型实现](../device/ep0_session_capture.h)、[独立解码器](../tools/analyze_ep0_session.py)、[构建回放工具](../tools/build_a23_session_correlation.py)、[native策略](../tests/ep0_session_policy_test.c)、[Python交叉检查](../tests/test_a23_session_correlation.py)。
- [审查audit](../private/analysis/A23-session-correlation-review-20261014/audit.json)：28份回放/独立REL1解码、24项策略、ARM.o与recipe/编译命令/输入hash。[manifest](../private/analysis/A23-session-correlation-review-20261014/SHA256SUMS)封存各文件。
- [验证摘要](../private/analysis/A23-session-correlation-validation-20261014/validation.json)：400项相关回归、生产/源码快照、三票据、历史封存与文档链接核验。[manifest](../private/analysis/A23-session-correlation-validation-20261014/SHA256SUMS)另行封存。

## 下一步

在新完整ARM副本中绑定真实startup runtime与VideoThread现有nonce发布，不增加随机/USB调用；以真实保存返回后的receipt替换注入值，重新核对启动失败、线程部分启动、join失败及正常/DIA1拒绝路径。REL1超过旧6656byte诊断sink上限，须单独设计容量与一次保存入口，明确初始化失败时FS是否实际可用；无FS、无owner或线程可能live时保留独立启动记录，不能伪造join/DIA1或借历史FS成功写卡。

新副本需另存recipe/ELF/代码、BSS/stack预算，并复核helper细阶段与64条容量。真实DMA/终结、线程join、SD持久性、运行开销和来源认证仍未测；本次拒绝/关联模型不解释首次SDK burst的seq0，根因未知。
