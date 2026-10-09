# A23：HS 125 µs 服务间隔对照

2026-10-07，A22完整4948byte设备日志已回收：HOS22.5.0/目标BuildID、A22启动标记、
runtime result0/22条记录、唯一seq1/URB387及status3/3072均匹配主机证据。
四个部署文件仍匹配，15份既有错误报告无新增或变更。prepare0.056146/post0.191615/
post-to-ACK0.000365/ACK0.173698/handler-to-ACK0.421823ms。
A22单次16包raw正确且连续，但全部native E00002ED/overall E000400E；严格验收失败。
发布前配置匹配，首两成功ED软件MFI差8tick，软件观察尚不能解释原生错误。

A23检验HS一毫秒轮询节奏是否参与缺槽/原生错误：HS端点bInterval从4改为1，
服务间隔由8个microframe改为1个（125µs）。MPS256、192bytes/包、16个独立TD/ED、
首包显式lead32、后15TD SIA1/FrameID0、两DSB、gate/原门铃尾部/所有权沿用A22。
原HOS installer按描述符配置端点context；不直接改写context、不新增MMIO操作。
控制器仅两条等长指令改变：输入interval检查和ISO7标记；其余代码/符号相同，仍680bytes。
SS描述符继续interval4，burst仍拒绝SS；此实验只处理HS。

