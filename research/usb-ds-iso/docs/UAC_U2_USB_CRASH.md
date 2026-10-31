# U2 v11 `usb` sysmodule fatal（2026-10-31 22:40）

## 结论先行

- Debian/Linux raw claim 成功；第一次 raw 16×192 transfer 完成
  （`valid=16 bad=0`），但 **`bytes=0`**（16 个包 `actual_length=0`）。
- 第一次 raw 尝试消耗了 v11 的 one-shot post；后续 `--trigger-first`
  没有新 post。
- 随后启动游戏时，系统 **`usb` sysmodule**（Program ID
  `0100000000000006`）发生 fatal **2162-0002**。
- crash 发生在 `usb` 模块，不是 `00FF0000A53BB666`；但 stack 落在我们
  U2 patch 所在的 request queue 区域附近，**不能排除 patch/残留 U2 状态
  的参与**。在解释前不再部署 U2 或上机。

## crash 关键字段

| 字段 | 值 |
| --- | --- |
| result | `0x4A2`（2162-0002） |
| process | `usb`，Program ID `0100000000000006` |
| PC | `0x7203419254`，模块 base `0x7203400000` → offset **0x19254** |
| 指令 | `svc #0x21`（syscall stub） |
| stack returns | `0x19cd0, 0x194f4, 0x975c, 0x9444, 0x9514, 0x9534, 0x9560, 0x40d0, 0x3ce0, 0x2c584, 0x2a3f4, 0x2a464, 0x28378, ...` |
| 相关 patch 地址 | `0x2c158`、`0x30364`、`0x30898`、`0x29xxx`、cave `0x68d54` |
| crash/fatal | `private/runs/UAC-u2-v11-debian-raw-20261031/crash/` |

`0x2c584` 位于 `usb.elf` 的 `0x2c520` 函数内（unmap/submit 路径）；
`0x2a3f4`/`0x2a464` 在 `PostBufferAsync` 路径附近。该区域与 U2 的
install/queue patch 相关，但 crash PC 本身是 syscall stub，需进一步
对照调用栈和用户指针。

## 时间线

1. Debian 13.7 ARM64 VM 安装完成，`uac-raw-probe` 编译。
2. Parallels 手动连接后 Linux 看到 `1209:ca57`。
3. `--claim-only`：`auto_detach=0`、`detach[3]=0`、`claim[3]=0`。
4. 完整 raw：`alt1=0`、`submit=0`、`set_cur=3`、`transfer status=0`、
   `valid=16 bad=0 bytes=0`。
5. 再跑 `--trigger-first --delay-ms 30`：packet0 0 字节、其余 bad
   （one-shot 已消耗）。
6. 启动游戏 → `usb` sysmodule fatal；crash/fatal/erpt 报告生成。
7. 读卡：恢复 `52069a44…`、删日志/新报告、安全弹出。

## 下一步（离线）

1. 对照 `usb.elf` 的 `0x2c520`/`0x2a3f4`/`0x2a464` 与 29 条 patch，
   确认 crash 是否由 U2 patch 破坏正常 USB 路径。
2. 补 raw per-packet 诊断/多 transfer 时序（工具已支持
   `--transfers`、`--trigger-first`、`--delay-ms`，未再上机）。
3. 若 crash 与 patch 相关，先回退/隔离 U2 patch；未解释前不再上机。
