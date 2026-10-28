# iOS 26 的安装记录、容器元数据与 persona：它们各自从哪里来

为了判断「补出已安装应用这套数据」要写哪些文件，用 idalib 与 dyld 共享缓存里各 framework 的字符串确认了 iOS 26 的实际情况，并与 16.5 的做法对照。结论先说：**26 没有一份可以直接照抄的安装记录文件，记录在 MobileContainerManager 的 SQLite 库里；`installd` 这个服务在我们的启动清单里没有，所以从来没跑过；`persona` 是内核对象，补文件不能满足它。**

## 1. `installd` 在跑，并且被判为卡住

我最初的结论是「`installd` 从来没有跑过」，依据是默认 `IOS_JOBS` 里没有 `com.apple.mobile.installd`、以及上一轮日志里 `installd[` 零次。**这两条依据都不成立，结论撤回**：

- 打包脚本对这类作业有第二个来源：`tools/k90auto/package.py:101` 的 `EXTRA_JOBS` 已含 `com.apple.mobile.installd.plist`，`add_extra_jobs()` 对它设 `RunAtLoad = True`（它不在 `ON_DEMAND_JOBS` 里），所以每轮开机都会拉起；产物 `root/xpc/launchd.plist` 与 `root/LaunchDaemons/` 都能查到。
- 计数方式也错了：判卡那条日志的写法是方括号朝内的 `[installd]`，不是进程前缀 `installd[`。实测原文（`kernel-12377-attr-biomed/run/s003.log` 起连续多份）：`memorystatus_perform_idle_demotion() timed out stuck process 35 [installd]`，同一轮还有 `[pkd]`（pid 73）与 `[extensionkitservice]`（pid 67）。

所以「没有安装记录」的成因指向 **`installd` 起来之后卡住**，卡住的签名与 `pkd`／`extensionkitservice`／`iconservicesagent` 一样（同一句 idle demotion 超时）。

**但「被判卡」不能当作判据**：`docs/analysis/2026-10-28-stuck-process-census.md` 统计了 58 个证据目录，11 个有这类日志，被判卡的只有五个进程名（`AudioConverterService`、`pkd`、`iconservicesagent`、`extensionkitservice`、`installd`），而最干净的一轮（`attr-linkd`，11,015 帧、无停帧）同样有 `AudioConverterService`、`pkd`、`extensionkitservice` 三个事件。被判卡是背景状态，好坏轮都有。`kernel-12377-attr26-persona2` 又出现一个先前普查里没有的名字：`linkd` 2 次（同一轮还有 `installd` 3、`AudioConverterService` 3、`pkd` 2）。这一条只记录，不作推断。**验收改用目录与计数**：`lsprobe` 的 `mobilelibrary=` 里是否出现 `MobileInstallation/`、`containers_entries=` 是否从 0 变非 0、`mobileinstallation_dir=` 是否非 0。作业定义本身：`com.apple.mobile.installd`，`MachServices` 只有 `com.apple.mobile.installd`，plist 里没有 `RunAtLoad`，由打包脚本强制打开。

## 2. 安装记录在 SQLite 里，不在 plist 里

在 26 的系统盘与共享缓存里查过这些名字：

- `LastLaunchServicesMap` —— **不存在**；
- `MobileInstallation.plist` —— **不存在**；
- `SystemAppInstallState`、`BackupSystemAppInstallState` —— 存在（`InstalledContentLibrary` 里，前者是 `SystemAppInstallState.plist`）。
- `MobileInstallation` 的数据目录仍是 `~/Library/MobileInstallation`（`/private/var/mobile/Library/MobileInstallation`），`~/Library/Logs/MobileInstallation` 也存在。

`containermanagerd` 本体是 54 KB 的壳（`strings` 只有 2 条），实现在 `ContainerManagerCommon`／`MobileContainerManager`。它在三轮里都在跑，日志里的写法是 `containermanager[37]`（biomed）、`containermanager[38]`（linkd）、`containermanager[54]`（crashlog），同一句 `minisandbox: request 5 (first seen from …): allowed`。`ContainerManagerCommon` 里是 SQLite 语句与列名：`identifier`、`code_signing_id`、`code_signing_id_text`、`child_code_signing_id_text`、`data_container_class`、`placeholder`、`advance_copy`、`registered_by_caller`、`invalid`、`codeSigningInfoData`，库文件名为 `com.apple.containermanagerd.SQLite`（另有统计库 `Analytics.sqlite`）。

**这条决定 desktop 的做法**：16.5 时代照抄 plist 的路子在这里没有对应文件。要让 `containermanagerd` 认得一个已安装应用，要么走它自己的 XPC 接口让它写库，要么把库与容器目录一起造出来。前者的接口在 `MobileContainerManager`／`installd` 的 XPC 上；后者需要匹配 `MCMMetadataSchemaVersion`。

