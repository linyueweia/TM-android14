# T68M × FriendlyElec Android 14：现状与方案（2026-11-03）

## 1. 基线固件解剖（rk3568-sd-android14-20251222.img.gz）

- **不是 RKFW**，是 GPT 整盘 SD 镜像：gzip 展开后 3.83 GiB，idbloader 在 LBA 64（magic `RKNS`）。
- GPT 17 分区：`uboot_a/b` 各 4 MiB、`misc`、`dtbo_a/b`、`vbmeta_a/b`、`boot_a/b` 各 64 MiB、
  `super` 3200 MiB、`userdata` 3614 MiB。
- `boot_a` 是 Android boot v2：kernel 31.8 MB / ramdisk 17.2 MB / second(RSCE) 7.4 MB，
  cmdline 含 `console=ttyFIQ0 androidboot.hardware=rk30board androidboot.selinux=permissive`。
- `uboot_a` 是 FIT（u-boot gzip 616 KB + ATF×6 + OP-TEE + MCU + 内部 dtb `rk3568-nanopi5`），
  config 名 `rk3568-nanopi5` → RK3568 全家族共用同一份 u-boot 构建。
- `vbmeta_a`：AVB 1.0，`auth_block=0`，`flags=0x2` → **VERIFICATION_DISABLED**。
  改 boot/super 内容不受 AVB 拦（与 `verifiedbootstate=orange` 一致）。

## 2. second 段 = RSCE v0 资源镜像（已解出格式）

```
+0x000 header 512 B : "RSCE" | u32 0 | u16 0x0101 | u16 0x0001 | u32 count | zeros
+0x200 entry 512 B  : "ENTR" @0 | path[256] @4 | u32 offset_blocks @0x104 | u32 size @0x108
data                : 从 512 + 512*count 起，512 对齐
```
offset **单位是 512 字节块**。本包 37 条：rk3399×10、rk3528×1、rk3566×3、
**rk3568-nanopi5-rev01/02/03/04/05/07 ×6**、rk3576×3、rk3588×12、logo.bmp、logo_kernel.bmp。

## 3. u-boot 怎么选 DTB（字符串实证）

uboot 二进制里：`rk3568-nanopi5-rev%02x.dtb`、`fdtfile`、`androidboot.dtb_idx=0`、
`failed to select board fdt index`、`DTB: %s (%d)`。

链路：**读板级 hwrev → 拼 `<soc>-nanopi5-rev%02x.dtb` → 在 RSCE 索引里按名字查 →
命中项下标写进 cmdline 的 `androidboot.dtb_idx=`**。

默认 env 里**没有** `fdtfile`，uboot 分区 0x3F8000 处的 env 区全零 → 不能靠 `setenv fdtfile` 绕过，
只能让名字命中，或改 u-boot 里的模板串。

## 4. 改造方案（已实现，待完整固件执行）

1. `tools/rsce_tool.py boot-replace` 把 `rk3568-nanopi5-rev*` 六个槽换成 T68M DTB，
   `--fill-revs 0-15` 再把 rev00/06/08..0f 十个缺失槽补上 → **hwrev 探测到 0x00..0x0f 任一号都命中**。
2. 校验：head+kernel+ramdisk 除 `second_size@0x18` 外逐字节不变；entry 数/名字/其它 blob 全保留。
3. 产出 `boot_a` 58.1 MB（分区 64 MB，未越界）。
4. `tools/make_sd_img.py` 流式解压源 gz → 只改 boot_a 区间 → 重新 gzip，峰值占用 ~4.5 GB。

已演练：用 fnOS 的 `lyw-OS/tools/tests/fixtures/rk3568-lyt-t68m-run73.dtb`（170516 B，model=LYT T68M，
`sata@fc800000` okay / `mmc@fe000000` okay / `pcie@fe270000+fe280000` okay）生成过 `boot_a.t68m.img`，
16 个 rk3568 槽全部 model=LYT T68M。

## 5. 阻塞项

- **用户手上的 img.gz 不完整**：物理 662,700,032 B（632 MiB），gzip 流在解出 1,811,939,328 B
  （声明 4,113,133,951 B，44%）处 `EOFError`。super 分区跨过断点，无法产出整盘镜像。
  判据：`python -c "import gzip;f=gzip.open(p);...` 计数到 1.81 GB 报 EOF。
  → 需要重下完整包（友善下载页 `https://dl.friendlyelec.com/nanopir5s`）。
