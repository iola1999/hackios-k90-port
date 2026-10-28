# 2026-10-24 认领状态四分类表

按[未推送审查](../analysis/2026-10-24-unpushed-review.md) §12 各行状态与主 agent 通报汇总，供并行收尾使用；过程细节以各行与其链接记录为准，本表不重复。日期与未知范围照录来源，无新增推断。build 与设备当前均等待。

## 1. 设备部署阻塞

| 项 | 当前状态 | 出口 |
|---|---|---|
| loader USB/返回实现（L1/L5/L2/L6/L7、U1 loader 子项） | 实施中；无设备、无完整构建、无提交 | 交付后逐项核对目标 asm 与新对象 |
| payload 契约 U1 FD/map | 生产源码子项通过，测试 token 修待快验（§12 PAYLOAD-TOOLS-P2 行；下一动作先只复验 phase2 FDT token 小修，见[集成验收准备](../analysis/local/astra-payload-final-integration-checklist.md) §6） | token 修快验后进入跨组件合并验收；FD/shim/loader/packer 同步随源长度方案与平台宏裁决 |
| 新 FD 离线封装 | 产物有限验收通过，可提交审批（FD 产物验收报告） | 封装固定新 FD hash，重新解包核对内嵌 BDS/BootShim/loader/DTB/header |
| 内核 mode1 | `313033ad` 正式产物通过验收 | 按正式构建验收报告 §5 最小清单申请设备操作授权；最新准入清单见[下次 idle 准入准备](../analysis/local/astra-next-idle-admission-checklist.md) |
| 设备授权总体 | L1 轮 B 后无新授权，试验暂停，候选 A/B 保持原样 | 新试验逐次单独授权 |

## 2. 内核 mode 2 前置

| 项 | 当前状态 | 出口 |
|---|---|---|
| G1 新判据 | `ec53bac` 判据待负责人签署；当前机状态需试验前实读 | 签署后按新判据实读放行 |
| G2 测试判别力（mode 2 前置） | 已完成并通过 Astra 独立有限验收（§12 GPU-G2–G6 行） | 无 |
| 真实移交与恢复风险 | 待主 agent 裁决（主 agent 通报） | 裁决后放行 |

验证边界记录（非已裁决的 mode 2 强制前置，不新增必要工作）：G2 第二数据批定向变异 m6/m7 与 16384 页大小下的 m1–m5 重放未执行、目标硬件 cache PoC 可见性未验证。mode 2 前置即上述三项：主 agent 签署、新预检实读、真实移交与恢复风险裁决。

## 3. 推送前

| 项 | 当前状态 | 动作 |
|---|---|---|
| 推送顺序（C1） | 内核 gitlink 未上 origin | 先 `hackios-xnu-kernel` 后父仓库，或 `git push --recurse-submodules=check` |
| 待提交集 | GPU 冻结 9 文件、loader 在改实现、PAYLOAD-TOOLS/P2 产物、本轮文档 | 来源核对与用户授权后提交 |
| 提交说明勘误（C2/C3、13 条长主题） | 历史未改写 | reword 待用户授权 |
| `.gitignore` `logs` 行 | 工作区未提交、归属不明，`git check-ignore` 验证实际生效 | 标已覆盖待提交 |

## 4. 可后置

- U7 新鲜 BASE 复现（后置且未完成）；L3 最小拆分待裁决，属合并前维护项；G7/G8 删减待决。
- 审查 §11 第 5 条的中低严重度条目（L3、L4、U1–U4、S1 优先，其余随相关文件修改）。

## 5. 冻结前覆盖项

- 55MiB（`0x03700000`）完整容器上限是共享 FD 容器上限的收紧，属兼容性变化；redwood map 仍为 64MiB；对 annibale 运行期无容量证明，运行期安全保留仍未知（§12 PAYLOAD-MEM 行与[集成验收准备](../analysis/local/astra-payload-final-integration-checklist.md) §2 口径）。
- DT 粗 reg 扫描是不完整证明：契约测试只对照 144 个 64 位 reg 单元，32 位设备地址单元与 TrustZone 动态占用在断言范围外，DTB 缺席时显式跳过（§12 PAYLOAD-TOOLS-P2 行边界）。
- 旧产物不含新 map：MemoryMapLib 的 `XNU_Payload 0xF0000000+0x03800000` 保留条目为 P2 新增，旧 FD 与旧 payload 产物不含该条目，不得当作已含保留。

## 6. `/tmp` 链接待替换清单

三份已 `cp -n` 归档到 Git 忽略的 `docs/analysis/local/` 并逐文件 sha256 与原件核对一致；各认领组编辑完成后按表把 §12 行内链接替换为仓库相对链接，替换前不动他人活跃行。

| §12 行 | 现链接 | 替换为 |
|---|---|---|
| PAYLOAD-MEM | `/tmp/astra-payload-memory-contract-review.md` | `local/astra-payload-memory-contract-review.md` |
| LOADER-L1/L2/L5/L6/L7+L4/L9/L10+U1 | `/tmp/astra-usb-return-implementation-spec.md` | `local/astra-usb-return-implementation-spec.md` |
| LOADER-L1/L2/L5/L6/L7+L4/L9/L10+U1 | `/tmp/astra-payload-contract-implementation-sheet.md` | `local/astra-payload-contract-implementation-sheet.md` |

GPU-G2–G6 行的链接已用仓库相对路径（ignored evidence 目录），无需替换。归档件仅作来源留存，必要结论已写入 §12 各行与本表。
