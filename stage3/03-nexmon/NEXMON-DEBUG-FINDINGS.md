# bcm43430a1 / 7.45.98 — hardware findings, 2026-09-02/03

Session notes from debugging a Pi Zero 2 W (`raspberrypi,model-zero-2-w`, BCM43430/1,
kernel 6.18.39, firmware `7.45.98 (TOB) (56df937 CY)`, nexmon build `c6fc-1` =
nexmon `c6fce06a`) that was wedging repeatedly under pwnagotchi 2.9.5.9 + bettercap.

Everything below marked **MEASURED** was reproduced on that hardware in this session.
Everything marked **OPEN** or **INFERRED** was not, and is flagged as such deliberately —
this file exists partly because three plausible-sounding hypotheses were killed by
measurement, and the wrong ones cost more time than the right one saved.

Companion tools in this directory: `nexprobe.py`, `hoptest.sh`.

## Tooling note — nexutil vs nexprobe.py

`nexutil` was **not** installed on the test image, so `nexprobe.py` was written to talk to
the driver directly over netlink. Wire format, from
`patches/driver/brcmfmac_6.18.y-nexmon/core.c`:

- `NETLINK_USER = 31`
- payload = `struct nexudp_ioctl_header`: `char nex[3]` (`"NEX"`), `char type` (0),
  `int securitycookie`, `uint cmd`, `uint set`, then the ioctl buffer — 16 bytes of header
- `set != 0` → `brcmf_fil_cmd_data_set`, replies `"ACK"`; `set == 0` →
  `brcmf_fil_cmd_data_get`, replies with the frame, buffer filled in
- reply is unicast to `nlh->nlmsg_pid`, so bind to a known pid

Once nexutil ships in the image, the ioctl half of `nexprobe.py` is redundant:

| purpose | nexprobe.py | nexutil |
|---|---|---|
| sanity (`0xDEADBEEF`) | `nexprobe.py sanity` | `nexutil -g601 -l4 -i` |
| pool/heap health (`NEX1`) | `nexprobe.py sample` | `nexutil -g612 -l32 -i` |
| d11 registers (`NEX3`) | `nexprobe.py sample --d11` | `nexutil -g604 -l24 -i` |
| injection counters (`NEX2`) | `nexprobe.py sample --guard` | `nexutil -g620 -l16 -i` |
| set monitor mode | `nexprobe.py monitor --mon 2` | `nexutil -m2` |

The parts of `nexprobe.py` that stay useful are the ones nexutil does not do: raw frame
injection (`burst`, `probe`), the escalating `soak`, and `leaktest`.

> ### Warning that carries over to nexutil
>
> **`nexutil -g604` will brick the chip on any build without the `wlc->hw->up` guard** — see
> §1. Nothing about using nexutil instead of nexprobe.py changes that; the danger is in the
> firmware handler, not the client. `nexprobe.py` refuses on an unguarded build (it checks
> for the `NEX3` magic); **nexutil has no such protection and will happily issue it.**
> Until a guarded firmware is flashed, treat `-g604` as a destructive command.
>
> The same reasoning applies to any new probe: give it a magic word, or a timed-out reply
> will read as valid all-zero data (§ Methodology, rule 1).

---

## 1. MEASURED — ioctl 604 bricks the chip on its own

**This is the single most important finding here, and it contaminates prior debugging.**

A single `604` call against an idle radio kills the SDIO backplane in ~10 ms:

```
[90.210547] brcmfmac: nexmon_nl_ioctl_handler: calling brcmf_fil_cmd_data_get, cmd: 604
[90.220244] brcmfmac: brcmf_sdio_isr: failed backplane access
```

Afterwards, permanently until a **power cycle**:

- every ioctl times out (`brcmf_sdio_bus_rxctl: resumed on timeout`)
- `F1 signature read @0x18000000` = `0xffffffff` (healthy: `0x1541a9a6`)
- `brcmf_chip_recognition: chip backplane type 15 is not supported`
- `brcmf_ops_sdio_probe: F2 error, probe failed -19`
- `modprobe -r brcmfmac && modprobe brcmfmac` does **not** recover it

Reproduced twice, from a clean boot, with **no injection, no RX load, no channel hopping**.

**Cause.** `case 604` dereferences `wlc->regs` (`wlc_info+0x0C`), which is a backplane read
of the d11 core. That is only valid while the core is out of reset and clocked. `wlan0`
being administratively UP is *not* sufficient — the radio must actually be enabled. The
register offsets are fine (`macintstatus` at `0x128`, as documented in
`bcm43436b0/9_88_4_77/PORTING_STATUS.md`); it is touching the core at all that hangs.