- CI `dtb-build` 正在编 Android SDK 版 `rk3568-lyt-t68m.dtb`（用 SDK 的 `rk3568.dtsi`，
  比 fnOS fixture 更贴合 Android 内核）。出来后替换本方案里的 dtb 再出最终镜像。

## 6. 风险边界

卡是 SD 整盘镜像，RK BootROM 优先 SD：刷坏只坏这张卡，板上 eMMC 里原有系统不受影响，
不需要救砖卡。未知项只有两个 —— 友善 loader 的 DDR 参数能否带起 T68M 的颗粒、以及 hwrev 探测值；
两者都在上电串口里立刻现形（u-boot 会打印 `DTB: <name> (<size>)`）。

## 7. 2026-11-04 复查：三套产物"跑绿但必挂"的根因

**结论：11-03 的 SD / eflasher / USB 三个 artifact 全部不可启动，缺的是 boot header 的 20 字节。**

### 现象（实机 2026-11-03）

```
DTB: rk3568-nanopi5-rev0f.dtb (172191)      ← 槽位命中，DTB 是我们的，没问题
Hash from header: 0xef77b76c…
Hash real:        0x757de090…
Failed to load android image
AVB verify failed / Android boot failed, error -1.
```
之后回落 eMMC 的 `boot.scr`（安卓 u-boot 不认 iNetOS 命令 → 乱码 SCRIPT FAILED），再掉进 PXE，
两口 PHY 各 -110 超时循环 —— 看起来像 loader/DDR 崩了，其实只是 20 字节。

### 为什么

RK u-boot 开了 `CONFIG_ANDROID_BOOT_IMAGE_HASH`，`common/image-android.c` 在进内核前校验 boot.img：
期望值存在 **AOSP v2 header 偏移 0x240 的 `id[8]`**（RK 复用那 32 字节）。摘要覆盖：

```
for seg in (kernel, ramdisk, second[, recovery_dtbo[, dtb]]):
    sha1.update(data[:size]); sha1.update(u32le(size))
```
（`image_load()` 里 `crypto_sha_update(data,datasz)` + `crypto_sha_update(&datasz,4)`；
 kernel 段先 `ramdst += pgsz; datasz -= pgsz`，所以 header 页不进 hash；size==0 的段仍喂 4 字节零）

`rsce_tool.py boot-replace` 换了 RSCE 里的 DTB → 内容变了 → id 还是原厂的 → 校验失败。

**不是 AVB**：`vbmeta` 是空的（`flags=0x2` = VERIFICATION_DISABLED），没有 descriptor 可重签。
日志里的 `OK_NOT_SIGNED` 是**通过**，不是错误。

### 当时的流水线

三个 workflow 的注入步骤只做了 `boot-replace` + `boot-list`，**没有回写 id**；
`tools/rk_boot_id.py` 甚至不在仓库里。所以 CI 绿了，产物是废的。

### 现在

```
tools/rk_boot_id.py              check / fix / info   ← 新增
tools/test_rk_boot_id.py         合成 v1/v2 夹具，12 项断言
tools/rehearse_boot_pipeline.py  用真实 T68M DTB 走 boot-replace → check → fix → check
```
三条 workflow 在注入之后都加了 `Fix boot header SHA1`，并以 `check` 输出 MATCH 作为门禁。

本地排练实测（合成容器 + 真 DTB 172191 B）：
```
boot-replace  3,172,352 -> 4,874,240 B（second 变长，正常）
check         MISMATCH            ← 注入后必然失配，因果链成立
fix           20 byte(s) changed  ← 只动 0x240..0x253
check         MATCH
boot-list     16/16 槽 = LYT T68M (172191 B)
```

### 仍未验证

- 友善 loader 的 DDR `sdram_configs_g` 能否带起 T68M 的颗粒（代码同源不等于表相同，见技能 §9）
- hwrev 实际探测值（16 槽已铺满，任一号都命中，风险已消除）
- NPU 在 Android 14 + 6.1 vendor 上是否 `panic_on_set_idle`（fnOS 线会崩，Android 出货板是全 okay）
- 实机一次都没跑过；下一轮上电看串口第四行是否变成 `ANDROID: Hash OK`