[Apple USB文档](https://developer.apple.com/library/archive/documentation/DeviceDrivers/Conceptual/USBBook/USBOverview/USBOverview.html)
说明HS的numFrames/frameList按传输机会计数，而frameStart仍以1ms帧起点计。
[Tegra XUDC设备驱动](https://code.googlesource.com/linux/torvalds/linux/+/9f7853d7609d59172eecfc5e7ccf503bc1b690bd/drivers/usb/gadget/udc/tegra-xudc.c)
按原始bInterval设置context interval，并对Isoch使用SIA。
这些是实验依据，不能证明HOS行为或根因。

采集窗口必须随间隔调整。原256槽在interval1下仅32ms，host lead64时名义覆盖
提交后64..96ms；A22首FrameID相对主机窗口推导首槽67，即约提交后131ms，超出该窗口。
因此A23使用960槽/120ms，名义覆盖64..184ms，保留host64/request192/wait40ms。
该覆盖推算依赖帧计数比较，时钟未独立同步；实机仍须核对实际调度和payload位置。
窗口长度也是有意的测量调整，A23不能视为主机参数全部相同的单变量因果证明。

接收器仅新增ISO7兼容、严格interval1描述符检查、CLI最大槽数512→960及相应提示。
冻结A17的callback、payload/native错误判断、定时/取消和已核验的静态backend不变。
960记录低于原backend1024诊断上限，raw分配184320bytes，单次有界采集。
仍要求16连续有序/exact192、native/public全0、overall0、自身URB3/3072与
terminal1/bitmapFFFF/actual3072。已终结URB不取消、不重投；失败保留全部证据。

ISO7使用ISO6的同一112byte布局、STATUS168bytes，发布前context只读快照与首两ED/
错误优先规则不变。解码期望interval1，FrameID与选帧关系仍为+32；每1ms帧对应8个
名义packet槽，后续SIA无显式FrameID。仍须核验配套NSP/IPS、ISO7及完整A23启动日志。
DMA上下文/report非原子，软件MFI不是总线时间戳，不证明DATA PID或硬件服务时间。

```sh
python3 research/usb-ds-iso/tools/build_patch.py --burst --event-audit --context-audit \
  --followup-sia --interval 1 --frame-lead 32 --explicit-all --mps 256 \
  --out research/usb-ds-iso/private/packages-A23-interval1
python3 research/usb-ds-iso/tools/package_experiment.py --burst --revision A23 \
  --packages research/usb-ds-iso/private/packages-A23-interval1
```

47项本地测试通过（43项核心、4项接收器，无跳过），覆盖256种输入interval、
8相位/帧回绕/两cycle、实际HS/SS描述符路径、ISO7解码、全部错误保留及960槽末端raw。
ISO2..6/A22 inject/IPS、A18..22接收器重建均逐字节一致；A23接收器有上述明确调整。
安装器22条记录预检、幂等、混合/部分写入及readback失败回滚通过；A/rollback构建、
NPDM和28+6文件/两ZIP校验通过。包保留构建时状态，实际部署见下方。插回Switch重启，USB2/HS、
视频关闭、host64/request192/40ms/960slot、仅一次burst，随后读卡回收完整设备日志。

2026-10-07T22:46:45.811193+08:00完成A22模块/补丁目录及4948byte日志备份，
A23四文件配套拷入；22:46:46.109253四文件SHA256读回一致，22:46:46.798593
正常推出disk4并确认挂载消失。无新增或变更错误报告。
实际部署记录见`private/deployments/latest-A23.txt`；交付包位于
`private/packages-A23-interval1/`，包manifest保留本地构建时未部署/未实机状态。
NSP SHA256 `e3bcec30c06e67ca3ce61db5740d99aa63e587206653e45c7a7e3a25b1eccb7d`；
IPS SHA256 `80991e082dda79da38f016b635715cec0bae4ec7c4963820a769cde17280416f`。
2026-10-08 00:01首次HS单次严格验收通过。只读预检确认HS/interval1/MPS256、
fresh IDLE/seq0/URB0；host64/request192/40ms/960slot仅一次提交。
16包seq1..16、exact192 raw逐字节正确，indices456..471连续，无缺槽；全部有效包
native/public0、overall0，receiver退出0。960条native记录均保留，其中944个空槽
actual0/status E00002E7；它们未计作有效包成功，也未归一化原生状态。
184320byte完整raw保存成功，其余槽全零。

自身URB387/report387/status3/requested=raw-count3072，ISO7 terminal1/bitmapFFFF/
actual3072完整终结，无取消/重投。首FrameID808/control32801411，对应首槽456，
全包相对首FrameID乘8加ordinal参考槽delta0。context_valid1、配置匹配，发布前
words为00010001 0100002E 80023001 00000000 01000C00 00000000 000C0000 00000000；
state1/type5/interval1/MPS256/MaxESIT256、mult0/burst0；选帧MFI6215，首边界6464，
提前249tick（模16384）。首两成功ED软件MFI6464/6465，差1tick，参考边界delta0/0。
这些仍是非原子软件快照，不能证明总线服务时间或DATA PID。

submit1.323ms/实际等待42.054ms/trigger45.932ms、rc0。原始native/JSONL/raw/STATUS/
预检/命令/退出码、summary及独立逐包核验已保存并SHA256校验，指针
`private/runs/latest-A23-run.txt`。ISO7运行诊断和interval1配置已观察，完整A23启动
标记/runtime安装/唯一提交及设备ticks待读卡；视频关闭是约定条件，未独立验证。
窗口也同时扩为960槽，单次通过不能证明此前错误的根因或稳定性。
下一步插读卡器回收完整日志，再确定后续稳定性验证；保持无重投。

2026-10-08 00:14完整5228byte设备日志已回收并与卡上SHA256一致，指针
`private/collections/latest-A23.txt`。A23/HOS22.5.0/目标BuildID、runtime result0/
record21（22条）、唯一seq1/HS/URB387/3072提交及status3/3072终结、首控制字
32801411全部匹配；运行revision身份已确认。prepare0.048750/post0.107813/
post-to-ACK0.000365/ACK0.164167/handler-to-ACK0.321094ms。
四文件仍匹配A23，15份既有错误报告无新增/变更；run20文件SHA256已更新。
单次严格成功已得到完整日志支持，稳定性及根因未确认。保留A23参数和文件，
本轮无需重复拷入，正常安全推出后重启，再做一次独立复现；
后续验证阶段及限制见[REPRODUCIBILITY.md](REPRODUCIBILITY.md)。
00:22:02.862955+08:00已再次核验四文件/日志后正常推出disk4，确认挂载消失；
本轮未改写SD或执行USB测试。收集记录保存最终流程完成及推出状态，构建包保持不变。

00:39第二次独立启动单次复现未通过：同样HS/interval1/fresh IDLE、host64/request192/
40ms/960slot，16包seq1..16/exact192 raw逐字节正确且indices522..537连续，但全部
有效包native E00002ED/public1、overall E000400E/transfer1，receiver退出1。
自身URB387/report387/status3/3072、ISO7 terminal1/bitmapFFFF/actual3072完整终结，
无取消/重投。首FrameID1754/control6DA01411对应声明首槽520，所有payload参考delta+2。
context_valid1/interval1配置匹配，words与首次相同；MFI13778，首边界14032，领先254tick，
首两成功ED MFI14032/14033差1tick，相对125µs参考边界0/0；快照非原子、时钟未同步。
submit1.070ms/实际等待45.052ms/trigger51.865ms、rc0；完整184320byte raw和960条
native记录均保存。首次成功未稳定复现，服务间隔调整未消除原生错误。
当前停止该验证阶段，下一步读卡确认本轮完整A23日志，再研究；根因未确认。

2026-10-08 01:24已回收第二轮4551byte完整日志，安装result0/22条与唯一URB387/3072终结匹配；
四文件未变，15份旧错误报告无新增。A23严格失败及首次成功证据均保留，根因未确认。
下一步保留A23，不重复拷卡；已构建并验证仅增加主机只读微帧观察的隔离工具，
见[HOST_MICROFRAME_AUDIT.md](HOST_MICROFRAME_AUDIT.md)。下次重启后仅一次诊断采集。

2026-10-08T01:37:28.095740+08:00再次核验四文件和4551byte日志后，正常推出disk4，
确认挂载消失。本轮SD写入0、USB测试0；下次重启后使用主机微帧观察工具单次测试。

2026-10-08 01:41主机microframe-audit-1单次HS采集严格通过：16包seq1..16/exact192，
indices536..551连续、有效包native/public0及overall0；URB387/status3/3072完整终结，
无取消/重投。四处只读微帧查询均成功，但读数均为8的倍数，真实微帧相位未解析。
新backend增加只读观察，不能将本轮视为原冻结backend的纯复现。稳定性和根因未确认；
本轮完整设备日志待读卡，当前下一步读卡，停止继续提交。

2026-10-08 01:49本轮2631byte完整日志已回收并SHA256核验，A23/HOS22.5.0/目标BuildID、
runtime result0/22记录、唯一seq1/URB387/status3/3072及首控制字51A01411与主机匹配。
模块base743E400000、首TRB偏移17D000匹配；四文件仍为A23，15份旧错误报告无新增/变化。
设备prepare0.049375/post0.374427/post至ACK0.000417/ACK0.117708/handler至ACK0.541927ms。
本次单次严格成功得到完整设备日志支持；post和handler时间比上一失败轮更长，
现有少量样本不能建立这些软件耗时与native失败的因果关系。主机四查询读数均为8的倍数，
真实微帧相位、总线服务时间和根因仍未确认。
下一步保持A23及同一microframe-audit-1工具/host64/request192/40ms/960槽/repeats1，
重新启动后做一次独立复现并停止提交，继续读卡核验。失败立即保留证据，不串行重试。
已重验原主机工具/receiver/backend/library/helper哈希，沿用通过的本地验证，不重复构建或测试。
本轮SD写入0、USB采集0；01:49:44.085333+08:00正常推出disk4并确认挂载消失。

2026-10-08 01:59同一microframe-audit-1工具第二次fresh IDLE/HS单次采集严格通过：
16包seq1..16/exact192/raw正确且indices567..582连续，native/public0、overall0。
URB387/status3/3072与ISO7 terminal1/FFFF完整终结，无取消/重投。四查询成功且计数均为8倍数，
FrameID1295推算首槽568而实际567，参考delta全-1，仍不能解析真实微帧相位。
工具/参数哈希与前轮相同，已有两轮严格成功；前轮2631byte日志已匹配，本轮完整设备日志
待读卡，暂不继续提交。稳定性与根因仍未确认，当前下一步读卡。

2026-10-08 02:05已回收第二轮主机诊断的完整2391byte日志，安装result0/22记录及唯一
seq1/URB387/3072正常终结与主机一致；无新增错误报告。两轮microframe-audit-1单次严格
成功均已完整日志核验。17E000环偏移按端点动态环指针/模块范围和ED标签验证，修正旧脚本
固定17D000假设；原检查中止时的日志也保留。稳定性、真实微帧相位和根因未确认。
已构建[逐次原生状态核验的串行工具](NATIVE_SERIAL_VALIDATION.md)，本地11个callback、
3个完整CLI模拟、3个分析器及3项参数拒绝验证通过；每次native/raw/ISO7完整终结
通过后才可提交下一次，最多16次，任一失败停止。本轮没有实机执行该阶段。
SD四文件保留A23，未重复拷入；02:20:17.555537+08:00正常推出disk4并确认挂载消失。
下一步重启、关闭视频、USB2/HS，执行一次最多16次串行的接收器会话以检查环回绕。
