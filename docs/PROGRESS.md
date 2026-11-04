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

**本轮方法论**：音频问题按 **内核时钟 → 声卡名 → 框架路由** 三层走，每层有独立判据，别跳层。
三个根因是**叠加**的，只修其中一两个都会「看起来改了但没声」，这是它拖了这么久的原因。

---

## 未闭环（不粉饰，接手先看这里）

| # | 项 | 现状 | 怎么闭合 |
|---|---|---|---|
| 1 | **三个 CI 包从未冷启动上板** | 只验证了构建链断言（`entries=18`、`grep rev0f.dtb`、size>170000、IP parity FATAL、`set -euo pipefail`）与回归产物逐字节相同 | 取一版 CI 产物写 TF 卡，跑一次冷启动，看串口三行 |
| 2 | 第三台板为什么拒绝合法的 `RKNS` | 头里 `0x90`/`0xe8` 是**明文** SHA256，而载荷 RC4 加密 → 离线不可复算 | 拔掉 TF 卡冷启动该机：能起 eMMC → BROM 顺序问题；起不来 → BROM 拒它 |
| 3 | USB `update.img` 只离线验证过打包 | RKDevTool/Maskrom 实刷未做 | 有空上板刷一次，确认能进系统 |
| 4 | A/B `successful:1, tries-remain:0` | 当前安全（successful 优先），但 `boot_b` 是旧镜像 | 下次换 boot 时同步刷 `boot_b` |
| 5 | **audio_policy 只在 vendor overlay 里** | 重启已实测保留；但刷 vendor / 恢复出厂会丢 | 重打包 super/vendor 风险大、收益小；现方案 = 丢了照 `board-overlay/README.md` 推三条命令 |

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
