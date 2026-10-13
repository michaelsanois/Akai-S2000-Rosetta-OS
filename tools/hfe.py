"""HFE v1 (HxC / FlashFloppy) <-> raw sector image, IBM MFM.

  python hfe.py info  disk.hfe              track 0 layout + sector map
  python hfe.py read  disk.hfe out.img      decode all sectors (CRC-checked)
  python hfe.py write template.hfe in.img out.hfe
      re-uses the template's bitstream (gaps, IDs, index) and only replaces
      the data fields, so the result has exactly the layout of a disk the
      drive/emulator already accepts.

Raw image order: cyl, head, sector id 1..N, sector size from the ID field.
"""
import struct
import sys

SYNC = "0100010010001001"  # A1 with missing clock (0x4489)
REV = [int(f"{i:08b}"[::-1], 2) for i in range(256)]
BITS = [f"{REV[i]:08b}" for i in range(256)]  # HFE stores bits LSB-first


def crc16(data, crc=0xFFFF):
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
        crc &= 0xFFFF
    return crc


class HFE:
    def __init__(self, raw):
        self.raw = bytearray(raw)
        assert raw[:8] == b"HXCPICFE", "not HFE v1"
        self.ntracks, self.nsides, self.encoding = raw[9], raw[10], raw[11]
        self.bitrate, = struct.unpack_from("<H", raw, 12)
        lut, = struct.unpack_from("<H", raw, 18)
        self.tracks = [struct.unpack_from("<HH", raw, lut * 512 + 4 * t) for t in range(self.ntracks)]

    def _side_index(self, t, side):
        """Byte offsets in the file holding this side's bitstream, in order."""
        off, length = self.tracks[t]
        base = off * 512
        idx = []
        for blk in range(0, length, 512):
            start = base + blk + 256 * side
            n = min(256, (length - blk) // 2)
            idx.extend(range(start, start + n))
        return idx

    def cells(self, t, side):
        return "".join(BITS[self.raw[i]] for i in self._side_index(t, side))

    def put_cells(self, t, side, cells):
        idx = self._side_index(t, side)
        assert len(cells) == 8 * len(idx)
        for k, i in enumerate(idx):
            self.raw[i] = REV[int(cells[8 * k:8 * k + 8], 2)]


def dec_bytes(cells, pos, n):
    """Decode n MFM bytes starting at cell pos (pos = clock bit of first byte)."""
    out = bytearray()
    for k in range(n):
        c = cells[pos + 16 * k:pos + 16 * k + 16]
        out.append(int(c[1::2], 2))
    return bytes(out)


def enc_bytes(data, prev_bit):
    cells = []
    for b in data:
        for i in range(7, -1, -1):
            bit = (b >> i) & 1
            clock = 1 if (bit == 0 and prev_bit == 0) else 0
            cells.append(f"{clock}{bit}")
            prev_bit = bit
    return "".join(cells), prev_bit


def scan_track(cells):
    """Return list of sectors: dict(c,h,r,n, data_pos, data, ok)."""
    secs = []
    p = 0
    last_id = None
    while True:
        p = cells.find(SYNC * 3, p)
        if p < 0:
            break
        mark_pos = p + 48
        mark = dec_bytes(cells, mark_pos, 1)[0]
        if mark == 0xFE:
            idf = dec_bytes(cells, mark_pos + 16, 6)
            ok = crc16(b"\xA1\xA1\xA1\xFE" + idf[:4]) == (idf[4] << 8 | idf[5])
            last_id = dict(c=idf[0], h=idf[1], r=idf[2], n=idf[3], id_ok=ok, id_pos=p)
        elif mark in (0xFB, 0xF8) and last_id is not None:
            size = 128 << last_id["n"]
            dpos = mark_pos + 16
            blob = dec_bytes(cells, dpos, size + 2)
            ok = crc16(bytes([0xA1, 0xA1, 0xA1, mark]) + blob[:size]) == (blob[size] << 8 | blob[size + 1])
            secs.append(dict(last_id, data_pos=dpos, data=blob[:size], ok=ok, mark=mark))
            last_id = None
        p = mark_pos + 16
    return secs


def cmd_info(path):
    h = HFE(open(path, "rb").read())
    print(f"tracks {h.ntracks} sides {h.nsides} enc {h.encoding} bitrate {h.bitrate} kbps")
    for t in (0, 1, h.ntracks - 1):
        for s in range(h.nsides):
            cells = h.cells(t, s)
            secs = scan_track(cells)
            print(f"t{t}s{s}: {len(cells)} cells, {len(secs)} sectors:",
                  " ".join(f"{x['r']}/{128 << x['n']}{'' if x['ok'] and x['id_ok'] else '!'}" for x in secs))
            if t == 0 and s == 0 and len(secs) > 1:
                first = secs[0]["id_pos"]
                gaps = [(secs[i + 1]["id_pos"] - secs[i]["data_pos"]) // 16 - (128 << secs[i]["n"]) - 2
                        for i in range(len(secs) - 1)]
                print(f"  first ID at byte {first // 16}, gap3+sync per sector (bytes): {gaps}")


def read_image(h):
    sectors = {}
    bad = 0
    for t in range(h.ntracks):
        for s in range(h.nsides):
            for x in scan_track(h.cells(t, s)):
                if not (x["ok"] and x["id_ok"]):
                    bad += 1
                sectors[(x["c"], x["h"], x["r"])] = x["data"]
    return sectors, bad


def cmd_read(path, out):
    h = HFE(open(path, "rb").read())
    sectors, bad = read_image(h)
    rs = sorted({k[2] for k in sectors})
    size = len(next(iter(sectors.values())))
    img = bytearray()
    missing = 0
    for c in range(h.ntracks):
        for hd in range(h.nsides):
            for r in rs:
                d = sectors.get((c, hd, r))
                if d is None:
                    missing += 1
                    d = bytes(size)
                img += d
    open(out, "wb").write(img)
    print(f"{len(img)} bytes, ids {rs[0]}..{rs[-1]} x {size}, bad crc {bad}, missing {missing}")


def cmd_write(template, img_path, out):
    h = HFE(open(template, "rb").read())
    img = open(img_path, "rb").read()
    written = 0
    for t in range(h.ntracks):
        for s in range(h.nsides):
            cells = h.cells(t, s)
            secs = scan_track(cells)
            nsec = len(secs)
            for x in secs:
                size = 128 << x["n"]
                lba = (x["c"] * h.nsides + x["h"]) * nsec + x["r"] - 1
                data = img[lba * size:(lba + 1) * size]
                assert len(data) == size, f"image too short at c{x['c']} h{x['h']} r{x['r']}"
                crc = crc16(bytes([0xA1, 0xA1, 0xA1, x["mark"]]) + data)
                blob = data + bytes([crc >> 8, crc & 0xFF])
                prev = x["mark"] & 1
                enc, last = enc_bytes(blob, prev)
                p = x["data_pos"]
                end = p + len(enc)
                # fix the clock bit of the cell pair right after the CRC
                nxt_bit = int(cells[end + 1])
                nxt_clock = "1" if (nxt_bit == 0 and last == 0) else "0"
                cells = cells[:p] + enc + nxt_clock + cells[end + 1:]
                written += 1
            h.put_cells(t, s, cells)
    open(out, "wb").write(h.raw)
    # verify by reading back
    chk, bad = read_image(HFE(h.raw))
    print(f"wrote {written} sectors -> {out}; read-back bad crc {bad}")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    {"info": cmd_info, "read": cmd_read, "write": cmd_write}[cmd](*args)
