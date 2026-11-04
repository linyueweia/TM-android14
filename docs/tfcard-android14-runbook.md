# T68M 从 TF 卡跑 Android 14：完整运行手册

> 状态：**实机跑通**（2026-11-05）。HDMI 出画面、进桌面、点「重启」能真正重启。
> 目标板：LYT T68M（RK3568，4 GB LPDDR4，板级版本 `0x0f`）
> 基线：友善 `rk3568-sd-android14-*` 官方包 + 只换板级 DTB

---

## 1. 结论先放前面

这条路线能成，**只取决于三段：loader(DDR) + u-boot + DTB**，跟 AOSP 源码无关。
总共踩了 9 个断点，每一个都有硬判据，不存在"再试一次说不定就过了"。

最终产物：

| 项 | 值 |
|---|---|
| boot.img | `boot_pwr.img` 58,161,152 B |
| boot header id@0x240 | `fa48d672f805d70e009e3aa63baf0898d34fbe2d`（`rk_boot_id.py check` = MATCH） |
| 板级 DTB | 172,541 B（槽容量 172,544，余量 3 B） |
| 冷启动到桌面 | 162.7 s（首次，含 dexopt）/ 74.0 s（之后） |
| 重启到桌面 | 74.0 s |
| hwcomposer 崩溃 | 0 次 |

---

## 2. 九个断点（按顺序打，别跳）

### 断点 1：BootROM 根本不看 TF 卡

**判据**：插卡上电，u-boot 无任何输出；eMMC 里的旧系统照旧启动。

**原因**：RK3568 BootROM 按 SPI → eMMC → SD 的顺序找 idbloader。eMMC 的 LBA64 处有厂商
`RKNS`（vendor storage + miniloader），BootROM 认它，就不会再往下找 SD。

**修法**：把 eMMC 的 LBA64 清零（只抹 1 个扇区，不动分区表）：

```bash
xxd -l 16 -s 32768 /dev/sdX          # 确认是 "RKNS"
dd if=/dev/zero of=/dev/sdX bs=512 seek=64 count=1
sync
```

> 这一步之后 eMMC 里的系统就起不来了。T68M 上 eMMC 原本是 iNextOS，确认可以牺牲再动。

---

### 断点 2：`No bootable slots found`

**判据**：u-boot 直接打这一行，不进内核。此时 `misc` 分区全零。

**原因**：AVB 的 A/B 元数据在 `misc` 的前 8 KB，全零时 bootloader 认为没有任何可启动槽。

**修法**：写回厂商 BCB（两处，偏移 0 和 `0x4000`）：

```
offset 0x0000: "boot-recovery\0"
offset 0x4000: "recovery\n--wipe_all\0"
```

`tools/` 里的写卡脚本已内置这一步。

---

### 断点 3：`trusty_read_rollback_index failed`

**判据**：OP-TEE 阶段报这个，紧跟一行 `devnum` 打印。

**原因**：u-boot 的环境变量 `devnum` 还是 0（默认 eMMC），而 eMMC 上没有 `security` 分区。
OP-TEE 去 eMMC 读 rollback index 必然失败。

**修法**：u-boot 命令行 `setenv devnum 1` + `saveenv`（1 = TF 卡）。
或者在 u-boot 里 `mmc dev 1` 之后再 boot。

---

### 断点 4：7.6 秒 `panic_on_set_idle`

**判据**：内核栈顶是

```
rk_iommu_driver_init → platform_probe → dev_pm_domain_attach → genpd_power_on
  → rockchip_pd_power_on → rockchip_pmu_set_idle_request → panic("panic_on_set_idle set")
```

`val=0x6`（fnOS 线是 `0x1ee`，同一根因不同栈）。

**原因**：NPU 电源域拿不到 idle ack。**关键在于先 probe 的是 `iommu@fde4b000`，不是 `npu@fde40000`**——
只关 npu 节点完全没用。

**修法**：两个节点都 `status = "fail"`。

```dts
&rknpu     { status = "fail"; };
&rknpu_mmu { status = "fail"; };
```

`"fail\0"` 与 `"okay\0"` 同为 5 字节，可以原地覆盖，不需要重排 FDT 结构块。
写 `"disabled"` 会长 5 字节，必须重建 struct block——不值得。

