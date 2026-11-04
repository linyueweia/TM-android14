# TM-android14

LYT T68M（RK3568）适配 Android 14，基线 = 友善电子 rk35xx-android14 SDK（gitea: friendlyelec/rk35xx-android14）。

## 背景

- T68M 与 NanoPi R5S 同为 RK3568（R5S 为 RK3568B2），友善官方 Android 14 BSP 原生支持 R5S，因此以该 SDK 为基线做板级移植是同 SoC 移植，不是跨平台移植。
- 板级 DTS 权威件：xck-nas 仓 `dts/rk3568-lyt-t68m.dts`（飞牛金标准，含 GPU/VPU/NPU 节点）；lyw-OS 仓 `patch/kernel/rk35xx-vendor-6.1/dt/rk3568-lyt-t68m.dts`（6.1 vendor 内核源码形态）。
- 板级硬件：2x GbE（gmac0/gmac1 RTL8211F）+ 2x RTL8125 2.5GbE（PCIe）、eMMC + TF + SATA2（combphy2，与 miniPCIe 二选一）、SDIO WiFi AIC8800、RK809 PMIC + TCS4525(vdd_cpu)、gpio/adc 双复位键。

## 云编译路线

GitHub Actions（ubuntu-latest）分两步走：

1. **probe**（`.github/workflows/probe.yml`）：实测 runner 磁盘余量、gitea 源可达性与浅克隆体积 —— 判据先行，确认全量构建可行性。
2. **build**（后续）：按 probe 结果落构建工作流（内核/DTB 编译 → 全量镜像或分段构建）。

## 状态

- [x] 仓库创建
- [x] probe 通过（runner 磁盘余量 + gitea 可达性判据）
- [x] T68M DTS 移植进 Android SDK 内核树 → `dist/rk3568-lyt-t68m-android.dtb`
- [x] 镜像产出：SD / eflasher / USB(update.img) 三条流水线
- [x] boot header SHA1 修正器 `tools/rk_boot_id.py`（**11-03 的产物缺这一步，全部不可启动**，见 `docs/t68m-android14-plan.md` §7）
- [x] **实机跑通（TF 卡，2026-11-05）**：HDMI 出画面、进桌面、点「重启」能真正重启

## 实机结果

| 项 | 值 |
|---|---|
| 冷启动到桌面 | 162.7 s（首启含 dexopt）/ 74.0 s（之后） |
| 重启到桌面 | 74.0 s |
| hwcomposer 崩溃 | 0 次 |
| 板级 DTB | 172,541 B（`dist/rk3568-lyt-t68m-android.dtb`） |
| boot.img | 58,161,152 B，`id@0x240 = fa48d672…`，`rk_boot_id.py check` = MATCH |

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

从厂商包到「HDMI 出桌面 + 重启可用」已全链路跑通，**改的只是一个 DTB**（外加重算 boot header 摘要）。
剩下的都是优化项，不是功能缺陷：second 段瘦身（31 个别的板子的 DTB 白占 6.34 MB）、
A/B `tries-remain` 恢复成 7。
