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
#
# Also watches for a milder, distinct degradation: brcmfmac's BCDC
# command channel to the firmware timing out (-110/ETIMEDOUT). Unlike the
# full wedge above, the interface stays up and mostly-functional, but this
# has been observed (see the pwngrid mesh-advertisement investigation) to
# silently black-hole raw packet TX with no other symptom anywhere. A
# single -110 isn't enough signal by itself - the same query fires from
# routine channel queries (`iw`/`iwconfig`), so one flaky reply shouldn't
# be treated as damning - only a cluster of them in a short window
# indicates the command channel is genuinely stuck. Recovery for this one
# is a driver reload via a bettercap/pwngrid-peer restart (bettercap's own
# launcher already calls reload_brcm + recreates wlan0mon on every start),
# not a reboot - this is the same modprobe -r/modprobe reattach already
# proven to clear it, just triggered proactively instead of only at the
# next interface bring-up/down.
source /usr/bin/pwnlib

BCDC_TIMEOUT_WINDOW_SECS=60
BCDC_TIMEOUT_MIN_COUNT=3
BCDC_TIMEOUT_COOLDOWN_SECS=300

last_trigger=0
last_bcdc_action=0
bcdc_timestamps=()

handle_full_wedge() {
  local line="$1"
  # the wedge cascade logs both signatures within the same millisecond -
  # debounce so one incident doesn't burn two slots off the shared reboot
  # budget
  local now
  now="$(date +%s)"
  if [ $((now - last_trigger)) -lt 10 ]; then
    return
  fi
  last_trigger=$now

  echo "brcmfmac-watchdog: SDIO backplane wedge detected: $line" >&2

  local uptime_secs
  uptime_secs="$(cut -d. -f1 /proc/uptime)"
  if [ "$uptime_secs" -le 120 ]; then
    echo "brcmfmac-watchdog: within boot/settle window, not rebooting" >&2
    return
  fi

  if should_reboot_for_brcm_wedge; then
    echo "brcmfmac-watchdog: rebooting" >&2
    sync
    reboot
    sleep 60
  else
    echo "brcmfmac-watchdog: reboot budget exhausted, not rebooting" >&2
  fi
}

handle_bcdc_timeout() {
  local line="$1" now cutoff kept=() ts

  now="$(date +%s)"
  bcdc_timestamps+=("$now")

  cutoff=$((now - BCDC_TIMEOUT_WINDOW_SECS))
  for ts in "${bcdc_timestamps[@]}"; do
    [ "$ts" -ge "$cutoff" ] && kept+=("$ts")
  done
  bcdc_timestamps=("${kept[@]}")

  if [ "${#bcdc_timestamps[@]}" -lt "$BCDC_TIMEOUT_MIN_COUNT" ]; then
    return
  fi

  if [ $((now - last_bcdc_action)) -lt "$BCDC_TIMEOUT_COOLDOWN_SECS" ]; then
    return
  fi

  local uptime_secs
  uptime_secs="$(cut -d. -f1 /proc/uptime)"
  if [ "$uptime_secs" -le 120 ]; then
    return
  fi

  last_bcdc_action=$now
  bcdc_timestamps=()

  echo "brcmfmac-watchdog: ${BCDC_TIMEOUT_MIN_COUNT}+ BCDC command timeouts in ${BCDC_TIMEOUT_WINDOW_SECS}s (last: $line), restarting bettercap/pwngrid-peer to reload the driver" >&2
  systemctl restart bettercap pwngrid-peer
}

# -n0: only react to new lines from now on, not historical journal entries
journalctl -kf -n0 | while read -r line; do
  if echo "$line" | grep -qE "brcmf_attach: dongle is not responding|failed backplane access over SDIO"; then
    handle_full_wedge "$line"
  elif echo "$line" | grep -qE "brcmf_proto_bcdc_query_dcmd: brcmf_proto_bcdc_msg failed w/status -110"; then
    handle_bcdc_timeout "$line"
  fi
done
