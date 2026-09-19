# bcm43430a1 / 7.45.98 — hardware findings, 2026-09-02/03 and 2026-09-19

Session notes from debugging a Pi Zero 2 W (`raspberrypi,model-zero-2-w`, BCM43430/1,
kernel 6.18.39, firmware `7.45.98 (TOB) (56df937 CY)`, nexmon build `c6fc-1` =
nexmon `c6fce06a`) that was wedging repeatedly under pwnagotchi 2.9.5.9 + bettercap.

A second session on **2026-09-19** re-ran the open questions against a newer image of the
same board — kernel 6.18.50, same firmware, nexmon `1654e185` — and its results are folded
in under dated **MEASURED 2026-09-19** sub-headings. Two of them disagree with the first
session (§2, §5); where they do, both are kept and the difference is called out rather than
overwritten, because what changed between the images has not been isolated.

Everything below marked **MEASURED** was reproduced on that hardware in the session it is
dated to.
Everything marked **OPEN** or **INFERRED** was not, and is flagged as such deliberately —
this file exists partly because three plausible-sounding hypotheses were killed by
measurement, and the wrong ones cost more time than the right one saved.

Companion tools in this directory: `nexprobe.py`, `hoptest.sh`.

## Tooling note — nexutil vs nexprobe.py

`nexutil` was **not** installed on the test image this session, so `nexprobe.py` was
written to talk to the driver directly over netlink. (It is now built from the same
nexmon checkout and installed to `/usr/local/bin/nexutil` by `01-run-chroot.sh`'s
`install_nexutil`, so on any image built after this note it is present.) Wire format, from
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
| sanity (`0xDEADBEEF`) | `nexprobe.py sanity` | `nexutil -g601 -l4` |
| pool/heap health (`NEX1`) | `nexprobe.py sample` | `nexutil -g612 -l32` |
| d11 registers (`NEX3`) | `nexprobe.py sample --d11` | `nexutil -g604 -l24` |
| injection counters (`NEX2`) | `nexprobe.py sample --inject-counters` | `nexutil -g620 -l16` |
| set monitor mode | `nexprobe.py monitor --mon 2` | `nexutil -m2` |

> **Do not add `-i` to those get commands — it segfaults.** An earlier revision of this
> table did. `-i` is the *input* encoding for `-v` ("read the value as an integer"), not an
> output format, so on a `-g` it is meaningless to begin with. Without `-v`,
> `custom_cmd_value` is `NULL` and `nexutil.c:446-450` still runs
> `strtoul(custom_cmd_value, NULL, 0)`, which dereferences it. **MEASURED** on the test
> device: `nexutil -g601 -l4 -i` → `rc=139`, while `nexutil -g601 -l4` returns
> `ef be ad de` correctly. Output is a hexdump; the words are little-endian.

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

**Fix** (landed in nexmon `1654e185`): gate on `wlc->hw->up`, the same predicate
`sendframe()` already uses, and return a `NEX3` magic word plus that predicate so "core was
down, didn't look" is distinguishable from "registers really read zero" and from a
timed-out reply. Layout becomes 6 words, `len >= 24`.

**MEASURED 2026-09-19 — the guard holds on hardware.** On an image carrying `1654e185`,
`nexutil -g604 -l24` against a live radio returns

```
0x000000: 33 58 45 4e 01 00 00 00 03 04 52 c5 04 00 00 00 3XEN......R.....
0x000010: 00 00 00 00 64 a8 e7 ba                         ....d...
```

`NEX3`, `hw_up=1`, `maccontrol=c5520403`, `maccommand=4`, `macintstatus=0`,
`macintmask=bae7a864` — the same mask as `38750224` — and the chip stayed alive through
this and every later probe. 604 was issued repeatedly during the 2026-09-19 session with no
backplane error at all. On `c6fce06a` the first such call killed the chip.

Whether a build is guarded can be checked without issuing the ioctl at all: the magic words
are literal-pool constants, so they appear in the firmware image in little-endian byte
order. `grep -abo 3XEN brcmfmac43430-sdio.bin` hitting means 604 is guarded; `2XEN` means
620 exists.

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

### MEASURED 2026-09-19 — the `-110` did not occur at all, which is itself the finding

The sub-question above is **still unanswered, and could not be answered**, because on an
image carrying nexmon `1654e185` (kernel 6.18.50) the failure never happened:

