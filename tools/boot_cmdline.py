#!/usr/bin/env python3
"""Read / rewrite the kernel cmdline of a Rockchip Android boot.img v1/v2.

WHY THIS EXISTS
  The board DTS for T68M is a Linux one: /chosen has stdout-path = "serial2:1500000n8"
  and uart2 (0xfe660000) is driven by the plain 8250 driver -- that is the exact console
  proven on this board (COM3 @ 1500000).  But the FriendlyElec Android boot.img ships
  `console=ttyFIQ0`, which only exists when a /fiq-debugger node binds uart2.  The T68M
  DTB has no such node, so after earlycon the kernel has nowhere to print: the board
  looks dead while it is actually booting, and every later diagnosis is guesswork.

  Keeping both consoles on the cmdline covers both worlds -- the kernel registers each
  console that actually found its driver and silently skips the ones that did not:

      console=ttyS2,1500000 console=ttyFIQ0 ...

  If a /fiq-debugger node is added later, ttyFIQ0 comes alive on its own; if not, ttyS2
  carries the log.  Nothing to re-flash in between.

WHY IT IS SAFE
  The cmdline lives at header offset 0x40, inside the header page, and the header page is
  NOT covered by u-boot's boot.img SHA1 (image_load does `ramdst += pgsz; datasz -= pgsz`
  for the kernel segment).  So rewriting the cmdline does not invalidate id[20] -- but run
  tools/rk_boot_id.py check afterwards anyway; it is one second and it proves it.

USAGE
  boot_cmdline.py show <boot.img>
  boot_cmdline.py set  <boot.img> -o out.img --console ttyS2,1500000   # idempotent
  boot_cmdline.py set  <boot.img> -o out.img --console ttyS2,1500000
  boot_cmdline.py set  <boot.img> -o out.img --add "console=ttyS2,1500000"
  boot_cmdline.py set  <boot.img> --inplace --yes --replace console=ttyFIQ0 console=ttyS2,1500000

  Field is BOOT_ARGS_SIZE = 512 bytes including the terminating NUL; a longer cmdline is
  refused rather than silently truncated (silent truncation would drop androidboot.* flags
  and change how init runs).
"""

import struct
import sys

CMDLINE_OFF = 0x40
CMDLINE_LEN = 512
MAGIC = b"ANDROID!"


def read_cmdline(img):
    if img[:8] != MAGIC:
        raise SystemExit("not a boot.img (magic %r)" % img[:8])
    raw = img[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN]
    return raw.split(b"\0")[0].decode("utf-8", "replace"), raw


def write_cmdline(img, text):
    if not text.isascii():
        raise SystemExit("cmdline must be ASCII")
    b = text.encode()
    if len(b) > CMDLINE_LEN - 1:
        raise SystemExit("cmdline is %d bytes, field holds %d incl. NUL"
                         % (len(b), CMDLINE_LEN))
    buf = bytearray(img)
    buf[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN] = b + b"\0" * (CMDLINE_LEN - len(b))
    return bytes(buf)


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, src = sys.argv[1], sys.argv[2]
    img = open(src, "rb").read()
    text, _ = read_cmdline(img)

    if cmd == "show":
        print("cmdline (%d/%d bytes):" % (len(text), CMDLINE_LEN - 1))
        print("  " + (text or "(empty)"))
        print("tokens:")
        for t in text.split():
            print("  - " + t)
        return 0

    out, inplace, yes = None, "--inplace" in sys.argv, "--yes" in sys.argv
    adds, repls, consoles = [], [], []
    for i, a in enumerate(sys.argv):
        if a == "-o":
            out = sys.argv[i + 1]
        elif a == "--add":
            adds.append(sys.argv[i + 1])
        elif a == "--console":
            consoles.append(sys.argv[i + 1])
        elif a == "--replace":
            # two separate argv entries: values contain '=' themselves, so splitting on
            # '=' (or ',' etc.) silently mis-parses "console=ttyFIQ0" into "console".
            repls.append((sys.argv[i + 1], sys.argv[i + 2]))
    if inplace and not yes:
        raise SystemExit("--inplace rewrites the input; pass --yes to confirm")
    if not out and not inplace:
        raise SystemExit("give -o OUT or --inplace --yes")

    tokens = text.split()
    for spec in consoles:
        # drop every console= token, then append exactly one.  Idempotent, and it does not
        # depend on which console the vendor happened to ship (ttyFIQ0 here, ttyS0/S2 there).
        kept = [t for t in tokens if not t.startswith("console=")]
        dropped = len(tokens) - len(kept)
        tokens = kept + ["console=" + spec]
        print("console  %s (dropped %d existing console= token(s))" % (spec, dropped))
    for old, new in repls:
        if old not in tokens:
            raise SystemExit("--replace: %r not in cmdline" % old)
        tokens[tokens.index(old)] = new
        print("replace  %s -> %s" % (old, new))
    for a in adds:
        if a in tokens:
            print("present  %s (no change)" % a)
        else:
            tokens.append(a)
            print("add      %s" % a)

    newtext = " ".join(tokens)
    blob = write_cmdline(img, newtext)
    assert len(blob) == len(img)

    dst = src if inplace else out
    open(dst, "wb").write(blob)
    back, _ = read_cmdline(open(dst, "rb").read())
    if back != newtext:
        raise SystemExit("READ-BACK FAILED:\n  wrote %r\n  read  %r" % (newtext, back))
    changed = sum(1 for a, b in zip(img, blob) if a != b)
    print("wrote %s: size %d unchanged, %d byte(s) changed" % (dst, len(blob), changed))
    print("cmdline now (%d/%d):" % (len(back), CMDLINE_LEN - 1))
    print("  " + back)
    return 0


if __name__ == "__main__":
    sys.exit(main())
