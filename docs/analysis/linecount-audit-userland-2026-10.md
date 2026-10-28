# 存量审计：用户态侧超 1000 行文件与拆分方案（只读，2026-10）

姊妹文档：内核侧见 [linecount-audit-2026-10.md](linecount-audit-2026-10.md)（task-15，drivers）。本文档对应 task-16，口径相同：AGENTS.md 新行数约定（代码文件 ≤1000 行，生成表/结构不可分者文件头写明理由即可豁免），审计阶段一行代码不动，只给层缝、预计片行数、风险面与时机。拆分本身由 Lead 按表另立任务。

## 1. 口径与范围

- 扫描：`hackios-xnu-userland` 内 `git ls-files userland tools | xargs wc -l`，阈值 >800，排除 `tools/mesa/mesa-*` 上游树（本次 checkout 本无该目录，mesa 树在容器构建目录里，不在 git）。
- 共 33 个代码文件越线。按性质分四类：AIR 前端（`tools/mesa/air/**`，26.2.5 基线，我们自己的编译器代码，细审见第 3 节）6 个 + `air_metal.h`/`air_print.c`；host 侧 python/C 工具（`tools/air/*.py`、`tools/apfs/*`、`tools/metal/*`）11 个；userland 设备侧 C/ObjC 14 个；构建脚本 1 个（`userland/build.sh` 847）。
- 不在表内但有账的：`tools/mesa/rebase-26/0003-restore-osmesa-26.x-drift-adaptations.patch` 3859 行——补丁文件不是编译单元，不适用行数约定；`userland/obj/eagl_gen.h` 6143 行——`userland/mkeagl.py`（156 行）生成的派发表，不在 git（构建产物），按「生成表」归类无需动；`ios165/` 物料与 `prebuilt/` 二进制不在扫描内。
- 风险面口径：装载面 = 该文件编进设备上被 dyld/插件机制装载或启动链执行的二进制（build.sh 的源→产物映射是权威表）。当前映射：
  - `inject*.c→libredwood*.dyld`、`redwoodmetal.m→libredwoodmetal.dylib`（backboardd 插件，dlopen libredwoodair）、`eagl.c→libredwood-gl.dylib`（backboardd，GL=1）。
  - `camera_device.c/camera_isp.c→libredwood-media.dylib`（mediaserverd，cam=5）、`audio_plugin.c→RedwoodAudio.driver`。
  - `init.c→/redwood 小镜像 process 1`、`var_store.c→persisted /private/var 打包器（persist 分区 darwin）`。
  - 设备诊断（`/redwood/bin` 下一次性程序）与测试 app（RedwoodTriangle）是设备面但不是装载链。
  - host 工具零设备风险，但 `tools/apfs/mkapfs.py` 是 system.apfs 镜像生成器——它产出正是本设备轮 gate 住的那块 apfs，拆它的验收 = 重打镜像字节一致。
- 现势约束：设备轮的 bits 已装配完（等用户设备 + 持久化 stage 的用户确认）。**任何改动 userland C/ObjC 或 mesa 源的拆分都会改 obj 字节、触发重装装（含持久化面）**，所以凡是产物进镜像的文件，时机一律建议设备轮后；真正「现在就可做且零字节影响」的只有纯 host python（`tools/air/*.py`、`tools/metal/*.py`、`tools/apfs/apfs.py`、`write-tests.py`）与不进镜像的 host C。

## 2. 总表（每文件一行；片行数为预计）

### 2.1 AIR 前端（tools/mesa/air/，细审见第 3 节）

