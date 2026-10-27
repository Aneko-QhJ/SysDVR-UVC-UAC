# A23 独立故障诊断落盘候选（2026-10-14）

新隔离候选接入**双线程join成功、Finish拒绝后的一次诊断保存**。正常/诊断文件路径独立；
6656byte最大诊断完整写入、读回后才commit。诊断保存成功仍sleep保留USB、Core和线程句柄，
不发布清理授权。27项实际adapter回放、14项实际退出代码回放、95次旧诊断文件回放和4项容量
检查通过ASan/UBSan；343项相关Python回归无跳过。两窗口配置各完整链接10对象libnx ELF。

本轮只在电脑执行服务模型，未执行ARM ELF、打包/部署或访问USB/SD。生产、旧候选/封存与
三份票据保持；burst仍failed_no_retry/remaining0，根因未知。上一阶段
[联合预检候选](A23_BOUNDED_CANDIDATE.md)保持原样，新source/recipe另建目录。

## 真实main的分支

[构建工具](../tools/build_a23_diagnostic_sink.py)复制最新封存候选，新增
[诊断文件adapter](../device/ep0_diagnostic_file.c)、[独立容量策略](../device/ep0_diagnostic_sink.h)，
并只在生成的main副本修改Finish失败分支。ISO/EP0 handler、17条请求预算、旧正常sink、
清理gate及EP0DIA1字节格式不改；recipe绑定新输入、旧manifest、编译器和libnx/FS头文件。

| main结果 | 保存行为 | 线程句柄与USB/Core清理 |
| --- | --- | --- |
| 任一个threadWaitForExit失败，或exporter身份查询失败 | 无保存，先于读取owner/guard拒绝 | 保留，sleep |
| 双join成功但Finish拒绝，已冻结/停止/正确交接的fault或pending | 尝试保存一次独立诊断 | 保存成功/失败均保留，sleep |
| 双join成功但owner未启动/未停止/未交接 | 序列化拒绝，不访问FS | 保留，sleep |
| Finish成功 | 原正常capture一次保存 | 仅保存成功后close线程、发布授权，回调清理一次 |
| 正常capture保存失败 | 保留原capture/文件，无诊断回退或重试 | 保留，sleep |
| 未启动/live异常回调 | 原子gate拒绝claim，不读账本/保存 | 保留，sleep |

adapter在检查两个join Result之后才调用normal bytes/owner/guard访问器。它要求没有正常
capture可用，再交给原ep0_diagnostic_capture核验：stopped/joined/frozen、无processing、
正确writer/exporter及fault/pending/denial/loss条件。存储只读取CPU元数据和trace，不读取URB
payload或guard范围指向的设备buffer，不清fault/pending、不补report或cancel、不授权清理。

join、身份和终结状态仍是API观察/模型输入，不是来源认证。native用访问器断言验证失败join
没有触及状态；实际线程、DMA/HOS及异常回调可达性仍未验证。

## 文件边界

[诊断API](../device/ep0_diagnostic_file.h)使用固定6656byte缓冲。EP0DIA1最大128byte头+
16槽×16byte账本+128byte inner头+128条×48byte记录=6656；旧正常EP0OWN1上限6640保持。
新一次sink拒绝0或6657byte，在任何create前失败。最大样例注入16个pending身份、128条
有效device-state记录及dropped1，独立decoder接受诊断；它用于容量验证，不模拟真实请求链。

文件名为`/ep0-<boot16+session16的64字符hex字符串>.diagnostic.bin`；正常文件仍用
`.capture.bin`。nonce取自已交接trace，无真实唯一性/随机源验证。create失败或冲突不删除、
截断、覆盖或重新命名。打开失败保留可能已创建的文件；所有已打开文件和本次SD filesystem
句柄会关闭。这里关闭临时文件句柄不表示释放仍有待完成传输的USB/Core资源。

