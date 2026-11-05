# TM-android14

LYT T68M（RK3568）适配 Android 14，基线 = 友善电子 rk35xx-android14 SDK（gitea: friendlyelec/rk35xx-android14）。

## 背景

- T68M 与 NanoPi R5S 同为 RK3568（R5S 为 RK3568B2），友善官方 Android 14 BSP 原生支持 R5S，因此以该 SDK 为基线做板级移植是同 SoC 移植，不是跨平台移植。
- 板级 DTS 权威件：xck-nas 仓 `dts/rk3568-lyt-t68m.dts`（飞牛金标准，含 GPU/VPU/NPU 节点）；lyw-OS 仓 `patch/kernel/rk35xx-vendor-6.1/dt/rk3568-lyt-t68m.dts`（6.1 vendor 内核源码形态）。
- 板级硬件：2x GbE（gmac0/gmac1 RTL8211F）+ 2x RTL8125 2.5GbE（PCIe）、eMMC + TF + SATA2（combphy2，与 miniPCIe 二选一）、SDIO WiFi AIC8800、RK809 PMIC + TCS4525(vdd_cpu)、gpio/adc 双复位键。

## 仓库里都是什么

| 路径 | 是什么 |
|---|---|
| `rk3568-lyt-t68m.dts` | **板级 DTS 源文件**，移植的全部成果都在这（NPU 供电、SDIO、combphy、HDMI 音频…）。CI 编译的就是这份 |
| `dist/rk3568-lyt-t68m-android.dtb` | 上面那份编出来的成品，172,764 B。**当前机器上跑的就是它** |
| `dist/rk3568-lyt-t68m-vendor.dtb` | **本板原厂 dtb**，从 `boot_a.img` 的 `rk3568-nanopi5-rev0f` 槽提取，`compatible = "lyt,t68m"`、`model = "LYT T68M"`。**所有 CI 的对比基线都是它** |
| `dist/rk3568-lyt-t68m-sdk.dtb` | 友善 SDK 编译出的原版 dtb（改之前长什么样） |
| `dist/rk3568-nanopi5-rev01-base.dtb` | R5S（nanopi5-rev01）出货 dtb。**不是本板基线**——那是另一块板，两版 493 项属性不同。仅作 SoC IP 能力的旁证 |
| `tools/` | 移植工具链 18 个脚本：修 boot 头 SHA1、拆装 second 段、编辑 dtb、打包镜像。按症状查见 [`tools/README.md`](tools/README.md) |
| `board-overlay/` | 刷机后要手工补的运行时改动（audio_policy 两份），见 [`board-overlay/README.md`](board-overlay/README.md) |
| `docs/` | 进度表、上板 runbook、验收清单 |
| `.github/workflows/` | 六条流水线 |

## 云编译路线

GitHub Actions（ubuntu-latest，全部 `workflow_dispatch` 手动触发）：

| 工作流 | 干什么 | 产物 |
|---|---|---|
| `firmware-probe.yml` | 判据先行：runner 磁盘余量、友善 CDN 可达性、包体积 | 探测报告 |
| `fetch-images.yml` | 拉取并缓存友善 Android 14 分区包 | 分区包 |
| `dtb-build.yml` | 由 DTS 源码编译 DTB，并与 `dist/` 做 **0 IP 差异** 回归 | `t68m-dtb` |
| `build-t68m-sd.yml` | TF 卡启动镜像（sd-fuse） | `t68m-android14-sd` |
| `build-t68m-eflasher.yml` | eMMC 烧写镜像（sd-fuse eflasher） | `t68m-android14-eflasher` |
| `build-t68m-usb.yml` | Maskrom/RKDevTool 线刷包（RKAF 容器） | `t68m-android14-usb` |

### 产物怎么下、多大

| 产物 | 内容 | 大小 | 用之前 |
|---|---|---|---|
| `t68m-android14-usb` | `update.img.zst`（默认只出这个） | **815 MB**（原始 2.21 GB，压到 36.0%） | 先 `zstd -d update.img.zst`，Windows 用 7-Zip ≥ 24 |
| ↑ 同上，`with_partitions=true` | 另加 `partitions.zip` | +1.03 GB | 分区烧写兜底时才要，平时别勾 |
| `t68m-android14-sd` | `*.img.gz` + `SHA256SUMS` | 已 gzip | 先 `gunzip` 再 `dd` / balenaEtcher |
| `t68m-android14-eflasher` | `*.img.gz` + `SHA256SUMS` | 已 gzip | 同上 |
| `t68m-dtb` | 编译出的板级 DTB | 约 40 KB | 直接比对/注入 |

实测对比（同一份产物，2026-11-04）：

```
修复前  4301.5 MB   update.img 原样上传 + partitions.zip 里又打了一份 update.img
修复后  1849.6 MB   只压 update.img(2262.9 MB -> 814.6 MB, 36.0%) + 分区包
再收一步  815 MB    分区包改为 with_partitions 才产出（默认不出，内容与 update.img 重复）
```

