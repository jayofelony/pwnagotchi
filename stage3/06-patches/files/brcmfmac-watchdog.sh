#!/usr/bin/env bash
# Watches the live kernel journal for the brcmfmac SDIO backplane wedge
# signature and reboots immediately, instead of waiting for something else
# (a bettercap.service restart running reload_brcm, or fix_services.py's
# once-per-epoch check - which can itself be stuck if pwnagotchi is hung on
# the wedge) to stumble into the same check. This is purely a faster trigger
# for the existing, already-safe recovery: a full reboot is the only thing
# that has ever recovered this wedge, see pwnlib's reload_brcm() and
# feedback-no-mmc-hw-reset-recovery - do not replace the reboot with a
# lower-level SDIO/mmc reset here.
source /usr/bin/pwnlib

last_trigger=0

# -n0: only react to new lines from now on, not historical journal entries
journalctl -kf -n0 | while read -r line; do
  if ! echo "$line" | grep -qE "brcmf_attach: dongle is not responding|failed backplane access over SDIO"; then
    continue
  fi

  # the wedge cascade logs both signatures within the same millisecond -
  # debounce so one incident doesn't burn two slots off the shared reboot
  # budget
  now="$(date +%s)"
  if [ $((now - last_trigger)) -lt 10 ]; then
    continue
  fi
  last_trigger=$now

  echo "brcmfmac-watchdog: SDIO backplane wedge detected: $line" >&2

  uptime_secs="$(cut -d. -f1 /proc/uptime)"
  if [ "$uptime_secs" -le 120 ]; then
    echo "brcmfmac-watchdog: within boot/settle window, not rebooting" >&2
    continue
  fi

  if should_reboot_for_brcm_wedge; then
    echo "brcmfmac-watchdog: rebooting" >&2
    sync
    reboot
    sleep 60
  else
    echo "brcmfmac-watchdog: reboot budget exhausted, not rebooting" >&2
  fi
done
