#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Android sparse image -> raw image (流式, 低内存)

用法: python sparse2raw.py <sparse.img> <out_raw.img>
"""
import os
import struct
import sys
import time

MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
CHUNK_FILL = 0xCAC2
CHUNK_DONT_CARE = 0xCAC3
CHUNK_CRC32 = 0xCAC4


def main(src, dst):
    t0 = time.time()
    fin = open(src, "rb")
    hdr = fin.read(28)
    magic, major, minor, fhsz, chsz, blksz, total_blks, total_chunks, csum = \
        struct.unpack("<IHHHHIIII", hdr)
    if magic != MAGIC:
        raise SystemExit("不是 sparse 镜像: magic=0x%08X" % magic)
    print("sparse v%d.%d  blk=%d  total_blks=%d (%d B)  chunks=%d"
          % (major, minor, blksz, total_blks, total_blks * blksz, total_chunks))
    fin.read(fhsz - 28)          # 跳过扩展头

    fout = open(dst, "wb")
    written = 0
    zero_chunk = b"\x00" * (1 << 20)
    for n in range(total_chunks):
        ch = fin.read(12)
        if len(ch) < 12:
            raise SystemExit("chunk %d 头被截断" % n)
        ctype, _, csz, tsz = struct.unpack("<HHII", ch)
        payload = csz * blksz
        if ctype == CHUNK_RAW:
            left = payload
            while left:
                d = fin.read(min(1 << 20, left))
                if not d:
                    raise SystemExit("chunk %d 数据截断" % n)
                fout.write(d)
                left -= len(d)
            written += payload
        elif ctype == CHUNK_FILL:
            fill = fin.read(4)
            buf = (fill * ((1 << 20) // 4 + 1))[: 1 << 20]
            left = payload
            while left:
                k = min(len(buf), left)
                fout.write(buf[:k])
                left -= k
            written += payload
        elif ctype == CHUNK_DONT_CARE:
            left = payload
            while left:
                k = min(len(zero_chunk), left)
                fout.write(zero_chunk[:k])
                left -= k
            written += payload
        elif ctype == CHUNK_CRC32:
            fin.read(tsz - 12)
        else:
            raise SystemExit("未知 chunk 类型 0x%04X @%d" % (ctype, n))
        if (n + 1) % 200 == 0:
            print("  %d/%d chunks  %.2f GiB  %.1fs"
                  % (n + 1, total_chunks, written / 1073741824, time.time() - t0))
    fout.close()
    fin.close()
    size = os.path.getsize(dst)
    print("完成: %s  %d B  (%.4f GiB)  用时 %.1fs"
          % (dst, size, size / 1073741824, time.time() - t0))
    if size != total_blks * blksz:
        print("!! 大小与头声明不符: 期望 %d" % (total_blks * blksz))
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
