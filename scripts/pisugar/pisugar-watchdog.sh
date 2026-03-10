#!/bin/bash
# PiSugar 3 MCU watchdog — detects when the MCU wakes from deep sleep
# and restarts pisugar-server so it reconnects via I2C.
#
# Requires: PiSugar 3 (I2C address 0x57 on bus 1, pisugar-server daemon).
# On non-PiSugar setups the I2C probe fails — script does nothing.
#
# Install:
#   sudo cp pisugar-watchdog.sh /usr/local/bin/ && sudo chmod +x /usr/local/bin/pisugar-watchdog.sh
#   sudo cp systemd/pisugar-watchdog.service /etc/systemd/system/
#   sudo cp systemd/pisugar-watchdog.timer /etc/systemd/system/
#   sudo systemctl daemon-reload && sudo systemctl enable --now pisugar-watchdog.timer

PISUGAR_ADDR=0x57

i2c_found() {
    python3 -c "
import fcntl, os
try:
    bus = os.open('/dev/i2c-1', os.O_RDWR)
    fcntl.ioctl(bus, 0x0703, $PISUGAR_ADDR)
    os.read(bus, 1)
    os.close(bus)
    exit(0)
except:
    exit(1)
" 2>/dev/null
}

pisugar_connected() {
    result=$(echo "get battery" | nc -q 1 127.0.0.1 8423 2>/dev/null)
    ! echo "$result" | grep -q "not connected"
}

if i2c_found && ! pisugar_connected; then
    logger "pisugar-watchdog: PiSugar MCU detected on I2C, restarting pisugar-server"
    systemctl restart pisugar-server
fi
