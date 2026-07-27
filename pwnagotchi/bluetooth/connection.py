import subprocess
import time
import re
import logging
import threading
import os
from .device import BluetoothDevice


class ConnectionManager:
    """Manages Bluetooth device connections, pairing, and status checking."""

    # Timing constants
    DEVICE_OPERATION_DELAY = 1
    DEVICE_OPERATION_LONGER_DELAY = 2
    SCAN_STOP_DELAY = 0.5
    PAIRING_SCAN_WAIT_TIMEOUT = 15
    PAIRING_PASSKEY_TIMEOUT = 90
    PAIRING_RETRY_DELAY = 2
    PAIRING_MAX_RETRIES = 2
    SCAN_DURATION = 30
    PAN_INTERFACE_WAIT = 2
    INTERNET_VERIFY_WAIT = 2
    DHCP_KILL_WAIT = 0.5
    DHCP_RELEASE_WAIT = 1
    OPERATION_SHORT_DELAY = 0.5
    OPERATION_MEDIUM_DELAY = 3

    # Subprocess timeouts
    SUBPROCESS_TIMEOUT_SHORT = 1
    SUBPROCESS_TIMEOUT_MEDIUM = 2
    SUBPROCESS_TIMEOUT_NORMAL = 3
    SUBPROCESS_TIMEOUT_STANDARD = 5
    SUBPROCESS_TIMEOUT_LONG = 10
    PROCESS_CLEANUP_DELAY = 0.2
    DBUS_OPERATION_RETRY_DELAY = 0.1

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self._lock = threading.Lock()
        self.scan_mac_pattern = re.compile(r"([0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2})")
        self.scan_ansi_pattern = re.compile(r"(\x1b\[[0-9;]*m|\x08)")

    def _strip_ansi_codes(self, text):
        """Remove ANSI escape codes from text."""
        if not text:
            return text
        return self.scan_ansi_pattern.sub("", text)

    def _run_cmd(self, cmd, capture=False, timeout=None):
        """Run shell command with error handling and deadlock prevention."""
        if timeout is None:
            timeout = self.SUBPROCESS_TIMEOUT_LONG

        try:
            env = dict(os.environ)
            env["NO_COLOR"] = "1"
            env["TERM"] = "dumb"

            if capture:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout, env=env
                )
                output = result.stdout + result.stderr
                return self._strip_ansi_codes(output)
            else:
                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=timeout,
                    env=env,
                )
                return None
        except subprocess.TimeoutExpired:
            self.logger.error(f"Command timeout ({timeout}s): {' '.join(cmd)}")
            if cmd and cmd[0] == "bluetoothctl":
                try:
                    subprocess.run(
                        ["pkill", "-9", "bluetoothctl"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=2,
                    )
                    time.sleep(self.PROCESS_CLEANUP_DELAY)
                except Exception as e:
                    self.logger.debug(f"Process kill failed: {e}")
            return "Timeout"
        except Exception as e:
            self.logger.error(f"Command failed: {' '.join(cmd)} - {e}")
            return None

    def is_responsive(self):
        """Check if Bluetooth service is responsive."""
        result = self._run_cmd(["bluetoothctl", "show"], capture=True, timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
        return result is not None and result != "Timeout"

    def restart_if_needed(self):
        """Restart Bluetooth service if it appears hung."""
        if not self.is_responsive():
            self.logger.info("Restarting Bluetooth service...")
            try:
                subprocess.run(
                    ["systemctl", "restart", "bluetooth"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                )
                time.sleep(3)
                return True
            except Exception as e:
                self.logger.warning(f"Failed to restart Bluetooth: {e}")
                return False
        return True

    def get_status(self, mac):
        """Get basic connection status for a device."""
        if not BluetoothDevice.validate_mac(mac):
            return None

        info = self._run_cmd(
            ["bluetoothctl", "info", mac],
            capture=True,
            timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
        )
        if not info:
            return None

        status = {
            "paired": "Paired: yes" in info,
            "trusted": "Trusted: yes" in info,
            "connected": "Connected: yes" in info,
        }
        return status

    def get_full_status(self, mac):
        """Get complete connection status including network details."""
        status = self.get_status(mac)
        if not status:
            return status

        status["pan_active"] = False
        status["interface"] = None
        status["ip_address"] = None

        # Check if PAN interface is active
        result = self._run_cmd(
            ["ip", "link", "show"],
            capture=True,
            timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
        )
        if result and ("bnep" in result or "bt-pan" in result):
            status["pan_active"] = True
            match = re.search(r"(\d+):\s+(bnep\d+|bt-pan\d*)", result)
            if match:
                iface = match.group(2)
                status["interface"] = iface
                ip_result = self._run_cmd(
                    ["ip", "addr", "show", iface],
                    capture=True,
                    timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
                )
                if ip_result:
                    ip_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", ip_result)
                    if ip_match:
                        status["ip_address"] = ip_match.group(1)

        return status

    def disconnect(self, mac):
        """Disconnect from a device."""
        self._run_cmd(["bluetoothctl", "disconnect", mac], timeout=self.SUBPROCESS_TIMEOUT_STANDARD)
        time.sleep(self.OPERATION_SHORT_DELAY)

    def unpair(self, mac):
        """Remove pairing with a device."""
        self._run_cmd(["bluetoothctl", "remove", mac], timeout=self.SUBPROCESS_TIMEOUT_LONG)
        time.sleep(self.OPERATION_SHORT_DELAY)

    def scan(self, duration=30):
        """Scan for Bluetooth devices."""
        self.logger.info(f"Starting Bluetooth scan ({duration}s)...")
        devices = []

        try:
            self._run_cmd(["bluetoothctl", "scan", "on"], timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
            time.sleep(duration)
            self._run_cmd(["bluetoothctl", "scan", "off"], timeout=self.SUBPROCESS_TIMEOUT_NORMAL)

            result = self._run_cmd(
                ["bluetoothctl", "devices"],
                capture=True,
                timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
            )
            if result:
                for line in result.split("\n"):
                    if "Device" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            mac = parts[1]
                            name = " ".join(parts[2:])
                            devices.append({"mac": mac, "name": name})

        except Exception as e:
            self.logger.error(f"Scan failed: {e}")

        return devices

    def connect_nap(self, mac):
        """Connect to device's NAP (Network Access Point) profile."""
        try:
            self.logger.info(f"Connecting to NAP profile for {mac}...")
            result = self._run_cmd(
                ["bluetoothctl", "connect", mac],
                capture=True,
                timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
            )
            if result and "successful" in result.lower():
                return True
            return False
        except Exception as e:
            self.logger.error(f"NAP connection failed: {e}")
            return False

    def pair_interactive(self, mac, name=""):
        """Pair with a device interactively."""
        try:
            self.logger.info(f"Starting pair for {mac} ({name})...")
            self._run_cmd(["bluetoothctl", "pair", mac], timeout=self.PAIRING_PASSKEY_TIMEOUT)
            time.sleep(self.DEVICE_OPERATION_DELAY)
            return True
        except Exception as e:
            self.logger.error(f"Pairing failed: {e}")
            return False

    def trust_device(self, mac):
        """Mark device as trusted."""
        self._run_cmd(["bluetoothctl", "trust", mac], timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
        time.sleep(self.DEVICE_OPERATION_DELAY)

    def get_trusted_devices(self):
        """Get list of trusted Bluetooth devices."""
        devices = []
        result = self._run_cmd(
            ["bluetoothctl", "devices"],
            capture=True,
            timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
        )
        if not result:
            return devices

        for line in result.split("\n"):
            if "Device" in line:
                parts = line.split()
                if len(parts) >= 3:
                    mac = parts[1]
                    name = " ".join(parts[2:])
                    status = self.get_status(mac)
                    if status and status.get("trusted"):
                        devices.append(BluetoothDevice(mac, name, paired=status["paired"], trusted=True, connected=status["connected"]))

        return devices
