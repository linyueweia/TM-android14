# T68M Android 14 移植 —— 每日进度表

> 日期以 **git 提交时间**为准（`git log --date=format:"%Y-%m-%d"`），不凭记忆。
> 每条都要能落到一个判据：字节数、sha256、串口某一行、或 CI 某个 run id。
> **「构建成功」不等于「能启动」**，状态列写「构建通过」的，就不要读成「已验证」。

图例：✅ 实机验证通过 ｜ 🟡 构建/离线验证通过（未上板）｜ ❌ 走过死路（已记录）｜ ⬜ 未开始

---

## Day 1 · 2026-11-03 —— 从零搭出构建链

| # | 完成项 | 判据 / 证据 | 状态 |
|---|---|---|---|
| 1 | 板级 DTS `rk3568-lyt-t68m.dts` 进 SDK 内核树，`dtb-build` 流水线跑通 | 产物 172,191 B（pyfdt 版）/ 172,259 B（dtc 正式编译），IP 功能矩阵一致 | 🟡 |
| 2 | 摸清 second 段格式 = **RSCE v0**（老资料说的 `rk-kernel.dtb` 是错的） | `tools/rsce_tool.py` 能列出 37 个 dtb 条目 | ✅ |
| 3 | u-boot 按**名字**选 dtb：`rk3568-nanopi5-rev%02x.dtb` ← hwrev | `rev0f` 槽存在与否决定能否上板 | ✅ |
| 4 | 三条流水线：`fetch-images` / `build-t68m-sd` / `build-t68m-eflasher` | SD 1,092,675,207 B、eflasher 1,392,627,345 B | 🟡 |
| 5 | USB 线刷包 `update.img`（RKAF，afptool + rkImageMaker）+ 分区包兜底 | 2,378,732,106 B | 🟡 |
| 6 | 踩坑：gitea→Azure clone 39~54 min 会 hang；Azure blob 支持 Range（16 段并发） | `curl -r 0-1023` 返回 206 | ❌→✅ |

**当日遗留（后来被证实是致命的）**：三套产物都缺 boot header SHA1 回写，上板必然停在 `Failed to load android image`，而且 console 是哑的（`ttyFIQ0` 在本板没接 fiq-debugger）。

---

## Day 2 · 2026-11-04 —— 打通实机，从「能构建」到「能启动」

| # | 完成项 | 判据 / 证据 | 状态 |
|---|---|---|---|
| 1 | 定位并修复 **boot header SHA1**（偏移 `0x240` 的 20 字节） | 自检 PASS → 真 boot.img MISMATCH → 改 20 字节 → `MATCH` | ✅ |
| 2 | console 从 `ttyFIQ0` 改 `ttyS2` | 串口开始有内核日志 | ✅ |
| 3 | **TF 卡实机跑通 Android 14**：HDMI 出画面、进桌面、点「重启」能真重启 | 冷启 u-boot 7.0s → init 9.9s → logo 15.3s → zygote 24.9s → 首启 dexopt ~150s → bootanim 退出 162.7s；二次启动 74.0s | ✅ |
| 4 | 修「重启变关机」：`SWITCH_REG2`/`LDO_REG5` 加 `regulator-always-on` | 重启后串口立刻出现 `DDR 03ea844c5d` + `U-Boot SPL board init` | ✅ |
| 5 | **NPU 结论反转两次，最终定为供电问题** | 根因是 `vdd_npu` 缺 `regulator-always-on/boot-on/init-microvolt`；补上后 `Initialized rknpu 0.9.8`、`failed to get ack` 计数 0 | ✅ |
| 6 | `adb` 直刷 `boot_a`：不拔卡换 DTB | push + sha256 比对 + `bs=512 count=` 精确写 + 回读校验，10 秒 | ✅ |
| 7 | 与 R5S 厂商 DTB 做 **IP 对齐**（"逐字节"的正确做法） | 语义级比对：共同节点 995、语义一致 964、**IP 差异 0**；补 `crypto`/`dfi`/`suspend` 三项 | ✅ |
| 8 | 抓出 **CI 三次假绿** 并修掉 | ① dts `&/* 注释 */` 语法错 + 无 pipefail；② YAML 块标量里 heredoc 顶格 → dispatch 422；③ `make_lite_boot` 丢 `--fill-revs` 缺 `rev0f` | ❌→✅ |
| 9 | 恢复 eMMC 系统（此前只动了 LBA64 前 4 字节） | 写回 `RKNS`，iStoreOS 打出 `is ready!` | ✅ |
| 10 | 定性启动优先级**分两层**：BROM 固定 SPI→eMMC→SD，u-boot 才 SD 先扫 | 四台对照：判据看 SPL 打 `MMC1`(eMMC) 还是 `MMC2`(SD) | ✅ |
| 11 | 第三台反例：eMMC 的 `RKNS` 合法却仍走 SD | 推翻「有 RKNS 就能启动」；**原因未定，不编** | ⚠️ |
| 12 | 修 iStoreOS 拿不到 IP | `network.lan.netmask` 缺失 → netifd 下发 /32 → dnsmasq 无 dhcp-range | ✅ |

