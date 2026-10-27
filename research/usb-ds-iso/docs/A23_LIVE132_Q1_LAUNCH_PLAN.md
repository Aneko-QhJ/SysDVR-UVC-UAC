# Q1 一次性计划与只读上下文核对（2026-10-26）

Q1 的一次性启动计划已完成离线审查，采用 r1；当前没有新实测、人工授权、序号保留或消费。当前 `remaining=0`、`acquisition_enabled=false`。软件能力已实现不增加执行权限。

本阶段承接 [672 来源软件准备](A23_LIVE132_Q1_SOFTWARE_READY.md)，没有修改该来源束或重编译接收器。最后真实运行仍是 651 来源的 417..464，见 [三轮实测与只读回收](A23_LIVE126_INTEREPOCH_FIRST_RESULT.md)。

## 本次计划要回答的问题

在已有三轮形状下，真实 SDK 是否能满足新增末轮服务窗口与终结采样合同：末轮完整检查的 worker 返回和复核后，记录轻量 poll 完成点，窗口至少 250ms、相邻完成点最大间隔 32ms、最多 512 点；原导出及单次 owner queue 续接之后保存终结事实，由新消费者独立验收。

成功只表示该次历史采样切点及队列前缀满足合同。它不证明采样之后设备仍健康、SDK 已排空、缓冲可复用或持续流已实现。32ms 是本地实验阈值。

| 计划项 | 固定值 |
| --- | --- |
| 候选 | `private/analysis/A23-live132-q1-review-20261026-r4/build`，672 来源、132 件归档、完整 49..464 历史 |
| build manifest SHA256 | `dc0373e727426069db1bf7d084da69a38b11c7a8207f56b5bf2be126dc2c7035`，1023 项 |
| receiver SHA256 | `16b80bdbbeba50d76bc103e947068f7f32c0dd52f1a2f14c8335f7bc185e2d01` |
| 有界范围 | 一次调用、最多三轮、每轮 128 个 transaction；465..512 整段一次性消费，不能补试 |
| 末轮合同 | 250000000ns / 最大间隔 32000000ns / 最多 512 点；completion pending 时禁止退出 |
| 启动顺序 | 新授权及当次完全关机/装卡/USB 确认 → 新上下文前检 → 消费 → 接收器实际 WAITING → 人工开机 |
| 失败 | 停止、不重试、保留原始失败材料；仍有 pending 资源时保留创建者及直接 child，按当次关机确认退出政策处理 |
| 结束 | 创建者直接 wait；新消费者回收并独立复算主机材料；随后另行只读回收设备日志 |

不同时改变设备补丁、事务形状、lead、时限或窗口阈值。当前设备位置、是否关机及连接状态均未刷新；上一次 SD 已安全弹出的历史记录不构成本次就绪确认。

## 计划与拒绝审查

封存计划为 `private/analysis/A23-live132-q1-launch-plan-20261026-r1`，其中 `plan.json` 和 `launch-once.py` 一同封存。launcher 默认仅 review；执行分支要求固定路径中存在与该 build、范围、末轮合同及当前就绪字段逐项相同的新人工回执，并独占创建实际尝试记录。该分支本轮没有运行。

绑定链为 launcher → Q1 facade → generated workflow → 原生 `--check-build` scope，同时检查 generated 的 builder 和成功/失败消费者身份。执行成功后还要求原始 run 已封存、直接 wait/exit0、新 analysis 无错误，并用 Q1 消费者再次只读回收后比较结果。异常不推断“未启动”或“已回收”，记录为需要检查且不允许重试。

审查材料为 `private/analysis/A23-live132-q1-launch-review-20261026-r1`：

- review CLI exit0；缺少新授权 CLI exit2，拒绝原因为 `new human authorization receipt missing`。
- 10 项拒绝：旧 651 外层、旧 666 generated builder、错误成功消费者、错误失败消费者、旧 666 scope、旧 417 范围、authorized=false、旧回执序号、未完全关机、错误服务间隔。
- 拒绝检查期间屏蔽真实 write/issue/capture；四份错误回执仅在临时目录内。未创建正式人工回执、actual 记录或 namespace。
- 两个 CLI 及三个原生文件 scope 子进程均由创建者 wait；没有编译、fixture、模型 namespace 或真实 SDK 对象。

当前以下三个路径均不存在，不能把 `plan.json` 内的 expected 模板当作实际授权：

```text
private/analysis/A23-live132-q1-human-authorization-20261026-r1.json
private/analysis/A23-live132-q1-once-20261026-r1.json
private/sequence-reservations48-465
```

## 自进程上下文结果

只调用封存接收器的 `--inspect-context`，读取自身进程、系统、加载框架及二进制信息；两次均 exit0。默认沙箱内 `sandbox_query_result=1`、`policy_pass=false`。通过自动审批的沙箱外同一命令返回 result0/errno0、`policy_pass=true`；系统 build `26A434`、框架 UUID `B0D41EEF-C9BF-39DD-A1C4-226DCB94E78B`、receiver SHA 均匹配。

原始工具结果、默认和沙箱外 JSON 及摘要保存在 `private/analysis/A23-live132-q1-context-20261026-r1`。这只是已完成进程的观察：`usb_open_permission_proven=false`，没有 USB 枚举或打开，没有 SD 访问或权限修改；未来实际 capture 必须重新进行自身上下文前检。

## 封存与后续边界

| 材料 | SHA256SUMS 摘要 |
| --- | --- |
| 软件准备父交接 | `d36970933f32f6f0e92982a41b1b3d0de92d8848368662e48c27b4770ead0a0a` |
| 只读上下文 r1 | `bb3e57883a0c48e6b762c1ccf0844636254cd9c853be6239579e595ec6020d96` |
| 启动计划 r1 | `2d555cf224b61277ed12a61b4e12f58de097c98b2dad7bb99f45ada600c000b7` |
| 拒绝审查 r1 | `496bb1533c889c452592b8be834b0fc9b67f01b153828912f5bbe829c6b2d8e6` |

最终交接为 `private/analysis/A23-live132-q1-plan-closeout-20261026`；保存票据前后、旧 actual417 与九个 namespace 摘要、672 来源清单、计划/审查/上下文引用及文档副本。原 sealed evidence 保持。

本阶段电脑准备闭合。下一次 Q1 实测须获得新的上述单次范围授权及当次完全关机、SD 已装回、USB 已连接确认；在接收器实际 WAITING 前不得提示开机。旧授权已耗尽，泛指“继续”不能替代新单次实验授权或现场确认。Q1 通过也不授权 Q2 连续流工作。