| 文件 | 行数 | 性质 | 建议拆法（片=预计行） | 风险面 | 时机 |
| --- | --- | --- | --- | --- | --- |
| air_metal.c | 6978 | 设备侧运行库（libredwoodair.dylib 的 Metal 面，红杉装载面） | 6 片：device+buffer≈700、texture≈850→再切 fill/readback=2 片各≈550、state(sampler/depth/vertex)≈800、argbuf≈480、compute≈800、render≈900→pipeline/state=2 片；共享 `air_metal_private.h`≈300（结构体从 air_metal.h 挑内部件，公开 ABI 不动） | 装载面（redwoodmetal dlopen）；`rwa_*` 符号表与 `static_assert(sizeof(rwa_color_blend)==32、rwa_render_info==116)` 契约必须在单一 TU | 设备轮后（与 libredwoodair 重装装同批） |
| air_metal_test.c | 6765 | host 测试主程序（libredwoodair 对软屏） | 公共 helpers（MTLB 装载 186-460、texel/格式 82-186、像素差分 2430-2476）抽 `air_metal_test.h/_common.c`≈450，测试按家族拆：compute≈700、texture≈900→2 片、depth≈500、render/picture≈900→2 片、vertex 流 3099-3260≈550、argbuf≈700、main≈450 | 零装载面；纯 host（macOS 直跑），是 air_metal 拆分的验收工具本身 | 最先做——拆它等于给其余 air_metal 拆分铺好回归网 |
| air_to_nir.c | 4086 | 翻译核心（进 libredwoodair + air2nir） | 按现成 banner 段切：`air_nir_emit.c`(values/constants/memory 51-692)≈660、`air_nir_argbuf.c`(1195-2038)≈844→把 2 个 helper 挪回主文件压 ≤800、`air_nir_instr.c`(instructions 2039-2691)≈670、`air_nir_cfg.c`(CFG 2692-3587)≈910→module-scope vars(3588-3799)独立成 `air_nir_gvars.c`≈220 后 CFG 片≈690、主文件留 header/metadata/stage/interface/entry≈800；共享声明并入既有 `air_private.h` | 装载面（编译进 dylib）；判据在翻译语义不在文件布局，host 验收面最强 | 设备轮后，host 侧先行批 |
| air_run.c | 2093 | host 软屏 harness（air_run） | main/CLI≈600、场景/纹理/quad 装载（1-467 大半）≈470、compute/draw 两路（468 起）≈1000→2 片各≈500 | 零装载面（host 测试二进制，mesa-host/darwin 构建） | host 先行批 |
| air_intrinsics.c | 1954 | intrinsic 表+翻译（进 dylib） | 按 banner：`air_intr_textures.c`(textures 1162-1908)≈760、`air_intr_ops.c`(atomics/barriers/flow/SIMD/llvm.* 601-1161)≈580、主文件留 families(180-600)+dispatcher≈600；描述符表共享声明走 `air_private.h`/`nir_air.h` | 装载面 | 设备轮后，host 侧先行批 |
| air_module.c | 1950 | LLVM bitcode 元数据读取（进 dylib+air2nir） | 按 banner：`air_module_body.c`(function bodies 954-1690)≈750、`air_module_types.c`(types+values 220-622)≈470、`air_module_meta.c`(metadata+records 623-953)≈390、主文件留 module block≈430 | 装载面 | 设备轮后，host 侧先行批 |
| air_print.c | 912 | 打印（进 dylib+air2nir，轻度越线） | instructions 段(377-912)独立 `air_print_instr.c`≈550，主文件 metadata+头部≈380 | 装载面（轻） | 设备轮后随 air 批 |
| air_metal.h | 1313 | 对 redwoodmetal.m 的公开 ABI 契约头（build.sh 按原路径拷给用户态） | **永不拆**：单一契约面，拆头会让「库侧声明/驱动侧拷贝」两头同步出裂缝；在文件头加豁免理由（AGENTS 允许）| 装载面本体 | 只补头注释，设备轮后做 |

### 2.2 host 工具（tools/，零设备装载面；check.sh 只取 rc）