## Day 2 晚 · 2026-11-04 —— 外接盘、/data 重建、产物瘦身

| # | 完成项 | 判据 / 证据 | 状态 |
|---|---|---|---|
| 1 | SATA「认不到」定性：**不是驱动，是 user 0 没解锁** | 内核 `ata1: SATA link up 6.0 Gbps` + `FORESEE 128GB SSD`；vold `delaying scan due to secure keyguard`；`dumpsys user` = `RUNNING_LOCKED` | ✅ |
| 2 | 根因确认：weaver 槽绑 SoC，换机后 `/data` 密码学不可恢复 | `weaver read failed (INCORRECT_KEY)` → `Failed to unwrap synthetic password` | ✅ |
| 3 | 走弯路并记录：删 spblob 无效、`locksettings clear` 假成功 | 变 `secdiscardable file not found`，比原来更糟 | ❌ |
| 4 | 查明「恢复出厂没生效」：这块板**没有 recovery 分区** | `bootreason=recovery` 但备份文件还在、`/data/app` 时间戳未变 | ✅ |
| 5 | 绕过 recovery 重建 `/data`：dd 抹超级块 → fstab `formattable` 自动重格式化 | user 0 `RUNNING_UNLOCKED`、`mCurrentFocus=QuickstepLauncher`、`/data` 3.5G 全新 | ✅ |
| 6 | **SATA 同时挂上了**（推翻我自己的 f2fs 判断） | `public:8,1 mounted 4d6577c6-…`，`/dev/fuse` 117G / 已用 4.1G，SSD 数据一字未动 | ✅ |
| 7 | USB 线刷包 **4301.5 MB → 815.3 MB（-81%）** | ① `zstd -19`：2,372,776,522 → 854,902,146 B（36.0%）；② zip 里重复打包 `update.img` 已排；③ 分区包改 opt-in | ✅ |
| 8 | 发布 **Release v1.0.0** | `update.img.zst` 815.3 MB + `.sha256`；job 级 `contents: write` | ✅ |
| 9 | 核对构建用的是最新 DTB（三重） | 172,602 B / `sha256 55766d94…` / 与提交内 blob 逐字节相同 / 该 dtb 是 0-IP-差异回归的被测对象 | ✅ |
| 10 | 仓库收尾：剔 `__pycache__`、补 `tools/README.md`、README 产物对照表 + 文档索引 | `git status` 干净 | ✅ |
| 11 | 技能库 `rk-android-board-porting` → **v1.5.3** | 新增 §8c 产物分发、§11e/11f/11g/11h；台账 H7~H12 | ✅ |
| 12 | 线刷包改 **zip**（最常用工具）+ 产物改名 `设备名-安卓版本-*` | `zstd -19` 36.0%/815 MB → `deflate -9` 实测 40.1%/~950 MB，仍远低于 Release 2 GiB 上限；7-Zip 旧版/资源管理器双击可开 | ✅ |

---

## Day 3 · 2026-11-04 —— HDMI 音频闭环（有画面没声音）

