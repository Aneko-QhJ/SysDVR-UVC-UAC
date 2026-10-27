# ALT1 vendor 探针（2026-10-27）

目标：在**不引入 UAC / ISO / IPS**的情况下，回答一个最小问题——
`usb:ds` 是否会把一个只出现在 alt1 的端点装好，宿主 `SET_INTERFACE(1)` 后能否完成一次传输。

## 问题卡

| 字段 | 内容 |
| --- | --- |
| 问题 | vendor 接口 alt1 上的 bulk IN `0x84`，能否被 `RegisterEndpoint` 安装、被宿主 `set_alt(1)` 选中，并完成一次 64B 读？ |
| 变化 | `ALT1_PROBE` build：第 3 个 vendor 接口，alt0 无端点、alt1 有 `0x84`；无 `ISO_PROBE`、无 IPS |
| 判别 | `set_alt(1)` 返回；`ALT1_PROBE_STATUS.post_result`/`state`/`urb_status`；bulk 是否收到 `ALT1` 图样 |
| 上限 | 一次 boot、一次 `set_alt(1)`、一次 trigger、一次 64B 读；不重试 |
| 停止 | `set_alt` 失败、post 失败、bulk 超时、设备不枚举、未知所有权、证据容量不足 |

## 产物

| 文件 | 路径 / SHA256 |
| --- | --- |
| NSP（含 `/logfile.txt` 日志） | `/tmp/alt1-probe-log/exefs.nsp`，`7fa38c98defa87eaa4bbec7e42628e890e1928d53bc305cb6a0180eca6103b60` |
| NPDM | `/tmp/alt1-probe-log/exefs.npdm`，与当前卡上 NPDM 逐字节相同 |
| Host | [alt1-probe](../host/alt1-probe)，libusb，`a7e4ca8963314317ef18887192d138c2e15c016672a99e07a5b2e71dc26da35b` |

- 构建：`make -B -j1 OUTPUT_DIR=/tmp/alt1-probe-log DEFINES="-DALT1_PROBE -DFILE_LOGGING"`。
- 只替换 `atmosphere/contents/00FF0000A53BB666/exefs.nsp`；`boot2.flag`、`toolbox.json` 不变。
- **不需要 IPS**。如果卡上还有旧的 usb IPS，必须移到回滚目录；否则 loader 可能在启动时打
  usb:ds，污染这次 alt1 结果。

## 卡操作

1. 完全关机，插入 SD 卡，确认卡身份。
2. 只读列出 `atmosphere/contents/00FF0000A53BB666/`；备份 `exefs.nsp`、`logfile.txt`
   和任何 `.ips` 到 `private/deployments/20261027-alt1-probe/rollback/`。
3. 写入新 `exefs.nsp`，逐字节回读 SHA256；移除/改名旧 IPS；同步并安全弹出。
4. 用户装卡、接 USB、开机；sysmodule 约 20 秒后接管 USB。
5. 运行 `./research/usb-ds-iso/host/alt1-probe`，保存 stdout。

## 首次结果（2026-10-27 20:45）

| 项 | 观察 |
| --- | --- |
| `claim_interface(2)` | 0 |
| `set_alt(1)` | 0（宿主接受 alt1） |
| trigger | 0 |
| bulk `0x84` | `-1` / `LIBUSB_ERROR_IO`，0 字节 |
| status | magic `31544c41`、alt `1`、state `3`、post `0x0002628c`、urb `0`、triggers `1`、reports `0` |

判定：**alt1 控制路径被接受，但端点 post 失败，数据路径没有建立；本轮不通过，不重试。**
`triggers=1` 说明 trigger 进入了 handler 且端点会话非空；失败点在 `PostBufferAsync`，
不是控制请求本身。`post=0x0002628c` 是 usb:ds/IPC 返回码，具体名称待 log/错误表核对。

设备日志补充（`/logfile.txt`，1388B，SHA256 `e09ad931…`）：

```
ALT1 probe iface=2 ep=0x84 hs=25 ss=31
ALT1 SET_INTERFACE 1
ALT1 trigger rc=0x2628c urb=0
```

- `ALT1 probe iface=2` 说明 `_setupAlt1Probe` 成功：alt1 描述符追加、
  `usbDsInterface_RegisterEndpoint(0x84)`、`EnableInterface` 都返回成功；端点会话存在。
- `ALT1 SET_INTERFACE 1` 说明客户端 alt1 状态机确实执行并 ACK。
- 失败点只在 `usbDsEndpoint_PostBufferAsync`：`0x2628c`、`urb=0`。
  `0x628C` 在公开错误表中是 Usb(140)/49 `ResultUsbEndpointAlreadyOpen`；
  `0x2628c` 额外带 bit17，具体描述码 305 未在表中，暂不命名。

结论：**alt1 的注册和控制路径可用，数据路径在 post 处失败。** 不是“端点没注册”，
而是“alt1 选中后端点不可 post/未被激活”。下一步是区分“端点在 alt0 就不可用”与
“alt 切换导致不可用”。

