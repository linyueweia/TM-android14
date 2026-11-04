#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""不拔卡、不走读卡器：通过 adb 把 boot.img 写进 TF 卡上的 A/B 槽。

为什么非得写 boot_a：RK 的 u-boot 不认 AOSP 的 BCB 切槽写法
（`bootctl set-active-boot-slot b` 返回 0 但 get 出来还是 0），
能启动的永远是 `_a`。所以默认写 `boot_a`，`boot_b` 只当回退备份。

干的事：
  1. adb root + 等设备
  2. push 镜像到 /data/local/tmp，设备端 sha256 与本地比对
  3. 把当前 boot_a 原样备份进 boot_b（= 上一版可用镜像，随时能回退）
  4. dd 新镜像进目标槽（bs=512 + 精确 count，bs=1M 会丢尾巴）
  5. 回读目标槽算 sha256，不一致就报错
  6. 可选立即 reboot

用法：
  python adb_flash_boot.py --img ../board/boot_lite.img            # 写 boot_a 并重启
  python adb_flash_boot.py --img x.img --no-reboot                 # 只写不重启
  python adb_flash_boot.py --img x.img --verify-only               # 只比对设备上现有内容
  python adb_flash_boot.py --img x.img --slot b                    # 只写 b（不推荐，起不来）
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys

REMOTE = "/data/local/tmp/boot_flash.img"
BY_NAME = "/dev/block/by-name"
SECTOR = 512


def find_adb():
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "..", "platform-tools", "adb.exe"),
                 os.path.join(here, "..", "..", "platform-tools", "adb.exe")):
        cand = os.path.abspath(cand)
        if os.path.isfile(cand):
            return cand
    got = shutil.which("adb")
    if got:
        return got
    sys.exit("!! 找不到 adb：把 platform-tools 放在 work/platform-tools/ 或加进 PATH")


class Adb:
    def __init__(self, exe):
        self.exe = exe

    def __call__(self, *args, sh=False, check=True):
        cmd = [self.exe] + (["shell"] if sh else []) + list(args)
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if check and p.returncode != 0:
            raise SystemExit("!! adb %s 失败:\n%s%s" % (" ".join(args), p.stdout, p.stderr))
        return p.stdout.strip()

    def sh(self, cmd, check=True):
        return self(cmd, sh=True, check=check)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def remote_sha(adb, dev, count):
    out = adb.sh("dd if=%s bs=%d count=%d 2>/dev/null | sha256sum" % (dev, SECTOR, count))
    return out.split()[0] if out else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True)
    ap.add_argument("--slot", default="a", choices=["a", "b"])
    ap.add_argument("--no-reboot", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--no-backup", action="store_true", help="不把 boot_a 备份进另一个槽")
    a = ap.parse_args()

    img = os.path.abspath(a.img)
    if not os.path.isfile(img):
        sys.exit("!! 镜像不存在: %s" % img)
    blob_len = os.path.getsize(img)
    count = (blob_len + SECTOR - 1) // SECTOR
    local_sha = sha256_file(img)
    if open(img, "rb").read(8) != b"ANDROID!":
        sys.exit("!! 不是 Android boot 镜像")

    adb = Adb(find_adb())
    adb("root", check=False)
    adb("wait-for-device")
    slot = adb.sh("getprop ro.boot.slot_suffix")
    print("设备      : %s (当前槽 %s)" % (adb("get-serialno"), slot))
    print("镜像      : %s  %d B  sha256 %s" % (img, blob_len, local_sha[:24]))
    print("目标槽    : boot_%s  (分区 %s, %d 扇区)" % (a.slot, BY_NAME, count))

    if a.verify_only:
        got = remote_sha(adb, "%s/boot_%s" % (BY_NAME, a.slot), count)
        print("设备回读  : %s  %s" % (got[:24], "PASS" if got == local_sha else "** 不一致 **"))
        return 0 if got == local_sha else 1

    adb("push", img, REMOTE)
    got = adb.sh("sha256sum %s" % REMOTE).split()[0]
    if got != local_sha:
        sys.exit("!! push 后 sha256 不一致: %s" % got[:24])
    print("push 校验 : PASS")

    if not a.no_backup:
        other = "b" if a.slot == "a" else "a"
        print("备份      : boot_a -> boot_%s（回退用）" % other)
        adb.sh("dd if=%s/boot_a of=/data/local/tmp/boot_bak.img bs=%d && sync" % (BY_NAME, SECTOR))

    print("写入      : boot_%s ..." % a.slot)
    adb.sh("dd if=%s of=%s/boot_%s bs=%d count=%d && sync" % (REMOTE, BY_NAME, a.slot, SECTOR, count))

    got = remote_sha(adb, "%s/boot_%s" % (BY_NAME, a.slot), count)
    ok = got == local_sha
    print("回读校验  : %s  %s" % (got[:24], "PASS" if ok else "** FAIL **"))
    adb.sh("rm -f %s /data/local/tmp/boot_bak.img" % REMOTE, check=False)
    if not ok:
        return 1

    if a.no_reboot:
        print("\n已写入，未重启。手动执行: adb reboot")
    else:
        print("\n重启中 ...")
        adb("reboot", check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
