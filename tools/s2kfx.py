"""PC side of the Rosetta SysEx lab (S2000 Rosetta >= 0.09): poke the L7A1045 / memory live over MIDI.

  py -3.10 s2kfx.py ping
  py -3.10 s2kfx.py peek SEG:OFF N
  py -3.10 s2kfx.py poke SEG:OFF HEXBYTES
  py -3.10 s2kfx.py outw PORT VALUE          (hex)      py -3.10 s2kfx.py inw PORT
  py -3.10 s2kfx.py fx on|off                 toggle Rosetta's reverb flag + reload its preset table
  py -3.10 s2kfx.py send HEXWORD              reg7 word1 OR value while FX is on (default 800F)
  py -3.10 s2kfx.py load PRESET               PRESET = name in PRESETS below or a 192-byte .bin
  py -3.10 s2kfx.py sel N                     (0.10+) Rosetta FX preset N: 0 OFF 1 ROOM 2 HALL 3 PLATE 4 ECHO
                                              5 PINGPONG 6 CHORUS 7 FLANGER
  py -3.10 s2kfx.py note [N] [ms]             play a note (PLAY-always-plays: audition if no program)
  py -3.10 s2kfx.py rec SECONDS OUT.wav [DEV] [note N]   record the S2000 outs (optionally trigger a note)

Ports: S2000 lab on the OCTA-CAPTURE only (the Focusrite belongs to the GP-16 session).
Values in SysEx are 4-bit nibbles, high first. Replies: 44 PEEK data, 45 PING version, 47 INW.
"""
import struct
import sys
import time

import mido

MIDI_OUT = "MIDI (OCTA-CAPTURE) 1"
MIDI_IN = "MIDI (OCTA-CAPTURE) 0"
AUDIO_IN = 6                              # MME "1-2 (OCTA-CAPTURE)": S2000 main L/R (user patched 2026-10-13)
MENU_SEG = 0x3F00
FXON_OFF, FXSEND_OFF = 0x0012, 0x0013
SHADOW = (0x0000, 0x6D00)                 # DS:6D00 reg-A shadow (32 functions x 6 bytes)


def nib(v, n):
    return [(v >> (4 * (n - 1 - k))) & 0xF for k in range(n)]


class Lab:
    def __init__(self):
        self.out = mido.open_output(MIDI_OUT)
        try:
            self.inp = mido.open_input(MIDI_IN)
        except OSError:
            self.inp = None

    def sx(self, body):
        self.out.send(mido.Message("sysex", data=[0x7D, 0x53] + body))
        time.sleep(0.03)

    def reply(self, code, timeout=2.0):
        if not self.inp:
            raise SystemExit("no MIDI in: connect S2000 MIDI OUT -> OCTA MIDI IN for replies")
        end = time.time() + timeout
        while time.time() < end:
            for m in self.inp.iter_pending():
                if m.type == "sysex" and list(m.data[:3]) == [0x7D, 0x53, code]:
                    d = list(m.data[3:])
                    return bytes((d[i] << 4) | d[i + 1] for i in range(0, len(d) - 1, 2))
            time.sleep(0.01)
        raise SystemExit(f"no reply {code:#x} (is Rosetta >= 0.09 booted, MIDI cabled both ways?)")

    def ping(self):
        self.sx([0x05])
        return struct.unpack(">H", self.reply(0x45))[0]

    def peek(self, seg, off, n):
        data = b""
        while n:
            k = min(n, 96)
            self.sx([0x04] + nib(seg, 4) + nib(off, 4) + nib(k, 2))
            r = self.reply(0x44)
            data += r[4:4 + k]
            off += k
            n -= k
        return data

    def poke(self, seg, off, data):
        for i in range(0, len(data), 96):
            chunk = data[i:i + 96]
            body = [0x03] + nib(seg, 4) + nib(off + i, 4) + nib(len(chunk), 2)
            for b in chunk:
                body += nib(b, 2)
            self.sx(body)

    def outw(self, port, val):
        self.sx([0x01] + nib(port, 2) + nib(val, 4))

    def inw(self, port):
        self.sx([0x07] + nib(port, 2))
        r = self.reply(0x47)
        return struct.unpack(">H", r[1:3])[0]

    def fxprog(self):
        self.sx([0x06])

    def select(self, n):
        """0.10+: switch to Rosetta FX preset n (0 = OFF; same as stepping there with EFFECTS)."""
        self.sx([0x08] + nib(n, 2))

    def load_table(self, table):
        assert len(table) == 192
        self.poke(*SHADOW, table)
        self.fxprog()

    def write_tap(self, fn, gain, route, delay):
        """Exact tap write (what 2345:81B4/81E4 do, minus the int8 level step): Q15 gain with the
        route in bits 1-0 (feedback = 3), length word = 2 - delay (delay = samples incl. the +1)."""
        gw = (int(round(gain * 32767)) & 0xFFFC) | (3 if route == 2 else route)
        self.outw(0x80, 0x0A00 | fn)
        self.outw(0x82, gw & 0xFFFF)
        self.outw(0x80, 0x0A00 | fn)
        self.outw(0x84, (2 - delay) & 0xFFFF)

    def load_taps(self, taps):
        """taps: [(gain, route, delay)] up to 30, on fn1-10, 12-31; the rest are zeroed."""
        fns = [f for f in range(1, 32) if f != 11]
        for i, fn in enumerate(fns):
            g, r, d = taps[i] if i < len(taps) else (0.0, 0, 2)
            self.write_tap(fn, g, r, d)

    def note(self, n=60, ms=400, vel=100):
        self.out.send(mido.Message("note_on", note=n, velocity=vel))
        time.sleep(ms / 1000)
        self.out.send(mido.Message("note_off", note=n))