| # | 完成项 | 判据 / 证据 | 状态 |
|---|---|---|---|
| 1 | 定性「有画面没声音」不是硬件/EDID 问题 | 同一台显示器在 R5S 厂商固件上画面+声音都正常；本板 `/proc/asound/cards` 只有 card 0，无板载 codec | ✅ |
| 2 | 根因一：`hdmi_sound` 的 `mclk-fs` 默认 256，dw-hdmi 按 **128×fs** 采样 | 设备树实读 `simple-audio-card,mclk-fs` = `00 00 00 80`（=128）；在此之前 DMA/DAPM 全正常、`dmesg` 零报错，静默无声 | ✅ |
| 3 | 根因二：声卡名不匹配 RK audio HAL 的硬编码 `rockchiphdmi0` | 设备树 `simple-audio-card,name` = `rockchip,hdmi0`；`/proc/asound/card0/id` = `rockchiphdmi0`；改前是 `invalid card num` | ✅ |
| 4 | 根因三：`audio_policy` 拿 `Speaker` 当默认输出、`attachedDevices` 无 `HDMI Out` | `defaultOutputDevice` = `HDMI Out`；`dumpsys audio` 里 stream 的 `Device` 12 条全是 `hdmi(400)` | ✅ |
| 5 | **实机出声**（用户听感确认） | 三项结构判据 + 人耳 | ✅ |
| 6 | audio_policy 纳入版本控制，解决「刷机即丢」 | 新增 `board-overlay/vendor/etc/`（两份 xml）+ `board-overlay/README.md` 写清推送步骤与三条自检判据 | ✅ |
| 7 | 重启后音频配置仍在（overlay 是否持久化） | 重启到 `sys.boot_completed=1` 后，两份 xml 的 md5 仍是 `a1fed148…` / `31b7c053…`，与仓库逐字节相同；声卡仍 `rockchiphdmi0`、`defaultOutputDevice` 仍 `HDMI Out` | ✅ |
| 8 | 记录一条判死禁忌：**别用 `tinyplay` 判断系统有没有声音** | `tinyplay` 直接打 PCM 到声卡、绕开 AudioFlinger，与系统媒体流是两条路 | ❌→✅ |
| 9 | 发现 CI 的 parity 门禁**管不到板级节点** | `dtb_diff.py --only-ip` 只比 SoC IP；`/hdmi-sound` 是板级节点，改回 256 也全绿 | ✅ |
| 10 | 补四道 dtb 门禁（编译产物断言 / 与 dist 语义一致 / 注入前校验 / 产物字节校验） | sd 实测 `gate: dtb in boot.img OK (172625 B at offset 49040896)` | ✅ |
| 11 | 六条流水线全部基于同一提交重跑 | `c320983`：dtb-build、sd、firmware-probe、fetch-images 全绿；usb/eflasher 跑完前关机 | 🟡 |
| 12 | 抓到门禁自身的 bug：比 `phandle` 误报 | run 41858170120 四个属性全对，却报 `/hdmi-sound differs: ['phandle']` → 排除后 c320983 通过 | ❌→✅ |

**本轮方法论**：音频问题按 **内核时钟 → 声卡名 → 框架路由** 三层走，每层有独立判据，别跳层。
三个根因是**叠加**的，只修其中一两个都会「看起来改了但没声」，这是它拖了这么久的原因。

---

## Day 4 · 2026-11-05 —— DTB 对齐到「这块板自己」

### 起因

USB3.0 口插 2.4G 接收器毫无反应（内核零日志），怀疑当初 DTB 对齐没做干净。
查下来怀疑只对了一半，但翻出一个更根本的问题。

### 关键事实

`boot.img` 的 second 段里有 47 个 dtb，这块板的槽位是 **`rk3568-nanopi5-rev0f.dtb`**，
`compatible = "lyt,t68m"`、`model = "LYT T68M"` —— **它才是本板原厂配置**，一直躺在固件里。

而 2026-11-04 的 `9a8ff0e「与 R5S 厂商 DTB 做 IP 对齐」` 拿的是 `nanopi5-rev01`，
那是 `FriendlyElec` 的 R5S，**另一块板**，两版之间 **493 项属性不同**。