> `panic_on_set_idle=0` 加 cmdline **无效**，内核没这个参数，只会出现在 `Unknown kernel command line`。

---

### 断点 5：SD 控制器 probe 静默失败

**判据**：`/sys/bus/platform/drivers/dwmmc_rockchip/` 下没有 `fe2b0000.mmc`，
但它的 `waiting_for_supplier` 是 0、也不在 `devices_deferred` 里。串口报：

```
rockchip-pinctrl: unable to find group for node sdmmc0-cd-gpio
vccio_sd / vcc3v3_sd: disabling
```

**原因**：`sdmmc0-cd-gpio` 这个 pinctrl 组被放在了 `/pinctrl` 的**顶层**。
rockchip pinctrl 把顶层节点当"功能(function)"解析，只有功能节点**下面**的子节点才是"引脚组(group)"。
名字对不上 → 组找不到 → 控制器拿不到 pinctrl → probe 失败，而且**静默**（没有 defer 日志）。

**修法**：把节点整段搬到 `/pinctrl/sdmmc0/` 下面：

```dts
&pinctrl {
    sdmmc0 {
        sdmmc0_cd_gpio: sdmmc0-cd-gpio {
            rockchip,pins = <0 RK_PA4 RK_FUNC_GPIO &pcfg_pull_up>;
        };
    };
};
```

已经在二进制 DTB 上时，用 `tools/fdt_move_node.py` 在结构块内整段搬移（长度不变，不必重算大小）：

```bash
python3 fdt_move_node.py in.dtb out.dtb \
    --node /pinctrl/sdmmc0-cd-gpio --to /pinctrl/sdmmc0
```

---

### 断点 6：`liblp invalid geometry magic`

**判据**：`super` 分区首扇区是 `3a ff 26 ed`（Android sparse 魔数），不是 liblp 的魔数。
正常 raw super 应该是：`geometry@4096` magic `0x616C4467`、`header@12288` magic `0x414C5030`。

**原因**：桌面/下载包里给的 `super.img` 是 **Android sparse 格式**，整卡原样拷进去当然挂不上。

**修法**：先展开成 raw 再写：

```bash
python3 tools/sparse2raw.py super.img super_raw.img     # 1.9 GiB → 3.125 GiB
```

---

### 断点 7：`DM_DEV_STATUS failed for system_b`

**判据**：u-boot 打印 `tries-remain: 0`，已经自动切到 `_b` 槽，而 `_b` 是空的。

**原因**：每次失败启动都会扣一次 tries（默认 7 次）。前面几个断点连续失败，把 tries 扣光了。
AVB 规则：`successful=0` 且 `tries=0` → 切到另一个槽。

**修法**：抹掉 `misc` 前 8 KB，让 AVB 元数据重建为 `_a, tries=7`。
写卡脚本在每次写 boot 前都会做这一步（同时也顺手解决了断点 2）。

---

### 断点 8：`hwcomposer-3` 每秒 SIGABRT

**判据**：klog 里

```
vop2_create_crtc *ERROR* No primary plane find for video_port0
rockchip-drm display-subsystem: bound fe040000.vop  ← 失败（-19）
```

`/dev/dri/card0` 不存在，`hwcomposer-3` 打 `Check failed: halImpl != nullptr` 后 abort。
表面现象是"卡在开机 logo"，实际是显示子系统整条链没起来。

**原因**：vop2 的 port 节点缺 `rockchip,plane-mask` 和 `rockchip,primary-plane`，
驱动找不到 primary plane 就不注册 crtc。

**修法**：给 port 补 plane 绑定（值取自 BSP `rk3568-evb`）：

```dts
&vop {
    ports {
        port@0 { rockchip,plane-mask = <0x0f>; rockchip,primary-plane = <0x02>; };
        port@1 { rockchip,plane-mask = <0x30>; rockchip,primary-plane = <0x04>; };
        port@2 { status = "disabled"; };
    };
};
```

修好后 u-boot 会打：

