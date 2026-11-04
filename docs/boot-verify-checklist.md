# T68M 上电验收清单（Android 14）

> 目的：把"能不能启动"从猜测变成一串可对照的判据。上电前把串口开好，
> 全程只用耳朵听、眼睛看，不在板子上跑任何写操作。

## 0. 上电前

| 项 | 要求 |
|---|---|
| 串口 | COM3（CH340），**1500000 8N1**，先开好抓取再上电 |
| 卡 | 用 CI 产物 `t68m-android14-sd` 的 `img.gz`，`gzip -dc | dd` 到 TF 卡（或 balenaEtcher 直写 .gz） |
| eMMC | 不动。SD 优先启动，刷坏只坏卡 |
| 备份 | 板上 iNextOS 若在跑生产，先记下 `/etc/config`、`/root/.ssh` |

写卡命令（Linux/macOS）：

```bash
gzip -dc rk3568-sd-android14-6.1-arm64-*.img.gz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress
sync
```

Windows 用 balenaEtcher / Rufus 直接选 `.img.gz`。

## 1. 串口应该依次出现（判据链）

```
# ① DDR / loader —— 友善 loader 能否带起本板颗粒
DDR ... fwver: v1.23
# ② u-boot 选中了哪份 DTB —— hwrev 的唯一可靠答案
DTB: rk3568-nanopi5-rev0X.dtb (172191)
# ③ 我们修的 20 字节到底对不对
ANDROID: Hash OK
#    ↑ 出现这行 = boot header SHA1 对上了，内核即将接管
# ④ 内核起来（这一步依赖 cmdline 已改成 ttyS2）
Booting Linux on physical CPU 0x0000000000 [0x412fd050]
Machine model: LYT T68M
...
Run /init as init process
```

**第 ③ 行是分水岭。** 出现 = 我们这轮的修正生效；不出现 = 看下面分支表。

## 2. 分支表：卡在哪，下一步查什么

| 现象 | 含义 | 下一步 |
|---|---|---|
| 串口全无输出 | loader 没跑起来 | DDR 配置表不兼容（`sdram_configs_g`），换板上现役 idbloader 覆盖 LBA64 |
| 有 DDR 日志，死在 `DDR ...` 之后 | DDR 训练失败 | 同 SoC 不同颗粒，需按 §9 换 loader，不是 DTB 问题 |
| `DTB: ... (尺寸不对)` | 落到了厂商 DTB | RSCE 槽位没铺满，查 `boot-list` 是否 16/16 |
| `Hash from header` ≠ `Hash real` | **我们漏了回写** | 这条 11-03 踩过；现在 CI 有门禁，若再现说明产物是旧的 |
| `ANDROID: Hash OK` 后立刻沉默 | 内核起来了但 console 哑 | cmdline 没换成 ttyS2（§4d），或 uart2 被别的驱动占了 |
| `Kernel panic - not syncing: ... npu` | NPU `panic_on_set_idle` | 临时把 `&rknpu` 关掉再编一版，先让系统进去 |
| 内核日志到 `Run /init` 后卡住 | init 阶段问题 | 看 SELinux（`androidboot.selinux=permissive`）、super 分区完整性 |

## 3. 一次性要抓的东西

```bash
# 串口全程日志（Windows + plink 或 putty 的 session log 都行）
# 上电后 60 秒内的完整输出，尤其 ① ② ③ 三段
```

如果能进 adb：

```bash
adb shell 'cat /proc/device-tree/model; ls /sys/class/ata_port; ls /sys/bus/sdio/devices; ls /dev/rknpu'
```

期望：`LYT T68M`、`ata1`、SDIO 设备非空、`/dev/rknpu` 存在。
NPU 存在不代表能用；跑 `rknn_server` 才有结论。

## 4. 回滚

SD 路线零风险：拔卡即回到 eMMC 的 iNextOS。
不要把 SD 镜像直接刷进 eMMC —— userdata 写死 3.6G、GPT 备份表落在 7.8G 处，
eMMC 容量不同会分区错位。要上 eMMC 用 `t68m-android14-eflasher` 那张卡。
