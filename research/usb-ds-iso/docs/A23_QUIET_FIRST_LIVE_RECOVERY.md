# quiet 首次实测的读卡回收：未找到导出文件（2026-10-16）

按用户“读卡吧”的指令，核对同一 SD 的 UUID 后卸载并重新只读挂载，保存部署文件、
原日志及错误报告，核对[本次主机 run](A23_QUIET_FIRST_LIVE_HOST.md)，最后安全弹出。
本轮未写卡、未签发次数、未重新启动接收器或发送 Switch USB 诊断请求。

## 回收事实

| 项目 | 结果 |
| --- | --- |
| SD | disk4s1 / SWITCH SD，UUID `37614F76-3E12-3470-B5C8-52B5A449C213`，只读挂载已核验 |
| 四个部署文件 | 均与已部署 quiet window-30s 候选一致，NSP 111234 字节，SHA `81314284…` |
| 日志 | 829 字节，SHA `9597a6e8fdc979ec17c85a614b7c5d1cefb4dd37a13eb189a26a07ae1529355b` |
| 根目录 ep0 文件 | 未找到任何 `ep0-*`，包括 execution/capture/diagnostic 和部分文件 |
| 错误报告 | 21 份；相对部署前逐路径、大小、摘要相同，无新增/修改/删除 |
| 推出 | 10-16 02:29:23 +08:00 正常弹出 disk4，确认挂载路径消失 |

日志止于 `UVC device initialized`，之前记录 HOS 22.5.0、预期控制器 Build ID、
runtime patch result=0 / record21。它与部署前的 1143 字节日志不同，已作为新原件
独立保存；没有用它覆盖旧日志，也没有由其缺少退出文本判定保存失败。

卡文件匹配、文本日志和主机接口选择各提供一部分观察，但没有带运行 recipe 和
boot/session nonce 的 EXE3，不能完成设备内部 trace 与主机请求的关联，也不能
认证物理同 run。当前没有可供解码的执行信封；未用空文件或模型文件替代。

## 可以确认与仍未知的部分

主机端一次控制请求约 0.3565ms 完成，一次 ISO 回调约 183.294ms，未超时、无 abort。
但 960 项实际长度全部为零，设备 STATUS 为 sequence1/state4、requested3072/
transferred0/urb_status2，因此仍不是有效载荷验收。此次读卡没有改变该失败结论。

用同一 quiet 版本的冻结源码核对，保存路径直接使用 `fsOpenSdCardFileSystem`，
文件名在该文件系统根目录，以 `/ep0-<nonce>` 开始。已检查的根目录就是预期位置；
“未找到文件”不能由文件应位于其他当前目录来解释。

源码显示 main 只有在 g_running 结束、清理入口允许、双 join 成功及 exporter 身份
满足后才进入相应导出/保存；失败分支可能永久保留。窗口在同步调用前后检查，不能
中断正在执行的调用。候选 g_running 已是 atomic_bool，不能直接套用普通 bool 可见性
猜测。日志在 worker 启动前静默，只有双 join 成功后才解除；829 字节日志停止的位置与
该设计相容，但它不是程序已经走到某个停止/保存分支的证明。

因此，目前无法区分以下情况：窗口/owner 尚未退出、线程交接未完成或失败、导出
前置条件失败，以及文件系统打开/创建之前失败。也不能排除受控关机时保存尚未完成。
没有新错误报告不能排除这些情况。没有文件更不能证明目标接口 2 请求没有到达。

## 独立封存与记录更新

| 材料 | 目录、条目数与 manifest SHA |
| --- | --- |
| 卡原件和挂载/推出回执 | `private/card-cycles/20261016-022343-quiet-first-live-recovery`，34 条，`de851d4eedc4a0ef1c6c5d1db6f5d32a99834bd8e73aaba76a034da8f4ace2bf` |
| 缺少设备文件的独立收集 | `private/collections/A23-quiet-first-live-missing-execution-20261016-022343`，32 条，`3d3d6d77233a63d249ae927f80ae5720980ad942f86f4401e57cfe8137f08e3e` |

收集使用专门的 incomplete schema，不冒充需要 EXE3 的标准完整收集。当前/冻结
接收器与六材料、消费回执、进程 claim、SDK claim 的只读校验通过，记录为
supplied_binding_consistent=true；完整链的 consistent/complete 和 hardware_verified
仍为 false。它保留实际主机材料、日志、文件缺口及引用，不伪造设备解码结果。

新可变记录仍为 failed_no_retry/remaining0/acquisition_enabled=false，仅补充本次
回收/收集路径和设备文件缺失状态。消费前后的历史快照保留，原主机 run 不改；旧三
实时票据和三份 offline-record 不补次、不修改。latest collection 指针更新为本次
缺证收集；卡上的 quiet 候选保持原样，没有新的部署版本。

## 下一研究路径

优先补齐结束到落盘链路的可观察证据：window stop → 双 join 返回 → exporter 身份
及导出结果 → SD 文件系统打开 → 创建/写入/提交。需要能在首个创建失败时仍保留阶段
或返回值，且继续遵守失败 join 前不读取 owner/DMA 缓冲、静默窗口内不做文本 I/O、
资源不明不强制释放的既有约束。具体方案尚未实现，不以此次缺文件直接指定某个原因。

在导出证据可取得前，不重复同一实测，不凭空修改控制超时、ISO 帧单位或载荷计划。
主机零长度、设备 URB 状态及原 16ms 超时均保留为不同层面的观察，不能合并成一个
已确认的因果结论。用户本次读卡要求已完成，SD 已可安全取出。
