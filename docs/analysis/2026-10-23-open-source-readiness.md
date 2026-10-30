# 仓库公开与隐私检查记录

## 1. 仓库状态与来源

本项目基于 OOSEX GANG 的 [HackiOS kernel](https://github.com/oosexgang/hackios-xnu-kernel) 和 [HackiOS userland](https://github.com/oosexgang/hackios-xnu-userland)。三个仓库 README 均说明来源与职责，原有许可证及版权声明保留。

| 仓库 | 默认分支 | 当前可见性 | GitHub fork 关系 |
|---|---|---|---|
| `hackios-k90-port` | `main` | public | 独立的顶层工作区 |
| `hackios-xnu-kernel` | `k90-port` | public | `oosexgang/hackios-xnu-kernel` 的 fork |
| `hackios-xnu-userland` | `k90-port` | public | `oosexgang/hackios-xnu-userland` 的 fork |

## 2. 隐私检查与处理范围

检查覆盖三个仓库的 Git 跟踪文件、待提交文件、所有本地分支与标签可达的文件版本，以及提交作者和提交者信息。二进制文件检查可识别的明文标识，gzip 数据解压后检查；顶层仓库的桌面截图另做目视检查。详细扫描结果和历史备份保存在已忽略的本地目录。Codex 在本机保存的差异快照引用另行识别，这些引用仍可能包含旧内容；本次只推送指定分支，快照引用与原始备份留在本机。

| 内容 | 检查结果与处理 |
|---|---|
| 个人提交邮箱 | 三个仓库的作者／提交者记录中存在；按用户要求保留 |
| 设备序列号 | 顶层说明、fastboot 输出、操作脚本及 kernel 旧版暂存脚本中存在；当前命令改用环境变量，历史副本同步清理 |
| 本机用户名、项目位置和 NAS 路径 | 顶层文档及旧版本中存在；改为项目相对位置或备份目录变量 |
| 会话标识 | 经验文档和可复用 Prompt 中存在；固定标识清理，Prompt 由执行者填写来源链接 |
| 私钥与常见服务令牌 | 本次规则扫描未检出；扫描结果不能覆盖所有凭据格式和编码方式 |
| 测试密码与内网地址匹配 | userland 中的匹配来自未修改的上游测试与任务配置，经上游文件比较确认；未发现属于本机用户的配置 |
| 图片与二进制材料 | 顶层已跟踪截图未见个人账号内容或 PNG 文本／EXIF 元数据；固件及镜像来源仍需按分发范围单独审阅 |

运行脚本使用 `SER` 或 `ANDROID_SERIAL` 选择设备。设备备份、原始日志、缓存及历史备份继续保存在 Git 忽略目录，仓库内仅保存分析结论和必要示例。

## 3. 历史清理与协作

只清理当前文件无法移除旧提交中的标识。本次对含有个人标识的可达历史执行定向替换，保留提交邮箱、上游版权声明及干净的上游历史。重写会改变受影响提交及其后续提交的 ID；顶层历史中的 kernel 子模块指针同步映射到清理后的 commit。

首次改写分支历史后，GitHub 仍能通过旧 SHA 读取顶层仓库和 kernel 的原提交。按用户要求，本轮删除三个旧线上仓库，再按原名称重建；两个代码仓库从对应上游创建正式 fork，顶层工作区创建独立仓库。三个新仓库均只推送清理后的本项目分支，本地备份和 Codex 差异快照引用继续保留在本机。

重建后使用已认证的 GitHub API 检查改写前的 87 个提交标识，其中顶层仓库 60 个、kernel 27 个，全部返回 HTTP 404。未登录访问检查中，两个仓库的当前提交 API 均返回 HTTP 200；各抽查一个改写前提交，其 commit API、网页及原始文件 URL 均返回 HTTP 404。提交邮箱按用户要求保留。

2026-10-30 第二次改写：顶层提交 `609b473` 往 `docs/progress/2026-10-30-status-consolidated.md` 写入了三个会话标识前缀，`7ee1d8e` 已从文件中删除，历史里仍在。按用户授权用 `git filter-repo --replace-text` 替换这三处后强推 `main`，`609b473` 及之后共 12 个提交的 ID 改变（改写后为 `95dc056` 至 `ea20a2c`），更早的提交不变；改写后的可达历史检索不到这三个标识。改写后未登录访问旧 SHA `609b473`、`7ee1d8e`、`e0a0bdb` 的提交网页仍返回 HTTP 200，从服务器上移除需要 GitHub 支持清理，或按上一轮做法删除后重建仓库。

已有其他 checkout 在继续推送前需要重新同步清理后的分支。旧 checkout 合并旧提交可能再次引入个人标识，推送前应检查所包含的历史。GitHub 的服务器备份及其他克隆副本无法通过仓库访问测试确认是否已清除，参见 [GitHub 历史清理说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。

## 4. fork 关系与仓库信息

两个代码仓库的 GitHub `parent` 分别指向 OOSEX GANG 的原仓库，默认分支均为 `k90-port`；fork 创建时取得的 `main` 分支保留上游内容。本地 `upstream` 继续用于读取上游变更，`origin` 和顶层 `.gitmodules` URL 保持原名称。

公开上游的 fork 必须公开，参见 [GitHub fork 可见性规则](https://docs.github.com/en/pull-requests/reference/forks)。本轮使用 [创建 fork API](https://docs.github.com/en/rest/repos/forks#create-a-fork) 建立关联，随后推送本地分支。

三个仓库的描述注明 REDMI K90、annibale、SM8750 及各自职责。GitHub Topics 使用 `hackios`、`ios`、`redmi-k90`、`annibale`、`sm8750`、`qualcomm`、`arm64` 等共同关键词，并按仓库补充文档、内核、UEFI、用户态、APFS 和图形相关主题。Topics 用于项目分类，Git 版本标签按实际发布计划维护。

## 5. 检查边界与后续维护

顶层仓库尚未选择单独的许可证；kernel 和 userland 保留各自现有 `LICENSE`。预构建固件、设备提取资料及其他第三方文件的分发许可仍需按实际发布内容核对，本次隐私扫描覆盖个人标识和常见凭据格式。

本轮只修改仓库关系说明与线上设置，并更新顶层子模块版本；设备调试会话正在修改的源码继续留在本地工作树。待发布分支及标签的可达历史未检出已识别的个人标识，顶层历史中的子模块指针均可在对应子模块分支或标签中找到。重建前没有 Issue、PR、Release、Actions 产物或额外协作者需要迁移。

后续推送继续检查当前文件、分支历史以及 Git LFS／Release／Actions 等托管内容。新发现的隐私格式需要补充扫描规则，原始日志和设备备份继续保存在 Git 忽略目录。