```
run 1:  70 hops, 1.5s dwell, no concurrent RX     === hop failures: 0 / 70 ===
run 2: 110 hops, 2.0s dwell, concurrent monitor RX
                                                  === hop failures: 0 / 110 ===
                                                  rx frames: 5971
final health: NEX1 heapfree=73680 blocks=12 osh0=1 freebufs=64 mfail=0 lbfail=0
final sanity: 0xDEADBEEF
```

Run 2 reproduces the original conditions deliberately — same `wlan0` down / `wlan0mon` up
config (§4), same 2 s dwell, monitor RX running throughout, which is what run 1 lacked. The
harness demonstrably reached the driver: `rc=0` on every hop (a cfg80211 `EBUSY` rejection
would surface as a failure, not a silent pass — rule 3), and retuning visibly changed what
was captured.

**180 hops with zero failures is not consistent with the ~3% rate measured before.** At the
originally observed 2/60, P(0 in 180) = 0.22%; at the 3% the text quotes, 0.42%. Something
changed between the two sessions.

**What changed is not isolated**, and the honest list is short: nexmon `c6fce06a` →
`1654e185` (which touched only ioctl 604 and the counters, nothing in the chanspec path),
kernel 6.18.39 → 6.18.50 with a newer DKMS driver build, a different image, and a different
RF environment. The driver-side change is the plausible one; the firmware change is not.

**Consequence for the retry debate above:** the premise on both sides of it — that a benign
`-ETIMEDOUT` arrives at roughly 3% and has to be either absorbed or propagated — does not
hold on this build. Restoring a bounded retry to `brcmf_cfg80211_nexmon_set_channel` would
now be paying a possible 2.5 s stall to absorb something that did not occur once in 180
hops. **`424adbd8` should stand until the `-110` is seen again on a current image.** If it
does come back, the `iw dev wlan0mon info` check is still the right first move.

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

## 5. RESOLVED — injection works; the 2026-09-02/03 null result did not reproduce

> **Status 2026-09-19: closed by measurement.** This was the most important open
> question in this file. On an image carrying nexmon `1654e185`, injected frames reach
> `sendframe()` *and* reach the air, and real APs answer them. The original observation
> below is kept because it was well-controlled and is still unexplained — what changed
> between the two sessions is not established by this measurement.

### Original observation (2026-09-02/03, nexmon `c6fce06a`) — not reproduced

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

> *2026-09-19: with injection now proven live, the original reading turns out to have been
> right after all — flat `freebufs` across 120 transmitted frames says there is no leak.
> The retraction was still correct at the time it was written: the run could not
> distinguish the two, and "inert path" was the live possibility. A conclusion that happens
> to survive is not the same as one that was justified.*

### MEASURED 2026-09-19 — both halves of the fork answered at once

Pi Zero 2 W, kernel 6.18.50, firmware `7.45.98 (TOB) (56df937 CY)` + nexmon `1654e185`,
`wlan0` down, `wlan0mon` up in monitor mode 2 on channel 6, pwnagotchi and bettercap
**stopped**. RX proven live first (42 frames on ch1, 200 on ch6) per rule 2.

**Counters — ioctl 620 climbs exactly in step with what was offered:**

```
620 BEFORE          2XEN  calls=0    sent=0
inject 30 probes    sent=30 failed=0
620 AFTER           2XEN  calls=30   sent=30
inject 90 more      (30 each at 1, 2, 11 Mbit)
620 AFTER           2XEN  calls=120  sent=120
```

Per the fork above, `calls` climbing in step means the frames **do** reach `wl_send_hook`
and **are** handed to `sendframe()`. The BCDC/SDIO path and the hooked pointer at `0x40fe0`
are exonerated.

**On air — the APs answered.** `tcpdump -i wlan0mon "wlan addr1 00:11:22:33:44:55"` while
injecting 90 frames captured **535 frames, all of them Probe Responses** addressed to the
fabricated MAC, from three distinct BSSIDs:

```
14:31:26.535957 2437 MHz -81dBm BSSID:94:2a:6f:7a:b9:74 DA:00:11:22:33:44:55
                SA:94:2a:6f:7a:b9:74 Probe Response (Jachtkamp18) CH: 6, PRIVACY
  192  SA:9a:2a:6f:7a:b9:74
  184  SA:94:2a:6f:7a:b9:74
  159  SA:9e:2a:6f:7a:b9:74
```

