# Mesa rebase 试验（25.0.7 → 26.2.5）

日期：2026-10-23。作者：mesa（GPU L2 前置试验，task-5）。产物：本文档 + `hackios-xnu-userland/tools/mesa/rebase-26/`。

## 0. 结论速览

- 8 个 fork 补丁在 26.2.5 上：**4 个原样存活**（air-frontend、air-metal、ir3-round-default、ir3-ssbo-subdword，其中 ssbo-subdword 带 fuzz），**1 个可安全退役**（ir3-shift-split，触发 bug 的上游折叠逻辑已消失），**3 个部分失效需改写**（air-ir3、freedreno-darwin、osmesa-es-profile），全部失效点已被 `rebase-26/0003` 适配层覆盖。
- darwin 原生编译**全绿**：26.2.5 + 两个 cherry-pick + 适配层后 `ninja` 零错误，产出 `libOSMesa.8.dylib`（20.3 MB，导出 1300 个 `gl*` + 13 个 `OSMesa*`），软管线冒烟（clear→readPixels 像素正确、ES profile 上下文报 "OpenGL ES 3.1 Mesa 26.2.5"）通过。
- a8xx（SM8750/adreno-830，chipid 0x44050000）：真实 devinfo 条目 26.1.0 起才存在（26.0.x 的 "FD830" 是 cffdump 假条目），`CHIP >= A8XX` 运行时分支 26.0.0 起可用；两个 7 月修复（2ee0a5e6 indirect-buffer WFM、779cdb8e gen8+ query barriers）只进 26.3，cherry-pick 到 26.2.5 干净。
- 建议路线：**26.2.5 + 0001 + 0002 + 适配层**为基线试验版本；自研 AIR 前端的 26.x NIR/st API 迁移**已完成**（第 8 节：编译链接全绿 + 软管线冒烟通过，改动全部在 `tools/mesa/air/` copy 目录内）。
- 阻塞点：hackios-dev 容器缺 meson/ninja/bison/flex/theos，iOS 交叉构建未做；真机 freedreno 路径未验证（需用户态整机跑通后测）。

## 1. 试验设置与复现

流程与 `hackios-xnu-userland/tools/mk-mesa.sh` 一致：解压上游 tarball → 依序应用 `tools/mesa/*.patch` → 拷入 `src/compiler/air`、`src/redwood-drm`（mk-mesa.sh 的 copy 目录，不是补丁）→ 应用 rebase-26 层。

- 基线：`mesa-26.2.5.tar.xz`，sha256 `794b3d1729075dae7ebd47c7283b7ca0cdb5dec668f7f11cc0a5d82f6138a0a5`（archive.mesa3d.org）。对照组：26.1.8、26.3.0-rc1（sha256 `63327d58a51d189c1d1600746c505609bba5c495123b4e51de4e0c038b745542`）。
- 构建机：macOS 27 / arm64 主机原生（补丁里的 darwin 分支按 `host_machine.system()=='darwin'` 走，与 iOS 交叉路径同一批代码）。工具链：ninja 1.13.2（brew），bison 3.8.2（brew，**本次会话在主机安装的**，系统 bison 2.3 过老），meson 1.12.1 + mako + pyyaml（venv，临时在 /tmp）。
- configure 相对 mk-mesa.sh 的改动：去掉 `-Dgallium-vdpau` `-Dgallium-xa`（26.x 已删这两个 option），`-Dshared-glapi=enabled` 保留但上游已标记废弃（deprecation warning），其余 flag 不变。完整命令见本报告末尾附录 A。

## 2. 逐补丁存活表（26.2.5）

