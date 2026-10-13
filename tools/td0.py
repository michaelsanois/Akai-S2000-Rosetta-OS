"""Teledisk .td0 -> raw sector image (normal "TD" images; advanced "td" LZHUF not handled).

Usage: python td0.py in.td0 out.img
Output order: cyl, head, sector (1-based sector ids), sector size taken from the image.
"""
import sys


def unpack_sector(enc, buf, size):
    if enc == 0:
        out = bytes(buf)
    elif enc == 1:  # count(2) + 2-byte pattern
        out = bytearray()
        i = 0
        while i < len(buf):
            n = buf[i] | buf[i + 1] << 8
            out += buf[i + 2:i + 4] * n
            i += 4
        out = bytes(out)
    elif enc == 2:  # RLE blocks
        out = bytearray()
        i = 0
        while i < len(buf):
            t = buf[i]
            if t == 0:
                n = buf[i + 1]
                out += buf[i + 2:i + 2 + n]
                i += 2 + n
            else:
                plen = t * 2
                rep = buf[i + 1]
                out += buf[i + 2:i + 2 + plen] * rep
                i += 2 + plen
        out = bytes(out)
    else:
        raise ValueError(f"unknown sector encoding {enc}")
    if len(out) != size:
        raise ValueError(f"sector unpacked to {len(out)} bytes, expected {size}")
    return out


def read_td0(data):
    if data[:2] == b"td":
        raise SystemExit("advanced-compression TD0 not supported")
    assert data[:2] == b"TD", "not a TD0 file"
    info = {"version": data[4], "rate": data[5], "sides": data[9]}
    p = 12
    if data[7] & 0x80:
        clen = data[p + 2] | data[p + 3] << 8
        info["comment"] = data[p + 10:p + 10 + clen].replace(b"\0", b"\n").decode("latin-1").strip()
        p += 10 + clen
    sectors = {}
    while True:
        nsec = data[p]
        if nsec == 0xFF:
            break
        cyl, head = data[p + 1], data[p + 2] & 1
        p += 4
        for _ in range(nsec):
            c, h, sid, sz, flags = data[p:p + 5]
            p += 6
            size = 128 << sz
            if flags & 0x30 or sz > 6:
                continue  # no data recorded for this sector
            dlen = data[p] | data[p + 1] << 8
            enc = data[p + 2]
            sectors[(cyl, head, sid)] = unpack_sector(enc, data[p + 3:p + 2 + dlen], size)
            p += 2 + dlen
    return info, sectors


def main():
    data = open(sys.argv[1], "rb").read()
    info, sectors = read_td0(data)
    # geometry comes from track 0; sectors that don't fit it (odd extra tracks) are reported, not imaged
    sids = sorted(k[2] for k in sectors if k[:2] == (0, 0))
    size = len(sectors[(0, 0, sids[0])])
    extras = {k: v for k, v in sectors.items() if k[2] not in sids or len(v) != size}
    for k, v in sorted(extras.items()):
        print(f"extra sector c{k[0]} h{k[1]} id{k[2]} {len(v)} B: {v[:32].hex()}")
        del sectors[k]
    cyls = max(k[0] for k in sectors) + 1
    heads = max(k[1] for k in sectors) + 1
    out = bytearray()
    missing = 0
    for c in range(cyls):
        for h in range(heads):
            for s in sids:
                d = sectors.get((c, h, s))
                if d is None:
                    missing += 1
                    d = bytes(size)
                out += d
    open(sys.argv[2], "wb").write(out)
    print(info)
    print(f"{cyls} cyl x {heads} heads x {len(sids)} sectors ({sids[0]}..{sids[-1]}) x {size} B = {len(out)} B, missing {missing}")


if __name__ == "__main__":
    main()
