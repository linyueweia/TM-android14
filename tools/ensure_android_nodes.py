#!/usr/bin/env python3
"""Make an RK3568 Android board dtb carry the SoC IP + Android nodes that the
vendor shipping board (rk3568-nanopi5-rev01) has but a router/NAS-derived dts
usually leaves out: NPU (+its bus + iommu), OP-TEE firmware node, linux,cma
and ramoops reserved-memory.

Pure Python (pyfdt), no dtc/gcc needed -- useful when the only thing available
is a compiled vendor dtb plus a CI box 40 minutes away.

usage:
  python ensure_android_nodes.py in.dtb out.dtb [--dry-run]
"""
import argparse
import io
import sys

from pyfdt.pyfdt import FdtBlobParse, FdtNode, FdtProperty, FdtPropertyStrings, FdtPropertyWords

sys.path.insert(0, __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0])
from dtb_tool import parse as fdt_parse  # noqa: E402

# values copied from the vendor Android board dtb (rk3568-nanopi5-rev01)
CMA_REG = [0x0, 0x10000000, 0x0, 0x800000]
RAMOOPS_REG = [0x0, 0x110000, 0x0, 0xF0000]


def items(node):
    return list(node)


def find_prop(node, name):
    for i, it in enumerate(node):
        if isinstance(it, FdtProperty) and it.name == name:
            return i, it
    return -1, None


def set_prop(node, name, prop, log):
    i, old = find_prop(node, name)
    if i >= 0:
        node[i] = prop
        log.append(f"    ~ {name} (replaced)")
    else:
        node.append(prop)
        log.append(f"    + {name}")


def set_status(node, value, log):
    set_prop(node, "status", FdtPropertyStrings("status", [value]), log)


def regulator_phandles(dtb_bytes):
    """regulator-name -> phandle, read with the plain-stdlib parser (pyfdt's
    walk() misses these: they sit under /i2c@.../pmic@20/regulators/)."""
    import struct
    _, nodes = fdt_parse(dtb_bytes)
    out = {}
    for n in nodes:
        pr = n["props"]
        nm = pr.get("regulator-name")
        ph = pr.get("phandle")
        if nm and ph:
            out[nm.rstrip(b"\x00").decode()] = struct.unpack(">I", ph)[0]
    return out


def ensure_node(parent, name, log):
    for it in parent:
        if isinstance(it, FdtNode) and it.name == name:
            log.append(f"  = /{name} exists")
            return it
    n = FdtNode(name)
    parent.append(n)
    log.append(f"  + /{name}")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    src_bytes = open(a.src, "rb").read()
    fdt = FdtBlobParse(io.BytesIO(src_bytes)).to_fdt()
    log = []

    regs = regulator_phandles(src_bytes)
    vdd_npu = regs.get("vdd_npu")
    vdd_logic = regs.get("vdd_logic")
    vdd_cpu = regs.get("vdd_cpu")
    log.append(f"regulator phandles: vdd_npu={vdd_npu} vdd_logic={vdd_logic} vdd_cpu={vdd_cpu}")

    # --- NPU ---
    npu = fdt.resolve_path("/npu@fde40000")
    if npu is not None:
        log.append("/npu@fde40000")
        set_status(npu, "okay", log)
        if vdd_npu:
            set_prop(npu, "rknpu-supply", FdtPropertyWords("rknpu-supply", [vdd_npu]), log)
    else:
        log.append("!! /npu@fde40000 absent -- SoC dtsi has no NPU node?")

    mmu = fdt.resolve_path("/iommu@fde4b000")
    if mmu is not None:
        log.append("/iommu@fde4b000")
        set_status(mmu, "okay", log)
    else:
        log.append("!! /iommu@fde4b000 absent")

    bus = fdt.resolve_path("/bus-npu")
    if bus is not None:
        log.append("/bus-npu")
        set_status(bus, "okay", log)
        if vdd_logic:
            set_prop(bus, "bus-supply", FdtPropertyWords("bus-supply", [vdd_logic]), log)
        if vdd_cpu:
            set_prop(bus, "pvtm-supply", FdtPropertyWords("pvtm-supply", [vdd_cpu]), log)
    else:
        log.append("!! /bus-npu absent")

    # --- reserved-memory: linux,cma + ramoops ---
    rm = fdt.resolve_path("/reserved-memory")
    if rm is None:
        log.append("!! /reserved-memory absent")
    else:
        log.append("/reserved-memory")
        cma = ensure_node(rm, "linux,cma", log)
        if cma.name == "linux,cma":
            set_prop(cma, "compatible", FdtPropertyStrings("compatible", ["shared-dma-pool"]), log)
            for empty in ("inactive", "reusable", "linux,cma-default"):
                if find_prop(cma, empty)[0] < 0:
                    cma.append(FdtProperty(empty))
                    log.append(f"    + {empty}")
            set_prop(cma, "reg", FdtPropertyWords("reg", CMA_REG), log)
        rp = ensure_node(rm, "ramoops@110000", log)
        if rp.name == "ramoops@110000":
            set_prop(rp, "compatible", FdtPropertyStrings("compatible", ["ramoops"]), log)
            set_prop(rp, "reg", FdtPropertyWords("reg", RAMOOPS_REG), log)
            set_prop(rp, "record-size", FdtPropertyWords("record-size", [0x20000]), log)
            set_prop(rp, "console-size", FdtPropertyWords("console-size", [0x80000]), log)
            set_prop(rp, "ftrace-size", FdtPropertyWords("ftrace-size", [0x0]), log)
            set_prop(rp, "pmsg-size", FdtPropertyWords("pmsg-size", [0x50000]), log)

    # --- firmware/optee ---
    fw = fdt.resolve_path("/firmware")
    if fw is None:
        log.append("!! /firmware absent")
    else:
        log.append("/firmware")
        op = ensure_node(fw, "optee", log)
        if op.name == "optee":
            set_prop(op, "compatible", FdtPropertyStrings("compatible", ["linaro,optee-tz"]), log)
            set_prop(op, "method", FdtPropertyStrings("method", ["smc"]), log)

    print("\n".join(log))
    if a.dry_run:
        print("\n(dry run, nothing written)")
        return
    blob = fdt.to_dtb()
    open(a.dst, "wb").write(blob)
    print(f"\nwrote {a.dst}: {len(blob)} bytes (src {len(open(a.src,'rb').read())})")


if __name__ == "__main__":
    sys.exit(main())
