# 短包首次实测：主机观察通过，设备保存失败（2026-10-27）

本轮已完成配套部署、唯一一次采集、关机后只读回收与分析。主机收到了连续的
16×24 字节包，但设备 capture/EXE3 文件创建失败，整轮未达到严格通过。
次数已消耗，不补试。接收器继续驻留，未授权释放或复用资源。

## 观察与判定

| 项目 | 本次证据 |
| --- | --- |
| 部署 | 新 NSP `42e820…` 与 IPS `b2151b…` 配套写入、回读通过并弹出；其余142件不变 |
| 启动 | 用户确认关机、装卡及USB；实际 WAITING 后才开机，用户反馈到达HOME |
| 次数 | 一次ISO、一次BURST，范围513..528，abort=0，remaining=0 |
| 原生状态 | overall/control/ISO回调为0，128项transaction均为0；control约0.464ms、ISO约47.252ms |
| 数据 | slots8..23连续16包，序号513..528，384字节IS24图样正确；新STATUS长度/URB387/ED核验通过 |
| 设备来源 | 四项部署字节不变；新日志记录short24与runtime patch result=0；LCP1匹配recipe `535606…` |
| 生命周期 | 新LCP1有27条有效记录；video/audio join结果均0、owner finish返回true；最后为retain，reason5 |
| 文件保存 | SD打开均0；capture创建4384字节、EXE3创建5440字节均返回54273 / `0xD401`，保存返回false |
| 完整链 | 新boot/session对应的capture与EXE3均未出现在回收快照，无法检查设备384字节post/ACK/ledger完整关系 |
| 当前主机 | 原观察保存后约125.878秒出现provider interest，另存later-0001；当前stop/fault，不覆盖早先观察 |

本机SDK把 `0xD401` 解码为module1/description106，即 `KernelError_InvalidMemoryState`。
该名称不证明实际失败地址、内核分支或具体IPC原因。原观察只代表采集时的历史结果，
不把关机后的later故障忽略为当前健康。资源仍持有，不据此声称SDK排空或安全交还。

## 准备回归与离线修正

`build_a23_short24_candidate.py` 的设备父树是较早的生命周期候选，漏带了已有的路径容量修正。
实际短包候选仍有96字节局部path及64字节静态life_path；已链接SDK使用769字节路径输入。
这是已确认的构建基线回归，也是保存失败的候选解释；尚未证明此次内核错误的确切根因。
此前“8条指令变化”只描述控制器，不能据此声称完整设备相对最近实测固件仅改变包长。

新增离线入口 `tools/build_a23_short24_path_span_candidate.py`，以已封存的路径修正版为父树，
重新生成短包设备。最终14对象ELF通过编译，5个已链接静态路径对象各769字节、总3845字节，
均位于BSS。相对本次实测设备仅4份路径源、路径头和recipe改变；短包控制器及runtime载荷
逐字节相同。新recipe为 `279586c43803e17d85a5cb0341087e4dad565fda3883beae1df23f591e47b860`。

专项CPU审计7个场景通过：normal/diagnostic正常保存、primary/EXE3创建失败保留、LCP完整
跨度保存，以及旧normal/LCP对象的ASan越界反例。模型读取完整769字节；固定版本检查尾部
清零。r1负例最初在填充断言处提前拒绝，未走到ASan对象边界；r2仅对负例取消填充断言，
确认两个旧对象均报告buffer-overflow。r1失败材料保留，最终采用r2。

该修正没有复现Switch内核错误，没有打包、绑定新接收器、写卡或追加实测。卡上仍是本轮
已部署的short24旧路径版本，最后已安全弹出。后续先准备修正版配套包/新recipe入口，核验
路径容量及相对本次设备的变化，再另定硬件范围；不复用513..528或旧票据次数。

## 证据与交接

- 部署前144件：`private/deployments/20261027-short24-paired`，清单 `f29adabd…`。
  相比此前138件基线，仅新增6份ep0记录和logfile更新，四项部署文件一致；新增旧记录不归入本轮。
- 主机原件：`private/runs/A-short24-513-20261027`，observation清单 `85d03e3e…`。
  PID22208 / exec session2564驻留；不要自动kill、重启入口、释放或复用缓冲。
- 只读145件：`private/card-cycles/20261027-short24-513-read`，清单 `5f823399…`。
  相对部署后新增1份LCP1、更新logfile；UUID `37614F76-3E12-3470-B5C8-52B5A449C213`，只读挂载后核验弹出。
- 首次实测分析和主机时点副本：`private/analysis/A23-short24-first-live-20261027-r1`，
  清单 `e21b3aecb0fa0bd0406b2de47e706bf6a1e689cb193db4fe0335df68e7bc6018`。
- 离线修正：`private/analysis/A23-short24-path-span-candidate-20261027-r1`，清单 `d5f18629…`；
  审计：`A23-short24-path-span-audit-20261027-r2`，清单 `7b168e31…`。
- 新mutable状态：`private/analysis/A23-short24-once-20261027-state.json`，
  `host_valid_device_save_failed_no_retry`、remaining0、acquisition_enabled=false、日志pending=false。
  已回收不表示缺失的capture/EXE3链已补齐；旧票据、旧10个消费namespace及原封存材料保持。

本次不证明持续音频、PCM内容、UAC互操作、时钟同步、缓冲复用、回调排空或旧超时根因。
