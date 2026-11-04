#!/usr/bin/env python3
"""Rebuild boot.img's second stage keeping only the entries this board needs.

Why: the vendor boot.img ships one dtb per FriendlyElec rk3568 model (rk3399/rk3566/
rk3576/rk3588/rk3528 variants included) -- 45 blobs, 9.1 MB.  For a single board that
is dead weight, and it also means the per-slot capacity is only 172,544 B (512-aligned
gap between two rk3568 slots), which we ran out of: enabling the NPU power domain needs
+65 B (status okay x2, regulator-always-on, -boot-on, -init-microvolt on DCDC_REG4).

What it does: keeps exactly the entries that match --keep (default: the board's own
rk3568-nanopi5* slots plus the boot logos), injects the new dtb into every kept board
slot, and rebuilds the RSCE index from scratch so every offset is recomputed from the
real layout.  It never shifts a blob without updating its index entry -- that exact
mistake is what produced `Failed to load DTB, ret=-9` once (ledger E9).

Refuses to emit an image it cannot re-parse:
  * every kept board slot must start with d00dfeed and totalsize == index size
  * dtb model must still be "LYT T68M"
  * no two entries may overlap
  * boot header SHA1 (id[20] @0x240) is recomputed and re-checked

Usage
  python3 make_lite_boot.py boot.orig.img new.dtb out.img
  python3 make_lite_boot.py boot.orig.img new.dtb out.img --keep 'rk3568-nanopi5*,logo*'
"""

import argparse
import hashlib
import re
import struct
import sys

import rsce_tool as R

MAGIC = b"\xd0\x0d\xfe\xed"
DEFAULT_KEEP = "rk3568-nanopi5*,logo*,logo_kernel*"


def align(n, a=512):
    return (n + a - 1) // a * a


def fdt_model(dtb):
    """Pull the root 'model' string out of a flattened device tree."""
    if dtb[:4] != MAGIC:
        return None
    off_struct, off_str = struct.unpack(">II", dtb[8:16])
    sz_str, sz_st = struct.unpack(">II", dtb[32:40])
    strs = dtb[off_str:off_str + sz_str]
    p, end = off_struct, off_struct + sz_st
    depth = 0
    while p < end - 3:
        tok = struct.unpack(">I", dtb[p:p + 4])[0]
        p += 4
        if tok == 1:
            e = dtb.find(b"\x00", p)
            p = (e + 4) & ~3
            depth += 1
        elif tok == 2:
            depth -= 1
        elif tok == 3:
            ln, no = struct.unpack(">II", dtb[p:p + 8])
            name = strs[no:strs.find(b"\x00", no)] if no < len(strs) else b""
            p += 8
            val = dtb[p:p + ln]
            p = (p + ln + 3) & ~3
            if depth == 1 and name == b"model":
                return val.split(b"\x00")[0].decode("utf-8", "replace")
        elif tok == 9:
            break
    return None


