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
