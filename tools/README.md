# tools/ —— 板级移植工具集

全部只用 Python 3 标准库（`serial` 仅 `adb_flash_boot.py` 之外的部分需要），Windows / Linux 都能跑。
每个脚本都能 `-h` 看参数，这里只写「什么时候用它」。

## 先看这里：按症状找工具

| 症状 | 先用哪个 |
|---|---|
| 板子起不来，串口停在 `Failed to load android image` | `rk_boot_id.py check` —— 99% 是 header 里的 20 字节 SHA1 过期 |
| 桌面能起但 NPU/GPU/VPU 静默残废 | `dtb_features.py --base <出货板 dtb>` 比功能矩阵 |
| 想证明「和厂商 DTB 除了板级差异啥都一样」 | `dtb_diff.py`（语义级，跳过 phandle 本身） |
| 换了板子，`hwrev` 探测不到自己的 dtb | `make_lite_boot.py --fill-revs 0-15`（16 个槽全铺） |
| 不拔卡想换 boot.img | `adb_flash_boot.py`（push + sha256 + 精确 dd + 回读校验） |
| 串口要登进 Linux/Android shell 跑命令 | `serial_shell.py`（在技能库里，同款） |

## 固件解剖 / 打包

| 脚本 | 用途 |
|---|---|
| `dtb_tool.py` | 最小 FDT 读写 + RSCE / boot.img 解析，其它工具的地基 |
| `rsce_tool.py` | RSCE v0 资源镜像与 boot.img v2 的 dtb 替换（`probe` / `boot-list` / `boot-replace`） |
| `make_lite_boot.py` | 只保留本板需要的 second 段条目，16 个 rev 槽全铺，显著瘦身 |
| `build_boot_img.py` | 从零组装 boot.img，并严格校验 head/kernel/ramdisk 未被改动 |
| `boot_cmdline.py` | 读/改 boot.img 的 kernel cmdline（`console=`、`androidboot.*`） |
| `rk_boot_id.py` | **重算 u-boot 校验的 `id[20]` SHA1**（偏移 0x240），`check` / `fix` / 自测 |
| `sparse2raw.py` | Android sparse → raw，流式低内存 |
| `make_sd_img.py` | 由友善 gz 包生成 T68M 版 SD 镜像 |
| `build_t68m_sd.sh` | sd-fuse 一键流程（SD / eflasher 两条） |

## DTB 编辑

| 脚本 | 用途 |
|---|---|
| `dtb_diff.py` | 两棵 DTB 的语义级差异；`--only-ip` 只看 SoC IP，`--summary` 看统计 |
| `dtb_features.py` | 打印/对比 NPU、GPU、VPU、RGA、PCIe、SATA、OP-TEE、CMA 的 enable 矩阵 |
| `ensure_android_nodes.py` | 给板级 dtb 补齐 Android 需要的节点（pyfdt 路线，注意 regulator phandle） |
| `fdt_edit.py` | 通用结构编辑：改/加属性、加/禁节点 |
| `fdt_move_node.py` | 整节点搬移（长度不变，纯结构块操作） |
| `patch_dtb_status.py` | 在 boot.img 的所有 `rev*` 槽里原地改某个节点的 status |

## 实机

| 脚本 | 用途 |
|---|---|
| `adb_flash_boot.py` | adb 直写 A/B boot 槽：`--img`、`--slot`、`--no-reboot`、`--verify-only` |

## 自测 / 复现

| 脚本 | 用途 |
|---|---|
| `test_rk_boot_id.py` | `rk_boot_id.py` 的自测，构造 v1/v2 合成 boot.img |
| `rehearse_boot_pipeline.py` | 用合成容器**按 CI 的真实顺序**跑一遍，不用下 1 GB 包 |

## 约定

- 改 DTB 一律**先验证结构**：`totalsize == len(data)`、逐 token 走完、depth 归零且只有一个 END。
- 改 boot.img 一律**重算 `id[20]`**，否则 u-boot 直接 `Failed to load android image`。
- 任何「字节数差几十」都不算问题，验收标准是**功能矩阵逐行一致**（`dtb_features.py`）。