> **线刷包压缩**：`update.img` 是 RKAF 裸容器，分区按扇区原样拼接、含大量零填充。
> 流水线用 `zstd -19` 压一遍再上传（artifact 本身 `compression-level: 0`，因为已是压缩包）；
> 以前的 4.3 GB 里有一半是同一个 `update.img` 被重复打进了 partitions.zip，已排除。
> dispatch 时填 `release_tag`（如 `v1.0.0`）可同时发布到 Release，避免 7 天 artifact 过期后重下。

## 状态

- [x] 仓库创建
- [x] probe 通过（runner 磁盘余量 + gitea 可达性判据）
- [x] T68M DTS 移植进 Android SDK 内核树 → `dist/rk3568-lyt-t68m-android.dtb`
- [x] 镜像产出：SD / eflasher / USB(update.img) 三条流水线
- [x] boot header SHA1 修正器 `tools/rk_boot_id.py`（**11-03 的产物缺这一步，全部不可启动**，见 `docs/t68m-android14-plan.md` §7）
- [x] **实机跑通（TF 卡，2026-11-04）**：HDMI 出画面、进桌面、点「重启」能真正重启
- [x] **HDMI 音频出声（2026-11-04）**：`mclk-fs 256→128` + 声卡名 `rockchip,hdmi0` + audio_policy 改 HDMI-only

## 实机结果

| 项 | 值 |
|---|---|
| 冷启动到桌面 | 162.7 s（首启含 dexopt）/ 74.0 s（之后） |
| 重启到桌面 | 74.0 s |
| hwcomposer 崩溃 | 0 次 |
| 板级 DTB | 172,764 B（`dist/rk3568-lyt-t68m-android.dtb`，`sha256 5347ff36…`） |
| boot.img | 58,161,152 B，`id@0x240 = fa48d672…`，`rk_boot_id.py check` = MATCH |
| HDMI 音频 | 声卡 `0 [rockchiphdmi0]`、`mclk-fs=0x80`、`dumpsys audio` route 全 `hdmi(400)` |

串口实证的关键几行：

```
DDR 03ea844c5d typ 24/09/03-10:42:57,fwver: v1.23
Bootdev(atags): mmc 1
MMC1: Legacy, 52Mhz
DTB: rk3568-nanopi5-rev0f.dtb (172541)
vp0 assign plane mask: Cluster0|Cluster1|Esmart0|Esmart1[0xf], primary plane phy id: Esmart0[2]
rockchip-drm display-subsystem: bound fe040000.vop
reboot: Restarting system with command 'userrequested'   ← 之后重新出现 DDR/U-Boot SPL
```

一共打通 **9 个断点**：eMMC RKNS 清零、misc BCB、OP-TEE `devnum`、NPU+iommu panic、
SD 控制器 pinctrl 层级、super sparse→raw、A/B tries 扣光、vop plane 绑定、
**reboot → MaskROM（TF 卡被 `mmc_power_off()` 断电）**。

完整修法、判据、时间线、回滚见 **`docs/tfcard-android14-runbook.md`**。

## 现状一句话

从厂商包到「HDMI 出画面 + 出声音 + 重启可用」已全链路跑通，**改的只是一个 DTB + 两份 audio_policy**。
剩下的都是优化项，不是功能缺陷：second 段瘦身（31 个别的板子的 DTB 白占 6.34 MB）、
A/B `tries-remain` 恢复成 7、把 audio_policy 的 overlay 改动落回 vendor 镜像。

## 刷机 / 恢复出厂后必做

DTS 的音频修复随 boot.img 持久，但 `/vendor/etc/` 里那两份 audio_policy 是 overlay 改动，
**刷 vendor 或恢复出厂就丢，表现是「又没声音了」**（画面正常，很容易误判成硬件坏了）。

源文件在 [`board-overlay/vendor/etc/`](board-overlay/vendor/etc/)，推三条 adb 命令即可，
具体步骤和三条自检判据见 [`board-overlay/README.md`](board-overlay/README.md)。

## 文档索引

| 文档 | 什么时候看 |
|---|---|
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | **每天做了什么、还差什么** —— 每日进度表 + 未闭环清单，接手先读这张 |
| [`docs/tfcard-android14-runbook.md`](docs/tfcard-android14-runbook.md) | 上板实操：9 个断点逐个修、判据、回滚、不拔卡换 boot |
| [`docs/t68m-android14-plan.md`](docs/t68m-android14-plan.md) | 固件解剖、方案取舍、boot header SHA1 那一节（§7） |
| [`docs/boot-verify-checklist.md`](docs/boot-verify-checklist.md) | 上电验收清单，把「能不能启动」变成可对照的判据 |
| [`docs/usb-flash-readme.txt`](docs/usb-flash-readme.txt) | USB 线刷三步走（随刷机包一起分发） |
| [`tools/README.md`](tools/README.md) | 工具集速查：按症状找脚本 |
| [`board-overlay/README.md`](board-overlay/README.md) | 刷机/恢复出厂后要补的运行时改动（目前只有 audio_policy 两份） |

## 一条硬纪律

**「构建成功」≠「能启动」。** CI 绿了只证明构建链完整（产物尺寸、`entries=18`、`grep rev0f.dtb`、
IP 功能矩阵 0 差异），不证明冷启动能过。判定能不能起，只看串口那三行：
`DTB: <name> (<size>)`、`androidboot.dtb_idx=`、以及 `Trying to boot from MMC1/MMC2`。