```
vp0 assign plane mask: Cluster0|Cluster1|Esmart0|Esmart1[0xf], primary plane phy id: Esmart0[2]
vp1 assign plane mask: Smart0|Smart1[0x30], primary plane phy id: Smart0[4]
rockchip-drm display-subsystem: bound fe040000.vop
[drm] Initialized rockchip 4.0.0 ... on minor 0
vop2_crtc_atomic_enable: Update mode to 1368x768p60 (if:HDMI0)
```

---

### 断点 9：点「重启」变成「关机」——实际是进了 MaskROM

**这是最隐蔽的一个**，因为它只在"系统已经能进桌面"之后才暴露，而且现象和拔电一模一样。

**判据**（只看两处）：

1. 串口：内核正常打 `reboot: Restarting system with command 'userrequested'`，
   **之后 0 字节输出**（连 `DDR Version` 都没有）。
2. PC：设备管理器里出现 `USB\VID_2207&PID_350A`（RK3568 MaskROM），
   Problem code 28 只是没装 rockusb 驱动，不影响判断。

板子是**活的**，只是停在 USB 下载模式等烧写。这个模式不输出串口、不出画面。

**原因**：完整链条

```
内核 reboot
  → dw_mmc .shutdown → mmc_power_off()
  → regulator_disable(vmmc = PMIC 的 SWITCH_REG2 / vcc3v3_sd)
  → TF 卡彻底断电
  → SoC 复位，但 PMIC 不复位 → 这个开关保持关闭
  → BootROM 遍历：eMMC 无 idbloader、SD 无电 → 全部失败 → 落 MaskROM
```

冷启动之所以正常：PMIC 从零上电，所有 regulator 默认全开。

**修法**：把 TF 卡的供电和 IO 电都标记成常开。

```dts
vccio_sd: LDO_REG5    { regulator-always-on; };   /* vqmmc */
vcc3v3_sd: SWITCH_REG2 { regulator-always-on; };  /* vmmc  */
```

修好后重启时串口立刻出现：

```
DDR 03ea844c5d typ 24/09/03-10:42:57,fwver: v1.23
U-Boot SPL board init
U-Boot SPL 2017.09-g50821b3c8bd-241113 #fa
U-Boot 2017.09 (Dec 22 2025 - 18:12:29 +0800)
```

**别走的岔路**：`sd-uhs-sdr50`（UHS 1.8V signaling）不是根因。
删掉它 + 加 `no-1-8-v` 之后重启**照样进 MaskROM**。1.8V 只影响速度协商，跟"卡有没有电"无关。
判据很简单：**重启后串口连 DDR 都没有 = BootROM 没跑起来 = 先查供电，不要查速率**。

> `no-1-8-v` 这一项仍然保留在最终 DTB 里——它对热复位是正向的（卡永远 3.3V，少一次电压切换），
> 代价是从 SDR50 降到 high-speed 50 MHz。TF 卡本来就是瓶颈，这个代价可以接受。

---

## 3. 改 boot.img 的铁律

这几条是拿"白烧半小时 + 三次失败启动"换来的：

1. **只许原位覆盖，绝不移动任何字节。** 曾经把补丁 DTB 插到 `0x1bb200`，
   压掉了 rev02 起的 DTB 正文，而 RSCE 索引的 offset 一个都没改 →
   u-boot 报 `Failed to load DTB, ret=-9` → `Failed to load android image`，
   **而 boot header 的摘要当时是 MATCH 的**，极具误导性。
2. **16 个 `model="LYT T68M"` 槽全部写同一份。** u-boot 按 `rk3568-nanopi5-rev0f.dtb`
   这样的名字选，选哪个事先不确定，只修 rev0f 可能修了个没人用的槽。
3. **中间槽超容直接报错，只有最后一个槽允许扩 `second_size`。**
4. **改完必须重算 `id[20]@0x240`。** 算法是「每段 hash 完紧跟 4 字节 LE 段长」，顺序
   kernel → ramdisk → second。**不是**三段拼接后整体 hash（这是最容易错的地方）。

统一走 `tools/build_boot_img.py`，它会做容量断言 + 写后重解析，任一项不满足就拒绝出图：

```bash
python3 tools/build_boot_img.py boot_a.img dist/rk3568-lyt-t68m-android.dtb boot_out.img
python3 tools/rk_boot_id.py fix boot_out.img --inplace --yes
python3 tools/rk_boot_id.py check boot_out.img        # 必须 MATCH
```