| 文件 | 行数 | 性质 | 建议拆法（片=预计行） | 风险面 | 时机 |
| --- | --- | --- | --- | --- | --- |
| tools/air/intrincheck.py | 2452 | CI harness（check.sh 两处调用：全量 + `--run --cases 4`） | 数据表(FLOATS/EDGE_FLOATS/INTS 144-180 起)+浮点位助手 `intrin_data.py`≈500、.ll 生成与 runner≈900、报告/CLI≈600；CLI 与 rc 语义不变 | check.sh 按路径调用，import 新模块无感；`--emit` 设备契约面不动 | **立即可做**（纯 host python，不进任何镜像） |
| tools/air/kinput.py | 1451 | harness 库+CLI（kstruct.py 等 import） | 内核输入布局/模式表(LAYOUT/SPAN/TABLE 125-158 起) `kinput_data.py`≈450、逻辑+main≈600；`import kinput` 的公开函数名保持 | kstruct.py import；改名即断 | 立即可做 |
| tools/air/metalcheck.py | 1387 | 设备日志 vs softpipe 对账 harness（check.sh `--newest`） | 日志解析(regex/新旧状态编号 102-135)+jobs 面 `metalcheck_logs.py`≈450、参考计算+runner+报告≈900→报告独立≈350 | 它**解析设备日志文本**（`drvtest:`/`redwoodmetal:` 前缀与 `TEST_KEYS_ON_SIX` 防不一致表），拆自身不改日志；动 regex 要对照 rc.jobs.metal* 现样例 | 立即可做 |
| tools/air/argbufcheck.py | 1096 | CI harness | 模块骨架/成员表(HEAD/TAIL/MEMBERS/build/chain 110-202) `argbufcheck_mods.py`≈420、runner+CLI≈700 | check.sh 取 rc（`tail -30` 展示） | 立即可做 |
| tools/air/sampcheck.py | 950 | CI harness（import texopcheck） | 比较表/骨架(COMPARE/BASE_WORD/骨架串 92-300) `sampcheck_cases.py`≈330、主≈630 | 同上；`texopcheck.TEX` import 不动 | 立即可做 |
| tools/air/loweringcheck.py | 838 | CI harness（借 cpuref.py） | 越线 38 行：骨架串(SKELETON/SRET/PSEL/PSTORE 79-400) `loweringcheck_cases.py`≈330、主≈530；或给文件头豁免理由 | 它硬编码 `build/mesa-host` 路径（本会话踩过），拆分时别同时修路径 | 立即可做 |
| tools/metal/owesclass.py | 1002 | 分析工具（类欠账表） | 常量表(NSOBJECT_ANSWERS/PROBES/HELPERS 143-197) `owesclass_data.py`≈250、分析+报告≈760；或整文件头豁免（查表型单工具） | appsends.py/ownes 数据文件路径依赖不动 | 立即可做 |
| tools/apfs/apfs-tool.c | 1790 | host/容器 APFS 只读工具（不进镜像） | 按 op 族：ls/tree(314-600)≈300、census+并行 walker(601-1006)≈410、cryptex cf 族(1007-1166)≈160→并入 census、lock 扫描(1293-)+nh(1167-1292)≈300、main+host_par+op 锁≈500；共享 `apfs_tool.h`≈150 | staging 链交叉核对面（write-tests.py `read_tool_bytes` 用它对拍）；host 编译即可验收 | 可做（不等设备，容器/host 直编） |
| tools/apfs/apfs.py | 1205 | python APFS 读者（被 mkapfs/write-tests import） | 读者核心(open_image/obj_hdr/btree 211-720)≈510 留主、xfields/decmpfs(721-928) `apfs_decmpfs.py`≈210→并入读者片、命令族(cmd_info/ls/tree/cat 958-1205) `apfs_cmds.py`≈250 | import 面（`import apfs` 的调用方按名引用）保持 | 可做 |
| tools/apfs/mkapfs.py | 938 | **system.apfs 镜像生成器**（build.sh 三处调用） | xfields/目录项/压缩 fork 构造(280-580) `mkapfs_objs.py`≈300、主+manifest≈640 | 产出=设备轮 gate 的那块 apfs；验收硬条件：**重打 system.apfs 字节一致**（它是确定性生成器，字节相等即零风险证明） | 可与设备轮并行做、合入等设备轮后（或字节一致证据直接说服 Lead 轮前合） |
| tools/apfs/write-tests.py | 933 | 写路径测试电池（host 跑 apfs-tool/mkapfs 对拍） | 读回对拍 helper(101-215)≈120、reseal/find_object+测试电池(215-933) `write-tests_battery.py`≈730、runner≈200；或测试单文件豁免 | 纯测试 | 可做 |

