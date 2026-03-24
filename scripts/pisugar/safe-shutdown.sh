#!/bin/bash
# Show shutdown face on e-ink display, then power off.
# Called by PiSugar soft_poweroff_shell (power button or battery protect).
#
# Requires: PiSugar 3 (pisugar-server on port 8423).
# On non-PiSugar setups the nc commands return empty — shutdown proceeds normally.
#
# Boot-loop guard: if battery is low AND charging (USB-C plugged in),
# skip shutdown — the Pi just auto-started to charge, don't kill it.
#
# Install:
#   sudo cp safe-shutdown.sh /usr/local/bin/ && sudo chmod +x /usr/local/bin/safe-shutdown.sh
#   Then set in PiSugar config: "soft_poweroff_shell": "sudo /usr/local/bin/safe-shutdown.sh"

PISUGAR="127.0.0.1 8423"

# Query PiSugar battery level and charging status
BATTERY=$(echo "get battery" | nc -q 1 $PISUGAR 2>/dev/null | grep -oP '[\d.]+' | head -1)
CHARGING=$(echo "get battery_power_plugged" | nc -q 1 $PISUGAR 2>/dev/null)

# Guard: low battery + charging = skip shutdown (charging from dead)
if echo "$CHARGING" | grep -q "true"; then
    BAT_INT=${BATTERY%.*}
    BAT_INT=${BAT_INT:-0}
    if [ "$BAT_INT" -lt 10 ] 2>/dev/null; then
        echo "Charging at ${BAT_INT}% — skipping shutdown" > /tmp/.pwnagotchi-button-msg
        exit 0
    fi
fi

# Normal shutdown flow
echo "Shutting down..." > /tmp/.pwnagotchi-button-msg

# Stop pwnagotchi first to release the SPI bus
systemctl stop pwnagotchi 2>/dev/null
sleep 2

# Draw sleeping face on e-ink (full refresh, persists after power cut)
/home/pi/.pwn/bin/python3 /usr/local/bin/epd-shutdown.py 2>/dev/null

# Power off
shutdown -h now
