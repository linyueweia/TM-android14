#!/usr/bin/env bash
# 把 HDMI-only 音频策略重新推到 /vendor/etc/ —— 刷机 / 恢复出厂后重跑这一条即可。
#
# 背景：本板只有 HDMI 一个物理音频输出（/proc/asound/cards 只有 card 0 rockchiphdmi0），
#       原厂 audio_policy 却把 Speaker 当默认输出，且 attachedDevices 里没有 HDMI Out，
#       结果 AudioFlinger 永远不往 HDMI 路由 —— 表现为「有画面没声音」。
#
# 这份策略是 adb remount 的 overlay 改动：
#   重启保留，但 **刷 vendor / 恢复出厂 / OTA 会丢**，所以必须能从仓库一键重放。
#
# 用法：tools/apply-audio-policy.sh [--reboot]
set -euo pipefail

ADB="${ADB:-adb}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/board-overlay/vendor/etc"
FILES=(audio_policy_configuration.xml audio_policy_configuration_singlehal.xml)
DO_REBOOT=0
[[ "${1:-}" == "--reboot" ]] && DO_REBOOT=1

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$SRC" ]] || die "找不到源目录 $SRC"

# adb 是 Windows 程序：远端 /vendor 路径不能被 MSYS 改写成 D:/...，
# 但本地源路径反过来必须是 Windows 形式 —— 所以关掉自动转换，本地手工 cygpath。
export MSYS_NO_PATHCONV=1
winpath() { cygpath -w "$1" 2>/dev/null || printf '%s' "$1"; }

"$ADB" get-state >/dev/null 2>&1 || die "设备未连接（adb devices 看一下）"

echo "==> 1/5 adb root"
"$ADB" root >/dev/null 2>&1 || true
sleep 2
"$ADB" wait-for-device

echo "==> 2/5 remount /vendor 为 overlay 可写"
# 已经 remount 过会返回非 0，不当失败
"$ADB" remount >/dev/null 2>&1 || true

echo "==> 3/5 推送策略文件"
for f in "${FILES[@]}"; do
  "$ADB" push "$(winpath "$SRC/$f")" "/vendor/etc/$f" || die "push $f 失败（remount 没生效？）"
  # 校验字节数一致
  local_n=$(stat -c%s "$SRC/$f")
  dev_n=$("$ADB" shell "wc -c < /vendor/etc/$f" | tr -d ' \r\n')
  [[ "$local_n" == "$dev_n" ]] || die "$f 字节数不符：本地 $local_n / 设备 $dev_n"
  echo "    $f  $dev_n B  OK"
done

echo "==> 4/5 重启 audioserver"
"$ADB" shell "stop audioserver; sleep 1; start audioserver" >/dev/null 2>&1 || true
sleep 3

echo "==> 5/5 自检"
CARD=$("$ADB" shell "cat /proc/asound/cards" | grep -c "rockchiphdmi0" || true)
DEF=$("$ADB" shell "grep -o '<defaultOutputDevice>[^<]*' /vendor/etc/audio_policy_configuration.xml" | sed 's/.*>//' | tr -d '\r')
HDMI_DEV=$("$ADB" shell "dumpsys audio" | grep -c 'hdmi(' || true)

echo "    声卡 rockchiphdmi0 : $CARD  (需 >=1)"
echo "    defaultOutputDevice: ${DEF:-<空>}  (需 = HDMI Out)"
echo "    route 里 hdmi( 条数 : $HDMI_DEV  (需 >=1)"

[[ "$CARD" -ge 1 ]] || die "声卡名不对 —— dtb 里的 simple-audio-card,name 没生效？"
[[ "$DEF" == "HDMI Out" ]] || die "默认输出不是 HDMI Out"
[[ "$HDMI_DEV" -ge 1 ]] || die "AudioFlinger 没把流路由到 HDMI"

echo
echo "OK: 策略已生效。放一首歌或视频，HDMI 应该出声。"
[[ $DO_REBOOT -eq 1 ]] && { echo "==> 重启"; "$ADB" reboot; }
exit 0
