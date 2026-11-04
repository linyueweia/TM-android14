#!/usr/bin/env python3
"""Rehearse the exact CI order on a synthetic container -- no 1 GB download needed.

Chain under test (same commands the workflows run):
    rsce_tool.py boot-replace  ->  rk_boot_id.py check  ->  fix  ->  check

What this pins down:
  1. boot-replace really changes the hashed bytes and leaves id[20] stale -> check MUST
     report MISMATCH.  If it ever reports MATCH here, the fix step in CI is dead code and
     the image would fail on the board exactly as it did on 2026-11-03.
  2. after fix, check MUST report MATCH and only 20 bytes may differ.
  3. all 16 hwrev slots must carry the T68M DTB afterwards (hwrev is not predictable).

The container is synthetic (kernel/ramdisk are zero filler); the DTB, the RSCE layout,
the injection code path and the hash code path are the real ones.

Run: python3 tools/rehearse_boot_pipeline.py [--dtb dist/rk3568-lyt-t68m-android.dtb]
"""
import argparse
import hashlib
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def run(*args, check=True):
    p = subprocess.run([sys.executable] + list(args), capture_output=True, text=True, cwd=REPO)
    out = p.stdout + p.stderr
    if check and p.returncode != 0:
        print(out)
        raise SystemExit("FAILED: %s" % " ".join(map(str, args)))
    return p.returncode, out


def build_rcs(entries):
    """entries: [(name, blob)] -> RSCE v0 image (512B header + 512B/entry + 512-aligned data)."""
    n = len(entries)
    hdr = bytearray(512)
    hdr[0:4] = b"RSCE"
    struct.pack_into("<H", hdr, 6, 0x0101)
    struct.pack_into("<H", hdr, 8, 0x0001)
    struct.pack_into("<I", hdr, 12, n)
    data_start = 512 + 512 * n
    body = bytearray()
    ent = bytearray()
    for name, blob in entries:
        off = data_start + len(body)
        e = bytearray(512)
        e[0:4] = b"ENTR"
        nb = name.encode()
        e[4:4 + len(nb)] = nb
        struct.pack_into("<I", e, 260, off // 512)   # offset unit = 512B blocks
        struct.pack_into("<I", e, 264, len(blob))
        ent += e
        body += blob + b"\0" * ((512 - len(blob) % 512) % 512)
    return bytes(hdr + ent + body)


def build_boot(rcs, page=2048, kernel=1_500_000, ramdisk=600_000, bad_id=True):
    hdr = bytearray(0x800)
    hdr[0:8] = b"ANDROID!"
    struct.pack_into("<I", hdr, 0x08, kernel)
    struct.pack_into("<I", hdr, 0x0C, 0x00200000)
    struct.pack_into("<I", hdr, 0x10, ramdisk)
    struct.pack_into("<I", hdr, 0x14, 0x01000000)
    struct.pack_into("<I", hdr, 0x18, len(rcs))
    struct.pack_into("<I", hdr, 0x1C, 0x00F00000)
    struct.pack_into("<I", hdr, 0x20, 0x00000100)
    struct.pack_into("<I", hdr, 0x24, page)
    struct.pack_into("<I", hdr, 0x28, 2)
    hdr[0x30:0x40] = b"t68m-rehearsal\0\0"
    cmd = b"console=ttyFIQ0 androidboot.hardware=rk30board androidboot.dtb_idx=0"
    hdr[0x40:0x40 + len(cmd)] = cmd
    struct.pack_into("<I", hdr, 0x660, 0)      # recovery_dtbo_size
    struct.pack_into("<Q", hdr, 0x664, 0)
    struct.pack_into("<I", hdr, 0x66C, 0x67C)  # header_size
    struct.pack_into("<I", hdr, 0x670, 0)      # dtb_size
    struct.pack_into("<Q", hdr, 0x674, 0)
    hdr[0x240:0x254] = b"\x11\x22\x33\x44" * 5 if bad_id else b"\0" * 20

    def pad(b):
        return b + b"\0" * ((page - len(b) % page) % page)

    return bytes(hdr[:page]) + pad(b"\x5a" * kernel) + pad(b"\xa5" * ramdisk) + pad(rcs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dtb", default="dist/rk3568-lyt-t68m-android.dtb")
    a = ap.parse_args()
    dtb_path = os.path.join(REPO, a.dtb)
    dtb = open(dtb_path, "rb").read()
    model = b"LYT T68M" in dtb
    print("dtb      %s  %d bytes  contains 'LYT T68M'=%s" % (a.dtb, len(dtb), model))
    if not model:
        raise SystemExit("this dtb is not the T68M one -- refusing to rehearse")

    base = open(os.path.join(REPO, "dist/rk3568-nanopi5-rev01-base.dtb"), "rb").read()
    slots = [("rk3568-nanopi5-rev%02x.dtb" % r, base) for r in (1, 2, 3, 4, 5, 7)]
    slots.append(("logo.bmp", b"BM" + b"\0" * 510))
    rcs = build_rcs(slots)
    boot = build_boot(rcs)

    tmp = tempfile.mkdtemp(prefix="rehearse-")
    orig = os.path.join(tmp, "boot.orig.img")
    open(orig, "wb").write(boot)
    print("container %s  %d bytes, %d RSCE slots" % (os.path.basename(orig), len(boot), len(slots)))

    injected = os.path.join(tmp, "boot.img")
    rc, out = run("tools/rsce_tool.py", "boot-replace", orig,
                  "--pattern", "rk3568-nanopi5-rev*", "--dtb", dtb_path,
                  "--fill-revs", "0-15", "-o", injected)
    print("[1] boot-replace ok, size %d -> %d" % (len(boot), os.path.getsize(injected)))

    rc, out = run("tools/rk_boot_id.py", "check", injected, check=False)
    stale_ok = (rc == 1 and "MISMATCH" in out)
    print("[2] check after inject: %s (expect MISMATCH)" %
          ("MISMATCH as expected" if stale_ok else "UNEXPECTED rc=%d" % rc))

    fixed = os.path.join(tmp, "boot.fixed.img")
    rc, out = run("tools/rk_boot_id.py", "fix", injected, "-o", fixed)
    print("[3] fix: %s" % [l for l in out.splitlines() if "byte(s) changed" in l][0].strip())

    rc, out = run("tools/rk_boot_id.py", "check", fixed)
    match_ok = "MATCH" in out
    print("[4] check after fix: %s" % ("MATCH" if match_ok else "STILL MISMATCH"))

    # every hwrev slot must now carry the T68M dtb
    rc, out = run("tools/rsce_tool.py", "boot-list", fixed)
    hits = [l for l in out.splitlines() if "rev" in l]
    t68m = sum(1 for l in hits if "LYT T68M" in l or str(len(dtb)) in l)
    print("[5] boot-list: %d slot line(s), %d referencing the injected dtb (%d bytes)"
          % (len(hits), t68m, len(dtb)))
    if hits:
        print("    " + hits[0].strip())
        print("    " + hits[-1].strip())

    verdict = stale_ok and match_ok and len(hits) >= 16
    print("")
    print("rehearsal: %s" % ("PASS" if verdict else "FAIL"))
    print("  inject leaves the digest stale : %s" % stale_ok)
    print("  fix restores MATCH             : %s" % match_ok)
    print("  16 hwrev slots covered          : %s (%d)" % (len(hits) >= 16, len(hits)))
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