### 2.3 userland 设备侧（进镜像；除注明外时机一律设备轮后）

| 文件 | 行数 | 性质（build.sh 映射） | 建议拆法（片=预计行） | 风险面 | 时机 |
| --- | --- | --- | --- | --- | --- |
| src/metal_drv_test.m | 7737 | 设备诊断 `/redwood/bin`（非装载链；metalperf job 驱动；metalcheck.py 解析它的 `drvtest:` 日志） | 公共 texel/格式/容器 helper(1-588)≈620、compute(589-1125)≈540、attrib helper(1126-1712)≈590、attrib_path(1713-2335)≈630、draw+sweep(2336-2726+3476-3775)≈690、depth+argbuf(2727-3475)≈750、picture(3776-5031)≈730+530、time(5032-7055)≈700+830→压片、owe 表+main(7056-7737)≈690，共≈12 片+`drvtest.h`。**先抽 `redwood_air_contract.h`**：rwa* 契约（dlsym 再声明）是三个消费者各自重声明同一契约的不同子集——`rwa_texture_decl`/`rwa_module_textures` 的私有副本仅在 drvtest 104-171（单份、失配最险），`rwa_argbuf_encoded_members` 另在 redwoodmetal.m 各写一份，device_open/close/name 与 texture_read/write/destroy 在 redwoodmetal.m 与 drawable_test.c 各写一份，这是天然的第一个去重件 | **日志字符串是机器契约**（metalcheck regex、OLD/NEW_SCHEME、TEST_KEYS_ON_SIX）：只搬代码一字不改输出；protocol-owe 表(≈7056 起)由 `tools/metal/owes.py` 生成，**逐字节留一片**（注释点名生成器）；实测 Apple 缓存地址（MTLAddDevice 0x181a1875c 等）是纯数据 move-safe；rc.jobs.metal* 步骤号契约不动 | 设备二进制里优先级最高（零装载面，重建+一次 `--time` run 即验收）；设备轮后随批或轮前单批皆可 |
| src/redwoodmetal.m | 6333 | Metal 驱动本体（libredwoodmetal.dylib + RedwoodMetal.bundle，backboardd 装载；dlopen libredwoodair） | 按 @implementation 类缝≈9-10 片：`RedwoodMetalSPI.h`(枚举再声明+`_Static_assert` 布局组 184-456 + `_MTL*` 桩与 Redwood* @interface 756-1129)≈780 头、Device impl(1130-2524) 拆 3 片（ initWithAcceleratorPort+load / pipeline+queue 工厂 / texture+argencoder 工厂）、resource 片（Buffer2526+Texture2734+Sampler3030+Depth3060≈745）、queue 片(3263-3610)≈350、cmdbuf 片(3611-4156)≈545、RenderEncoder(4158-5495) 拆 2 片（后者走 **ObjC 分类**跨 TU）、compute+argencoder(5497-6333)≈725+ | 装载面最深（docs/metal.md 10 全是实测常量）。三条硬规矩：(a) `rwa_color_blend==32`/`rwa_render_info==116` 等布局断言与 libredwoodair 对账，**逐字节进单一私有头**；(b) dylib 只许引用 `_OBJC_CLASS_$__MTLDevice` 这一个私有类符号（其余 `_MTL*` 一律不得变成链接导入，文件里有注释说明为什么避开 `_MTLFunction`）；(c) 现有 4 个 `+load`(1132/2528/2736/5887) 变跨 TU 后次序=链接序，搬动时确认各自的 install 幂等守卫在。分类不加类导入、ObjC 非脆弱 ABI，MTLAddDevice 只断言 conformsToProtocol:——分类拆法本身不动 Apple 测的布局；类名/选择器/`redwoodmetal:` 日志前缀不动 | 设备轮后（QEMU SpringBoard×2 门 + 设备 Metal smoke 各一次） |
| src/eagl.c | 4205 | GL 入口（libredwood-gl.dylib，backboardd EAGL 面；GL=1） | 按作者 `/* ---- */` banner：`eagl_private.h`(类型/名字表 78-209 含 `EAGL_GEN_DECLARATIONS` include + struct eagl/enter/leave)≈450、主 ≈700(1-77 + context 210-512 + EAGLContext 替换族+install 构造 3812-4205 + `EAGL_GEN_TABLE` include)、`eagl_surfaces.c`(IOSurfaces 513-1186)≈675、`eagl_trace.c`(trace_* 1245-1983)≈740、`eagl_emulate.c`(vblur+clear_now+census+group+plain 1984-2145+2396-3033)≈800、`eagl_entries.c`(my_gl 手写入口 1187-1244+3034-3811)≈1025→与 trace 再平衡≈2×800 | **mkeagl.py argv[4] 只扫单一源文件**：mkeagl.py:49 用 `^my_(gl\w+)\(` 认手写入口、:106 扫 `gl*` 调用补 extern——**拆分必须在同一 commit 改 build.sh:358 与 mkeagl 扫描清单**，否则手写入口静默退化成生成的 pass-through；出片的 `my_gl*` 要去 static，`EAGL_GEN_TABLE` include 留在 install/my_getMacroContextPrivate 所属 TU；`redwood_gl_function_values/_refused` 已是 inject.c 契约的非 static 导出；GL=1 stamp 块内含 mkeagl 命令行（复现关键） | 设备轮后（与 GL 设备验证同轮，mkeagl/build.sh 改动同 commit） |
| src/inject.c | 1266 | libredwood.dylib（backboardd + 两个 containermanagerd：vtable 替换 + HID 输入面） | 作者 banner 即缝：`inject_private.h`(CACHE_BASE/VSLOT/replace_virtual)≈100、`inject_windowserver.c`(CA::WindowServer+OpenGL ES 保送 101-669)≈570、`inject_hid.c`(光照+触摸/按键+input_thread 670-1123)≈455、`inject_containerd.c`(1124-1205)≈85、主(1-100+构造 1206-1266)≈160 | **实测常量最密文件**：vtable unslid 地址（VT_APPLE_CLCD_DISPLAY 0x1d5b44520、VT_EAGL_SERVER 0x1d5b45c58、VT_GLES_CONTEXT 0x1d5b3b540、MTL_DEVICE_ARRAY 0x1e1efe9a0）+ 槽偏移 0xb0/0x138/0x170/0x178/0x1a0/0x378 + 期望原值——运行时逐项校验，搬动安全但**一字不许「整理」**；构造里 opengl_es→window_server_fixes→input_start→container_manager_fixes 调用次序留一片内；DYLD_INSERT 契约=构造函数 only | 设备轮后 |
| src/inject_sb.c | 1247 | libredwood-sb.dylib（SpringBoard；构造也在别的宿主跑，那时只挂 layers 观测） | banner 即缝：`inject_sb_private.h`(say/replace_method)≈130、主(1-126+load_tweaks+构造 1059-1247)≈330、`sb_activation.c`(127-215)≈90、`sb_battery.c`(216-381)≈165、`sb_lockscreen.c`(382-555 含 remote control)≈175、`sb_switcher.c`(556-855)≈300、`sb_layers.c`(856-1058 含 CC)≈205 | 替换全按选择器名=字符串契约，move-safe；非 SpringBoard 的 layers 分发与 REDWOOD_TWEAK_LOADER dlopen 留构造片 | 设备轮后 |
| src/inject_store.c | 1827 | libredwood-store.dylib（appstored，**STOREFRONT=1 才入装配**，"not for an image anybody else boots"） | banner 即缝：`inject_store_private.h`≈120、主(1-341 观测 helper + `replacements[]` 表+image_added+构造 1668-1827)≈500、`store_watch.c`(watcher 族 342-1063)≈720、`store_answer.c`(storefront 应答+request 族 1064-1667)≈605 | 替换按类/选择器字符串注册，move-safe；若改各片自带 replacement[] 由 image_added 拼接，**必须保住晚级类加载语义**；CACHE_BASE 0x180000000 与注释里的实测地址是数据 | 观测族纯 instrumentation、替换族才碰行为；默认装配不含它——可 STOREFRONT 轮单独闸 |
| src/init.c | 1463 | process 1（/redwood 小镜像，static -nostdlib，启 launchd.ios；兼 rc 命令执行器） | banner 即缝：`init_private.h`≈60、`init_fs.c`(root_apfs 族 37-271 + copy/graft/var 恢复 540-1003)≈710、`init_tests.c`(boot 检查 272-539 + count/writable 1004-1149 + devices/time 1292-1346)≈470、主(1-36 + run_command/run_rc 1150-1291 + inject/vnodes 1347-1463)≈270 | 无实测表，风险全在行为：run_command 语义被每个 rc 文件依赖（逐字节搬）；mini.h 与 child/stage0 共享；静态链序无关 | 设备轮后、**最后拆**（复验=一次完整真机 boot）；纯注释编辑可轮前 |
| src/var_store.c | 1406 | /private/var 持久化打包器（save/load/watch；init 开机解包；persist 分区 darwin 唯一写者面） | banner 即缝：`var_store.h`(**盘上格式契约** 1-108：`HEAD_MAGIC "RDWVAR\0"`(82)+HEAD_VERSION+struct head+CRC(184-220，加载器回读校验同一算法) 单一之家、数值冻结)、`vs_io.c`(109-477)≈370、`vs_pack.c`(478-888)≈410、`vs_unpack.c`(889-1198)≈310、`vs_cli.c`(1199-1406)≈210 | struct head+magic+version+CRC 是内核 bsd/dev/redwood_ufs.c/加载器回读算的账——**只进一个私有头**；sysctl kern.redwood.var_save 是字符串 | 设备轮后、且等持久化实测稳定（格式不变则旧包可读回，验收=旧 slot show/load 对拍） |
| src/camera_device.c | 1828 | libredwood-media.dylib（mediaserverd，cam=5） | 八个作者 banner 即缝：`camera_device_private.h`(CMDerivedObject 函数表 71-186+结构)≈150、props/formats(229-397，plist 抄来的数据)≈170、`_stream.c`(398-809)≈415、`_frames.c`(810-1304 含 af)≈500、`_worker.c`(1305-1667)≈365、`_device.c`(1668-1828)≈165 | H10ISP 函数表=实测布局，表+结构逐字节进私有头；`redwood_camera_device_create` 是 inject_media.c 吃的导出名 | 设备轮后（相机排期内不插队） |
| src/audio_plugin.c | 1041 | RedwoodAudio.driver（CoreAudio HAL 插件，mediaserverd；-bundle） | banner 即缝：`audio_plugin_private.h` = COM 四张函数表+手声明结构+UID 表(70-245)≈180（与内核侧 redwood_audio.h 配对）、主(helper+COM plumbing 246-384+构造导出)≈160、`audio_props.c`(configuration_change 大 switch+has/is_settable/size/get/set 385-837)≈455、`audio_io.c`(codec open/close/read+io 操作+时间戳 838-1036)≈200 | **COM 表字段序=Apple 固定 ABI（手声明等价物），单一家逐字节**；RedwoodAudio_Create+audio_plugin.plist factory 键=dlopen 字符串契约；设备 UID 字符串是 VirtualAudio.plugin 匹配的数据，逐字节 | 设备轮后（音频排期，当前设备轮不涉声音） |
| src/camera_isp.c | 1033 | 同 mediaserverd 库（ISP 软件管线） | banner 即缝：`camera_isp_internal.h`(struct pipe+静态)≈60、`isp_stats.c`(init/sharpness/measure/ae/cct/awb/set_ccm 20-393)≈375、`isp_render.c`(pipe_init/曲线/pixel/LUT/两渲染器 394-811 含 demosaic)≈420、`isp_tune.c`(lsc_from_flat/tuning 加载混合 814-1033)≈220 | tuning 文件记录格式由 tools/camtuning.py 产（格式常量承重、数据 move-safe）；WHITE/LUT_WHITE 随渲染片 | 设备轮后（相机排期） |
| src/triangle_app.m | 1273 | RedwoodTriangle.app（自家 app，首个非守护进程 Metal 客户端，非装载链） | banner 全齐≈5 片：`rwt_private.h`≈120、`rwt_setup.m`(say+device+pipeline 156-501)≈350、`rwt_readback.m`(读回+IOSurface 502-732)≈235、`rwt_frame.m`(one frame+layer mode 733-1103)≈375、`rwt_app.m`(UIKit 类+main 1104-1273)≈175 | 无实测常量（无 vtable/导出）；rwt_* 共享全局进头；build.sh:434 有一处按「src/triangle_app.m」记的算术对账注释，搬后同步 re-grep | 进镜像字节变→默认随设备轮批；若 Lead 轮前一并重建，验证成本=重编+一次启动，可轮前做 |
| src/metal_stubdev.m | 877 | 设备诊断 `/redwood/bin`（越线 77 行） | 两片即够：`stubdev_probe.h`≈40 + `stubdev_probe.m`(stub 机制+minimal_subclass+dump/replay 134-517)≈420 + 主(1-133+interrogate/minimal/main 518-877)≈490；最小 diff 方案=只挪 note()/cache_slide | MTL_ADD/CREATE_DEVICE_UNSLID 实测字面量，move-safe；类是运行时拼的，无静态布局 | 同进镜像；轮前一并重建则验证=重编+跑一遍 |
| userland/build.sh | 847 | 构建脚本（越线 47 行；非编译单元） | **建议永不拆 + 文件头豁免**：可变全局（PREBUILT/INJECT/$M/$MESA_BUILD）线性流水、PREBUILT 分支有意复刻下方装配步骤、GL=1 stamp 块（≈330-380：MESA_FROM sha256+built-from-air 检查+mkeagl 重生成+libredwood-gl 链接）是复现承重墙——source 抽段的风险恰落在这面墙上。若要字面合规只有两条安全出口：usage 注释(1-77)挪 docs/（纯注释），或自包含的 fw/camera 循环(590-635)抽 sourced helper | 无装载面；坑在 stamp 块与 PREBUILT 路径。给其他拆分记账：每个搬出的文件都要在这里加链接项（drv_test:237、redwoodmetal:232-234、eagl+mkeagl:358-361、triangle:252、inject_*:292-310） | n/a——豁免口径（§4 第 2 项同步改） |

