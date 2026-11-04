T68M (LYT RK3568) Android 14 —— USB 线刷包

【先解压】update.img.zst -> update.img
  下载到的是 update.img.zst（zstd 压缩，约 3 倍，2.4 GB 原文件压到 ~700 MB~1 GB）。
  Linux/macOS : zstd -d update.img.zst          （没装就先 apt install zstd / brew install zstd）
  Windows     : 用 7-Zip 24.0+ 右键「解压」，或装 zstd 后 zstd -d update.img.zst
  校验        : sha256sum -c update.img.zst.sha256   （Windows: certutil -hashfile update.img.zst SHA256）
  解压出来的文件名必须还原成 update.img，RKDevTool 只认这个扩展名。

【方式一】RKDevTool 刷 update.img（推荐）
  1. 板子进 Maskrom：断电 → 按住 RECOVERY 键（或短接）→ 上电 → USB 接 OTG 口
  2. RKDevTool 底部显示 "发现一个 MASKROM 设备"
  3. 「升级固件」页 → 固件选 update.img → 升级
  4. 刷完断电重新上电

【方式二】RKDevTool 分区烧写（update.img 不可用 / 打包失败时用这个）
  「高级功能 → 分区烧写」，按下表逐个加载再点"执行"：
     bootloader      MiniLoaderAll.bin
     uboot           uboot.img
     misc            misc.img
     dtbo            dtbo.img
     vbmeta          vbmeta.img
     boot            boot.img
     super           super.img
     baseparameter   baseparameter.img
  地址以 parameter.txt 里的 CMDLINE 为准（RKDevTool 会自动填，别手改）

【方式三】rkdeveloptool 命令行（Linux / macOS）
  rkdeveloptool db MiniLoaderAll.bin          # 下载 loader
  rkdeveloptool ul MiniLoaderAll.bin          # 升级 loader
  rkdeveloptool wl <扇区地址> <分区.img>       # 地址查 parameter.txt 的 CMDLINE
  例：0x00004000 处是 uboot，转成 0x4000*512 字节偏移

要点
- boot.img 已注入 T68M 板级 DTB：16 个 rk3568-nanopi5-rev00..0f 槽全部指向本板设备树，
  hwrev 探测到哪个号都能命中。
- vbmeta 是 VERIFICATION_DISABLED（flags=0x2），改过的 boot.img 不会被 AVB 拦。
- 线刷会覆盖 eMMC 上的原有系统（这台板子的 eMMC 装的是 iNextOS 的 /boot），刷之前先留底：
  dd if=/dev/mmcblk0p1 of=/storage/Downloads/emmc-p1-boot.img bs=1M
- 起不来时看串口（1500000 8N1），u-boot 会打印 DTB: <name> (<size>) 和 androidboot.dtb_idx=，
  那是判断 hwrev / DDR 的唯一现场。
