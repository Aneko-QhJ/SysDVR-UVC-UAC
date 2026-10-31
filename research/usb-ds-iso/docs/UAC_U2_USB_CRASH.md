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

## 16 包 0 字节的时序解释

第一次 raw probe 是 **先 submit、后 SET_CUR**。Linux xHCI 会立即把 16 个
ISO 包排到当前 frame 起的 16 个 frame；而 cave 把 TD 排在
`MFI>>3 + 32`（+32 frame）。因此 host 的 16 个包在设备 TD 之前就完成，
得到 `valid=16` 但 `actual_length=0`，且没有 transaction error。设备侧
第一个 post 仍报告 `3072/status=3`，两者并不矛盾。

下一次 fresh boot 应改用 **trigger-first + delay ~30 ms**（或
`--transfers` 连续 URB 覆盖 +32 frame），而不是先 submit。v11 的
one-shot 已被第一次尝试消耗，所以之前的 trigger-first 结果无效；必须
用 v10 one-shot fresh boot 重测。

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

## 根因假设（离线，待验证）

v11 的 32-post train 在第二个 `PostBufferAsync` 之后 100 ms 超时并
`break`，**没有取消已经提交的第二个请求**：

```c
if (R_FAILED(eventWait(&...CompletionEvent, 100E+6))) {
    LOG("UAC U2 no completion within 100ms seq=%u\n", seq);
    ...
    break;   // 第二个 request 仍 pending
}
```

随后 raw host 恢复 alt0 并关闭 endpoint；usb 模块在 endpoint teardown
时遇到这个 pending ISO request。crash stack 的 `0x2c584` 位于
`usb.elf` 的 `0x2c520`（unmap/submit 路径），`0x2a3f4`/`0x2a464` 位于
`PostBufferAsync` 路径附近，和“pending request + 关闭 endpoint”一致。
**这是当前最可疑的 crash 根因**，比 8 个 descriptor-parser NOP 更直接。

8 个 NOP（`0x29694..0x29fe8`）是全局 alt0-filter；它们位于配置描述符
解析器，会影响所有 USB 设备的 endpoint 解析，是**次要但真实的风险**。
下一版应只针对 UAC 配置/接口放宽，而不是全局 NOP。

## 下一步（离线）

1. **不再用 v11 train 做 raw 测试**；改用 v13 one-shot+cancel
   `5bfcc67a…`（91101 B，29 edits / cave 592B），它只 post 一个 3072B
   请求，并在超时调用 `usbDsEndpoint_Cancel`，不会留下 pending request。
2. raw host 下一轮用 **fresh boot + `--trigger-first --delay-ms 30`**
   （或 `--transfers` 多 URB）匹配 cave 的 +32 frame；测试结束前不要让
   host 恢复 alt0，先确认 completion 已到。
3. 若 v10 one-shot + raw host 仍崩溃，再隔离 NOP/hook（只 descriptor 编辑、
   只 NOP、只 hook 三个对照）。
4. 未解释前不再部署 U2 或上机。