# ---- preset tables -----------------------------------------------------------------------
# One function = 6 bytes: int8 level (x 0x28F -> gain, +-50 ~ full scale), u8 routing
# (0 = left out, 1 = right out, 2 = feedback into the buffer; the OS loader turns 2 into 3),
# u16 length in samples (tap delay), u16 spare. fn0 is never written by the loader; stock
# presets always keep fn11 = (0, 0, 65535) -- copied as-is until we know what it does.
def table(taps):
    t = bytearray(192)
    struct.pack_into("<bBHH", t, 6 * 11, 0, 0, 65535, 0)
    for fn, (lvl, dd, ln) in taps.items():
        assert fn not in (0, 11) and 1 <= fn <= 31
        struct.pack_into("<bBHH", t, 6 * fn, lvl, dd, ln, 0)
    return bytes(t)


def stock_preset(n):
    """Stock presets out of the OS image (0 = off, 1 = unused reverb, 2 = tape backup)."""
    import os
    img = open(os.path.join(os.path.dirname(__file__), "..", "build", "os20_stock.bin"), "rb").read()
    base = 0x2D950 + 0x33A0 + n * 0xC0
    return img[base:base + 192]


SR = 44100


def ms(x):
    return int(SR * x / 1000)


PRESETS = {
    "off": lambda: stock_preset(0),
    "stock1": lambda: stock_preset(1),
    # echo: L+R taps at 375 ms, feedback 40% at the same length
    "echo": lambda: table({12: (30, 0, ms(375)), 13: (30, 1, ms(375)), 14: (20, 2, ms(375))}),
    # ping-pong: L at T, R at 2T, feedback from 2T
    "pingpong": lambda: table({12: (32, 0, ms(300)), 13: (32, 1, ms(600)), 14: (22, 2, ms(600))}),
}
for _fn in (1, 4, 8, 10, 12, 31):
    PRESETS[f"p{_fn}"] = (lambda fn: lambda: table({fn: (30, 1, ms(100))}))(_fn)
PRESETS["pdd0"] = lambda: table({12: (30, 0, ms(100))})
PRESETS["pneg"] = lambda: table({12: (-30, 1, ms(100)), 13: (30, 0, ms(150))})
PRESETS["p11"] = lambda: (lambda t: t[:66] + bytes.fromhex("00000040") + t[70:])(table({12: (30, 1, ms(100)), 14: (20, 2, ms(100))}))


def main():
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    lab = Lab()
    cmd = a[0]
    if cmd == "ping":
        print(f"Rosetta lab version {lab.ping():#06x}")
    elif cmd == "peek":
        seg, off = (int(x, 16) for x in a[1].split(":"))
        print(lab.peek(seg, off, int(a[2], 0)).hex(" "))
    elif cmd == "poke":
        seg, off = (int(x, 16) for x in a[1].split(":"))
        lab.poke(seg, off, bytes.fromhex(a[2]))
    elif cmd == "outw":
        lab.outw(int(a[1], 16), int(a[2], 16))
    elif cmd == "inw":
        print(f"{lab.inw(int(a[1], 16)):#06x}")
    elif cmd == "fx":
        on = a[1] == "on"
        lab.poke(MENU_SEG, FXON_OFF, bytes([1 if on else 0]))
        lab.load_table(PRESETS["stock1" if on else "off"]())
    elif cmd == "sel":
        lab.select(int(a[1]))
    elif cmd == "send":
        lab.poke(MENU_SEG, FXSEND_OFF, struct.pack("<H", int(a[1], 16)))
    elif cmd == "load":
        name = a[1]
        t = PRESETS[name]() if name in PRESETS else open(name, "rb").read()
        lab.poke(MENU_SEG, FXON_OFF, b"\x01")
        lab.load_table(t)
        print(f"loaded {name}")
    elif cmd == "note":
        lab.note(int(a[1]) if len(a) > 1 else 60, int(a[2]) if len(a) > 2 else 400)
    elif cmd == "rec":
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
        secs, path = float(a[1]), a[2]
        dev = a[3] if len(a) > 3 and a[3] != "note" else AUDIO_IN
        dev = int(dev) if str(dev).isdigit() else dev
        rec = sd.rec(int(secs * SR), samplerate=SR, channels=2, device=dev, dtype="float32")
        if "note" in a:
            time.sleep(0.2)
            lab.note(int(a[a.index("note") + 1]), 150)
        sd.wait()
        sf.write(path, rec, SR)
        print(f"recorded {path}: peak {np.abs(rec).max():.3f}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
