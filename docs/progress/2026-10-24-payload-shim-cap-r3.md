# BootShim 严格分支、packer PAYLOAD_CAP 与 CAP 接入：r3 收口归档（2026-10-24）

## 1. 范围与结论

本条工作覆盖三个文件族：`Mu-Silicium/BootShim/BootShim.S` 的通用严格分支（同时定义 `PAYLOAD_BASE` 与 `PAYLOAD_CAP` 宏时启用，含运行期地址算术前检与六条编译期配置自检）、`mkxnuimg.py` 的 `PAYLOAD_CAP` 严格模式（容器规则校验与全部非法输入在首次 unlink/make/写输出之前拒绝）、`uefi/mu-silicium.patch` 的 BootShim 段同步，以及 CAP 接入三件（`common/devices/annibale.conf` 置 `PAYLOAD_CAP=0x03700000`、`common/build.sh` 原样转发、`common/lib.sh` 的 `load_device` 在 source 目标设备配置前仅 `unset PAYLOAD_CAP`）。Astra r3 独立快验通过，结论为：以上源码与 host 侧模拟有限通过，无新增必要修复，生产文件与测试冻结不再扩实现、不提交。

## 2. Astra 复核结论记录

r2 复核：packer 前置验证已关闭非法容器与 FD 长度类输入的运行前拒绝；尚缺 `PAYLOAD_BASE` 负值、`PAYLOAD_BASE+PAYLOAD_CAP` 越过低 4 GiB 边界、FD 目标与 payload 窗口交叠三类配置的前置拒绝（此类配置会先删除旧 shim 并在 make 阶段被编译期自检拒绝）。r3 增量按 Astra 复现值补齐三项，判定式与端点语义同 BootShim 编译 guard 一致。r3 独立快验：两份 r2 清单与 r3 增量核验成功，39+9 项与新增反例复跑成功，独立复现确认三类配置现在首个构建副作用之前拒绝；CAP 接入与 shim Q=0 修复、固定机器码有限通过。

## 3. 测试统计（主机侧，均为成功记录）

契约测试 `tools/test-bootshim-contract.py` 全量 40 项：改动前基线由改动前 patch 重建并哈希比对；legacy 与 plain 编译产物同基线逐字节一致；静态核对含 annibale 严格机器码固定（`.text` sha256 前缀 `0a5cbe63`，368 字节）；11 例错误编译配置被编译期自检拒绝；packer 9 组容器边界与畸形输入；完整 CLI 夹具 15 例非法输入 0 次 make 调用且 sentinel 逐字节不变、2 例合法输入恰好一次 make；qemu 真实执行 15 布局。接入测试 `tools/test-payload-cap-wiring.py` 9 项：CAP 经真实 `load_device` 与 build 调用行进入 make 宏，继承清空、双向设备切换、profile 覆盖、其余环境变量保留。

## 4. 尚待验收边界

实际新 FD 镜像的产出与回读、最终封装镜像、loader（BootManagerLib 侧消费方）及真机运行期契约在本条工作中未验证；本轮全部验证为 host 侧编译、模拟执行与 stub 夹具，未做设备操作、端到端镜像与整构建，未提交。15 个 qemu 布局在 r3 增量轮未于工作树重跑（机器码未变），仅在其冻结快照副本内跑过全量 40 项。

## 5. 归档目录标识

以下本地临时归档目录（Git 忽略区）以清单自哈希唯一标识；复核时在归档目录内执行 `shasum -a 256 -c SHA256SUMS` 并比对下值：

| 归档内容 | 清单自哈希（SHA256SUMS.sha256 首字段） |
|---|---|
| shim/packer r1（36 项契约测试基线） | `70a0ab5e4333769b64cb846b54907c61b2f646e71114961799f6ac543e203922` |
| CAP 接入 r1 | `42a8aef21fb8f8778b5199c7ed918eb3325cb4965b22cc374f11300f43b1ea22` |
| 依赖补充与环境继承反例 | `2ec4167bafbdcb4a7b5a83a0c212aabaa196f5f6fbc238d33777feb95c79b8f0` |
| shim/packer r2（两条必修项，39 项） | `5246917a3c42690d49d8dfb44d41c84f11b4242dbaa6492444d78c2415441ee7` |
| CAP 接入 r2（load_device 清空，9 项） | `0e7544566b93474537a952cbf7d2f277444722fc2e10ae5329c217cf9e26d3fa` |
| packer 预检对齐 r3（guard 全量对照，40 项） | `c0ac9a57d4e23248945738eb71fcef11949bbb879b2e913a53a8af1793f9a864` |

## 6. 构建输入哈希清单（供 7b 构建输入准备）

工作树相对路径，基线为内核子模块 HEAD `c0716bffc0246e7d1494b1f130672fae0f170f6c`、Mu 子模块 HEAD `87416d23ecde1a2be3a5b0b00b8c914071e802e1`：

| 文件（相对 hackios-xnu-kernel/） | SHA256 |
|---|---|
| `common/lib.sh` | `98a3dfb109b766f5334d4d52bfd928d8095b686b978271f0e64897543654ee8e` |
| `common/build.sh` | `b38ab49e7fffda0de48790226b9dec3ffb9dcf4574436b74db8c175869e20642` |
| `common/devices/annibale.conf` | `c2746a00682ee629ca61b34df6629acaba1b4123b011b6e85766e5d9b43c81e5` |
| `mkxnuimg.py` | `9fbc4ced159de6a72baf039496de19e6f7a689bc1367e5a1d4cf428fa8c05d77` |
| `uefi/mu-silicium.patch` | `67569759e576c1741cd95725423791abeec5e90f21bfb134f22d199bc9c874fa` |
| `Mu-Silicium/BootShim/BootShim.S` | `18e247cf58faac685f18977cc729491bca043bb192cf3733e3218b9341c3563f` |
| `tools/test-bootshim-contract.py` | `9cea2540941ec2e7da25aab14976d47e2d7e6ebbaa134704d74b790187a53ae3` |
| `tools/test-payload-cap-wiring.py` | `dc5b180e0e5939dc7eea305e1396f18522651b9803831f73f534020f6cc9f8e8` |

`tools/` 两文件为未跟踪新文件；其余六个文件相对各自子模块 HEAD 为修改状态。patch 的 BootShim 段与工作树 `BootShim.S` 逐字节一致（契约测试内含该断言）。
