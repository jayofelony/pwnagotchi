#!/usr/bin/env python3
"""Minimal nexutil replacement: talks to the nexmon brcmfmac driver over
netlink (NETLINK_USER=31), plus a raw-socket frame injector.

Wire format from patches/driver/brcmfmac_6.18.y-nexmon/core.c:

    struct nexudp_header      { char nex[3]; char type; int securitycookie; }
    struct nexudp_ioctl_header{ nexudp_header; uint cmd; uint set; char payload[1]; }

set != 0 -> brcmf_fil_cmd_data_set, replies "ACK"
set == 0 -> brcmf_fil_cmd_data_get, replies with the frame, payload filled in
reply is unicast to nlh->nlmsg_pid, so we bind to a known pid.
"""
import argparse
import os
import socket
import struct
import sys
import time

NETLINK_USER = 31
NLMSG_DONE = 3

# nexmon debug ioctls compiled into bcm43430a1/7_45_98
IOCTL_SANITY = 601      # writes 0xDEADBEEF
IOCTL_D11REGS = 604     # maccontrol, maccommand, macintstatus, macintmask
IOCTL_HEALTH = 612      # "NEX1" magic, heap, osh[0], free-buffer probe
IOCTL_INJGUARD = 620    # "NEX2" magic, inject sent/dropped (only after rebuild)

WLC_SET_MONITOR = 108

MAGIC_NEX1 = 0x4E455831
MAGIC_NEX2 = 0x4E455832


class Nex:
    def __init__(self, timeout=3.0):
        self.pid = os.getpid() & 0x3FFFFFFF
        self.sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_USER)
        self.sock.bind((self.pid, 0))
        self.sock.settimeout(timeout)
        self.seq = 0

    def _frame(self, cmd, set_, payload):
        # nex[3] type[1] securitycookie[4] cmd[4] set[4] payload[]
        return b"NEX" + b"\x00" + struct.pack("<I", 0) + \
               struct.pack("<II", cmd, set_) + payload

    def _send(self, body):
        self.seq += 1
        nlh = struct.pack("<IHHII", 16 + len(body), NLMSG_DONE, 0,
                          self.seq, self.pid)
        self.sock.send(nlh + body)

    def get(self, cmd, length):
        """Issue a get ioctl. Returns `length` payload bytes, or None on timeout."""
        self._send(self._frame(cmd, 0, b"\x00" * length))
        try:
            data = self.sock.recv(65536)
        except socket.timeout:
            return None
        # strip nlmsghdr(16) + nexudp_ioctl_header(16)
        return data[16 + 16:16 + 16 + length]

    def set(self, cmd, payload):
        self._send(self._frame(cmd, 1, payload))
        try:
            self.sock.recv(65536)
            return True
        except socket.timeout:
            return False

    def words(self, cmd, n):
        raw = self.get(cmd, n * 4)
        if raw is None or len(raw) < n * 4:
            return None
        return list(struct.unpack("<%dI" % n, raw[:n * 4]))


def sanity(nex):
    w = nex.words(IOCTL_SANITY, 1)
    if w is None:
        return "NO REPLY (chip not answering)"
    return "0x%08X %s" % (w[0], "OK" if w[0] == 0xDEADBEEF else "UNEXPECTED")


MAGIC_NEX3 = 0x4E455833


def d11(nex):
    """Read the d11 registers via ioctl 604.

    DANGEROUS on any build without the wlc->hw->up guard: 604 dereferences
    wlc->regs, which reaches the d11 core across the backplane. Against an idle
    radio that access hangs and bricks the chip until a power cycle (F1 reads
    0xffffffff, modprobe cannot recover). Never call this from a sampling loop
    on an unguarded firmware - it is indistinguishable from the wedge it is
    meant to measure. Guarded builds answer with the NEX3 magic word.
    """
    w = nex.words(IOCTL_D11REGS, 6)
    if w is None:
        return None
    if w[0] != MAGIC_NEX3:
        return {"unguarded": True}
    return {
        "hw_up": w[1],
        "maccontrol": w[2], "maccommand": w[3],
        "macintstatus": w[4], "macintmask": w[5],
        "rxov": bool(w[4] & 0x100),
    }


