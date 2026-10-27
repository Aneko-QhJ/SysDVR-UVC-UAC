# A23：重启后的独立复现验证

本页记录原A23接收器的独立复现阶段；该阶段已在第二次启动失败后停止。
后续主机观察和串行结果见各专题，最新进度及后续条件见[当前状态](STATUS.md)和[测试计划](TEST_PLAN.md)。

## 条件与目的

A23同时改变HS服务间隔和主机采集窗口，首次单次成功不足以确认修复。
此前A17也曾单次成功、后续失败，因此原计划保留A23 NSP/IPS、接收器和冻结backend，
暂以三个独立启动各一次检查能否复现成功；不直接启用旧接收器的16次循环。

每次fresh boot、USB2/HS、视频关闭，预检为interval1/MPS256及IDLE/seq0/URB0。
host64/request192/40ms/960槽、repeats1；16包连续有序、exact192、native/public0及overall0，
自己的URB/report匹配、status3/requested=raw-count3072及ISO7 terminal1/FFFF/actual3072。
保留960条native记录、184320byte raw、JSONL/STATUS与时间记录，再读卡核对完整设备日志。
具体首槽、FrameID、MFI和环偏移不能硬编码；软件快照不作为总线时间戳。

## 已核验结果

| 独立启动 | 主机结果 | 完整设备日志 |
| --- | --- | --- |
| 2026-10-08 00:01 | seq1..16、192bytes、indices456..471连续，native/public0、overall0，严格通过 | 5228bytes，安装、唯一提交及终结匹配 |
| 2026-10-08 00:39 | raw正确、indices522..537连续，但有效包native E00002ED/public1、overall E000400E，严格失败 | 4551bytes，01:24回收核验，安装、唯一提交及终结匹配 |

两轮自己的URB387/status3/3072和ISO7终结均完整，无取消或重投。失败轮context配置
与首轮相同，首两成功ED软件MFI差1tick；不能据此排除总线问题或确定原生错误根因。
成功轮handler至ACK0.321094ms，失败轮0.330885ms；少量软件耗时样本不足以建立因果关系。

第三次原工具复现未执行。两轮完整日志均已核验，没有本阶段待读卡事项。
后来只读微帧观察工具的两次单次成功不补计为原冻结backend的第三次复现。

历史run为`private/runs/A-A23-HS-interval1-20261008-000112/`和
`private/runs/A-A23-HS-interval1-20261008-003952/`；逐次部署、收集及软件快照详见[历史结果](RESULTS.md)。
`latest-A23-*`指针目前已指向后续串行测试，不应再用于引用这两次历史运行。

## 后续阶段

[主机微帧观察](HOST_MICROFRAME_AUDIT.md)于01:41和01:59各一次严格通过，完整设备日志已匹配。
之后[串行工具](NATIVE_SERIAL_VALIDATION.md)加入每轮native核验和失败停止，10-09实机首轮
原生失败后停止。原三次启动计划和后续串行阶段均不能标为稳定性通过。