| 补丁 | 严格应用(fuzz=0) | 默认 fuzz | 逐文件明细 | 处置 |
| --- | --- | --- | --- | --- |
| air-frontend | 通过 | 通过 | `subdir('air')` 锚点未漂移 | 保留 |
| air-metal | 通过 | 通过 | libredwoodair/air_metal_test 目标声明可应用 | 保留 |
| air-ir3 | 失败 | 失败 | `ir3_cmdline.c` 已被上游删除（986530d231，25.3+），8 hunk 全空；freedreno/meson.build 的 `air_run` exe hunk 上下文漂移 | 删 cmdline 部分；`air_run` 声明并入 0003 |
| freedreno-darwin | 失败 | 失败 | `src/freedreno/drm/meson.build` 1/2（libvdrm TODO hunk，上游已修）；`fd6_draw.cc` 1/1（fb_read 锚点漂移）；`freedreno_screen.c` 2/2（`pipe_screen.ram_size`/sysinfo 已删）；osmesa 三文件（frontends/targets meson、osmesa_target.c）因文件缺失跳过 | 拆分：删死 hunk，fb_read 重锚与 osmesa 钩子并入 0003 |
| osmesa-es-profile | （空跑） | （空跑） | `include/GL/osmesa.h`、`osmesa.c` 在 26.x 整体不存在（见第 3 节） | 内容并入 0003 的恢复文件 |
| ir3-round-default | 通过 | 通过 | `create_cov` 舍入块 26.2.5 仍无 else 分支（ir3_compiler_nir.c:411 附近），修复仍然必要 | 保留 |
| ir3-shift-split | 失败 | 失败 | helper 函数 hunk 可应用；使用点 hunk 失败——26.x 重写后的 `ir3_nir_try_propagate_bit_shift` 只匹配纯 ishl/ishr/ushr，不再拆 `(c+x)>>s` | **退役**：实测 bug（grid_buf[id-1] 读 0）成因已在上游消失，负常量 iadd 折叠已不存在 |
| ir3-ssbo-subdword | 失败 | 通过 | 两 hunk（cb_data 传 compiler、`may_lower_unaligned_stores_to_atomics`）均带 fuzz 应用成功，vanilla 26.2.5 无 `may_lower_*` 字段确认是补丁生效 | 保留（提交前把 hunk 上下文刷新成严格匹配） |

对照：26.1.8 与 26.3.0-rc1 上默认 fuzz 的失败集合与 26.2.5 基本相同（rc1 另有个别 osmesa 文件缺失跳过导致的退出码差异）。

## 3. 最大成本：上游删除了 OSMesa

upstream 027ccd963b（2025-03-04，自 25.1-branchpoint 起生效）整体删除 OSMesa 前后端，替代路线是 EGL surfaceless；而 hackios 的 CoreAnimation 供帧路径（`userland/src/eagl.c`、`gl_osmesa.c`）dlopen 的是 `libOSMesa.8.dylib`，iOS 侧没有现成 EGL 栈，短期只能恢复 OSMesa。恢复清单（全部固化在 `rebase-26/0003-restore-osmesa-26.x-drift-adaptations.patch`）：

1. 反向应用 027ccd963b 的 meson 接线：`meson.options` 加回 `osmesa` option，根 `meson.build`/`include/meson.build`/`src/gallium/meson.build` 恢复 `frontends/osmesa`、`targets/osmesa` 子目录。
2. 从打补丁的 25.0.7 树取回 9 个文件（`include/GL/osmesa.h`、frontends/osmesa 2 个、targets/osmesa 6 个），内容已含 osmesa-es-profile 与 freedreno-darwin 的 osmesa 钩子。
3. 六类 26.x 适配（这是真正的漂移成本）：
   - `inc_mapi` 不复存在；`inc_glapi` 只在 `src/mesa/glapi` 子目录可见，三处 meson 改用字面 `include_directories('../../../mesa/glapi')`。
   - `with_shared_glapi` 变量没了，targets/osmesa 直接链 `libglapi`。
   - **gl\* 导出**：26.x 的 shared-glapi 静态库只含调度核心，`gl*` 桩在 `libglapi_bridge`（wgl/libgl-xlib 专用），osmesa 目标不链它导致 dylib 一个 `gl*` 都不导出——把 `libglapi_bridge` 加进 `link_whole` 后恢复 1300 个导出（arm64 上该桥库原生可编译，实测无 asm 问题）。
   - `driParseConfigFiles` 变 3 参（`driConfigFileParseParams`），osmesa_target.c 调用点重写。
   - 26.x 删除了 osmesa 的 postprocess 阶段（`postprocess/filters.h`），`pp_*` 全部剥离，`OSMesaPostprocess` 保留为 no-op 存根（本端口从未启用 filter；`OSMesaFinish` 25.0.7 也从未有过，非本次引入）。
   - `src/util/u_sync_provider.c` 在 declare_dependency 场景被误编译（darwin 下 redwood-drm 替身无 syncobj），加 `host_machine.system() != 'darwin'` 门控。

