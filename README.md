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
- [ ] probe 通过（拿到磁盘/克隆体积判据）
- [ ] T68M DTS 移植进 Android SDK 内核树
- [ ] 镜像产出与实机启动验证
