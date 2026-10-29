# UAC U2：alt1 端点安装与一次 ISO burst（离线准备，2026-10-30）

> 目标：验证 AS alt1 EP `0x84` 的端点安装和一次 16×192B ISO burst。
> 当前只完成 26 条基础 payload（18 描述符 + 8 NOP）与 host 入口；
> **producer 尚未迁移，未部署、未实机**。

## 现状

- 26 条基础 payload：18 条描述符 + 8 条 alt0-filter NOP。
  - header：`private/analysis/UAC-u2-base-20261030/uac_u2_base_payload.h`
  - NSP：`private/analysis/UAC-u2-base-20261030/build/outputs/exefs.nsp`
    87461 B，SHA256 `abdaff618403bcea9aab8adfcc6dac2bb474f45ec5536c6e9d57289e2e64e607`
  - defines：`-DUAC_HOST_PROBE -DUAC_U2_BASE_PATCH -DFILE_LOGGING`
  - 应用侧 `UAC_U2_BASE_PATCH` 在 `usbDsEnable()` 前应用；失败即拒绝启用。
- host 入口：[uac-burst.c](../host/uac-burst.c)
  - claim interface 3，alt1，发 `SET_CUR(48000)` 触发，然后读一次 16×192B。
  - 已编译；没有 producer 时预期超时，不作为通过。
- **producer 尚未迁移**：A23 的 `iso_burst_patch.S` 硬编码 EP `0x83`/MPS256；
  直接用于 `0x84` 会被 `iso_enter` 的端点检查拒绝。

## NOP 影响评估

- 8 条 NOP 去掉 `FUN_000295d0` 的 alt0-only 过滤（`cbnz w9` → `nop`），
  地址 `0x29694/0x29ad4/0x29ba4/0x29c88/0x29d54/0x29e38/0x29f04/0x29fe8`；
  本机 usb.elf 已逐条核对。
- 效果是 **全局的**：bus Configured 时所有接口/速度的 alt 端点描述符都会把
  `entry+8` 置 1。UAC build 的接口为 VC(0)、VS(1, EP0x82 bulk alt0)、AC(2)、
  AS(3, alt1 EP0x84 only)；没有重复端点地址，端点数量也很少，当前风险可控。
- 仍需注意：全局安装会影响其他 `usb:ds` 使用方；产品化应把 NOP 收窄到目标
  接口/端点，或改为 `SET_INTERFACE` 时按需安装。

## producer 迁移方案（未实现）

1. 复制 `patches/iso_burst_patch.S` 为 `iso_burst_uac84.S`，只改端点常量：
   - 端点检查 `0x01000183`（addr 0x83, ISO, MPS256）→ `0x00C00184`
     （addr 0x84, ISO, MPS192）；
   - 完成回调 `mov w1, #0x83` → `#0x84`；
   - report 过滤 `cmp w8, #0x83` → `#0x84`。
   - 16×192B、bInterval4、HS 检查保持不变。
2. 在 `0x68d54` 组装 cave（≤684B），生成 30 条编辑：
   cave + 分支 `0x30364/0x30898/0x2cbe0` + 18 描述符 + 8 NOP。
3. 应用侧新增 `UAC_U2_PATCH`（或扩展现有 U2 base），在 `usbDsEnable()` 前
   应用 30 条；BuildID/size 仍校验 `AD8D36F2…`/`0x369000`。
4. 触发：`SET_INTERFACE(1)` 或 alt1 后的 `SET_CUR` 里，向 EP `0x84` post 一个
   4KB 对齐的 3072B 缓冲（`g_audioEndpointBuffer`），flush cache 后 ACK；
   host `uac-burst` 已在 alt1 后发 `SET_CUR` 并读一次 16×192。
5. 离线验证：逐条 before word、cave 反汇编、分支目标；有条件时用 Unicorn
   回放 producer 的 TRB 构造，再上硬件。

## U2 实机计划（producer 就绪后）

- 一次 boot、一次 burst、不做 PCM。
- 通过：host 收到 16/16 个 192B 包；设备 `posts=1 completes=1 errors=0`；
  无 usb fatal；`SET_INTERFACE(0)` 恢复。
- 停止：无数据、post 错误、fatal、断连；读卡并恢复 `52069a44…`，不重试。

## 边界

- 本文只是离线准备；没有 USB/SD/实机操作。
- 26 条基础 payload 没有 producer，不能证明数据路径；不要把它当作 U2 通过。
- NOP 是全局的；U2 通过后仍需评估收窄方案。