验证（macOS 主机）：`ninja` rc=0；`nm -gU` 见 1300 个 `_gl*`、13 个 `_OSMesa*`；`rebase-26/smoke-osmesa.c` 输出 `GL_VERSION: 3.3 (Compatibility Profile) Mesa 26.2.5 / GL_RENDERER: softpipe`，clear(0.25,0.5,0.75) 回读像素 (64,128,191,255) 正确；`smoke-osmesa-es.c` 用 `OSMESA_ES_PROFILE` 建出 "OpenGL ES 3.1" 上下文。真机 msm 屏路径（osmesa_target 的 driinfo "msm" screen 创建 + IOSurface 导入）未经设备验证。

## 4. AIR 前端 26.x API 漂移（已按第 8 节迁移完成）

`src/compiler/air`（copy 目录）在 26.2.5 下 `air_run` 与 `libredwoodair` 编译失败（每 TU 20 错误被截断），归为 12 类机械问题：`PIPE_SHADER_*`→`MESA_SHADER_*`；`gl_shader_stage`→`mesa_shader_stage` 及 `gl_shader_stage_name` 转内部；`nir_builder.exact` 移除（4 处）；NIR pass 参数 `nir_shader*`→`nir_function_impl*`（2 处）；3 个函数签名参数数变化（含 air_run.c 里同样的 `driParseConfigFiles` 10 参调用）；`pipe_screen.get_compiler_options` 移除；`pipe_context.create_surface` 移除；glsl_type 查询回调返回类型 int→unsigned。libOSMesa 主库不受影响（air 目标 `build_by_default:false`）。预计 1–2 个工作日，全部是机械改写 + 一轮语义复核（尤其 `b->exact` 移除后 iadd 溢出标志的取舍）。

## 5. a8xx（SM8750）可用性结论

- 真实 devinfo：`0xffff44050000` + a8xx_gen1 gallium props（含 `gmem_vpc_bv_pos_buf_size`）由 48be91d1 于 **26.1.0** 进入；26.0.x 仅有 cffdump 假 "FD830"，**26.0.x 否决**。
- `CHIP >= A8XX` 运行时分支：26.0.0 起存在（fd6_emit.cc 等），26.2.5 齐备。
- 两个关键修复仅在 26.3-branchpoint：`2ee0a5e6`（Indirect buffer needs WFM on a8xx+，改 fd6_barrier.*/fd6_context.cc）、`779cdb8e`（Fix query barriers for gen8+，改 fd6_query.cc）。cherry-pick 到 26.2.5 零冲突，已作为 `rebase-26/0001、0002` 存档。
- 26.3.0-rc1 原生含这两个修复，且 fork 补丁栈失败集合与 26.2.5 相同、适配层 0003 仅 `freedreno/meson.build` 2 个 hunk 需手工移植——想省 cherry-pick 可换 26.3 基线，代价是 rc 质量。

## 6. 建议路线

1. 短期试验基线：**26.2.5 + 0001 + 0002 + 0003**，`mk-mesa.sh` 的 `VERSION=25.0.7`、`SHA256=592272df…` 改 `26.2.5` / `794b3d17…`，并在原 `for p in tools/mesa/*.patch` 循环后追加 `for p in tools/mesa/rebase-26/*.patch`（rebase-26 子目录不在现有 glob 内；mk-mesa.sh 不在本次写权限内，留给 Lead 改）。
2. 稳定后整理补丁栈：ir3-shift-split 删除；freedreno-darwin 按功能拆成 drm-meson / bo-iosurface / batch-fb_read / osmesa-target 多片；osmesa 恢复独立成片（升级上游版本时最先重挂的就是它）。
3. AIR 前端按第 4 节清单迁移，迁移完再谈 iOS 交叉与真机。
4. 真机验证清单（设备可用后）：a830 上 air_run 单测 → GLES 用例经 eagl/OSMesa 全链路 → `2ee0a5e6/779cdb8e` 针对的 indirect/query 场景专项。

