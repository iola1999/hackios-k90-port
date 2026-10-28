# 「已安装应用」记录清单：16.5 载荷里有什么（2026-10-28）

这一页要回答一个问题：给 iOS 26 补「已安装应用」这套数据之前，把 iOS 16.5 那份工作载荷里对应的文件读出来当模板。读完的结论与本来的假设不一致，先说结论。

## 1. 结论：16.5 载荷里没有这套文件

三处查证，都指向同一件事。

**两个数据分区骨架结构相同，都没有安装记录。** `ios165/var.skel`（112 行）与 `ios26/var.skel`（129 行）都由 `mkvarskel.py` 从同一个来源生成：系统盘里 `/private/var` 的模板目录，去掉 `staged_system_apps` 与 `MobileAsset`，末尾补几个守护进程需要但只有运行中的 iOS 才会建的目录。两份都不含 `MobileInstallation`、`SpringBoard`、`PosterBoard`、`PlugInKit`。iOS 26 那份多出来的是 `/private/var/db/DarwinDirectory/local/{users,groups}`、`/private/var/mobile/Library/Metadata`、`/private/var/OOPJit`、`/private/var/boot`，都与安装记录无关。

**仓库里没有这些文件的正本。** `find` 全仓：没有任何 `IconState.plist`，没有任何 `MobileInstallation` 目录。文档里只有我自己写的两处描述，没有数据。

**16.5 时代的轮次也没有让它们持久化。** `var_store=1` 会把 `/private/var` 跨重启保存到 darwin 分区（`userland/src/var_store.c`），全仓 24 份轮次 manifest 的 cmdline 里没有一份带这个参数。也就是说每一次开机 `/private/var` 都是空的骨架，16.5 那些出图标的轮次同样如此。

所以「16.5 有这套记录、26 没有」在这份仓库里不成立。16.5 出图标与小组件的依据不是安装记录。

## 2. 16.5 靠什么出图标

`ios165/rootfs/Applications` 有 142 个 app bundle，每个带完整 `Info.plist`（`CFBundleIdentifier`、`CFBundleExecutable`、`SBAppTags` 等）。SpringBoard 在拿不到 `IconState.plist` 时按 LaunchServices 枚举到的应用生成默认布局，这是 iOS 的既定行为：`IconState.plist` 存的是**用户排列**，缺它就退回默认排列，并不阻止图标显示。系统应用的容器由 `containermanagerd` 在应用首次运行时按需创建，不依赖 `MobileInstallation` 里的记录。

这解释了 16.5 的现象，也把「26 为什么不同」这个问题挪到了别处：差别在 26 上某些服务拿不到容器或 persona 时的行为，安装记录的有无解释不了它。

## 3. 逐项对照

| 项 | 16.5 载荷 | iOS 26 载荷 | 谁读它 |
|---|---|---|---|
| `/private/var/mobile/Library/MobileInstallation/` | 不存在 | 不存在（骨架里没有这一级） | `installd` 写、`containermanagerd` 读，用于第三方应用的安装记录 |
| `IconState.plist` | 不存在 | 不存在 | SpringBoard 读，缺省时按 LaunchServices 枚举生成默认布局 |
| `/private/var/mobile/Containers/Data/Application/<uuid>/` | 只到 `Containers`、`Data` 两级，无条目 | 同左 | `containermanagerd` 按需创建，metadata 写在 `.com.apple.mobile_container_manager.metadata.plist` |
| `posterboard` 默认记录 | 不存在 | 不存在（`posterboard_dir=-1`） | PosterBoard 自建容器后写入，选中记录在它自己的 SQLite 里 |
| `persona`（type 6） | 骨架里没有 `DarwinDirectory` | 骨架里有 `db/DarwinDirectory/local/{users,groups}`，但**内容为空** | `personad`／`containermanagerd` 读 DarwinDirectory |

第六行是 26 相对 16.5 唯一实质新增的目录。**它不是宿主起不来的原因**：`launchd` 查不到 `PERSONA_SYSTEM_PROXY` 时只跳过 `posix_spawnattr_set_persona_np`／`set_persona_uid_np`／`set_persona_gid_np` 三个属性，进程照常 spawn（display 的 idalib 结论，`sys_persona.c:133` 要求 `com.apple.private.persona.write`；内核侧没有这个检查）。`DarwinDirectory` 仍然是 persona 记录的来源，`usermanagerd`／`useracctd` 读它，只是缺它不致命。

## 4. 探针读数怎么读

上一轮（旧二进制）拿到 `containers=-1`、`mobileinstallation_dir=-1`、`posterboard_dir=-1`、`iconstate=1`。`-1` 是「目录打不开」，`0` 是「目录存在且为空」；`iconstate=1` 是 `stat()` 成功，即 `IconState.plist` 这个文件存在，`0` 是不存在。（`iconstate=1` 与 `posterboard_dir=-1` 并列出现，说明两者看的是不同位置：前者在 `mobile/Library/SpringBoard` 下，后者是 `mobile/Library/PosterBoard`。）这与第 3 节的对照一致，说明这些路径从来就不在载荷里，不是这一轮丢的。

## 5. 真正能当模板的两处

**一处是设备上可能还留着的 `var_store`。** darwin 分区里若存在某次开机保存下来的 `/private/var`，那里就是一份真实运行过的数据分区，含 `MobileInstallation`、`IconState.plist` 与容器 metadata。`var_store show` 能列出两个槽的内容，成本一次设备命令、不需要跑一轮。有没有值，查一次就知道。这是唯一可能拿到「真实格式」的本地来源。

**另一处是 `installd` 与 `containermanagerd` 的二进制。** 它们读哪些路径、要不要版本号、`MobileInstallation` 用 plist 还是二进制，只能从二进制里读。这一项适合并给 display 用 idalib 做，我这边没有在做二进制反编译。

## 6. 我建议的下一步（待你定）

不建议先动手造 `MobileInstallation` 记录。理由是：格式未定、版本敏感，写错的记录会让 `installd` 在开机时把容器目录当成孤儿删掉，比现在更难查。

建议按代价从低到高排三步：

1. **设备上查 `var_store show`**（一次命令）。有槽就读出真实格式，没有就关掉这条路。
2. **用探针确认宿主退在与容器有关的哪一步**。现在有 `containers=` 与进程表两项，再加一项「某个具体宿主进程的退出码与信号」就能判定它是不是容器问题；这一步不改载荷，只加观测。
3. **只造最小的一件：给一个宿主建容器目录**，看它是否活过断言窗口。一件能验证方向，成本低且可回退。

第 2、3 步都不需要「安装记录」，也不需要改系统镜像。如果第 2 步证明宿主的退出与容器无关，那这一整条线就该停。

## 7. 风险与约束

- 造数据的脚本提交到 `tools/k90auto/`，`ROUND_NOTES` 与归档说明写清「本轮新增安装记录与容器数据」，不放任何真实个人信息（`AGENTS.md` §3）。
- 写 `MobileInstallation` 之前先确认它的写者是谁：若 `installd` 开机时会用库里的记录覆盖目录，手造的记录会在下一轮消失，白做；若它会清理没有记录的容器，手造容器也会被删。
- 这一条会改变载荷哈希，`library-baseline.json` 的基线检查会拦一次，属预期。