def health(nex):
    w = nex.words(IOCTL_HEALTH, 8)
    if w is None:
        return None
    if w[0] != MAGIC_NEX1:
        return {"invalid": True, "magic": w[0]}
    return {
        "heapfree": w[1], "blocks": w[2], "biggest": w[3],
        "osh0": w[4], "freebufs": w[5],
        "mallocfail": w[6], "lbfail": w[7],
    }


def injguard(nex):
    w = nex.words(IOCTL_INJGUARD, 4)
    if w is None or w[0] != MAGIC_NEX2:
        return None
    return {"sent": w[1], "dropped": w[2], "reserve": w[3]}


def sample(nex, label, want_guard=False, want_d11=False):
    h = health(nex)
    # 604 is opt-in: on a firmware without the hw->up guard it bricks the chip.
    d = d11(nex) if want_d11 else None
    # Only probe 620 when the firmware is expected to have it. On a build
    # without it the ioctl falls through to wlc_ioctl, which never answers,
    # costing a 2500ms DCMD timeout and leaving the *next* read invalid.
    g = injguard(nex) if want_guard else None
    if h is None and (d is None and want_d11):
        print("%-10s *** NO REPLY - chip wedged ***" % label)
        return False
    if h is None:
        print("%-10s *** health NO REPLY - chip wedged ***" % label)
        return False
    parts = [label]
    if h is None:
        parts.append("health=NOREPLY")
    elif h.get("invalid"):
        parts.append("health=INVALID(magic=%08x)" % h["magic"])
    else:
        parts.append("freebufs=%-3d osh0=%-3d heap=%-6d blocks=%-3d mfail=%d lbfail=%d"
                     % (h["freebufs"], h["osh0"], h["heapfree"], h["blocks"],
                        h["mallocfail"], h["lbfail"]))
    if d is None:
        if want_d11:
            parts.append("d11=NOREPLY")
    elif d.get("unguarded"):
        parts.append("d11=UNGUARDED-BUILD(refusing)")
    else:
        parts.append("hw_up=%d macintstatus=%08x RXOV=%d mask=%08x"
                     % (d["hw_up"], d["macintstatus"], d["rxov"], d["macintmask"]))
    if g is not None:
        parts.append("inj_sent=%d inj_dropped=%d" % (g["sent"], g["dropped"]))
    print("  ".join(parts))
    return True


# Bare radiotap: no fields present, so inject_frame() parses data_rate = 0 and
# passes a zero rate override to wlc_d11hdrs.
RADIOTAP = bytes([0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00])


def radiotap_rate(rate_500k=2):
    """Radiotap carrying only IEEE80211_RADIOTAP_RATE (bit 2), in 500kbps units.
    2 = 1Mbit/s, the most robust rate for management frames."""
    return bytes([0x00, 0x00, 0x09, 0x00, 0x04, 0x00, 0x00, 0x00, rate_500k & 0xff])


def deauth(sta, ap):
    return (b"\xc0\x00" + b"\x00\x00" + sta + ap + ap + b"\x00\x00" +
            b"\x07\x00")


def probereq(src):
    """Broadcast probe request with a wildcard SSID.

    Proof that injection reaches the air without needing a second radio: APs in
    range answer a probe request with a probe response addressed to the source
    MAC. If those come back for a MAC that exists nowhere but in this frame,
    the frame was genuinely transmitted.
    """
    bcast = b"\xff" * 6
    return (b"\x40\x00" + b"\x00\x00" + bcast + src + bcast + b"\x00\x00" +
            b"\x00\x00" +                      # SSID IE, wildcard (len 0)
            b"\x01\x04\x02\x04\x0b\x16")   # supported rates


def inject_probes(iface, count, src, rate=0):
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
    s.bind((iface, 0))
    frame = (radiotap_rate(rate) if rate else RADIOTAP) + probereq(src)
    sent = failed = 0
    for _ in range(count):
        try:
            s.send(frame); sent += 1
        except OSError:
            failed += 1
        time.sleep(0.05)
    s.close()
    return sent, failed