## 7. 环境缺件与阻塞记录

- hackios-dev 容器（Ubuntu 24.04 arm64）缺 meson、ninja、bison、flex、theos 与 iPhoneOS16.5.sdk，iOS 交叉构建本次未做；未在容器硬装（按约定记录）。
- 主机侧本次装了 brew bison 3.8.2（系统 2.3 不可用）；meson 用 /tmp 临时 venv，均为试验环境，不进 prebuilt 流程。
- 上游源：GitHub 镜像不可靠，走 gitlab.freedesktop.org（GitLab API project 176 查 commit/diff）+ archive.mesa3d.org tarball；`git ls-remote --tags` 的 tag 有 `mesa-` 前缀。
- 过程文件（构建日志、参考树、diff 前的原树）在 `/tmp/mesa-rebase/`，非持久。

## 8. AIR 前端迁移到 26.2.5（task-6，已完成）

按第 4 节清单把 `tools/mesa/air/`（copy 目录，源即真身，不另做补丁）迁到 26.2.5：`libair.a`、`air2nir`、`air_run`、`libredwoodair.dylib` 及 `air_metal_test` 全部编译链接通过，软管线冒烟通过。改动 7 个文件 +132/−122，全部落在 `tools/mesa/air/`，`rebase-26/0003` 无需连带修改。

### 8.1 逐类落地情况

| 第 4 节清单项 | 落地方式 |
| --- | --- |
| `PIPE_SHADER_*`→`MESA_SHADER_*` | 全局改名（`PIPE_SHADER_IR_NIR` 仍在 p_defines.h，不受影响）；`enum pipe_shader_type`→`mesa_shader_stage` |
| `gl_shader_stage`/`gl_shader_stage_name` | →`mesa_shader_stage`/`_mesa_shader_stage_to_string`（shader_enums.h） |
| `nir_builder.exact` 移除 | 26.x 用 `b.fp_math_ctrl` 位域替代；air_private.h 加 `air_builder_set_exact()`（清/置 `nir_fp_exact` = no_contract\|no_reassoc\|no_transform），4 处 save/restore 改存 `uint32_t`，语义等价 |
| NIR pass 参数 `nir_shader*`→`nir_function_impl*` | `nir_block_create(c->nir)`→`nir_block_create(c->b.impl)`（2 处）；`nir_shader_create` 第四参 driver_options 删除（1 处） |
| 3 个函数签名参数数变化 | `driParseConfigFiles` 10 参→`driConfigFileParseParams` 3 参（air_run.c、air_metal.c 两处，与 0003 同款只填 screenNum/driverName）；`set_constant_buffer` 去 `take_ownership`；`set_sampler_views` 去尾 bool |
| `get_compiler_options` 移除 | 改读 `screen->nir_options[MESA_SHADER_*]`（freedreno 对 i≤COMPUTE 都填；null=无 NIR，判空语义不变） |
| `create_surface` 移除 | **实际比清单更大**：26.x 的 `pipe_surface` 成了纯值结构，`pipe_framebuffer_state.cbufs/zsbuf` 按值内嵌。air_metal.c 帧目标块与 air_run.c RT 循环重写为 `pipe_surface_init()` 就地填充，销毁=对 `.texture` 做 `pipe_resource_reference(&…, NULL)`（与 u_fb_copy/u_fb_destroy 的上游惯例一致）；值填充不可能失败，原两条 create 失败错误分支按语义删除 |
| glsl_type 回调返回 int→unsigned | 两处 `type_size_vec4` 返回类型改 `unsigned` |

### 8.2 清单之外新发现的漂移（本节为权威清单）