**Control:** 20 s on the same channel with no injection produced **1** such frame, and ioctl
620 stayed at `calls=120` throughout — so the 535 are caused by our injection and are not an
ambient artifact.

**Chip health across 120 injected frames:** `freebufs=64` unchanged, `mfail=0`, `lbfail=0`,
heap 73796 → 73348 → 73284. No pool movement, no leak, no wedge.

### What this does and does not establish

It establishes that on this build injection works end to end. It does **not** explain the
2026-09-02/03 null result, and the difference is not isolated: that session ran `c6fce06a`
on kernel 6.18.39, this one runs `1654e185` on 6.18.50 from a later image. `1654e185`
changed only ioctl 604 and added the counters — nothing in the TX path — so a firmware fix
is *not* the obvious explanation.

The likeliest candidate, and it is **INFERRED, not measured:** that session's chip had
already been through unguarded 604 calls (§1), which is exactly the harness contamination
§1 warns about. A chip whose backplane has been damaged can plausibly still receive while
failing to transmit, which is the shape of the null result. Anyone re-opening this should
re-read the §5 runs to check what the harness had issued beforehand.

Alternative cross-check if it ever needs one: a second radio in monitor mode. On this
desktop, `wlp5s0` (Intel `iwlwifi`) supports monitor but `wpa_supplicant` resets the
interface — the channel will not stick until it is stopped or NetworkManager is told to
release the device. The AP-response method above made this unnecessary.

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
- injection at bettercap scale (600 frames) — §5, and since 2026-09-19 known to be
  genuinely transmitting, not inert (120 frames, 535 probe responses, `freebufs` flat)
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

**Still the open item as of 2026-09-19.** That session ran with pwnagotchi and bettercap
deliberately stopped, to keep §5's counters clean. Everything it exercised — 120 injected
frames, 180 hops, sustained monitor RX — left the chip healthy (`freebufs=64`, `mfail=0`,
`lbfail=0`, `0xDEADBEEF` at the end of every run). The wedge has now survived two sessions
of synthetic load without reproducing, which is itself evidence that it needs *bettercap's*
particular sequence rather than raw volume.

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

**FIXED.** Three firmware-independent hardening changes:

- `pwnagotchi/mesh/peer.py` — peer advertisements are untrusted mesh JSON. A null
  advertisement, or a null/wrong-typed `name`/`face`/`pwnd_run`/`pwnd_tot`/`rssi` inside
  one, used to crash `_update_peers` on every `_fetch_stats` pass (`int(None)`, a bare
  `.get()` returning `None` into the UI). All advert accessors now coerce to a sane typed
  default via `_adv_str` / `_adv_int`.
- `pwnagotchi/plugins/default/fix_services.py` — `on_bcap_sys_log` did
  `re.search(pattern, event['data']['Message'])` with no guard; a partial bettercap
  `sys.log` event (common while the radio is spewing errors) has `Message` missing or
  non-string, so `re.search` raised `expected string or bytes` and took out the recovery
  path — the `except` then logged `SYSLOG wifi.recon flip fail` and re-entered
  `_tryTurningItOffAndOnAgain`, which crashed the same way. Now it extracts the message
  defensively and returns early if it is not a string.
- `pwnagotchi/ui/components.py` — `Text.draw` / `LabeledValue.draw` now coerce a
  non-string value to `str` instead of letting it raise inside `TextWrapper`/PIL. Because
  `view.update()` redraws every element on every call, one bad value used to wedge the
  entire UI permanently, so the "I'm blind!" recovery screen could never render.

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

## Changes to the nexmon tree — written here as uncommitted, landed as `1654e185`

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

> ### Superseded — all of the above landed
>
> **2026-09-19.** Both files are committed as nexmon `1654e185`, and `~/Projects/nexmon` is
> clean. They are no longer uncommitted, and they are no longer merely compile-untested:
> the resulting firmware was built through this pi-gen stage, flashed, and exercised on a
> Pi Zero 2 W. `3XEN` and `2XEN` are both present in the shipped
> `brcmfmac43430-sdio.bin`, ioctl 604 answers without killing the chip (§1), and ioctl 620
> produced the measurement that closed §5. This section is kept for the history of how the
> change was carried; nothing in it is still pending.
