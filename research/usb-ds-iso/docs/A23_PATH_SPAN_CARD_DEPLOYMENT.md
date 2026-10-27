# 路径缓冲候选现场部署（2026-10-16，Asia/Shanghai）

用户按提示保持 Switch 关机并回复“已接好”后，已完成新候选备份、部署、读回和安全弹出。操作目录名沿用 19:12 准备脚本时的标识；实际弹出时间为 **22:54:35+08**。本轮未签发一次记录或启动实机测试。

重新扫描识别 UUID `37614F76-3E12-3470-B5C8-52B5A449C213`，实际分区 disk4s1、整盘 disk4、挂载点 `/Volumes/SWITCH SD`，核验外置 FAT 及可写模式。233 项来源、141 项已通过回归的封存材料、新包/接收器和旧记录再次核验通过。

## 备份与读回

先保存并读回 **34 个选取原件**，四部署文件匹配最近生命周期基线 `bca717…` / 116864 字节。随后电脑端四文件备份读回，只替换 `atmosphere/contents/00FF0000A53BB666/exefs.nsp`。

新文件 **117024 字节**，SHA256 **`b54747adb8e824bb0a08709868335a06c1aca53c6b1e4e8ce6a1d2e761b8deb8`**。四部署文件读回均匹配新包，其他三个部署文件、日志、报告、旧失败临时文件及两份 LCP1 均保持本次备份时的全部字节。

本次临时辅助文件再次出现，其全部字节匹配既有封存样本，已在电脑操作证据中保存；替换后的选取清单没有本次额外辅助文件。只报告前后观察，不推断中间系统内部处理。

新工具真实部署回执已通过第 5 代入口的新包/设备绑定、四文件读回及对应整盘弹出核验。22:54:35+08 安全弹出 disk4，确认挂载消失。`latest-A23.txt` 与新增 `latest-path-span.txt` 指向本次实际部署；旧 lifecycle/quiet 指针保留各自版本。

| 材料 | 路径（相对 research/usb-ds-iso） | 条目 | manifest SHA256 |
| --- | --- | ---: | --- |
| 新备份 | `private/card-cycles/20261016-191203-path-span-predeploy` | 35 | `101caf5c7ab8d0729e19bbdf2e0278db0a8ad5beb409cb355fc3a5a41fde6de0` |
| 部署回执 | `private/deployments/20261016-191203-path-span-window-30s` | 9 | `ec11155faadb0f731092a65d60c52c11337b74bb681f253d67e0664ed446ec0c` |
| 现场操作 | `private/analysis/A23-path-span-card-deploy-20261016-191203` | 7 | `17e089ccfb7cbeb1907950f975ec64612b40350cb82d4714ad9b879ed7b7dcdd` |

## 旧阶段记录的保留

与 14:31 只读回收相比，本次备份新增 `ep0-life-788b8c90dea40002fb9026fd8c7fe70f.bin`，日志内容也有变化；旧原件没有缺失。原来 `ea16d…` 的 LCP1 保持原摘要。

两份文件均为 3968 字节，按旧生命周期 recipe `39b109…` 解码，各有 27 条有效阶段记录、最后供应阶段为 retain。新增文件 SHA256 `5f37d38b41441a1aadd3f399cb0a7673195fb2100ffc7368510a99eedb9b8ca6`。它在本次替换前已经存在，不能当作新路径候选执行结果，也没有绑定成一次新的主机实测。两份原件全部保存，不自动挑选或删除。

## 接续状态

`private/analysis/A23-path-span-pending-deployment.json` 已改为 deployed_ejected；原 waiting_for_card 状态保存在 `private/analysis/A23-path-span-deployment-closeout-20261016`。正式 `A23-path-span-once-*.json` 仍不存在，两个旧现场记录保持 failed_no_retry / remaining0。此次仅验证卡文件部署路径，未执行新候选固件或接收器，未证明 `0xD401` 已消失或 ISO 问题已解决。

可以装回 SD，但先保持 Switch 关机。下一次明确开始诊断时，基于本次真实部署回执签发独立一次记录，主机进入 WAITING 后才提示开机。结束后按关机取卡流程保留全部原件，并以本次备份中的两份旧 LCP1 清单作为比较依据。