一次操作顺序：create/open→write→flush→size恰等于长度→循环读回并逐字节比较→file close→
commit→filesystem close。ABI仍采用libnx write无返回byte count；静默短写必须被完整读回
检测。短读可继续，零count、超过请求count、错误size、损坏数据和服务错误均拒绝。

- commit失败时`content_verified=true`、`commit_acknowledged=false`，原字节和文件保留。
- 磁盘文件可被decoder解析，只能说明内容格式；不能证明commit成功或断电持久性。
- fsOpen失败也消费唯一尝试；已经尝试之后的第二次调用没有任何FS调用。
- 无删除、自动重试、恢复默认文件名或清理授权。失败结果留在内存sink observation；
  EP0DIA1不新增文件服务错误字段，因其序列化发生在保存之前。

## 验证与交付

[16项Python检查](../tests/test_a23_diagnostic_sink.py)覆盖真实adapter及抽取的main退出段/
__appExit、failed join读取边界、最大容量/旧上限、collision/错误保存、正常路径和文件读回。

- 27项adapter场景：pending/fault、live/unstarted/wrong exporter、两join失败、healthy、
  最大文件、短读和文件服务各阶段故障。owner/guard逐字节前后比较一致；repeat不重试。
- 14项退出场景：抽取生成main的双join/Finish/save/授权段与原回调，线程/FS/关闭服务注入。
  pending保存成功或commit/collision/fs-open失败均停在JOINING，线程/USB/Core/sm关闭数0。
  正常分支两线程close、USB/Core/sm各1；重复回调不再清理。未执行真实main启动或线程调度。
- 19份旧真实handler回放产生的诊断分别做5种sink回放，共95次；成功/commit失败的内容
  与旧文件逐字节相同，独立decoder保持旧recipe关联，不重标成新candidate产生的会话。
- 4项独立长度策略检查；总140项native检查/回放。相关343项Python回归无跳过。
- 默认时间窗口关闭与30秒样例各10对象完整libnx ELF，真实main和FS IPC符号存在；只链接。
  未被main调用的诊断字节访问器可被优化链接删除，native单独验证它的输出。

`private/analysis/A23-diagnostic-sink-review-20261014`封存生成源码/ELF/recipe、native模型、
独立捕获/decoder、audit与SHA256SUMS。`private/analysis/A23-diagnostic-sink-validation-20261014`
另封存回归、当前源码/生产快照、旧证据/票据/文档链接核验与独立validation。

```sh
python3 research/usb-ds-iso/tools/build_a23_diagnostic_sink.py --output /private/tmp/A23-diagnostic-sink-new
```

输出必须为新目录。没有新NSO/NSP、设备运行入口或测试次数。

## 还需继续的研究

admission的trace_refusals/bound_violations/stop_skips等只留在内存与native JSON；旧DIA1
reason4仍同时表示身份容量/trace容量。后续应另定义版本化诊断扩展及独立decoder，不覆写
DIA1/旧封存，并将文件保存失败与诊断内容关联。CRC、nonce和recipe均不认证运行时来源。

初始化失败仍需要单独资源审查，不能用owner尚未启动推断没有服务资源：当前CoreInit可先
fsInitialize再CaptureInitialize，后者失败时g_coreInitialized尚未置位，CoreExit会直接返回；
UvcDeviceInitialize的原cleanup仍内部调用usbDsExit；LaunchThread的threadCreate/threadStart
错误走R_THROW，是否进入回调没有实机证据。当前原子gate阻止未授权回调清理，但不覆盖这些
初始化函数内部的早退/cleanup。此次不设计新回滚或声称异常退出安全。

真实DMA终结、ID重用、join/调度/停止延迟、FS提交持久性和trace成本未测；128条/16槽不证明
完整枚举/协商有足够容量。当前remaining0，根因未知，不能把候选主动拒绝seq0当作首次SDK
burst失败原因。下次优先审计初始化/启动失败各阶段及诊断扩展字段，仍只做电脑研究。