| 节点 | 原厂 T68M(rev0f) | R5S(rev01) | 我们当时 |
|---|---|---|---|
| `/dfi@fe230000` | okay | disabled | disabled |
| `/crypto@fe380000` | disabled | okay | okay |
| `/rockchip-suspend` | disabled | okay | okay |
| `power-domain@6` | disabled | 无 status | 无 status |

### 但 USB 不是这个原因

对原厂 rev0f 与运行中的 dtb 做 **USB/PHY 21 个节点全量对比：0 差异**。
控制器 `phys` 指针、`usb2-phy@fe8a0000/host-port` 的 `status`、`phy-supply`、
USB3 combphy 全一样。**USB 段从 SDK 继承，一个字没改，改 DTB 也不会好。**

### 真正修掉的

| # | 项 | 判据 |
|---|---|---|
| 1 | 基线换成 `dist/rk3568-lyt-t68m-vendor.dtb`（从 boot 提取的原厂），4 条流水线 `--base` 全改 | `dtb_features` 里 `SD-card disabled <<< DIFF` 假告警消失 |
| 2 | 四项偏差改成**显式声明 + 注释为什么与原厂不同**，不再靠默认值 | 编译产物 status 与意图一致 |
| 3 | `headroom 0 B` 确认是**误报**：槽 size 恒等于 dtb 大小，`max-len` 必然 0 | 打印改成 `16 board slot(s), 172764 B each`，三条构建的 grep 同步换 |
| 4 | **补回 `vop-supply` + `support-multi-area`**（原厂有、我们缺，真 bug） | 见下 |
| 5 | boot_a **和** boot_b 都刷同一镜像，A/B 对等 | 两槽 sha256 都是 `91a0ea9f` |

### VOP 那条是真 bug

```
before: rockchip-vop2 fe040000.vop: error -ENODEV: _opp_set_regulators: no regulator (vop) found
        rockchip-vop2 fe040000.vop: failed to init opp info
after : vop2_bind 正常，bin=0 leakage=62 leakage-volt-sel=0
```

`vop-supply` 指向 `DCDC_REG1`（`vdd_logic`，0.75–1.35 V）。缺它 → OPP 表设不起来 →
按频率调压失效，高分/高刷时可能花屏掉帧。这一条是从 SDK 版继承时丢的，跟 R5S 无关。

### 不是问题的三条（已核实原厂同样报，别浪费时间）

- `rockchip-snps-pcie3-phy fe8c0000: failed to find rockchip,pipe_grf regmap`
  —— `/phy@fe8c0000` 两边属性逐项一致，驱动找的属性名与 dtsi 不符
- `clk: failed to reparent i2s1_mclkout_tx ... -22` —— `&i2s1_8ch` 只加了 `trcm-sync-tx-only`
- `mali fde60000.gpu: no DT entry: mali-simple-power-model.*`
  —— `/gpu@fde60000/power-model` 这个节点**三份 dtb（T68M 原厂 / R5S / 我们）属性逐项一致**，
  `compatible` 都是 `simple-power-model`，而 DDK g25p0 找的是 `arm,mali-simple-power-model`。
  名字对不上是 dtsi 与驱动版本的错配，**R5S 同样会报**。驱动随后自己 fallback：
  `Using configured power model mali-g52_r1-power-model`，GPU 功能不受影响，只是功耗估算用内置表。

### 实机验收（重启后）

| 项 | 结果 |
|---|---|
| 启动 | `sys.boot_completed=1`，`bootreason=reboot,shell`（真重启） |
| 运行树 vs dist | 只差 6 个运行时动态节点（serial / bootargs / MAC / memory / sdhci） |
| 音频 | `card0=rockchiphdmi0`、`defaultOutputDevice=HDMI Out`、12 条 `hdmi(` 路由 |
| VOP | OPP 生效，`failed to init opp info` 消失 |
| A/B | boot_a / boot_b sha256 一致 |

### CI

`dtb-build` 通过，输出 `dist parity OK (0 IP diff)`：源码编出的 dtb（172,565 B）与刷进机器的
（172,764 B）字节不同，但语义完全一致 —— 差异来自手工 `fdt_edit` 与 `dtc` 的字符串表排布。