## 3. AIR 前端细审（tools/mesa/air，26.2.5 基线）

- 这些文件是 `src/compiler/air` 的仓内母本（rsync 进 mesa 树编译，`meson.build` 列源）。拆分 = 加 .c 文件 + meson.build 加行，容器 `mk-mesa.sh` 全量重建自动带入；**判据**：host `check.sh` 全家绿（corpus/intrincheck/texopcheck/argbuf/sampcheck/lowering/fbfetch/vattr…只取 rc）+ `air_metal_test` 全跑 + corpus `--json` 前后逐模块对账（translate 集合与 intrinsic 计数逐字节同）→ 再容器重建出 dylib，sha 入 `prebuilt/userland/SHA256SUMS` 新表段并同步文档。
- 建议批内次序（先易后难、先建网后动刀）：`air_metal_test.c`（纯 host，是其余一切的回归工具）→ `air_print.c`（912，最小刀）→ `air_module.c` → `air_intrinsics.c` → `air_to_nir.c`（核心，段边界现成，唯一硬骨头是 argbuf 段 844 行压片）→ `air_metal.c`（设备 ABI，最后）→ `air_metal.h` 不拆、只补头注释。每片一个 commit，坏一片 revert 一片。
- `air_metal.c` 的 ABI 红线：`air_metal.h` 是库↔redwoodmetal.m 的唯一契约（build.sh 把它按路径拷进镜像），拆 .c 不动 .h；两个 `static_assert`（rwa_color_blend==32、rwa_render_info==116）连同其生产者代码留在 render 一片内；`rwa_*` 导出符号一个不少（`nm -gU` 前后对表，31 个 rwa* 是现账）。
- `air_to_nir.c`/`air_intrinsics.c`/`air_module.c` 的 banner 段就是层缝本身（values/constants/memory/argbuf/instructions/CFG、families/textures/dispatcher、types/values/metadata/bodies/block），不需要发明边界；共享的翻译上下文/描述符声明集中进既有的 `air_private.h`（该模式已在用，符合 AGENTS 的 `*_private.h` 约定）。
- `air_run.c` 与 `air_metal_test.c` 都是 host-only：它们的重建不动 iOS dylib（meson 只重编改动目标），但为了少动 obj/SHA 台账，仍建议与 air 批同轮。