def burst(iface, count, sta, ap):
    """Inject `count` deauth frames as fast as possible, like bettercap does."""
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
    s.bind((iface, 0))
    frame = RADIOTAP + deauth(sta, ap)
    sent = failed = 0
    for _ in range(count):
        try:
            s.send(frame)
            sent += 1
        except OSError:
            failed += 1
    s.close()
    return sent, failed


def mac(s):
    return bytes(int(x, 16) for x in s.split(":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["sanity", "sample", "monitor", "burst", "soak", "leaktest", "probe"])
    ap.add_argument("--iface", default="wlan0mon")
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--mon", type=int, default=2)
    ap.add_argument("--sta", default="00:11:22:33:44:55")
    ap.add_argument("--ap", default="00:aa:bb:cc:dd:ee")
    ap.add_argument("--d11", action="store_true",
                    help="also read ioctl 604 - ONLY on a build with the hw->up guard")
    ap.add_argument("--rate", type=int, default=0,
                    help="radiotap rate in 500kbps units (0 = omit the field)")
    ap.add_argument("--guard", action="store_true",
                    help="also read ioctl 620 (only on a build that has it)")
    args = ap.parse_args()

    nex = Nex()

    if args.mode == "sanity":
        print("ioctl 601 ->", sanity(nex))
        return

    if args.mode == "monitor":
        ok = nex.set(WLC_SET_MONITOR, struct.pack("<I", args.mon))
        print("set monitor=%d -> %s" % (args.mon, "ACK" if ok else "NO REPLY"))
        return

    if args.mode == "sample":
        sample(nex, "sample", args.guard, args.d11)
        return

    if args.mode == "probe":
        s, f = inject_probes(args.iface, args.count, mac(args.sta), args.rate)
        print("probe requests sent=%d failed=%d src=%s rate=%s"
              % (s, f, args.sta, args.rate or "none(0)"))
        return

    if args.mode == "burst":
        s, f = burst(args.iface, args.count, mac(args.sta), mac(args.ap))
        print("injected sent=%d failed=%d" % (s, f))
        return

    if args.mode == "leaktest":
        # Decisive test for pkt_buf_free_skb @0x6c74 (wrapper.c records it as a
        # 32B-signature match - the weak tier). 612 allocates up to 64 buffers
        # and frees them all. If the free wrapper is wrong, heapfree decays by
        # ~64 buffers per call and freebufs follows it down. If the address is
        # right, both stay flat. Nothing else is issued, so nothing else can be
        # blamed for the result.
        print("# ioctl 612 only, %d calls - watching for decay" % args.rounds)
        first = None
        for i in range(1, args.rounds + 1):
            h = health(nex)
            if h is None:
                print("call %-3d *** NO REPLY - chip stopped answering ***" % i)
                return 1
            if h.get("invalid"):
                print("call %-3d INVALID magic=%08x (discard)" % (i, h["magic"]))
                continue
            if first is None:
                first = h
            print("call %-3d freebufs=%-3d osh0=%-3d heapfree=%-6d (%+d)  "
                  "blocks=%-3d biggest=%-6d mfail=%d lbfail=%d"
                  % (i, h["freebufs"], h["osh0"], h["heapfree"],
                     h["heapfree"] - first["heapfree"], h["blocks"],
                     h["biggest"], h["mallocfail"], h["lbfail"]))
            time.sleep(0.3)
        print("# flat heapfree/freebufs => pkt_buf_free_skb is correct")
        return 0

    if args.mode == "soak":
        print("# escalating injection burst soak on %s" % args.iface)
        print("# sanity:", sanity(nex))
        sample(nex, "baseline", args.guard, args.d11)
        for r in range(1, args.rounds + 1):
            n = args.count
            s, f = burst(args.iface, n, mac(args.sta), mac(args.ap))
            time.sleep(0.5)
            alive = sample(nex, "r%-2d(+%d)" % (r, n), args.guard, args.d11)
            print("           injected sent=%d failed=%d" % (s, f))
            if not alive:
                print("*** wedged after %d rounds, ~%d frames offered ***"
                      % (r, r * n))
                return 1
        print("survived %d rounds x %d frames" % (args.rounds, args.count))
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