- `pipe->clear` 6 参→8 参：新增 `color_clear_mask`/`stencil_clear_mask`/`scissor_state`；两处调用改传 `0xf`/`0xff`/NULL（整面清除，attachments 仍由 buffers 位决定）。
- `pipe_screen.get_compute_param` 移除，改 `screen->compute_caps` 值结构：`max_threads_per_group` 直读；**`subgroup_sizes` 语义变了**——25.0.7 freedreno 答字面 32，26.x 存"支持宽度集合的位掩码"（rusticl 取位号还原，freedreno 填 `threadsize_base |= 2×base`），取最低位（32|64→32）作为执行宽度；softpipe 全零时仍回退 1，与旧 decline 行为一致。
- `unreachable()` 改名 `UNREACHABLE()`（util/macros.h），air_metal.c 补 include。
- `nir_copy_prop`→`nir_opt_copy_prop`（air2nir.c，1 处）。
- 上游删 `ir3_cmdline.c` 的连带面在测试侧：`discardcheck.py`/`cpuref.py` 需要 `ir3-compiler` 工具（26.x 没有），这两个 harness 在 26.x 主机环境暂不可跑，属 harness 待适配而非前端缺陷。

### 8.3 软管线冒烟（macOS 主机，`AIR_RUN_SOFTWARE=1`，air_run/air_metal_test 均为 26.2.5 产物）

- `fragpos.ll`（自证像素坐标约定的片元着色器）：air_run 4×4 绘制回读像素 (0,0) = **(0.5, 0.5, 0, 1)**，左上原点+y 翻转视口正确。
- `tools/air/texopcheck.py`：纹理取样 **27/27** 逐一精确命中。
- `tools/air/argbufruncheck.sh`（走 libredwoodair 的 compute dispatch + 渲染双路径、参数缓冲上传、fence）：**20/20 通过**（air_metal_test 需 install_name_tool 把 `/redwood/lib/libredwoodair.dylib` 改指本地 dylib，纯主机链接路径问题）。
- 未做：`ios165/rootfs` 的 456 模块 corpus 未在本机解包，corpus.py/intrincheck 语料项跑 0 例（脚本自报 "NOTHING WAS COMPARED"，非失败）；iOS 交叉与真机仍按第 6 节顺序待设备。

### 8.4 复现

构建树 `/tmp/mesa-rebase`（REBASE=26 流程产物）：改 `tools/mesa/air/` 后 `rsync -a --delete` 进 `mesa-26.2.5/src/compiler/air/`，`ninja -C build-darwin -k 0 src/gallium/drivers/freedreno/air_run src/gallium/drivers/freedreno/libredwoodair.dylib src/compiler/air/air2nir src/gallium/drivers/freedreno/air_metal_test`。

## 附录 A：复现命令

```bash
# 假设 /tmp/mesa-rebase 下已解压 mesa-26.2.5 并应用 fork 补丁栈 + rebase-26/*.patch，
# src/compiler/air、src/redwood-drm 已按 mk-mesa.sh 拷入
export PATH=/opt/homebrew/opt/bison/bin:$PWD/venv/bin:$PATH   # bison>=3 + meson venv
meson setup build-darwin mesa-26.2.5 --wrap-mode=nofallback --prefix=/redwood --libdir=lib \
  --buildtype=release -Db_ndebug=true -Dplatforms= -Dgallium-drivers=softpipe,freedreno \
  -Dfreedreno-kmds=msm -Dvulkan-drivers= -Dglx=disabled -Degl=disabled -Dgbm=disabled \
  -Dosmesa=true -Dllvm=disabled -Dshared-glapi=enabled -Dgles1=disabled -Dgles2=enabled \
  -Dopengl=true -Dzstd=disabled -Dxmlconfig=disabled -Dexpat=disabled -Dshader-cache=disabled \
  -Dvalgrind=disabled -Dlibunwind=disabled -Dglvnd=disabled -Dvideo-codecs= -Dtools= \
  -Dgallium-va=disabled -Dlmsensors=disabled -Dbuild-tests=false
ninja -C build-darwin
```