def fix_header_id(boot):
    """Recompute id[20] with the exact rule u-boot uses (see tools/rk_boot_id.py).

    header_version >= 1 also hashes recovery_dtbo and (v2) dtb segments -- each one
    contributes its 4-byte LE size even when it is empty, so a hand-rolled 3-segment
    hash produces a MISMATCH and u-boot answers 'Failed to load android image'.
    """
    import rk_boot_id as K
    h = K.parse(boot)
    out = bytearray(boot)
    out[0x240:0x254] = K.digest(boot, h)
    return bytes(out), K.digest(bytes(out), K.parse(bytes(out))).hex()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("boot")
    ap.add_argument("dtb")
    ap.add_argument("out")
    ap.add_argument("--keep", default=DEFAULT_KEEP,
                    help="comma separated glob list of entry names to keep")
    ap.add_argument("--model", default="LYT T68M")
    ap.add_argument("--fill-revs", default="0-15",
                    help="补齐缺失的 rev 槽（默认 0-15，空字符串=不补）")
    a = ap.parse_args()

    boot = open(a.boot, "rb").read()
    dtb = open(a.dtb, "rb").read()
    info = R.boot_parse(boot)
    page, off, ssize = info["page_size"], info["second_off"], info["second_size"]
    second = boot[off:off + ssize]
    entries = R.parse_rcs(second)

    pats = [p.strip() for p in a.keep.split(",") if p.strip()]
    import fnmatch
    keep, drop = [], []
    for e in entries:
        (keep if any(fnmatch.fnmatchcase(e["name"], p) for p in pats) else drop).append(e)

    if not keep:
        raise SystemExit("keep patterns matched nothing; names: %s" %
                         ", ".join(e["name"] for e in entries[:10]))

    board = [e for e in keep if "rk3568-nanopi5" in e["name"]]
    if not board:
        raise SystemExit("no board slots kept -- refusing to build a card that cannot boot")
    for e in board:
        e["data"] = dtb

    # 补齐缺失的 rev 槽。SD 包里的 boot.img 只带 rev01..rev07（37 条目版），而这
    # 块板的 hwrev 是 0x0f —— u-boot 按**名字**选 dtb，找不到 rk3568-nanopi5-rev0f.dtb
    # 就是无 dtb 可用。PC 上那张卡的 boot.img 是 47 条目版，碰巧带 rev0f，所以这个
    # 缺口只会在 CI 产物上暴露。补满 0-15，全部写同一份 dtb。
    added = []
    if a.fill_revs:
        lo, hi = (int(x, 0) for x in a.fill_revs.split("-"))
        m = re.search(r"rev([0-9a-fA-F]{2})", board[0]["name"])
        if not m:
            raise SystemExit("cannot derive rev template from %r" % board[0]["name"])
        tpl = board[0]["name"][:m.start(1)] + "%02x" + board[0]["name"][m.end(1):]
        have = {e["name"] for e in keep}
        for rev in range(lo, hi + 1):
            nm = tpl % rev
            if nm in have:
                continue
            keep.append({"idx": len(keep), "name": nm, "raw": board[0]["raw"],
                         "offset": 0, "size": len(dtb), "data": dtb})
            added.append(nm)
        if added:
            print("  filled %d missing rev slot(s): %s" % (len(added), ", ".join(added)))

    print("second %d B, %d entries -> keep %d, drop %d" %
          (ssize, len(entries), len(keep), len(drop)))
    print("  kept:", ", ".join(e["name"] for e in keep))
    if drop:
        print("  dropped %d foreign blobs, %d B of dead weight" %
              (len(drop), sum(e["size"] for e in drop)))

    new_second = R.build_rcs(keep, second[:512])
    pad = (-len(new_second)) % page
    head = bytearray(boot[:off])
    struct.pack_into("<I", head, 0x18, len(new_second))
    out = bytes(head) + new_second + b"\x00" * pad
    print("second %d -> %d B; file %d -> %d B" % (ssize, len(new_second), len(boot), len(out)))

    # ---- verify before writing ----
    err = []
    chk = R.parse_rcs(out[R.boot_parse(out)["second_off"]:][:R.boot_parse(out)["second_size"]])
    spans = []
    for e in chk:
        spans.append((e["offset"], e["offset"] + e["size"], e["name"]))
        if "rk3568-nanopi5" in e["name"]:
            if e["data"][:4] != MAGIC:
                err.append("%s: no FDT magic" % e["name"])
                continue
            ts = struct.unpack(">I", e["data"][4:8])[0]
            if ts != e["size"]:
                err.append("%s: totalsize %d != index size %d" % (e["name"], ts, e["size"]))
            m = fdt_model(e["data"])
            if m != a.model:
                err.append("%s: model %r != %r" % (e["name"], m, a.model))
    spans.sort()
    for i in range(len(spans) - 1):
        if spans[i][1] > spans[i + 1][0]:
            err.append("overlap: %s and %s" % (spans[i][2], spans[i + 1][2]))
    if err:
        for e in err:
            print("  FAIL:", e)
        raise SystemExit("refusing to emit an image that does not re-parse")

    out, digest = fix_header_id(out)
    # independent re-check with the same rule the u-boot uses
    import rk_boot_id as K
    if K.digest(out, K.parse(out)) != out[0x240:0x254]:
        raise SystemExit("header SHA1 mismatch after write")

    open(a.out, "wb").write(out)
    print("OK %s  %d B  entries=%d  second=%d  id=%s" %
          (a.out, len(out), len(chk), len(new_second), digest[:16]))
    print("   slot capacity now %d B, dtb is %d B (headroom %d B)" %
          (max(e["size"] for e in chk if "rk3568" in e["name"]), len(dtb),
           max(e["size"] for e in chk if "rk3568" in e["name"]) - len(dtb)))


if __name__ == "__main__":
    sys.exit(main())
