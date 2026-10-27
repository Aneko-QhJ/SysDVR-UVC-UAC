# 启动标记现场核验与63份新基线（2026-10-18，Asia/Shanghai）

后续离线重建已完成：[独立63份基线流程](A23_CONTEXT65_BASELINE63.md)。新版预览接受真实回执，旧59拒绝继续保留；以下为本次现场核验原始结论，未重跑或修改封存证据。

用户明确要求实际修复，并确认完全关机、SD已接好。已运行一次正式backup阶段；在只读挂载后的59文件精确比较处拒绝，未进入execute阶段。作业failed_no_retry、backup_remaining0/repair_remaining1，阶段锁及介质占用保持，没有重跑或补次。

随后进行了独立、人工审查范围内的只读差异保存：重新核对同卡UUID，要求卡仍已只读挂载，不再次挂载；保存63份文件并于2026-10-18 14:11:50+08安全弹出。boot2.flag已经存在、0字节且SHA匹配，四部署项均匹配。代理没有创建或覆盖部署文件，不能把这次观察解释为代理修复成功；标记由谁、何时恢复仍未确定。无需再进入写入阶段。

相对15:49的59份锚点：新增正确空标记、一组EXE3/primary及一份LCP1，共4文件；无删除，logfile.txt发生变化，其他58份原件字节保持。两版日志均已封存，不会把旧日志写回卡来通过原门禁。新日志运行时补丁结果0/record21，旧日志为1/record21；模块基址和读到的指令也有变化，仅记录观察，不推断具体执行时间或根因。

新增EXE3与外部240字节primary一致，控制轨迹0条、丢弃/无效0。LCP1有27条有效记录，zero_tail、main_return/result0，保存与上下文能对应这份EXE3。没有本次USB主机测试，没有序号65 BURST或ISO结果；8份既有ERPT字节均保持，无新增ERPT。这些设备原件不能唯一绑定到本轮主机过程。

旧发行器用新63份真实回执预览，仍拒绝“saved59 originals changed or missing after flag repair”，具体变化是logfile.txt。四部署项匹配与旧59基线契约通过是不同事实；不放宽旧工具、不签发65、不改49已消费记录。下一项离线重建63份基线绑定，保留旧新日志和全部原件，再审查独立发行资格。新测试仍需独立指令。

新增只读检查工具[inspect_a23_context65_flag_card.py](../tools/inspect_a23_context65_flag_card.py)通过16项测试，10份保存作业（8模型、旧planned快照、实际失败作业）判读通过。它只读本地计划、状态、命令和封存，不跟随MountPoint访问卡，不探测PID，不解锁或补次。未决PID只是保存的数据，退出记录缺失不表示进程已死；记录“创建返回”也不表示部署验收通过。检查器新增2项来源，总闭包303；旧301来源及其proof保持。

| private下材料 | 用途 |
| --- | --- |
| card-cycles/20261018-context65-flag-drift-read | 63份只读原件、四文件匹配及真实弹出回执 |
| analysis/A23-context65-flag-card-ready-20261018 | 已失败且封存的原作业；不是仍可执行的planned作业 |
| analysis/A23-context65-flag-card-drift-triage-20261018 | 独立只读命令、差异及范围 |
| analysis/A23-context65-flag-card-live-analysis-20261018 | 新EXE3/LCP1解码、日志diff和旧发行器拒绝 |
| analysis/A23-context65-flag-inspector-review-20261018-r1 | 10份作业的文件检查报告 |
| analysis/A23-context65-flag-inspector-validation-20261018-r1 | 最终16项日志、303来源 |
| analysis/A23-context65-flag-card-live-closeout-20261018 | 用户确认、真实操作范围、保护项及交接 |

真实介质访问已经发生，不能再沿用此前“SD0”作为当前状态。本次只有只读核查/保存和弹出，没有可写挂载命令、标记创建、SDK对象或USB测试。旧49记录的recovered=false指其原15:49回执拒绝，不表示现在待读卡；本次63份当前回执另外保存，不重写旧历史。