---

## 交接（截至 2026-11-05 13:00，机器在线）

### 现在是什么状态

**这台 T68M 是能用的**：TF 卡启动 → HDMI 出画面 + 出声音 → 点重启能真重启 → SATA 盘 117G 数据完好。
当前在跑的 dtb 是 `172,764 B / sha256 5347ff36…`，与仓库 `dist/rk3568-lyt-t68m-android.dtb`
语义一致（`/sys/firmware/fdt` 只差 6 个运行时动态节点）。A/B 两槽同一镜像（`sha256 91a0ea9f…`）。

| 已闭环 | 判据 |
|---|---|
| 启动 + 重启 | 冷启 162.7 s / 热启 74.0 s，重启后串口重新出 DDR + U-Boot SPL |
| NPU | `Initialized rknpu 0.9.8`，`failed to get ack` = 0 |
| SATA 外接盘 | user 0 解锁后 `public:8,1 mounted`，117 G / 已用 4.1 G |
| HDMI 音频 | 声卡 `rockchiphdmi0`、`mclk-fs=0x80`、route 全 `hdmi(400)`、人耳确认 |
| 音频配置持久性 | 重启后两份 xml 的 md5 与仓库一致（刷 vendor/恢复出厂才丢） |
| DTB 基线 | 换成 `dist/rk3568-lyt-t68m-vendor.dtb`（本板原厂 rev0f），四条流水线 `--base` 全改 |
| VOP OPP | 补回 `vop-supply` 后 `failed to init opp info` 消失，改为 `bin=0 leakage=62` |
| A/B 对等 | boot_a / boot_b 同一镜像，两槽回读 sha256 相同 |
| CI 门禁 | `dtb-build` 输出 `dist parity OK (0 IP diff)` |

### 在跑的三条（2026-11-05 12:46 触发，基于 `0ec44e1`）

| 流水线 | run id |
|---|---|
| `build-t68m-sd` | **41969792044** |
| `build-t68m-usb` | **41969795647** |
| `build-t68m-eflasher` | **41969799453** |

**如果失败了，先看是不是 dtb 门禁拦的** —— 那说明 dtb 有问题，不是流水线坏了。

### 下次开机第一件事

```bash
# 1) 看 device 还认不认。**必须插 OTG 口**，两个 USB2.0 口是纯 host，插了 adb 会断
adb devices
# 2) 音频还在不在 —— 恢复出厂过的话大概率没了
adb shell cat /proc/asound/card0/id          # 需 rockchiphdmi0
adb shell "grep -o '<defaultOutputDevice>[^<]*' /vendor/etc/audio_policy_configuration.xml"
# 3) 不在就补：见 board-overlay/README.md 的四条命令
```

### 尚未闭环（按优先级）

1. ~~**USB3.0 口不认 USB2 设备**~~ —— **已在 Day 5 闭环**。真因是 OTG 角色锁死 device，
   与差分对、供电、连接器都无关。本段原先的推断已被实测推翻，**不要再引用**。
2. **鼠标右键→返回没持久化** —— 现方案是 `getevent` + `input keyevent 4` 的脚本，重启即失效。
   要落到 `/vendor/etc/init/*.rc` 才算真解决（一并考虑 `input` 每次起 Java 进程 ~150 ms 的延迟）。
3. **三个 CI 产物从未冷启动上板** —— 所有"能启动"的结论都来自手工产物。
4. **USB `update.img` 未实刷**，只离线验过打包 + 门禁。
5. **audio_policy 没落到 vendor 镜像** —— 重打包 super 风险大，现方案是丢了照文档推一遍。
6. **第三台板拒绝合法 `RKNS`** —— 原因未定，不编。头里 `0x90`/`0xe8` 是**明文** SHA256，
   而载荷 RC4 加密，离线不可复算。判据：拔掉 TF 卡冷启动该机，能起 eMMC → BROM 顺序问题；
   起不来 → BROM 拒它。

## Day 5 · 2026-11-05 —— USB3.0 口固定 host（真因是 OTG 角色锁死）

