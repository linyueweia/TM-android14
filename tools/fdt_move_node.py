#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 FDT 中把某个节点整体搬到另一个节点下面（纯结构块搬移，长度不变）。

用法:
  fdt_move_node.py in.dtb -o out.dtb --node /pinctrl/sdmmc0-cd-gpio --under /pinctrl/sdmmc0

搬移只是字节重排，结构块长度、字符串块、头部偏移与文件总长全部保持不变，
因此可以直接原地替换 boot.img 里的 DTB 槽，不需要改 RSCE 表和槽大小。
"""
import argparse
import struct

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9


def hdr(d):
    f = struct.unpack_from('>10I', d, 0)
    return dict(magic=f[0], total=f[1], off_struct=f[2], off_strings=f[3],
                off_rsv=f[4], ver=f[5], lastcomp=f[6], cpuid=f[7],
                size_str=f[8], size_struct=f[9])


def parse_tree(d):
    """返回 [dict(path, name, begin, end, depth)]，begin/end 为结构块内字节区间。"""
    h = hdr(d)
    off, end_off = h['off_struct'], h['off_struct'] + h['size_struct']
    pos = off
    stack, nodes, opened = [], [], []
    while pos < end_off:
        tok = struct.unpack_from('>I', d, pos)[0]
        if tok == FDT_BEGIN_NODE:
            b = pos
            p = pos + 4
            e = d.index(b'\x00', p)
            name = d[p:e].decode('latin1')
            pos = (e + 4) & ~3
            stack.append(name)
            node = dict(path='/' + '/'.join([x for x in stack if x]),
                        name=name, begin=b, end=None, depth=len(stack))
            nodes.append(node)
            opened.append(node)
        elif tok == FDT_END_NODE:
            pos += 4
            if not opened:
                raise SystemExit('多余的 FDT_END_NODE @%d' % pos)
            n = opened.pop()
            if n['depth'] != len(stack):
                raise SystemExit('结构块不平衡 @%d' % pos)
            n['end'] = pos
            stack.pop()
        elif tok == FDT_PROP:
            ln, _ = struct.unpack_from('>II', d, pos + 4)
            pos += 12 + ((ln + 3) & ~3)
        elif tok == FDT_NOP:
            pos += 4
        elif tok == FDT_END:
            break
        else:
            raise SystemExit('未知 token %d @%d' % (tok, pos))
    return nodes


def find(nodes, path):
    for n in nodes:
        if n['path'] == path:
            return n
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dtb')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--node', required=True)
    ap.add_argument('--under', required=True)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    raw = open(a.dtb, 'rb').read()
    h = hdr(raw)
    if h['magic'] != FDT_MAGIC:
        raise SystemExit('不是 FDT 文件')
    if h['total'] != len(raw):
        print('[!] 头部 totalsize=%d 文件长度=%d' % (h['total'], len(raw)))

    nodes = parse_tree(raw)
    src = find(nodes, a.node)
    dst = find(nodes, a.under)
    if not src:
        raise SystemExit('找不到节点 %s' % a.node)
    if not dst:
        raise SystemExit('找不到父节点 %s' % a.under)
    if src['begin'] >= dst['begin'] and src['end'] <= dst['end']:
        raise SystemExit('源节点在目标节点内部，不支持')

    blk = raw[src['begin']:src['end']]
    if len(blk) % 4:
        raise SystemExit('节点块未对齐')

    insert_at = dst['end'] - 4          # 目标节点自己的 FDT_END_NODE
    body = bytearray(raw[:src['begin']] + raw[src['end']:])
    if insert_at > src['begin']:
        insert_at -= len(blk)
    body[insert_at:insert_at] = blk
    out = bytes(body)

    if len(out) != len(raw):
        raise SystemExit('长度变化 %d -> %d，中止' % (len(raw), len(out)))
    if hdr(out) != h:
        raise SystemExit('头部被改动，中止')

    n2 = parse_tree(out)
    if len(n2) != len(nodes):
        raise SystemExit('节点数变化 %d -> %d' % (len(nodes), len(n2)))
    newpath = a.under.rstrip('/') + '/' + src['name']
    if find(n2, newpath) is None:
        raise SystemExit('搬移后找不到新路径 %s' % newpath)
    left = find(n2, a.node)
    if left is not None:
        print('[!] 原路径 %s 仍存在（可能有同名节点）' % a.node)

    print('节点 %-32s %d 字节  depth %d -> %d' % (a.node, len(blk), src['depth'], dst['depth'] + 1))
    print('新路径 %s' % newpath)
    print('节点数 %d，长度 %d（未变）' % (len(n2), len(out)))
    if not a.dry_run:
        open(a.out, 'wb').write(out)
        print('已写入', a.out)


if __name__ == '__main__':
    main()
