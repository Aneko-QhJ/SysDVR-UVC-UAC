# A23 真实两轮CLI、一次许可与失败留证（2026-10-22）

最新实测结果（2026-10-22）：[同接口两轮成功及时间线](A23_LIVE75_FIRST_RESULT.md)已核对。一次采集完成113..128和129..144，两个新URB387/403共6144正确字节，STATUS/ISO7通过，接收器exit0并由创建者直接wait。唯一150条设备trace与两轮状态/序号/URB一致，关联27条生命周期报告正常返回；SD91原件已只读回收并安全弹出。
本次许可与113..144整段耗尽、remaining0，不补次。另有一份生命周期仅4条有效记录、末条quiet_enter，无明确上下文，保留为未归因；此前81失败字段仍未知。已确认有限串行复用观察，持续流、长期稳定、跨时钟及quiet drain仍未验证。
电脑时间线显示两次触发相隔1.639秒，首轮保存至第二轮STATUS意图1.476秒；冻结调用链在轮间至少执行六次完整校验，尚无单次哈希独立计时。下一项在电脑上设计校验去重与计时，保留每轮提交前变化拒绝；以后真实节奏需新有界实验及新授权。本次旧75件候选只可归档验证，不能重启。以下未执行/未保留/待授权表述均为此前阶段历史。

最新实测候选（2026-10-22）：[当前75件基线的两轮CLI](A23_LIVE75_TWO_EPOCH_READY.md)已编译封存。STATUS修正已接入真实入口，绑定597来源、75原件及旧81..112完整消费记录；只允许新范围113..144。19原生场景、6归档拒绝场景、10项专项测试通过；沙箱外context通过，USB打开及真实两轮尚未验证。
新后继namespace、正式记录、保留和消费均未创建；旧592来源和既有证据保持。一次启动脚本已准备，等待新的单次最多两轮授权及当前完全关机/装卡/USB确认，再先WAITING后提示开机。失败即停、不补次、不复用81..112；不继续扩展通用框架或模拟矩阵。以下为此前阶段历史。

最新软件修正（2026-10-22）：[STATUS计数语义与判断前留证](A23_STATUS_CAPTURE_REVISION.md)的独立候选通过37个原生注入场景、3个历史成功STATUS原件回放及8项专项测试。允许终态report_count0/1和第二轮前该字段双向变化；其他URB/STATUS/ISO7及字节保持条件不变。每次STATUS先封存raw、SDK观察和失败字段，保存失败不继续。新5来源，总592，原587及实测包保持。
本轮USB/SD/真实SDK/正式发行消费均0；81..112仍耗尽，实际首轮具体失败字段仍未知，第二轮未实测。下一步将修正接入当前75件基线和新范围候选的独立实测build，完成审查后再取得新一次授权；113..144尚未保留。以下为此前阶段历史。

最新实测与回收（2026-10-22）：[首轮结果、验收缺陷和证据缺口](A23_LIVE_TWO_EPOCH_FIRST_RESULT.md)已封存。一次许可及81..112整段已消费，第一轮收到81..96共3072正确字节、设备COMPLETE/URB387 status3；新入口在STATUS/URB/ISO7谓词处失败，第二轮未提交。用户确认关机后接收器exit1并由创建者直接wait；SD75原件只读回收、安全弹出，日志不再待回收，remaining0。
发现新验收要求report_count1与旧65成功STATUS原件count0不兼容；仅改该字段的合成副本通过其余冻结谓词。本次完整after STATUS未保存，具体失败字段和唯一根因未知，整体失败不追认通过。下一步电脑核对报告条数语义并补失败原件留证，再评估新的实机实验；不补测、不复用81..112，旧587来源和旧证据保持。以下准备完成/未授权/未保留描述均为该次实测前历史。

本阶段完成上一份[实机实验选择](A23_NEXT_LIVE_TWO_EPOCH.md)要求的最小入口。新增8来源，合计587，原579逐字节保持。专用原生CLI已编译，25项专项检查通过；全部执行证据仍为文件检查和假SDK/IOKit注入，没有进行真实两轮实测。

## 已接通的路径

新main把被动等待适配器、A23PairedSDKProvider、现有两轮entry/驱动、只读构建复核器和一次许可接通。文件检查和环境查询分支不构造SDK provider。acquire-once要求真实生产命名空间下的已消费job及唯一run目录，重新检查本进程context，再经永久native process/selection attempt门槛进入等待和SDK。

新scope schema为A23-live-shared32-scope-1。构建中的acquisition_mode_implemented、formal_issuance_available和hardware_entry_enabled表示新入口的代码能力，不能代替本次人的授权或证明硬件成功。预览不创建job、保留或次数。旧文件检查程序、旧scope schema及49/65一次记录保持，不能拿来续次或直接改模拟开关。

构建冻结587来源，并确定性派生四个独立原生文件：scope/permit只扩展新scope能力和新文件清单；driver/entry只增加读取已有owner证据的出口。原始来源不改写。旧观察协议里的hardware/provenance/drain声明继续false；不将新CLI能力误标为物理认证。

每个job一次保留81..112整个区间，持久消费后才启动接收器；本次尚未发行或保留。第一轮验证并持久保存后才允许第二轮，新帧样本、独立存储和新URB条件沿用既有驱动。上限为2次ISO、2次BURST、4次显式STATUS，失败停止不补次。该实验检验有限重入，不能认证长流、最初失败根因或标准UAC。

