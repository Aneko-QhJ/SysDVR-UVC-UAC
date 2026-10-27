# A23 同接口两轮实测结果（2026-10-22）

后续电脑研究：[显式校验去重与计时候选](A23_GUARD_CADENCE.md)已完成隔离原生验证；真实controller尚未采用，本次实测原件和结论保持。

本次单次许可已完成：同一SDK会话、同一设备和接口上，先保存并验收第一轮，再用新URB完成第二轮。113..144共32个正确包、6,144字节；接收器exit0，由实际创建者直接wait。**确认的是一次有限串行复用观察；连续流与长期稳定性仍未验证。**

本次许可和113..144整个范围均已消费，remaining0；旧81..112保持耗尽。以下结论来自这一次采集及随后只读回收，没有追加实测、部署或SD写入。候选准备阶段见[75件基线准备记录](A23_LIVE75_TWO_EPOCH_READY.md)。

## 主机与设备证据

| 项目 | 第一轮 | 第二轮 |
| --- | --- | --- |
| 序号 | 113..128 | 129..144 |
| 有效载荷 | 3,072字节，16包 | 3,072字节，16包 |
| 设备URB | 387 | 403，新URB |
| STATUS | COMPLETE、requested/transferred3072、urb_status3 | 同左 |
| 终态report_count | 0 | 0 |
| ISO/control回调 | 各一次、status0 | 各一次、status0 |
| ISO7 completion/ring/context | 通过 | 通过 |

四份before/after STATUS原件、SDK观察和验收字段均已保存；第二轮before与首轮after逐字节相同。两轮960项transaction记录分别通过既有严格检查，无abort、timeout或指针不匹配。会话为`5F7CF075-3CB9-411B-83C3-E54FF8784242`，device/interface ID为4295016855/4295016867。

18份已保存EXE3中，唯一一份与本次完整控制顺序、113/129序号、URB387/403及状态链一致：`ep0-d59d1aedde2318e8f2cf696967744048a536c3b79204cbc6c0fb832972054b53.execution.bin`。其150条trace无丢弃/非法记录；两个ISO post均3072字节、result0，ownership ledger报告两个ISO URB终结。

关联生命周期`ep0-life-07166a8436d784ddb2de333f614fa3d9.bin`有27条有效记录，明确joined_context与上述boot/session一致，末条main_return/result0。外部primary与EXE3内嵌primary一致，设备回执报告commit已确认。设备trace只提供状态/序号等字段，未绑定全部168字节STATUS；来源认证、物理运行认证及主机/设备跨时钟对齐不因此提升。

## 只读回收与未归因材料

用户确认完全关机后，按UUID核对SD身份、只读挂载并回收91份原件，随后安全弹出。相对此前75件基线新增16份：5份EXE3、5份primary、6份生命周期；仅logfile.txt变化，74份既有非log原件保持，8份ERPT保持且无新增ERPT，四项部署文件匹配。

其他4份新增EXE3不含本次113/129控制链，各自的primary和正常生命周期关联已保存。不能据新增文件数量推断用户开机次数。

另有`ep0-life-39fdefe5d14bfdecba94b91f5bc0e0f2.bin`仅含4条有效前缀，末条quiet_enter，无joined_context和终结记录。当前无法归因于本次，也不能证明与本次无关；作为未归因证据保留，不能视作正常关闭。

此前81首轮缺少完整after STATUS，具体失败字段仍未知。本次两个count0终态通过支持了修正后的兼容政策，但不能恢复旧缺失原件或确认旧失败唯一根因。

## 已有时间线能回答的问题

采用本次记录的Mach timebase125/3，按向上取整转换；以下均为同一主机时钟间隔，不是USB总线时序认证。

| 区间 | 实测间隔 |
| --- | --- |
| prepared至首轮STATUS意图 | 1.473509秒 |
| 第一轮saved至第二轮STATUS意图 | 1.476301秒 |
| 两轮触发 | 1.638889秒 |
| 两轮ISO submit至回调 | 151.534 / 151.615毫秒 |
| 两轮epoch保存 | 2.320 / 1.041毫秒 |
| 两轮ISO enqueue | 0.318 / 0.343毫秒 |
| 两轮控制触发至回调 | 3.806 / 4.215毫秒 |
| 最后观察窗口 | 1.581771秒，满足最低250毫秒 |

冻结源码调用链还显示：每个coordinator guard先直接verifyScope，再经permit.result→healthy→verifier block再次verifyScope；两条路径均进入verifyCore。首轮保存后、第二轮STATUS前至少经过三处guard，即**至少六次完整校验**。这是静态调用次数推导，没有独立的运行时计数或单次哈希耗时；轮间区间也含调度及其他工作，不能全部归因于哈希。

当前每1毫秒配置的timer并不保证1毫秒运行一次。无在途IO时，tick/result/finalStatus会触发完整文件校验；在途期间跳过完整哈希。保存后第二轮刻意等待后续poll。因此本次两轮成功不能视为连续包流；末尾观察也不证明回调排空。

下一项优先在电脑上整理独立候选：消除同一决策内重复完整校验及状态getter隐藏哈希，保留每轮arm前与最终封存的明确完整校验，记录校验次数和起止。卡基线、来源、历史或作业变化仍须在下一次ISO前拒绝；许可不能重新消费，错误STATUS仍须先留证，不读取活跃IO缓冲区。不能用“一次缓存”替代这些检查后宣称全程未变。

电脑可以验证上述调用和拒绝接线；修改后的真实轮间延迟、更多轮SDK复用及持续流行为，需要新的有界实测问题、当前91件基线、全新范围与新单次授权。本次不创建新范围或续发许可。

## 封存索引

以下路径相对`private`，摘要为对应SHA256SUMS摘要。

| 材料 | 路径或摘要 |
| --- | --- |
| 实际运行 | `runs/A-two-epoch-cfa8f217-d65c-4365-989a-ae2b6b712dea` |
| 主机独立收集 | `analysis/A23-live75-first-live-host-20261022`；`9eb12350b4ca98b94785556f299c59da36ecef77afa3e299e9e43caea4d16291` |
| SD91原件 | `card-cycles/20261022-live75-first-read`；`2865ffdd86c2c6a246e1e8381371a2d1c07abbdb58e4ff72b29c327b005fbd75` |
| 回收命令与回执 | `analysis/A23-live75-first-live-read-20261022-r1` |
| 唯一设备关联与负对照 | `analysis/A23-live75-first-live-analysis-20261022-r1`；`5de3fdf9c91af7524b11897835f526c80c788e6b797fa40e96fcf5758889f22d` |
| 时间线算术 | `analysis/A23-live75-timing-analysis-20261022-r1`；`862c3ef7e031e982d0e6254696a3aa944cfa04b2228c7f1e4a080eb52340391b` |
| 重复校验调用图 | `analysis/A23-live75-guard-map-20261022-r1` |
| 本次结果交接 | `analysis/A23-live75-first-live-closeout-20261022` |

597来源、旧49/65账本、旧81 namespace与失败记录、失败修卡owner/state及本次113 namespace都保留原件。新增SD回收使旧75件候选失去“当前基线”资格，后续仅可做归档验证，不再调用旧候选的当前scope检查或再次启动脚本。
