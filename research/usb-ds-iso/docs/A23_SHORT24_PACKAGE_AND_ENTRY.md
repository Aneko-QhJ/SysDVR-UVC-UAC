# 短包配套包、驻留入口与写盘（2026-10-27）

本配套包已用于[首次短包实测](A23_SHORT24_FIRST_LIVE.md)：主机384字节观察通过，设备保存失败。
此包从旧设备父树生成，漏带已有路径容量修正；不得作为后续设备构建基线或再次启动已耗尽范围。
新离线路径修正版尚未打包/绑定/部署。下文保留首次实测前的准备记录。

本阶段离线准备已完成：新NSP与IPS配套包、可编译的一次性主机入口、独占写盘及驻留包装
已经核验。真实SDK打开和采集分支**尚未执行**，没有授权签发、写卡部署、USB测试或新范围消费。

## 配套部署材料

最终包位于`private/analysis/A23-short24-package-20261027-r1`，已核验并封存。
ELF→压缩NSO的3个段逐字节相同，段摘要与Build-ID对应，PFS0仅包含main和main.npdm，
NPDM程序ID/范围均为00FF0000A53BB666，原线程配置保持。

| 文件 | 旧快照SHA256 | 新包SHA256 |
| --- | --- | --- |
| exefs.nsp | b54747adb8e824bb0a08709868335a06c1aca53c6b1e4e8ce6a1d2e761b8deb8 | 42e820c00794741ad6d674ef03da4a5d750eaa94113ea30807d78af1efa3ba5a |
| HOS Build-ID对应IPS | 80991e082dda79da38f016b635715cec0bae4ec7c4963820a769cde17280416f | b2151be89c7f685b26fa498cd3c44e6115c4b407fe1efdbe5761e3fc4029f28a |

将来部署须配套替换这两个文件。boot2.flag及toolbox.json不需要变化；四项旧文件均从
最近138件封存卡快照另存为rollback-review，没有读取当前卡。sd-review是电脑上的候选副本。

实际运行时安装器的4个CPU模型场景通过：原映像应用新22项编辑；新IPS已安装时返回1且
不写；旧A23 IPS映像或混合映像返回-2且不写。**如果旧IPS被loader应用，新NSP会拒绝该
旧映像**；这不证明loader在旧实测中是否应用了IPS。配套新IPS支持已安装路径，未应用时
仍可走原映像运行时安装路径，实际结果需实机记录。

## 命令行入口与授权边界

最终入口：`private/analysis/A23-short24-entry-20261027-r2/short24-receiver`。
源码：[a23_short24_entry_main.m](../host/a23_short24_entry_main.m)。

- `--describe`只输出编译时配置，不读取当前硬件或认证现场。
- `--check-authorization FILE`只检查文件；可检查明确model_only=true的模型记录，绝不消费。
- `--acquire-once FILE RUN`是未来采集分支，当前只执行了模型记录被拒绝的检查。
  真正启动需要新的人工授权记录，绑定本入口摘要、配套包/NSP/IPS摘要、新recipe、基线及现场确认。

拟用范围固定为513..528、一次调用/一个16包burst。当前只是编译时计划，**未保留或消费**。
以后只有真实新授权才能独占创建`private/short24-once/513-528.CONSUMED`，在任何注册表/
SDK访问之前完成写入、回读与fsync。旧Q1记录、错误范围或模型记录不能启动；文件创建
不确定或失败时不访问设备、不重试。旧remaining=0保持，没有改写旧签发器。

初始设备须不在匹配表中。程序先实际输出WAITING，未来用户看到该行后再开机。最多等待
120秒；多个候选、错误身份、等待到期或停止请求均终止本次等待。进入原生构造后再次
核对注册表身份，打开的interface/pipe、SDK IO、capture和runtime均由原进程持有。
这些真实选择、打开和硬件错误路径目前只完成编译/来源审查，未执行。

## 驻留与停止

[a23_short24_runtime.m](../host/a23_short24_runtime.m)先独占保存start-intent，再允许capture
开始。初始意图写盘失败也保留已准备的对象，不发送ISO。五秒是poll之间的采集预算，
同步SDK调用可能超过它，不能称作硬截止或进程寿命上限。

正常观察或停止后只尝试保存一次observation。**打开原生对象后，进程不会自动退出**，
包括成功、SDK准备失败、错误、未知归属与保存失败。SIGINT/SIGTERM转换为停止请求，
仍保留对象；没有destroy/release、再次提交或强制退出分支。

这是当前有限诊断的资源保留政策，不是交还证明。未来实测的主机可能长期驻留；清理需要
另行明确依据与操作，不把Switch关机、保存成功或安静采样直接当作可以释放的证据。

## 写盘和后来故障

observation固定写raw.bin、transactions.bin、before.bin、after.bin、metadata.json，以及
SHA256SUMS/COMMITTED。使用新目录和独占文件，逐文件fsync并完整回读，再同步目录。
写入失败保留部分材料，不删文件、不覆盖或重试，不确认交还。

第一次保存后仍poll现有capture，不新增USB请求。后来的重复回调或interest等变化写入独立
later-0001.json等，最多8次；不改原observation。尝试数与成功写盘数分开记录，写盘失败
或容量耗尽即停止新记录，但继续保留资源。因此原metadata中的完成只说明历史观察，
后来故障不会被覆盖，也不能把旧通过当作当前健康。

## 本轮针对性检查

最终审计：`private/analysis/A23-short24-entry-audit-20261027-r2`。

- 7个ASan/UBSan原生注入场景：正常、迟到重复、later容量耗尽、later写盘失败、pending、
  已有observation、已有start-intent。重复调用start不产生第二次提交。
- 独立文件限制场景：RLIMIT_FSIZE将单文件限制为16字节；真实write失败后保留16字节，
  不产生COMMITTED，未使用真实SDK对象。
- 5项独立持久化检查通过：封存校验/条件关系、历史与后来状态、pending及失败保留、
  部分文件、later尝试与提交计数。正常和后来故障样本的原始观察仍可独立核验。
- 10类授权拒绝通过；模型授权可只读检查，但采集模式拒绝，未创建run或正式范围claim。

此前21个SDK注入场景/7项关系检查和15项ARM检查保持封存，本轮未重复扩张。
所有本轮执行均为文件检查、编译及模拟I/O；真实SDK对象数、USB操作和SD访问均为0。

开发中初次runtime fixture使用相对输出路径被构造器拒绝，改用规范绝对路径；部分写入fixture
最初误用NSData的dataWithLength，改为NSMutableData后通过。初始草稿与失败日志保持。
最终选入口r2/审计r2，包仍为r1，没有为修正覆盖旧原件。

## 下一步与问题卡

下一步已涉及具体硬件，见[一次短包问题卡](A23_SHORT24_ONCE_PLAN.md)。执行前须新授权与
当次物理确认；目前没有创建真实授权记录或执行部署。按[当前规则](RESEARCH_RULES.md)保留
探索观察与严格验收的区别，不因软件准备完成就宣布短包实机能力或持续PCM通过。