## 3. 容器目录与元数据文件

- 应用数据容器：`/private/var/mobile/Containers/Data/Application/<UUID>`，同类目录还有 `PluginKitPlugin`、`XPCService`、`InternalDaemon`、`VPNPlugin`、`TempDir`；
- 共享容器：`/private/var/mobile/Containers/Shared/AppGroup/<uuid>`、`/private/var/mobile/Containers/Shared/Extension`；
- 系统容器：`/private/var/containers/Data/System`、`/private/var/containers/Shared/SystemGroup/systemgroup.com.apple.installcoordinationd`；
- **persona 卷**：`PersonaVolumes/<uuid>/Containers/Data/InternalDaemon/...`、`PersonaVolumes/<uuid>/Containers/Shared/AppGroup/...`。
- 每个容器的元数据文件名是 **`.com.apple.mobile_container_manager.metadata.plist`**（前面有个点），键为：`MCMMetadataIdentifier`、`MCMMetadataUUID`、`MCMMetadataSchemaVersion`、`MCMMetadataContentClass`、`MCMMetadataVersion`、`MCMMetadataPersona`、`MCMMetadataUserIdentity`、`MCMMetadataInfo`、`MCMMetadataCreator`、`MCMMetadataActiveDPClass`、`MCMMetadataUserManagedAssetsDirName`。

`kernel-12377-attr26-persona3` 的探针读数把容器这一块量清楚了：`containers_mobile=240`（`/private/var/mobile/Containers/Data/Application` 下 240 个）、`workspace=258`、`workspace_extensions=296`、`iconstate=1`。也就是应用数据容器与 LaunchServices 的应用／扩展名录都已经存在，扩展宿主不是「找不到容器」才退出。

同一轮的对照很直接：`containers_mobile=240`，而 `containers_system=-1`、`posterboard_dir=-1`、`pluginkit_dir=-1`、`files_staged=-1`。**mobile 侧那几个目录被运行时填上了，system 侧这几个在我们的 `/private/var` 骨架里根本没有**，所以 `-1` 的四个是骨架缺目录，不是运行时行为。

宿主死亡的直接记录也在同一轮：4 条 `Process[<pid>] crashed: <comm>. Too many corpses being created.`（快照重叠已去重），来自 `bsd/kern/kern_exit.c:2188` 的 `task_mark_corpse` 失败分支，进程名只有三个——`BarcodeScannerWi`、`CalculatorWidget`、`LauncherControlE`。这三个是小组件与控制的宿主扩展，它们起来、崩掉，corpse 名额被耗尽。这条比「拿不到容器」更贴近现象。

## 4. `IconState` 与 16.5 相同

`/usr/libexec/SpringBoard` 里两条路径字符串：`~/Library/SpringBoard/IconState.plist` 与 `~/Library/SpringBoard/DesiredIconState.plist`，另有一个 `/newIconState.plist`。`SpringBoardHome` 里的键是 `iconLists`、`buttonBar`、`currentPageIndex`（以及 `_currentIconStateURL`、`_desiredIconStateURL`、`_isIconStateDirty` 这些内部名）。**这一块 26 与 16.5 一致，可以从 16.5 的工作载荷照抄。**

## 5. `persona`：内核对象，补文件不能满足

日志里 `Unable to find persona with type %d: %d - %s` 这个格式串在 **`/sbin/launchd`**（`0x10006b5be`，函数 `sub_100034354`），调用链是 `sub_100028BA4`（作业 spawn）→ `sub_100034354` → `posix_spawnattr_set_persona_np`。

- 类型来自 `bsd/sys/persona.h`：**6 = `PERSONA_SYSTEM_PROXY`**，4 = `PERSONA_SYSTEM`。`sub_100034354` 先问一个 xpc bool，真则用 4，假则用 6。
- **它不是致命的**：lookup 失败返回 -1 时，launchd 只是跳过 `set_persona_np`／`set_persona_uid_np`／`set_persona_gid_np`，进程照常 spawn。所以这条日志是噪声，不是宿主退出的原因。
- persona 由内核维护（`bsd/kern/kern_persona.c`，`config/MASTER.arm64.bcm2837:27` 的 `BSD_BASE` 含 `config_personas`，我们的 DEVELOPMENT 配置编译进去了）。创建走 `persona()` 系统调用 `PERSONA_OP_ALLOC`，而 `bsd/kern/sys_persona.c:133` 要求 **`com.apple.private.persona.write`** 这项 entitlement。
- 所以「补一个 persona 文件」不可能生效。可行的是两条：在启动早期以带该 entitlement 的进程调 `persona_alloc(PERSONA_ID_NONE, "systemproxy", PERSONA_SYSTEM_PROXY, NULL, 0, &err)`，或者在我们的内核代码里直接调 `persona_alloc`（内核侧没有 entitlement 检查）。