| # | 完成项 | 判据 / 证据 | 状态 |
|---|---|---|---|
| 1 | 定位真因：不是 DTB 缺节点，是 **OTG 角色永久锁死 device** | 拔掉调试线后 `extcon0` 仍持续报 `USB=1/SDP=1`，63 秒采样一次未变；同组 `USB_VBUS_EN=0` | ✅ |
| 2 | 运行时强制切 host，证明硬件通路完好 | `echo host > /sys/kernel/debug/usb/fcc00000.usb/mode` 后 **1.7 s** 注册 `xhci-hcd.7.auto`，`port01 = Powered Connected Enabled Link:U0`，接收器 `7-1` 枚举（鼠标可用） | ✅ |
| 3 | 试「照抄 R5S」方案并否决 | R5S 的 `fcc00000` 多 `usb-role-switch` / `role-switch-default-mode="host"` / `role-switch-visible`；照抄重启后 **114 条采样全部 `mode=device`**，一次未变 | ❌ |
| 4 | 最终修复：`dr_mode = "host"` + 删 `extcon` | dist dtb 172,764 → **172,745 B**；995 节点中 994 语义一致，仅 `fcc00000` 两处改动 | ✅ |
| 5 | 实机冷启动验证 | 串口 1500000：`xhci-hcd.0.auto: irq 42, io mem 0xfcc00000`、`usb 5-1: Product: Wireless Receiver`、`hid-generic … [Telink Wireless Receiver]`；串口查得 `MK:host`、`XH:xhci-hcd.0.auto` | ✅ |

**被推翻的三个判断（留痕）**：

1. Day 4 记的「该口只引了 SuperSpeed 差分对，全速 12 Mbps 接收器物理上不可能工作」——**推翻**。
   切成 host 后该接收器正常枚举，USB2 差分对是通的，硬件从来没问题。
2. 「照 R5S 加 role-switch 三属性即可解决」——**推翻**。属性确实注册成功
   （`/sys/class/usb_role/fcc00000.usb-role-switch` 出现），但 `extcon` 一直持有 device
   请求，`role-switch-default-mode` 轮不到生效。
3. 「DTB 的 USB/PHY 节点与原厂 0 差异，改 DTB 不会好」—— 只对了一半：节点集合确实一致，
   但**角色属性的取值本身就是原厂给错的**（`dr_mode=otg` + `extcon`），所以出路仍在 DTB。

**取舍**：该口物理上只有一条角色通道，host 与 device 不能共存。本板固定 host，
调试改走串口（`COM3` / 1500000 / `su 0` 有 root shell）。

**未闭环**：
- **网络 adb 没打通**：eth1 `link up 1000M`、`IpClient` 已在跑，但网线另一端没有 DHCP 服务器；
  `ndc interface setcfg` 被 netd 拒（`400 Failed to set address`），Android 14 的
  `cmd ethernet` 未实现（`No shell command implementation`）。
- 鼠标右键→返回仍未持久化（同 Day 4 第 2 条）。

### 改动落在哪

- 仓库 `github.com/linyueweia/TM-android14`，分支 `main`
- 板级修复全在 `rk3568-lyt-t68m.dts` → 编出 `dist/*.dtb` → CI 注入 boot.img
- 运行时改动只有 audio_policy 两份，在 `board-overlay/`
- 技能库 `rk-android-board-porting` v1.5.6：§8d（四道门禁）、§8e（选对基线）、§11i（HDMI 三层判据）

---

## 每日追加模板（复制下面这段，别改格式）

```markdown
## Day N · YYYY-MM-DD —— 一句话主题

| # | 完成项 | 判据 / 证据 | 状态 |
|---|---|---|---|
| 1 |  |  |  |

**未闭环**：
**下一日**：
```

三条写法约定：

1. **判据列只写真数据**——字节数、sha256、串口原话、run id。写「已验证通过」不算判据。
2. **被推翻的结论要留痕**，标明「推翻」，别悄悄改掉（H10 就是这么救回来的）。
3. 一天里如果有死路，用 ❌ 记，并写清「为什么此路不通」——这比记成功更有价值。
