# AGENTS.md — hackios-k90-port 工作区约定

HackiOS（XNU + 未修改 iOS 16.5 用户态）移植到 REDMI K90（SM8750，代号 `annibale`）的顶层工作区。
代码在两个 submodule（`hackios-xnu-kernel/`、`hackios-xnu-userland/`，工作分支均为 `k90-port`），
本仓库只放文档、脚本、配置。背景速览见 [README.md](README.md)，计划见 `docs/plan/`。

## 文档写作约定（必须遵守）

1. **禁止按字符宽度硬换行**。一个段落 = 一行物理行；一个列表项（含有序/无序/嵌套项）= 一行；
   引用块的一段 = 一行（`> ` 开头，段内不断行）。写新文档、改旧文档时都不要为了"行不太长"而中途折行。
   理由：硬换行会让 diff 噪音大、段落级修改互相冲突，且渲染前后行为不一致。
2. 唯一允许的行内换行手段是 Markdown 硬换行（行尾两个空格），且仅在确实需要视觉换行时使用。
3. 代码块（``` 围栏内）、表格行、标题行不受本节约束，保持原样。
4. 中英文混排连接处遵循原文风格：西文/数字/反引号片段与中文之间可留一个空格；
   中文与中文、中文与全角标点之间不加空格。
5. 存量文件若发现硬换行，用本仓库脚本批量修复，不要手工逐行改：
   `python3 tools/unwrap_md.py [--check] <file.md> ...`（`--check` 只出 diff 不写文件；
   脚本会保护代码块/表格/标题/列表结构，把续行合并进所属段落或列表项）。

## 其他

- 过程记录写 `docs/progress/`（按日期命名），规划写 `docs/plan/`，调研/实测数据写 `docs/analysis/`。
- `annibale-backup/` 是分区备份数据说明，内容勿删。
- 真机操作前后先看 `docs/plan/device-test-playbook.md` 的陷阱清单。
