# ALT1 端点安装 patch（2026-10-27）

## 根因

HOS `usb:ds` 的 `FUN_000295d0` 在 bus state 变为 Configured 时，为每个接口/速度解析配置
描述符并安装端点。四个 alt 块（alt0..3 × HS/SS）都把过滤条件写成了
`if (bAlternateSetting == 0)`，因此 **只有 alt0 的 endpoint descriptor 会把
`entry+8` 置 1**。alt1-only 的端点虽然能 `RegisterEndpoint`、能 ACK
`SET_INTERFACE(1)`，但 `PostBufferAsync` → `FUN_0002a330` 看到 `entry+8 != 1`，
返回 `0x2628c`，URB 不分配。

alt0+alt1 变体之所以能 post，是因为 alt0 的同一地址端点先被装好；alt1 只是复用了那个
entry。alt1-only 没有 alt0 入口，所以永远不可用。

## Patch

把 8 个 alt0 过滤分支（`cbnz w9`，编码 `35ffff09`）改成 NOP（`d503201f`）：

| 地址 |
| --- |
| `0x29694`、`0x29ad4`、`0x29ba4`、`0x29c88` |
| `0x29d54`、`0x29e38`、`0x29f04`、`0x29fe8` |

- Build-ID：`AD8D36F2029822A4C498F055ADBDAA789EB913C6000000000000000000000000`
- 模块大小：`0x369000`；原始 NSO SHA256：`08e0c60a…`
- 运行时通过已有 `ISO_RUNTIME_PATCH` 安装；入口仍是 `_logIsoTarget` 的
  `svcDebugActiveProcess` + `isoApplyRuntimePatch`。
- IPS 版本已生成（`private/patches/alt1-nop-20261027/.../AD8D….ips`，SHA256
  `f471eb84…`），但本次实测 **没有生效**；runtime 版本 `result=0`。loader 的
  `exefs_patches` 路径目前不可作为该补丁的部署方式。

## 证据

设备日志（1945B，SHA256 `eae883eb…`）：

```
ISO usb module[0] BuildID=AD8D… base=0x2150200000 size=0x369000
ISO runtime patch result=0 record=7 last-rc=0x0
ALT1 probe iface=2 ep=0x84 hs=25 ss=31
ALT1 SET_INTERFACE 1
ALT1 trigger rc=0x0 urb=388
```

Host：

```
set_alt(1): 0
trigger: 0
bulk(0x84): 0 transferred=64  data=41 4c 54 31 …
status: alt=1 state=2 post=0x00000000 urb=388 completed=1 transferred=64 urb_status=3
```

结论：**alt1 的 bulk 端点安装/选择/传输已经打通。** 这是 usb:ds 的 alt0-only
过滤 bug，不是宿主问题，也不是 `RegisterEndpoint` 本身失败。

## ISO alt1 实测（22:12）

- NSP `9120570d…`：vendor interface 2，alt0 无端点，alt1 `EP0x83` ISO、MPS256、
  bInterval4。
- runtime payload：A23 base burst producer（684B cave + hooks）+ 8 个 NOP，共 30 条。
- 设备日志：`ISO runtime patch result=0 record=29`；
  `ISO submit seq=1 speed=3 length=3072 rc=0x0 urb=387`；
  `ISO seq=1 URB=387 requested=3072 raw-count=3072 status=3`。
- Host：`iso-probe --burst --alt1` 收到 16/16 个 192B 包，payload/completion 都 verified，
  exit 0。
- 结论：**NOP patch + A23 burst producer 在 alt1 ISO 上工作。** 这是 16×192 的一次性诊断
  burst，不是连续 PCM；UAC 标准宿主仍未验证。

## 边界

- bulk alt1 与 ISO alt1 的一次性 burst 都已验证；连续 PCM、UAC 标准宿主尚未验证。
- 补丁是全局的：所有接口的所有 alt 端点都会在 Configured 时安装。需要评估对其他
  `usb:ds` 客户端、端点资源和重复地址的影响；产品化应收窄到目标接口或改到
  `SET_INTERFACE` 时按需安装。
- 地址依赖 Build-ID；每个 HOS 版本都要重新定位这 8 个 filter。
- runtime patch 依赖 `dmnt`/debug attach；IPS 路径未成立。

## 下一步

1. **ISO alt1**：把这条 NOP 与 A23 的 ISO producer patch 合并，针对 UAC AS 的
   `0x84`/alt1 或一个 vendor ISO `0x84` 做最小验证。
2. **UAC alt1**：用 P0 的 AC/AS 描述符 + NOP + ISO producer，接 Linux
   `snd-usb-audio` 做标准宿主枚举/播放。
3. **收窄 patch**：从全局 NOP 改为只对目标接口/端点在 `SET_INTERFACE` 时安装，
   避免影响其他 usb:ds 使用方。
