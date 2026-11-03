#!/usr/bin/env bash
# Build a T68M (LYT RK3568) Android 14 SD image from the FriendlyElec rk3568
# android14 .img.gz: verify the gz, swap the RSCE dtb slots in boot_a, re-gzip.
#
# usage: tools/build_t68m_sd.sh <src.img.gz> <t68m.dtb> [out.img.gz]
set -euo pipefail
cd "$(dirname "$0")/.."

SRC=${1:?usage: build_t68m_sd.sh <src.img.gz> <t68m.dtb> [out.img.gz]}
DTB=${2:?missing t68m.dtb}
OUT=${3:-T68M-android14-$(date +%Y%m%d).img.gz}

[ -f "$SRC" ] || { echo "no such file: $SRC"; exit 1; }
[ -f "$DTB" ] || { echo "no such file: $DTB"; exit 1; }

# 1. gz must be complete -- a truncated download otherwise wastes the whole run
python3 - "$SRC" <<'EOF'
import gzip, sys
p = sys.argv[1]
n = 0
try:
    with gzip.open(p, "rb") as f:
        while True:
            b = f.read(16 << 20)
            if not b:
                break
            n += len(b)
except Exception as e:
    sys.exit(f"FAIL: gz incomplete after {n} bytes ({e}). Re-download the image.")
print(f"gz OK: {n} bytes decompressed")
if n < 3_000_000_000:
    sys.exit("FAIL: decompressed size suspiciously small for a 3.83 GiB SD image")
EOF

# 2. dtb sanity: model must be the T68M board
python3 - "$DTB" <<'EOF'
import sys
sys.path.insert(0, "tools")
from dtb_tool import parse
d = open(sys.argv[1], "rb").read()
_, nodes = parse(d)
model = nodes[0]["props"].get("model", b"").rstrip(b"\0").decode()
print(f"dtb: {len(d)} bytes model={model!r}")
if model != "LYT T68M":
    sys.exit("FAIL: dtb model is not 'LYT T68M'")
EOF

# 3. build
python3 tools/make_sd_img.py --src "$SRC" --dtb "$DTB" --out "$OUT" \
	--pattern 'rk3568-nanopi5-rev*' --fill-revs 0-15

echo
echo "done: $OUT"
ls -l "$OUT"
echo "flash:  zcat $OUT | sudo dd of=/dev/sdX bs=4M conv=fsync   (or balenaEtcher)"
