"""16-bit x86 (NEC V53) helpers for the S2000 OS image, loaded at linear 0.

  py -3.11 -I x86dis.py OS.bin d SEG:OFF [n]     disassemble n instructions (default 40)
  py -3.11 -I x86dis.py OS.bin far                histogram of far call/jmp target segments
  py -3.11 -I x86dis.py OS.bin imm VALUE [seg]    instructions with a 16-bit immediate/disp == VALUE
  py -3.11 -I x86dis.py OS.bin calls SEG:OFF      near calls (E8) and far calls (9A) into SEG:OFF
  py -3.11 -I x86dis.py OS.bin ports              in/out with immediate port numbers + histogram
"""
import collections
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_16, Cs

D = b""
MD = Cs(CS_ARCH_X86, CS_MODE_16)
MD.detail = False


def lin(seg, off):
    return (seg << 4) + off


def parse_so(s):
    seg, off = s.split(":")
    return int(seg, 16), int(off, 16)


def disasm(seg, off, n=40, stop_on_ret=False):
    base = lin(seg, off)
    out = []
    for ins in MD.disasm(D[base:base + n * 8], off):
        out.append(ins)
        if len(out) >= n or (stop_on_ret and ins.mnemonic in ("ret", "retf", "iret")):
            break
    return out


def fmt(seg, ins):
    return f"{seg:04x}:{ins.address:04x} [{lin(seg, ins.address):05x}]  {ins.bytes.hex():16s} {ins.mnemonic} {ins.op_str}"


def cmd_d(so, n="40"):
    seg, off = parse_so(so)
    for ins in disasm(seg, off, int(n)):
        print(fmt(seg, ins))


def far_targets():
    """Byte-pattern scan for 9A/EA far call/jmp; keep targets that land inside the image."""
    hits = []
    for op in (b"\x9a", b"\xea"):
        i = D.find(op)
        while i >= 0:
            if i + 5 <= len(D):
                off, seg = struct.unpack_from("<HH", D, i + 1)
                t = lin(seg, off)
                if t < len(D) and seg:
                    hits.append((i, op[0], seg, off))
            i = D.find(op, i + 1)
    return hits


def cmd_far():
    hits = far_targets()
    c = collections.Counter(h[2] for h in hits if h[1] == 0x9A)
    print("far call target segments (count >= 5):")
    for seg, n in c.most_common():
        if n >= 5:
            print(f"  {seg:04x} (linear {seg << 4:05x}): {n}")


def cmd_imm(value, seg=None):
    v = int(value, 16).to_bytes(2, "little")
    i = D.find(v)
    while i >= 0:
        # try decoding an instruction that ends with or contains these bytes, starting 1..4 bytes earlier
        for back in range(1, 5):
            st = i - back
            if st < 0:
                continue
            ins = next(MD.disasm(D[st:st + 8], st), None)
            if ins and ins.size > back and st + ins.size >= i + 2 and f"0x{int(value, 16):x}" in ins.op_str:
                print(f"[{st:05x}]  {ins.bytes.hex():16s} {ins.mnemonic} {ins.op_str}")
                break
        i = D.find(v, i + 1)


def cmd_calls(so):
    seg, off = parse_so(so)
    tgt = lin(seg, off)
    for i, op, s, o in far_targets():
        if op == 0x9A and lin(s, o) == tgt:
            print(f"far call from [{i:05x}]")
    # near calls: E8 rel16 within the same 64K segment window
    i = D.find(b"\xe8")
    while i >= 0:
        rel, = struct.unpack_from("<h", D, i + 1)
        if (i + 3 + rel) & 0xFFFFF == tgt and abs((i + 3) - tgt) < 0x10000:
            print(f"near call from [{i:05x}]")
        i = D.find(b"\xe8", i + 1)


def cmd_ports():
    c = collections.Counter()
    for m in (0xE4, 0xE5, 0xE6, 0xE7):
        i = D.find(bytes([m]))
        while i >= 0:
            c[(("in" if m < 0xE6 else "out"), D[i + 1])] += 1
            i = D.find(bytes([m]), i + 1)
    print("immediate port ops (noisy byte scan):", sorted(c.items(), key=lambda x: -x[1])[:30])
    # mov dx, imm16 followed soon by in/out dx
    c2 = collections.Counter()
    i = D.find(b"\xba")
    while i >= 0:
        port, = struct.unpack_from("<H", D, i + 1)
        nxt = D[i + 3:i + 9]
        if any(b in (0xEC, 0xED, 0xEE, 0xEF) for b in nxt):
            c2[port] += 1
        i = D.find(b"\xba", i + 1)
    print("mov dx,PORT near in/out dx:")
    for p, n in c2.most_common(40):
        print(f"  {p:04x}: {n}")


if __name__ == "__main__":
    D = open(sys.argv[1], "rb").read()
    cmd, *args = sys.argv[2:]
    {"d": cmd_d, "far": cmd_far, "imm": cmd_imm, "calls": cmd_calls, "ports": cmd_ports}[cmd](*args)