### 槽容量会咬人

| 版本 | DTB 大小 | 剩余 |
|---|---|---|
| 厂商原厂 | 172,191 | 353 B |
| 补丁版（npu/iommu/vop/cd-gpio/no-1-8-v） | 172,517 | 27 B |
| 再加 2 个 `regulator-always-on` | 172,541 | **3 B** |
| 再加 2 个 `regulator-boot-on` | 172,565 | **超容 21 B，拒绝出图** |

每个空属性在结构块里固定占 12 字节（属性名若已存在于 strings 块就不额外增长）。
真要再改，先精简 second 段：47 个条目里 31 个是别的板子（rk3399×10、rk3528×1、
rk3566×3、rk3576×3、rk3588×12），白占 6.34 MB，T68M 自己只占 2.59 MB。

---

## 4. 验收判据

串口按顺序应该看到：

```
DDR 03ea844c5d ...                          ← DDR 训练通过
U-Boot SPL board init
Bootdev(atags): mmc 1                        ← 从 TF 卡启动
MMC1: Legacy, 52Mhz                          ← 注意：不是 UHS
SPL: A/B-slot: _a, successful: 1
DTB: rk3568-nanopi5-rev0f.dtb (172541)
ANDROID: sha1(...) + OK
mmc1: new high speed SDHC card
rockchip-drm display-subsystem: bound fe040000.vop
vop2_crtc_atomic_enable: Update mode to ... (if:HDMI0)
```

系统侧：

```bash
getprop sys.boot_completed        # 1
ls /dev/dri/card0                 # 存在
ps -A | grep hwcomposer           # 存活，且不重启
```

时间线（4 GB LPDDR4 + TF 卡）：

| 阶段 | 时刻 |
|---|---|
| u-boot 走完 | 7.0 s |
| init | 9.9 s |
| SurfaceFlinger / hwcomposer / bootanim → HDMI 出 logo | 15.3 s |
| zygote | 24.9 s |
| **首次** dexopt 完成 | ~150 s |
| `sys.boot_completed=1`（首次） | 162.7 s |
| `sys.boot_completed=1`（二次及以后） | 74.0 s |

首启那 125 秒不是卡住，是 PackageManager 全量扫描 + 预装应用 AOT 编译，结果缓存在
`/data/dalvik-cache`。TF 卡随机写比 eMMC 慢一个数量级，所以被放大。

---

## 5. 已知遗留（都不影响使用）

| 项 | 说明 |
|---|---|
| `A/B successful: 1, tries-remain: 0` | `successful=1` 优先，tries 不参与判断，安全；想干净就在写卡时清 misc |
| `E/TA read_data_from_uboot_ta TEE_InvokeTACommand 0xffff0006` ×30 | 某 vendor 服务循环向 TEE 要 u-boot 阶段的数据，OP-TEE 没存。噪音 |
| `system_server` 触发 2 次 `simple_bugreportd` | 首次启动 watchdog 抓到的卡顿，二次启动不再出现 |
| 显示分辨率 1368×768p60 | HDMI EDID 自动协商结果，换显示器会变 |
| SD 卡跑在 52 MHz legacy/high-speed | 有意为之，见断点 9 |

---

## 6. 回滚

任何一步都能只坏 TF 卡，不动 eMMC/板子：

```bash
# 回到厂商原始 boot
dd if=boot_a.img of=/dev/sdX bs=512 seek=0x10000 conv=notrunc
dd if=boot_a.img of=/dev/sdX bs=512 seek=0x30000 conv=notrunc
# 清 misc（让 AVB 重建）
dd if=/dev/zero of=/dev/sdX bs=512 seek=$((0x40000)) count=16 conv=notrunc
```

> boot_a 起始 LBA = `0x10000`，boot_b = `0x30000`，misc = `0x40000`。

---

## 7. 参考

- `docs/boot-verify-checklist.md` —— 写卡前后的校验清单
- `rk3568-lyt-t68m.dts` —— 目标板 dts（上面 9 个断点的修法全在里面）
- 技能库 `rk-android-board-porting/references/pitfall-ledger-android-t68m.md` —— 逐阶段坑位台账（A–H 组）
