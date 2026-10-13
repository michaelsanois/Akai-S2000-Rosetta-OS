"""Linear-sweep disassembly of the S2000 OS code segments -> port map, far-call graph, data xrefs.

  py -3.11 -I sweep.py OS.bin ports            I/O port usage (port, in/out, count, sample sites)
  py -3.11 -I sweep.py OS.bin xref ADDR        instructions touching DS:ADDR (hex, DS=0)
  py -3.11 -I sweep.py OS.bin funcs SEG        far-call entry points into SEG with caller counts
"""
import collections
import re
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_16, Cs

# (segment, start offset, end offset) of code, from far-call targets + segment bases
CODE = [(0x0FE4, 0x0000, 0xF6B2), (0x1F50, 0x0000, 0x3F50), (0x2345, 0x0000, 0x8900),
        (0x2BD5, 0x0000, 0x0D20), (0x2CA7, 0x0000, 0x0590), (0x2D00, 0x0000, 0x0950)]


def sweep(d):
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    md.skipdata = True
    for seg, lo, hi in CODE:
        base = seg << 4
        for ins in md.disasm(d[base + lo:base + hi], lo):
            yield seg, ins


def cmd_ports(d):
    use = collections.defaultdict(list)
    dx = None
    for seg, ins in sweep(d):
        m, ops = ins.mnemonic, ins.op_str
        mm = re.match(r"dx, (0x[0-9a-f]+|\d+)$", ops)
        if m == "mov" and mm:
            dx = int(mm.group(1), 0)
        if m in ("in", "out"):
            p = None
            mm = re.search(r"(0x[0-9a-f]+|\b\d+\b)", ops)
            if "dx" in ops:
                p = dx
            elif mm:
                p = int(mm.group(1), 0)
            if p is not None:
                use[(p, m)].append(f"{seg:04x}:{ins.address:04x}")
        if m in ("ret", "retf", "jmp", "call", "iret"):
            dx = None if m != "call" else dx
    for (p, m), sites in sorted(use.items()):
        print(f"{p:#06x} {m:3s} x{len(sites):<4d} {' '.join(sites[:6])}")


def cmd_xref(d, addr):
    a = int(addr, 16)
    pat = re.compile(rf"\[(0x{a:x})\]|\[[a-z]{{2}} \+ 0x{a:x}\]")
    for seg, ins in sweep(d):
        if pat.search(ins.op_str) or re.search(rf"\b0x{a:x}\b", ins.op_str) and ins.mnemonic in ("mov", "cmp", "test", "lea"):
            print(f"{seg:04x}:{ins.address:04x}  {ins.mnemonic} {ins.op_str}")


def cmd_funcs(d, seg):
    s = int(seg, 16)
    c = collections.Counter()
    for i in range(len(d) - 5):
        if d[i] == 0x9A:
            off, sg = struct.unpack_from("<HH", d, i + 1)
            if sg == s:
                c[off] += 1
    for off, n in sorted(c.items()):
        print(f"{s:04x}:{off:04x}  x{n}")


if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    cmd, *args = sys.argv[2:]
    {"ports": cmd_ports, "xref": cmd_xref, "funcs": cmd_funcs}[cmd](data, *args)