This explains why 604 worked in earlier sessions — the radio was actively running monitor
traffic — and kills a freshly booted chip.

**Why this matters beyond the landmine.** The terminal signature of an unguarded 604 is
*identical* to the wedge that `REVERSE_ENGINEERING_NOTES.md` has been chasing: `-110` on
everything, no TRAP, unrecoverable without a power cycle. **Any sampling loop that called
604 was a candidate cause of the death it then attributed to hop count or frame count.**
Worth re-reading the runs behind "wedges at hop 9–11" and "rx frozen at 38–39" to check
which probes that harness issued.

The `MI_RXOV` / `im=bae7a864` data in `38750224` looks safe — it came from the
firmware-side heartbeat, not from 604.

**Fix** (uncommitted in the nexmon working tree): gate on `wlc->hw->up`, the same predicate
`sendframe()` already uses, and return a `NEX3` magic word plus that predicate so "core was
down, didn't look" is distinguishable from "registers really read zero" and from a
timed-out reply. Layout becomes 6 words, `len >= 24`.

> **Rule: never call 604 on a build without that guard.** `nexprobe.py` makes it opt-in
> (`--d11`) and refuses on an unguarded build.

---

## 2. MEASURED — the `-110` on set_channel is transient and is NOT the wedge

60 hops through the *real* `brcmf_cfg80211_nexmon_set_channel` path, 2 s dwell, monitor RX
running concurrently:

```
hop 37 ch9  FAILED rc=146: command failed: Connection timed out (-110)
hop 52 ch10 FAILED rc=146: command failed: Connection timed out (-110)
=== hop failures: 2 / 60 ===
=== rx frames captured: 2750 ===
=== final sanity === ioctl 601 -> 0xDEADBEEF OK
```

The chip **recovered by itself** and kept hopping (40, 45, 50, 55 all clean). Throughout:
`freebufs=64`, `heap` flat at 74020–74036, `osh0=1` stable, `mfail=0 lbfail=0`.

Six `-110`s over 900+ s across five different chanspecs (4100/4101/4102/4105/4106 — not
channel-specific), with **zero** `checkdied`, **zero** TRAP, **zero** `sdio_isr`/backplane
errors, and the chip healthy at the end.

So `-110` on the chanspec iovar is a benign, intermittent DCMD timeout at roughly a 3% rate.
It is a symptom that occurs routinely and harmlessly; it is not the wedge.

### Consequence for `424adbd8`

That commit removed the retry loop from `brcmf_cfg80211_nexmon_set_channel`, reasoning:

> *"Deliberately no retry loop here. Of the errors this can return only `-ETIMEDOUT` is
> transient, and it already costs `DCMD_RESP_TIMEOUT` (2500ms) ... so retrying would block
> this cfg80211 op for >7s without fixing anything."*

The measurement says the opposite: `-ETIMEDOUT` **is** transient *and* the very next hop
succeeds, so a retry would in fact absorb it. Propagating a benign ~3% transient as a hard
hop failure is what bettercap logs as `error while hopping to channel N`, and that is
plausibly what drives the `fix_services` recovery churn seen in the field logs
(`[Fix_Services] SYSLOG wifi.recon flip fail` repeating).

**Not changed here** — whether to restore a bounded retry is a real trade-off against the
2.5 s stall per attempt, and it is a maintainer call. **INFERRED, not measured:** that this
churn contributes to the user-visible "failing a lot". Worth testing directly.

**Unresolved sub-question worth one cheap test:** after a `-110`, did the radio actually
land on the requested channel? If the chanspec was applied despite the timeout, swallowing
`-ETIMEDOUT` is safe; if not, the caller is on the wrong channel until the next hop. Query
`iw dev wlan0mon info` immediately after a failure to find out.

---

## 3. MEASURED — `pkt_buf_free_skb @0x6c74` is correct

`wrapper.c:425` records it as a 32-byte-signature match, which is the weak evidence tier
`relocate.py` warns about, so it was worth checking — especially as anything probing the
pool depends on it.

12 × ioctl 612 (each allocating up to 64 buffers and freeing them all = 768 alloc/free
cycles), nothing else issued:

```
call 1   freebufs=64  osh0=0  heapfree=98344  (+0)  blocks=14  biggest=80916  mfail=0 lbfail=0
...
call 12  freebufs=64  osh0=0  heapfree=98344  (+0)  blocks=14  biggest=80916  mfail=0 lbfail=0
```

Bit-identical throughout. A stubbed or misplaced free would have bled ~8 KB per call.