## 4. 优先级建议（拆分不碰装载面的排序）

1. **零字节影响、现在就能做**：`tools/air/intrincheck.py`、`kinput.py`、`metalcheck.py`、`argbufcheck.py`、`sampcheck.py`、`loweringcheck.py`、`tools/metal/owesclass.py`、`tools/apfs/apfs.py`、`write-tests.py`——纯 host python，check.sh/调用方只认路径+rc，不进任何产物。其中 intrincheck 最大（2452）且表/逻辑分离最干净，最值得先拆。
2. **host C、容器/host 可全验**：`tools/apfs/apfs-tool.c`（write-tests 对拍即验收）。`build.sh` 改按**豁免口径**处理（见 2.3 表该行：流水式可变全局 + stamp 承重墙，抽段收益 < 风险，只做文件头说明；硬要动只许 usage 注释或 fw/camera 自包含循环两处）。
3. **设备轮后第一批（AIR）**：第 3 节批内次序。理由：验证面最强（check.sh+corpus 对账能在 host 一小时内证明零翻译差异），一次重建一次重装配覆盖全批。
4. **设备轮后第二批（userland C/ObjC）**：先抽 **`redwood_air_contract.h`**（同一 rwa 契约被 metal_drv_test.m、redwoodmetal.m、drawable_test.c 三个消费者各自重声明不同子集（字段级分布见 2.3 表 metal_drv_test.m 行），去重是任何一片落地前的自然第一步）。之后按顺序：
   - `metal_drv_test.m`（体量大、零装载面、metalcheck 对账可验；若 Lead 轮前一并重编设备二进制，它是唯一可提前验收的）。
   - `inject_store.c`（观测族独立，STOREFRONT 轮单独闸）。
   - `eagl.c`（等 GL 设备验证之后；**拆分 commit 必须同时改 mkeagl.py 扫描清单与 build.sh:358**，否则手写 GL 入口静默退化）。
   - `redwoodmetal.m`（最深实测面，QEMU+设备两轮复验，三条硬规矩见 2.3 表）。
   - `inject.c`/`inject_sb.c` → camera/audio → `var_store.c`（等 persist 实测；RDWVAR 盘上格式进单一头）→ `init.c` 最后（复验成本=整机 boot）。
   - `mkapfs.py` 拆片若拿到「重打镜像字节一致」证据，可提前单独合。
   - triangle_app.m/metal_stubdev.m 验证成本极低（重编+跑一遍），Lead 轮前若重建镜像可顺带。
5. **永不拆**：`air_metal.h`（契约头，补豁免注释）；`userland/build.sh`（豁免口径，见第 4.2 项）；`eagl_gen.h` 在表外（生成物、不在 git）。`write-tests.py`/`owesclass.py` 二选一豁免也行（测试电池/查表工具，整文件头注释替代拆分）。

## 5. 复现

```
cd hackios-xnu-userland
git ls-files -z userland tools | xargs -0 wc -l | grep -v ' total$' | sort -rn | awk '$1 > 800'
grep -n "^[a-z_][a-z0-9_]*(" userland/src/<f>        # C 函数行号表
grep -n "^@implementation\|^@end" userland/src/<f>.m # ObjC 类范围
grep -n "^/\* --" tools/mesa/air/<f>                 # AIR 的 banner 段缝
grep -n "tools/air\|python3" tools/air/check.sh      # harness 的 rc-only 消费面
```
