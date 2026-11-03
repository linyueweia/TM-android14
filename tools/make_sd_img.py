#!/usr/bin/env python3
"""Build a T68M-flavoured SD image from the FriendlyElec rk3568 android14 gz.

Steps: stream-decompress the source .img.gz, replace the boot_a partition's
RSCE dtb slots with the given DTB (optionally filling all rev00..rev0f slots),
and re-gzip. Streaming, so it needs only ~4.5 GB peak free space.

Usage:
  python make_sd_img.py --dtb t68m.dtb --out T68M-android14.img.gz \
      --pattern 'rk3568-nanopi5-rev*' --fill-revs 0-15
"""
import argparse
import gzip
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rsce_tool import boot_replace  # noqa: E402

BOOT_A_LBA = 65536
BOOT_A_LEN = 64 * 1024 * 1024
CHUNK = 8 * 1024 * 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.expanduser(
        "~/Downloads/rk3568-sd-android14-20251222.img.gz"))
    ap.add_argument("--dtb", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pattern", default="rk3568-nanopi5-rev*")
    ap.add_argument("--fill-revs", default="")
    ap.add_argument("--raw", default="", help="keep the uncompressed image at this path")
    a = ap.parse_args()

    fr = None
    if a.fill_revs:
        lo, hi = a.fill_revs.split("-")
        fr = (int(lo, 0), int(hi, 0))
    dtb = open(a.dtb, "rb").read()
    assert dtb[:4] == b"\xd0\x0d\xfe\xed", "not a DTB"

    off = BOOT_A_LBA * 512
    raw_path = a.raw or (a.out + ".raw")
    with gzip.open(a.src, "rb") as f, open(raw_path, "wb") as o:
        shutil.copyfileobj(f, o, CHUNK) if False else None
        o.write(f.read(off))
        old = f.read(BOOT_A_LEN)
        assert old[:8] == b"ANDROID!", old[:8]
        new = boot_replace(old, a.pattern, dtb, fr)
        assert len(new) <= BOOT_A_LEN, f"boot img {len(new)} > partition {BOOT_A_LEN}"
        o.write(new)
        o.write(b"\0" * (BOOT_A_LEN - len(new)))
        while True:
            buf = f.read(CHUNK)
            if not buf:
                break
            o.write(buf)
    print("raw image:", raw_path, os.path.getsize(raw_path), "bytes")

    with open(raw_path, "rb") as i, gzip.open(a.out, "wb", compresslevel=6) as g:
        shutil.copyfileobj(i, g, CHUNK)
    print("gz image:", a.out, os.path.getsize(a.out), "bytes")
    if not a.raw:
        os.remove(raw_path)
        print("removed intermediate raw image")


if __name__ == "__main__":
    main()