## 6. 另一处缺的服务：`coreduetd.context` 与 `dasd`

那一轮里 132 条 `NSCocoaErrorDomain Code=4099` 是 `com.apple.coreduetd.context` 的 lookup 失败，错误 3「No such process」，键路径是 `/device/dasd/widgetBudget`、`/device/dasd/widgetSystemAdded`、`/device/dasd/widgetOverride`。也就是小组件的刷新预算查询全部落空。

服务与提供者逐条核过，`com.apple.coreduetd.context` **不是 `dasd` 提供的**：

| 服务名 | 提供者作业标签 | plist 路径 |
|---|---|---|
| `com.apple.coreduetd.context` | `com.apple.contextstored` | `System/Library/LaunchDaemons/com.apple.contextstored.plist`（程序 `/System/Library/PrivateFrameworks/CoreDuetContext.framework/Resources/contextstored`） |
| `com.apple.duetactivityscheduler`、`com.apple.dasd.end-prewarm` | `com.apple.dasd` | `System/Library/LaunchDaemons/com.apple.dasd.plist`（程序 `/usr/libexec/dasd`） |
| `com.apple.mobile.installd` | `com.apple.mobile.installd` | `System/Library/LaunchDaemons/com.apple.mobile.installd.plist`（程序 `/usr/libexec/installd`） |

三个程序在 `ios26/rootfs` 里都在。所以只加 `dasd` 消不掉那 132 条 4099，必须同时加 `com.apple.contextstored`。

这条与「小组件每分钟抓取一次」相关：预算查询失败会让 `chronod` 走它自己的重试路径。**补 `dasd` 与 `coreduetd.context` 的服务，比补 `appprotectiond` 更贴近停帧那条线。**

## 7. 下一步的最小集合

1. **数据卷骨架先补父目录**：`/private/var/mobile/Library/MobileInstallation` 与 `/private/var/mobile/Library/SpringBoard`（501:501、755）。这是 `installd` 建库前要写的位置，父目录不存在则无处可写。已由 desktop 落在内核仓 `0ff060a`。判据是上面那条：目录里出现文件、`containers_entries` 从 0 变非 0。
2. **`com.apple.contextstored` 与 `com.apple.dasd`**：`com.apple.coreduetd.context` 由 `com.apple.contextstored` 提供（`/System/Library/PrivateFrameworks/CoreDuetContext.framework/Resources/contextstored`），`com.apple.dasd` 提供 `com.apple.duetactivityscheduler` 与 `com.apple.dasd.end-prewarm`，两者都不在默认作业集里，三个程序在盘上都在。
3. 桌面的 `IconState.plist` 从 16.5 模板照抄，键用 `iconLists`／`buttonBar`／`currentPageIndex`。
4. 安装记录与容器：等 `installd` 不再被判卡之后看它是否自己重建；仍为空再按 `MCMMetadata*` 键造容器并写 `com.apple.containermanagerd.SQLite`（需要先读出 `MCMMetadataSchemaVersion` 的当前值）。

## 8. 三次「进程名不在列表里」的误判

同一个形态今晚出现三次，写在一起当作判据的边界：**探针或清单里没有某个名字，不能推出那个东西没在跑。**

- **`installd`**：我按默认 `IOS_JOBS` 与日志前缀 `installd[` 判它「从来没跑过」。实际它有第二个作业来源（`tools/k90auto/package.py:101` 的 `EXTRA_JOBS`，`add_extra_jobs()` 强制 `RunAtLoad = True`），日志里的判卡行写作方括号朝内的 `[installd]`。它在跑，并且被判卡。
- **`pkd`**：因为 `com.apple.pluginkit.pkd` 从没出现在我看的那几处清单里，一度按「插件服务没起来」理解。实际它一直在跑，`kernel-12377-attr26-persona3` 里有 `stuck process [pkd]` 三条。
- **`pluginkit`**：`lsprobe` 的 `WATCHED` 表里有一项叫 `pluginkit`，读数一直是 `-`，被当成「守护进程没起来」。实际 iOS 26 没有这个可执行文件，`pluginkit` 只出现在 LaunchServices 的扩展名表里（`… plugin, pluginkit, prefpane, qlgenerator …`），PluginKit 的守护进程是 `pkd`。

三次的共同点：名字的来源（清单、日志前缀、探针表）与生效点（打包脚本、作业缓存、实际进程名）不在同一处。判据要写成「它是 X 类东西，`-` 意味着 Y」，而不是「它没在跑」。
