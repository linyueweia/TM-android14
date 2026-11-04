# board-overlay/ —— 刷机后需要手工补回的运行时改动

仓库里其他地方（`dist/*.dtb`、`rk3568-lyt-t68m.dts`）都随固件走，刷完就在。
**这个目录不是**：里面是 `adb remount` 的 overlay 改动，重启保留，但刷 vendor / 恢复出厂 / OTA 就没了。

## 为什么会有这个目录

本板只有 HDMI 一个音频输出（`/proc/asound/cards` 就 card 0，没有板载 codec），
但原厂 `audio_policy` 把 `Speaker` 当默认输出、`attachedDevices` 里也没有 `HDMI Out`，
AudioFlinger 因此永不往 HDMI 路由。表现是**有画面没声音，日志零报错**。

配合 `rk3568-lyt-t68m.dts` 里 `&hdmi_sound` 的两项（`mclk-fs = <128>`、`name = "rockchip,hdmi0"`，
这两项在 boot.img 里，持久），三处齐了才有声音。

## 怎么补回去

```
adb root
adb remount
adb push audio_policy_configuration.xml            /vendor/etc/
adb push audio_policy_configuration_singlehal.xml  /vendor/etc/
adb shell "stop audioserver; start audioserver"
```

在 Git Bash / MSYS 下要先 `export MSYS_NO_PATHCONV=1`，否则 `/vendor/etc/...`
会被改写成 `D:/...`，报 `cannot stat remote object`。

## 怎么确认补对了

```
adb shell cat /proc/asound/card0/id
# 须为 rockchiphdmi0 —— 不是的话是 dtb 没生效，不是策略问题

adb shell "grep -o '<defaultOutputDevice>[^<]*' /vendor/etc/audio_policy_configuration.xml"
# 须为 <defaultOutputDevice>HDMI Out

adb shell "dumpsys audio" | grep -c 'hdmi('
# 播放时须 > 0；hdmi(400) = AUDIO_DEVICE_OUT_AUX_DIGITAL
```

三条都过才叫通。别用 `tinyplay` 判断——它绕开 AudioFlinger 直接打 PCM，响了不代表系统音能出来。

## 恢复出厂后没声音，就是这个原因

不是硬件坏了，也不是 dtb 丢了（`cat /sys/firmware/devicetree/base/hdmi-sound/simple-audio-card,name`
应该还是 `rockchip,hdmi0`）。照着上面推一遍即可。
