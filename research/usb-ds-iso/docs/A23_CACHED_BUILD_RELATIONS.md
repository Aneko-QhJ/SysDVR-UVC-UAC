# 缓存构建结构与日志引用关联

后续：[缓存中的entry、receipt与SDK session关联](A23_CACHED_SESSION_LINKS.md)已建立两种binding间的数据联系；原生许可/context和时限仍待核验，注入driver时钟与owner真实时钟不可直接混用。以下保留原阶段。

2026-10-20，承接[构建字节分组](A23_GROUPED_BUILD_BYTES.md)。新增三个来源文件，总数422；原419项与23项保护记录保持原字节。两份既有构建仍冻结392项来源，没有重新编译或执行。

本阶段从分组缓存核对构建内部结构，再关联同一历史模型的92份日志/事务缓存。正常材料满足定义的子集；28个重新计算字节清单及嵌套封存的语义反例拒绝。结果为`consistent_cached_build_subset`，完整SDK链、编译来源、可执行语义及现场认证继续false。

## 已核对的关系

receiver有486份文件，supervisor有395份文件，继续通过原来的4+4组、488+397片校验入口加载。新消费者先重新验证分片和原文件摘要，不直接信任可手工构造的聚合缓存对象。

| 范围 | 从缓存执行的检查 |
| --- | --- |
| descriptor | 字段集合、规范JSON和摘要类型；当前failure模型说明严格匹配，采集/发行/硬件入口均false；声明路径仅词法检查 |
| 冻结成员 | receiver的392来源、71基线成员、5历史成员、12恢复索引逐项重算SHA256；精确文件覆盖拒绝额外成员 |
| 绑定头与binary | 按descriptor字节逐项生成十进制数组摘要，与缓存头文件匹配；binary记录对应descriptor及分片读取的二进制摘要 |
| 基线摘要 | 重新计算71成员原清单摘要，以及69份`card/`内容的大小/摘要清单；匹配descriptor的两种摘要 |
| supervisor | 严格model-only元数据、392来源和二进制摘要；文件集合完整且无额外成员 |
| 两角色 | 完整来源表一致，模型二进制摘要一致；本历史fixture明确复用同一模型二进制 |
| worker与日志 | 外部固定的逻辑构建根、原构建清单和分组目录对应worker；source-marker、envelope、final collection和两份handoff中的构建引用与缓存重算结果一致 |
| scope与entry | namespace scope匹配重建scope；config、entry-current、entry-final中的构建绑定匹配，字段集合、81..112整数范围和授权摘要类型检查通过 |

同时复用既有缓存消费者检查完整日志链、封存、声明关系和两轮事务/STATUS子集。字段`complete`等旧分析结论不能直接升级新结果。源标记中的冻结来源数必须与构建重算数一致；布尔值不能替代计数或序号。

外部链接合同同时固定角色、原构建清单摘要、分组目录摘要、日志原清单摘要和worker声明中的逻辑构建根。消费函数只接收缓存及字节参数。路径只作字符串比较，搬移后不会打开旧路径，也不认证这些路径实际指向的文件或进程。

## 反例与复核

29个场景中正常1个、拒绝28个。反例覆盖receiver成员/表/头/二进制/文件覆盖错误，descriptor额外字段、重复键、路径越界、布尔摘要、权限提升、基线两种摘要错误，supervisor的成员/二进制/权限/覆盖错误，单独有效的来源或二进制角色拼接，以及worker、marker计数、envelope、final、handoff、namespace、entry与布尔序号错误。

每个反例都重新生成分组目录及原文件清单；日志反例还自底向上重建嵌套SHA256SUMS/COMMITTED和事件链。测试要求先通过字节层，再得到指定的语义拒绝类别，避免仅因旧摘要未更新而失败。反例字节由冻结来源、保留的正常缓存和确定性变更函数重建；逐场景保存输入摘要和分析，不为每个反例重复落盘全部分片。

新增15项测试、旧分组14项和旧日志/事务15项回归全部通过，共44项，无跳过。另验证伪造compile.log和非命令内容不会改变内部结构检查：编译记录内容不在认证范围，不能把它当作二进制编译来源证明。

422项来源及独立材料搬移后，全29场景重新生成并与保存分析逐字节一致；三种CLI正确/错误/缺失外部归档摘要分别退出0/2/2。消费者文件打开0，搬移复核进程对原仓库和`/Volumes`文件打开0。Python审计钩子不覆盖CLI子进程，不提供OS能力隔离。

首轮r1把原生entry-current无末尾换行误当成非规范JSON，保留失败诊断；r2进一步暴露误将epoch session绑定当成entry构建绑定的字段假设。最终r3复用既有原生JSON读取规则，并明确只检查config/current/final的entry构建绑定，不改写历史材料。两轮失败的来源、材料和日志独立封存。

## 尚未认证的边界

epoch绑定是SDK session、设备身份和USB描述符摘要；entry绑定是构建及授权回执摘要，两者不是同一schema。接下来必须通过session日志、SDK receipt/snapshot及driver记录建立联系，再核对发行/消费、原生许可/context、时限和250ms观察窗口。本阶段没有证明entry构建与epoch SDK session之间的完整关联。

descriptor中的历史和恢复索引目前只验证成员摘要；尚未重新认证它们的完整业务关系、描述中的历史来源、基线物理状态或编译器。build-command和compile.log为保留原件，未执行或采用其成功声明。完整descriptor语义、编译来源、二进制行为、进程退出认证、回调排空及现场认证均false。

本轮USB、SD、真实SDK、原生执行、固件构建、正式发行及序号保留均0。真实49/65、旧账本、失败修复owner和23项保护记录保持。65已回收、remaining=0，81..112未保留，生产32序号目录未创建，生产采集仍关闭。

最终审查：`private/analysis/A23-build-relations-review-20261020-r3`，SHA256SUMS摘要`52ce13d7e8d8a3b374e7f710eff2d222b8d8ae838ba7d506cb375dc2faad4e34`。

验证与交接：`A23-build-relations-validation-20261020-r1`、`A23-build-relations-closeout-20261020`，以各自SHA256SUMS和COMMITTED为准。

只读复核（仓库根目录，Python3.14）：

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.14 research/usb-ds-iso/tools/audit_a23_cached_build_relations.py \
  --check "$PWD/research/usb-ds-iso/private/analysis/A23-build-relations-review-20261020-r3" \
  --expected-sha256 52ce13d7e8d8a3b374e7f710eff2d222b8d8ae838ba7d506cb375dc2faad4e34
```
