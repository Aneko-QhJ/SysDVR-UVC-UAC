# 新接口第一次实际空窗口（2026-10-12 19:41，Asia/Shanghai）

后续：控制广播审计已修正，同一原始证据重审完整性通过；原拒绝记录保留，政策仍未接受。见[重审说明](IOUSBHOST_CONTROL_TRACE_REVIEW.md)。
后续：19:54已回收完整设备日志并安全推出，控制广播记录需离线审计，见[读卡核验](IOUSBHOST_FIRST_EMPTY_CARD_REVIEW.md)。以下为19:41主机观察时记录。

匹配修正和执行环境修正后，已执行一次真实 IOUSBHost transaction 无 TD 空窗口。
主机观察完整：唯一接口、两次有效原始 STATUS、一次帧号、一次提交和一次 callback，
核心包写盘核验后资源关闭，接收器退出0。没有 abort、重复请求或设备 burst trigger。
完整设备日志尚未回收；原生空槽政策与基线接受均未放行。

| 原始观察 | 结果 |
| --- | --- |
| transaction记录 | 960 × 28 bytes；requestCount均192，offset均为槽号×192，options均0 |
| 槽状态 | 960条均0x00000000；未见Underrun或NotSent |
| completeCount | 全部0；这不是接收192bytes成功的证明 |
| timestamp | 960条均非零；保留原始SDK值，不据此证明总线相位 |
| 整体结果 | overall0；一次callback，无超时/断开/迟到事件观察 |
| raw | 184320bytes，全零，未见有效包 |
| STATUS | 前后各168bytes，原始内容相同，与journal逐字节绑定 |
| 帧号与提交 | currentFrame22076973，firstFrame22077037，lead64 |
| 软件预算 | query12.834µs，最终采样年龄161.542µs，enqueue调用370.709µs；软件条件通过 |
| 退出 | 保存/ack后关闭，退出0；无资源持有；250ms关闭后观察不证明SDK排空 |

新API的空槽结果与旧backend的Underrun不同，先保留这个差异，不能直接套旧政策，
也不能据此解释旧NotSent或native/raw分歧。分析器 host_observation_complete=true 只表示
主机证据完整；hardware_verified、usb_strict_pass、baseline_accepted、allow_next_burst、
empty_status_policy_verified、callback_drain_verified 均为false。

## 证据与剩余步骤

run：private/runs/A-A23-HS-IOUSBHost-no-td-20261012-114122-20d2bc8d/，14文件SHA256核验通过。
构建：private/host-A23-IOUSBHost-no-td-unsandboxed-20261012-114056/，包含当前源码快照。
准备及独立记录检查：private/analysis/A23-IOUSBHost-unsandboxed-test-20261012-114056/。
执行使用已批准的沙箱外环境；凭据已消耗，stage=captured_logs_pending，remaining=0。
前几次匹配/打开失败以及沙箱内外准备对照保持原始证据，不改成传输成功。
原串行阶段和次数不变，设备仍A23，UAC/PCM禁用，本轮SD访问0。

接下来关闭Switch并回收SD卡上的完整本次启动设备日志，再与两个STATUS及控制记录核对。
应确认A23/BuildID安装、无设备TD/提交/终结、两次STATUS及日志完整性，然后冻结新的hardware
collection，解释并定义新接口的空槽政策。只回收日志，无需给SD部署新文件。
当前Mac没有可用的该SD挂载，不能用旧日志或Mock日志补齐实机证据。
完成这些工作前不追加burst、第二窗口或串行测试。

```sh
# 仅审计保存的主机证据，不访问USB。
python3 research/usb-ds-iso/tools/analyze_io_usb_host_hardware.py run \
  research/usb-ds-iso/private/runs/A-A23-HS-IOUSBHost-no-td-20261012-114122-20d2bc8d
```