## 实际收尾和失败留证

控制器在两轮完成且观察窗口通过后，只尝试一次最终checkpoint和live-final导出，随后再次核对结果当前性。成功路径的输出可以由原有严格SDK/entry分析器复核，保持原始184320字节data、26880字节事务表和完整STATUS。

停止时写live-failure。若owner已经有独立raw/transactions快照，则按epoch排他写live-evidence-epoch-N；后续回调才产生的快照也各最多保存一次。读取的是owner现有NSData副本，不重新读取SDK可能仍在写入的数据区。仍未产生快照的epoch不伪造raw，不把缺件判成功。

任何保留SDK资源的失败默认保持进程和引用，绝不套用Python取样进程的TERM/KILL清理。SIGINT/TERM仅请求停止；创建者继续保留并wait自己的Popen对象。新原生程序用主队列的timer和signal source运行，source本身保持强引用。

如果进入unresolved_keep_alive，需要用户先明确确认Switch已经完全关机，然后写绑定run/job的device-off-confirmed.json。创建者读取该回执后，仅通过自己保留的Popen对象发送一次SIGUSR1；不读取日志PID发信号。原生程序核对规范JSON和run/job绑定，只有处于未决失败时才接受这一结束入口，记录operator-stop并以失败码正常结束。此处的关机是用户声明，不是软件测量；pending_sdk_work_unverified与callback_drain_verified=false保持，既不释放活跃对象也不声称已经排空。进程退出和创建者wait另行记录。

## 已完成的检查

25项专项检查通过。10个控制器场景包含正常两轮、坏载荷、控制超时、等待时退出、运行中退出、观察不足、导出碰撞、回执碰撞、最终前旧回调，以及未决失败后明确确认关机。正常两轮被独立严格分析器接受；首轮坏载荷/超时不产生第二轮提交，失败不销毁SDK资源。

5个scope/原生permit注入场景覆盖正常、坏载荷、准备后来源变化、两轮间来源变化及停止时仍有未决I/O。完整新scope和native许可绑定通过，重放消费/原生声明拒绝；未决I/O时不做整包扫描，不因模型文件完整而升级物理来源。

另以实际冻结main源码编译解析器，未调用其中的acquisition main：Python关机回执和恢复的规范回执接受；错job、整数冒充布尔、额外换行、重复字段拒绝，共6项。创建者真实timeout分支在假child上验证只通过保留对象转发一次USR1并恢复父handler；另有中断转发及转发失败继续wait的专项检查。

当前实际环境只读检查：沙箱内sandbox=1/policy_pass=false，沙箱外sandbox=0/policy_pass=true；OS build为26A434，IOUSBHost UUID为B0D41EEF-C9BF-39DD-A1C4-226DCB94E78B。该检查只读取自身环境，不创建SDK对象，也不证明USB打开许可。

开发中间版均保存，未用失败结果冒认最终通过：r1夹具unused helper编译拒绝；r2/r3引擎类名和prepare接口接线错误；r4全部进程模型完成但使用了文件数较小的卡快照校验器；r5的23项检查通过，是增加关机完成路径前的中间版；r6夹具条件修改导致编译拒绝。最终r7为25项通过。各版合计61个模型场景、19次原生编译尝试，补充解析器另1次编译；这些数字不是实机样本数。未新增真实SDK对象、USB、SD、固件或部署。

## 固定候选与操作顺序

- review：private/analysis/A23-live-two-epoch-review-20261022-r1
- review SHA256SUMS：f3f79b41056c29ac45e88d1cea7204252acd9dac0d84db0bdf8740d69c6231a9
- build：上述review内build
- build SHA256SUMS：0b54650f0fc78dbc5e6fd0dd13c7e4da5073c6367a3ed64e6e14bb42bc6877c4
- binary SHA256：626b006bdec876bf82bb1205f29a52d66a99ffaca871bd8cdcb31b19971b16af
- validation：private/analysis/A23-live-two-epoch-validation-20261022-r1
- 开发记录：private/analysis/A23-live-two-epoch-development-20261022-r1至r6
- closeout：private/analysis/A23-live-two-epoch-closeout-20261022

只读预览，不发行或访问USB：

```sh
/opt/homebrew/bin/python3.13 -B research/usb-ds-iso/tools/a23_live_two_epoch_workflow.py --build research/usb-ds-iso/private/analysis/A23-live-two-epoch-review-20261022-r1/build preview
```

本次获得新的一次授权且确认设备完全关机、SD在Switch中、USB已接好之后，才使用该构建发行一次32序号job；先在沙箱外重新检查环境，再消费/启动。接收器明确输出WAITING后才提示用户开机进入CFW。没有WAITING就不提示开机；任一失败不自动重试、不重新发行。

成功后按计划保持足够设备日志保存时间，再由用户确认完全关机并只读回收SD。未决失败则先确认完全关机，再执行绑定该run的acknowledge-power-off；确认入口不会启动USB或新测试。收集阶段保存全部原件，设备trace和物理同次关联需独立判读，不能仅凭主机两轮结果宣称全链成功。

当前23保护项、旧49/65账本及失败owner/state保持；65已回收/remaining0，81..112实际未保留，生产32目录不存在。任意构造指令中断、创建者整进程崩溃、真实SDK回调排空、设备包双轮行为、长时流与根因仍有明确缺口；这些不是本次离线结果已证明的内容。
