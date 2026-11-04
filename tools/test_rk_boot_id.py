#!/usr/bin/env python3
"""Self-test for rk_boot_id.py -- builds synthetic boot.img v1/v2 fixtures.

The point is NOT to re-implement the hash (that would be circular).  It is to prove the
plumbing around it: header offsets, page alignment of every segment, size-field order,
the "zero-size segment still hashes 4 bytes" rule, and that `fix` touches exactly 20
bytes and verifies itself by reading the file back.

Run: python3 tools/test_rk_boot_id.py
"""
import hashlib
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "rk_boot_id.py")


def build(path, header_version=2, page=2048, with_dtb=True, with_dtbo=False, bad_id=True):
    rnd = lambda n, seed: hashlib.sha1(seed).digest() * (n // 20 + 1)
    kernel = rnd(300_000, b"kernel")[:300_000]
    ramdisk = rnd(120_000, b"ramdisk")[:120_000]
    second = rnd(90_000, b"second")[:90_000]
    dtbo = rnd(50_000, b"dtbo")[:50_000] if with_dtbo else b""
    dtb = rnd(40_000, b"dtb")[:40_000] if (with_dtb and header_version >= 2) else b""

    hdr = bytearray(0x800)
    hdr[0:8] = b"ANDROID!"
    struct.pack_into("<I", hdr, 0x08, len(kernel))
    struct.pack_into("<I", hdr, 0x0C, 0x00200000)
    struct.pack_into("<I", hdr, 0x10, len(ramdisk))
    struct.pack_into("<I", hdr, 0x14, 0x01000000)
    struct.pack_into("<I", hdr, 0x18, len(second))
    struct.pack_into("<I", hdr, 0x1C, 0x00F00000)
    struct.pack_into("<I", hdr, 0x20, 0x00000100)
    struct.pack_into("<I", hdr, 0x24, page)
    struct.pack_into("<I", hdr, 0x28, header_version)
    hdr[0x30:0x30 + 9] = b"t68m-test"
    cmd = (b"console=ttyFIQ0 androidboot.hardware=rk30board "
           b"androidboot.selinux=permissive androidboot.dtb_idx=15")
    hdr[0x40:0x40 + len(cmd)] = cmd
    if header_version >= 1:
        struct.pack_into("<I", hdr, 0x660, len(dtbo))
        struct.pack_into("<Q", hdr, 0x664, 0)
        struct.pack_into("<I", hdr, 0x66C, 0x67C)
    if header_version >= 2:
        struct.pack_into("<I", hdr, 0x670, len(dtb))
        struct.pack_into("<Q", hdr, 0x674, 0)

    # deliberately wrong digest unless asked for a correct one
    good = hashlib.sha1()
    for seg in (kernel, ramdisk, second,
                *( ((dtbo,) if header_version >= 1 else ()) ),
                *( ((dtb,) if header_version >= 2 else ()) )):
        good.update(seg)
        good.update(struct.pack("<I", len(seg)))
    # id[8] is a 32-byte field in the AOSP struct; only the first 20 bytes are the SHA1.
    # Assign into a 32-byte-wide slice, never replace it with a 20-byte value -- doing the
    # latter shortens the bytearray and silently shifts every following field left by 12.
    hdr[0x240:0x254] = (b"\xde\xad\xbe\xef" * 5) if bad_id else good.digest()[:20]

    def pad(b):
        return b + b"\0" * (2048 - len(b) % 2048 if len(b) % 2048 else 0)

    blob = bytes(hdr[:page]) + pad(kernel) + pad(ramdisk) + pad(second) \
        + (pad(dtbo) if header_version >= 1 else b"") \
        + (pad(dtb) if header_version >= 2 else b"")
    open(path, "wb").write(blob)
    return good.hexdigest()[:40], len(blob)


def run(*args):
    p = subprocess.run([sys.executable, TOOL] + list(args), capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    tmp = tempfile.mkdtemp(prefix="bootid-")
    fails = 0

    def ok(cond, msg):
        nonlocal fails
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        if not cond:
            fails += 1

    # ---- case 1: v2, DTB present, wrong id
    src = os.path.join(tmp, "v2.img")
    expect, size = build(src, 2, with_dtb=True)
    print("case 1  v2 with dtb, %d bytes" % size)
    rc, out = run("check", src)
    ok(rc == 1, "check exits 1 on a wrong id")
    ok("MISMATCH" in out, "check reports MISMATCH")
    fixed = os.path.join(tmp, "v2.fixed.img")
    rc, out = run("fix", src, "-o", fixed)
    ok(rc == 0, "fix exits 0")
    ok("recomputed %s" % expect in out, "fix recomputes exactly the independently built digest")
    ok("20 byte(s) changed" in out, "exactly 20 bytes changed")
    ok(os.path.getsize(fixed) == size, "size unchanged")
    rc, out = run("check", fixed)
    ok(rc == 0 and "MATCH" in out, "check on fixed file says MATCH")
    rc, out = run("fix", fixed, "-o", fixed + ".again")
    ok("nothing to do" in out, "fix is idempotent (converges in one pass)")

    # ---- case 2: v1, no dtb segment
    src1 = os.path.join(tmp, "v1.img")
    expect1, _ = build(src1, 1, with_dtb=False)
    print("case 2  v1 without dtb")
    rc, out = run("fix", src1, "-o", src1 + ".f")
    ok(rc == 0 and "recomputed %s" % expect1 in out, "v1 digest matches (no dtb segment hashed)")
    ok(run("check", src1 + ".f")[0] == 0, "v1 fixed file verifies")

    # ---- case 3: zero-size recovery_dtbo still contributes 4 bytes
    src2 = os.path.join(tmp, "v2z.img")
    expect2, _ = build(src2, 2, with_dtb=True, with_dtbo=False)
    print("case 3  v2, recovery_dtbo_size=0 (must still hash 4 zero bytes)")
    rc, out = run("fix", src2, "-o", src2 + ".f")
    ok("recomputed %s" % expect2 in out, "digest matches the fixture built with the zero-size rule")

    # ---- case 4: truncated image must be refused, not silently hashed
    trunc = os.path.join(tmp, "trunc.img")
    data = open(src, "rb").read()
    open(trunc, "wb").write(data[:len(data) - 300_000])
    print("case 4  truncated image")
    rc, out = run("check", trunc)
    ok(rc != 0 and "exceeds file size" in out, "refuses a truncated image instead of hashing garbage")

    # ---- case 5: --inplace without --yes is refused
    print("case 5  in-place guard")
    rc, out = run("fix", src, "--inplace")
    ok(rc != 0 and "confirm" in out, "refuses --inplace without --yes")

    print("")
    print("result: %s" % ("ALL PASS" if fails == 0 else "%d FAILED" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