证据：`private/runs/A-alt1-probe-20261027/`（`host.txt`、`logfile.txt`、`manifest.json`）。

下一步：先用同一 NSP 做 host-only alt0 测试（不 `set_alt`，trigger+status），
判断端点是否在 alt0 可用；若仍失败，再做 alt0 端点变体或 patch。
不要重复同一次 alt1 探针。

## alt0 对照（2026-10-27 20:50）

同一 NSP，不 `set_alt`，直接在 alt0 trigger：

| 项 | 观察 |
| --- | --- |
| claim | 0 |
| `set_alt(1)` | skipped |
| trigger | 0 |
| bulk `0x84` | `-5` / `LIBUSB_ERROR_NOT_FOUND`（alt0 描述符没有该端点，预期） |
| status | alt `0`、state `3`、post `0x0002628c`、urb `0`、triggers `1` |

结论：**alt0 与 alt1 的 post 都以 `0x2628c` 失败。** 所以不是“`SET_INTERFACE(1)` 把端点
关掉”，而是“alt1-only 描述符注册出的端点从未成为可用的控制器上下文”。bulk 的
`NOT_FOUND` 只说明 alt0 没有该端点，post 结果才是关键。

下一步：把同一个 bulk 端点同时放进 alt0（`ALT1_PROBE_ENDPOINT_ALT0`），先测 alt0，
再测 alt1；这样才能区分“descriptor walk 需要 alt0”与“alt 切换仍会失效”。

## alt0 端点变体（2026-10-27 20:55）

NSP `c9d1aaa6…`：同一个 bulk 端点同时放进 alt0 和 alt1。同一 boot 先跑 alt0，再跑 alt1。

| 阶段 | set_alt | post | urb_status | bulk | 判定 |
| --- | --- | --- | --- | --- | --- |
| alt0 | skipped | 0 | 3 | 64B，`ALT1` 图样 | **通过** |
| alt1 | 1 | 0 | 3 | `LIBUSB_ERROR_TIMEOUT`，0B | 失败 |

- **alt0 可用**：端点放进 alt0 后，`PostBufferAsync` 成功、host 收到 64B。说明 `usb:ds`
  的 descriptor walk 只把 alt0 的端点装成可用的控制器上下文；仅靠
  `usbDsInterface_RegisterEndpoint`（alt1-only 描述符）不够。
- **alt1 仍不可用**：`SET_INTERFACE(1)` 后设备侧 post 仍成功（urb 404、transferred 64、
  urb_status 3），但 host 的 alt1 bulk 读超时、0B。即端点仍停在 alt0 上下文，
  host 的 alt1 pipe 收不到这批数据；不是 post 失败，而是 alt 切换后端点与 host pipe 不匹配。
设备日志（1796B，SHA256 `70d15218…`）确认：

```
ALT1 probe iface=2 ep=0x84 hs=32 ss=44
ALT1 trigger rc=0x0 urb=388
ALT1 SET_INTERFACE 1
ALT1 trigger rc=0x0 urb=404
ALT1 SET_INTERFACE 0
```

两次 `PostBufferAsync` 都成功；alt1 的失败只发生在 host 的 bulk 读，设备侧没有报错。
这条路径给出了一个**非标准但可工作的 alt0 数据面**；标准 UAC 宿主是否愿意在 alt0
流，仍需单独验证。

下一步：

1. **alt0-only UAC 描述符**：AS 只保留带端点的 alt0（或 alt0 有端点、alt1 无端点），
   用 Linux `snd-usb-audio`/`arecord` 看宿主是否选择 alt0 并收到 PCM。
2. **patch `usb:ds`**：在 `SET_INTERFACE(1)` 时重配端点上下文；需要 usb NSO/Ghidra。
3. **custom host alt0 only**：只能作为诊断，不是免客户端产品。

## 判读

| 观察 | 含义 | 下一步 |
| --- | --- | --- |
| `set_alt(1)` 成功；`post_result=0`、`state=2`、`urb_status=3`；bulk 收到 `ALT1` | alt1 的 bulk 端点安装/选择可用 | 再测 ISO alt1（需 ISO producer/patch） |
| `set_alt(1)` 成功；`post_result≠0` 或 `state=3` | alt1 描述符被接受，但端点未安装/不可用 | 读 log，考虑 patch 或 alt0 变通 |
| `set_alt(1)` 返回 `PIPE`/`NOT_FOUND` | 宿主或 usb:ds 拒绝 alt1 | 走 patch/alt0 方案 |
| 设备不枚举 / 视频也消失 | probe setup 破坏了配置 | 读 `/logfile.txt`，回滚，停止 |

## 不证明

- 不证明 ISO alt1、UAC、PCM、持续流、时钟或标准宿主枚举。
- bulk alt1 成功只说明“alt1 端点安装”这一层；ISO 仍需单独验证。