Also verified statically — the TX wrapper relocations are sound, contrary to an early
suspicion:

| wrapper | 41.46 | 7.45.98 | `relocate.py --auto` |
|---|---|---|---|
| `wlc_get_txh_info` | `0x9ED6` | `0xbe02` | UNIQUE to 96B |
| `wlc_txfifo` | `0xf680` | `0x11ed0` | UNIQUE to 64B |
| `wlc_d11hdrs` | `0xA024` | `0xbf50` | UNIQUE to 32B (weakest of the three) |

---

## 4. MEASURED — correct radio config (this invalidates naive hop tests)

Monitor RX **and** channel hopping both work only in this configuration:

```
wlan0 UP once      # initialises the MAC
wlan0 DOWN         # release the channel from the managed vif
wlan0mon UP + WLC_SET_MONITOR=2
```

- With `wlan0` **UP**: RX works, but every `iw dev wlan0mon set channel` returns
  **`EBUSY (-16)`** — rejected by cfg80211 in the kernel, **never reaching the driver**.
  A hop test run this way exercises nothing. (An initial 30-hop run of mine was entirely
  worthless for this reason.)
- With `wlan0` **DOWN before it was ever brought up**: 0 frames captured.
- With `wlan0` **DOWN after being brought up once**: hopping works, RX works (1039+ frames).

Also seen: `ch13` → `-22`, *"(extension) channel is disabled"* — regulatory, matching the
ETSI note already in the nexmon notes. Reg domain here is `country 00` (world).

---

## 5. OPEN — injection produces no observable on-air effect

**This is the most important open question and it is well-controlled.**

Config: `wlan0` down, `wlan0mon` verified tuned to channel 6, ~1250 ambient frames captured
in the same runs (so RX and tuning both demonstrably work).

- 30 broadcast probe requests injected on `wlan0mon` with a fabricated source MAC
  (`00:11:22:33:44:55`), radiotap carrying an explicit rate
- Repeated at 1, 2 and 11 Mbit — **90 frames total**
- Result: **zero** probe responses addressed to that MAC, **zero** frames of any kind
  addressed to it

The host stack accepted every frame (`sent=N failed=0`), and the driver does deliver them —
`brcmf_netdev_ops_mon` has `.ndo_start_xmit = brcmf_netdev_start_xmit` (`core.c:858`), which
passes anything longer than an Ethernet header to `brcmf_proto_tx_queue_data`.

Nearby APs answer a probe request from any MAC; three were in range at −64 to −69 dBm
(confirmed by `iw dev wlan0 scan`). They did not answer.

### This retracts an earlier conclusion of mine

A 600-frame injection soak moved `heap` by 364 bytes and `freebufs` not at all. I first read
that as *"TX reclaim works fine, there is no injection leak."* Given the probe result, the
likelier reading is that **nothing was ever transmitted, so nothing was ever consumed** —
that run says nothing either way about reclaim. Flat counters are not evidence of health
when the path under test may be inert.

### How to settle it — one build

`nex_inject_calls` / `nex_inject_sent`, read via **ioctl 620** (uncommitted in the nexmon
tree), split the two remaining possibilities:

- `calls == 0` after injecting ⇒ frames never reach `wl_send_hook`; the fault is between the
  BCDC/SDIO path and the hooked function pointer at `0x40fe0`
- `calls` climbing in step with what was offered ⇒ frames reach `sendframe()` and are lost at
  or below `wlc_txfifo`

Alternative without a rebuild: a second radio in monitor mode. On this desktop, `wlp5s0`
(Intel `iwlwifi`) supports monitor but `wpa_supplicant` resets the interface — the channel
will not stick until it is stopped or NetworkManager is told to release the device.

---

## 6. RETRACTED — the injection-guard hypothesis

I proposed that bettercap deauth bursts (50+ frames) drain the ~40-buffer packet pool, and
wrote a guard reserving buffers for RX. **It was never supported by measurement:** 600
injected frames with concurrent RX produced no pool or heap movement whatsoever, and §5
suggests the frames may not even transmit.

The guard was removed. Only the counters were kept, because instrumentation is what the
situation actually called for. Recorded here because the reasoning was seductive and fit the
field logs neatly — the `21:59:15` inject burst followed 19 s later by the first `-110`
matched `46b0feb6`'s documented 18 s CPU-pegged-before-death gap almost exactly. It was
still wrong. Correlation in a field log is not a mechanism.

---

## 7. What is still unexplained — the actual pwnagotchi wedge

Post-`0x160b0`-NOP, none of these wedge the chip:

- sustained channel hopping (60 hops, 2750 RX frames) — §2
- injection at bettercap scale (600 frames) — §5, though possibly inert
- monitor RX soak (thousands of frames)
- ioctl 612 hammering (768 alloc/free cycles) — §3

The only thing that reliably wedged it in this session was **ioctl 604** — which pwnagotchi
and bettercap never call. So the field wedge remains unreproduced.

### Differences between this harness and real pwnagotchi, untested

Ranked by how much they differ from what was tested:

1. **bettercap's hop rate and dwell** — the field logs show ~2.5 s promiscuous toggles, but
   bettercap also does `wifi.recon` on/off flips and short `wifi channels: [N]` locks during
   attacks. Not reproduced.
2. **Association attacks** — `sending association frame to ...` is a different frame path
   from deauth; both were only tested as raw injection.
3. **`wifi.recon` on/off cycling** driven by `fix_services` — this repeatedly reconfigures
   the radio, and given §2 it may be firing on benign `-110`s.
4. **Runtime** — the field wedges took ~4–5 minutes of real activity; the longest clean run
   here was ~2 minutes of hopping.
5. **`brcmf_sdio_bus_reset()` after `28d42c04`** — single-attempt `mmc_hw_reset()`, delegating
   recovery to userspace policy. If §8's Python bug stops that policy running, a chip that
   *could* have recovered stays dead.

Highest-value next test: drive real bettercap against the APs with `nexprobe.py sample`
polling on a 2 s cadence (612 only — **never** 604 on an unguarded build), and capture the
last valid sample before the chip stops answering. That distinguishes resource exhaustion
from a clean stop, which is the fork nothing has yet resolved for the *field* failure.

---

## 8. Separate bug — pwnagotchi recovery is broken (FIX IN PROGRESS)

> **Status 2026-09-03: being fixed.** Kept here because it shaped every field log quoted in
> this file, and because it changes how §7's test should be read. Once recovery works, a
> wedge should self-clear — so the field measurement becomes *how often does it wedge*
> rather than *did it stay dead*, and "the Pi was still broken 7 minutes later" stops being
> evidence about the firmware at all.

Not firmware. Spamming the field logs:

- `TypeError: expected string or bytes` from `agent._fetch_stats → update_peers`
- the same exception from `fix_services._tryTurningItOffAndOnAgain` while rendering the
  "I'm blind!" screen — **the recovery UI itself crashes**
- `[Fix_Services] SYSLOG wifi.recon flip fail: expected string or bytes`, repeating

Combined with `28d42c04` delegating SDIO-reset recovery to userspace policy, a wedged radio
means the Pi sits with a dead interface and never reboots itself. That is what turns a
recoverable wedge into "failing a lot", independent of whatever causes the wedge.

---

## Methodology rules this session re-earned

1. **A probe that can time out must prove it ran.** `fc3fdc78` established this for ioctl
   612 (`NEX1` magic). Ioctl **604 had no magic word**, so its all-zero non-reply was being
   printed as `macintstatus=0 RXOV=0` — data that looks completely plausible. The same trap,
   in new code, one commit later. 604 and 620 now carry `NEX3`/`NEX2`.
2. **Verify the path under test is live before trusting a null result.** "No pool movement
   during injection" and "injection may not transmit" are indistinguishable from flat
   counters alone.
3. **Check the harness reaches the code under test.** 30 "hops" that never got past
   cfg80211's `EBUSY` looked exactly like 30 successful hops in the log.
4. **A 32-byte signature match is the weak tier.** `relocate.py --auto` reports the length at
   which uniqueness fails; treat anything that only matches short as unverified.

---

## Uncommitted changes in the nexmon working tree

At `~/Projects/nexmon` (branch `dev`), not yet committed:

- `patches/bcm43430a1/7_45_98/nexmon/src/ioctl.c` — 604 `wlc->hw->up` guard + `NEX3` magic
  (§1); ioctl 620 injection counters (§5)
- `patches/bcm43430a1/7_45_98/nexmon/src/injection.c` — `nex_inject_calls` /
  `nex_inject_sent` (§5)

The 604 fix is worth landing on its own regardless of where the injection question goes —
it removes a chip-bricking landmine from the debug build.

**Not compile-tested.** Only the macOS toolchain is vendored in the nexmon repo; the Linux
path needs a system `arm-none-eabi-` plus the GCC-5.4-era plugin built from
`buildtools/gcc-nexmon-plugin/nexmon.c`, and the current Debian candidate is GCC 14.2. The
build has to go through this pi-gen stage.
