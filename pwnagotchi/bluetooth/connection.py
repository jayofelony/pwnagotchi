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
    NAP_CONNECT_TIMEOUT = 20

    def __init__(self, logger=None, options=None):
        self.logger = logger or logging.getLogger(__name__)
        self.options = options or {}
        self.nap_connect_timeout = self.options.get("nap_connect_timeout", self.NAP_CONNECT_TIMEOUT)
        self._lock = threading.Lock()
        self.scan_mac_pattern = re.compile(r"([0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2})")
        self.scan_ansi_pattern = re.compile(r"(\x1b\[[0-9;]*m|\x08)")
        self._scan_results = {}  # Track scan results in real-time

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
                if not output and result.returncode != 0:
                    self.logger.warning(f"Command returned error code {result.returncode}: {' '.join(cmd)}")
                return self._strip_ansi_codes(output)
            else:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=timeout,
                    env=env,
                )
                if result.returncode != 0:
                    self.logger.warning(f"Command returned error code {result.returncode}: {' '.join(cmd)}")
                return None
        except subprocess.TimeoutExpired:
            self.logger.error(f"Command timeout ({timeout}s): {' '.join(cmd)}")
            if cmd and len(cmd) > 0 and cmd[0] == "bluetoothctl":
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
        is_resp = result is not None and result != "Timeout"
        self.logger.debug(f"Bluetooth responsive: {is_resp}, result preview: {repr(result[:100] if result else result)}")
        return is_resp

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
            return {
                "paired": False,
                "trusted": False,
                "connected": False,
            }

        try:
            info = self._run_cmd(
                ["bluetoothctl", "info", mac],
                capture=True,
                timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
            )
            if not info:
                return {
                    "paired": False,
                    "trusted": False,
                    "connected": False,
                }

            status = {
                "paired": "Paired: yes" in info,
                "trusted": "Trusted: yes" in info,
                "connected": "Connected: yes" in info,
            }
            return status
        except Exception as e:
            self.logger.debug(f"Error getting status for {mac}: {e}")
            return {
                "paired": False,
                "trusted": False,
                "connected": False,
            }

    def get_full_status(self, mac):
        """Get complete connection status including network details."""
        try:
            status = self.get_status(mac)
            if not status:
                status = {
                    "paired": False,
                    "trusted": False,
                    "connected": False,
                }

            status["pan_active"] = False
            status["interface"] = None
            status["ip_address"] = None
            status["ipv6"] = None

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
                        # Global (non-link-local) IPv6 - some tethering is v6-only
                        v6_result = self._run_cmd(
                            ["ip", "-6", "addr", "show", iface, "scope", "global"],
                            capture=True,
                            timeout=self.SUBPROCESS_TIMEOUT_MEDIUM,
                        )
                        if v6_result:
                            v6_match = re.search(r"inet6\s+([0-9a-fA-F:]+)", v6_result)
                            if v6_match:
                                status["ipv6"] = v6_match.group(1)

            return status
        except Exception as e:
            self.logger.debug(f"Error getting full status for {mac}: {e}")
            return {
                "paired": False,
                "trusted": False,
                "connected": False,
                "pan_active": False,
                "interface": None,
                "ip_address": None,
                "ipv6": None,
            }

    def disconnect(self, mac):
        """Disconnect from a device."""
        self._run_cmd(["bluetoothctl", "disconnect", mac], timeout=self.SUBPROCESS_TIMEOUT_STANDARD)
        time.sleep(self.OPERATION_SHORT_DELAY)

    def unpair(self, mac):
        """Remove pairing with a device."""
        self._run_cmd(["bluetoothctl", "remove", mac], timeout=self.SUBPROCESS_TIMEOUT_LONG)
        time.sleep(self.OPERATION_SHORT_DELAY)

    def scan_old_broken(self, duration=30):
        """Scan for Bluetooth devices using interactive bluetoothctl."""
        self.logger.info(f"Starting Bluetooth scan ({duration}s)...")

        # Clear previous scan results
        with self._lock:
            self._scan_results = {}

        import select
        import subprocess as sp
        import os

        try:
            # Ensure Bluetooth is powered on first
            self.logger.debug("Powering on Bluetooth...")
            self._run_cmd(["bluetoothctl", "power", "on"], timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
            time.sleep(0.5)

            # Pre-load all currently known devices (paired, trusted, or cached)
            self.logger.debug("Pre-loading known devices...")

            # Try with sudo first for system dbus access
            result = self._run_cmd(
                ["sudo", "bluetoothctl", "devices"],
                capture=True,
                timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
            )

            if not result or result == "Timeout":
                self.logger.debug("Sudo bluetoothctl failed, trying direct bluetoothctl...")
                result = self._run_cmd(
                    ["bluetoothctl", "devices"],
                    capture=True,
                    timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
                )

            # If bluetoothctl failed, try dbus directly
            if not result or result == "Timeout":
                self.logger.debug("Bluetoothctl failed, trying dbus...")
                dbus_devices = self._get_devices_via_dbus()
                with self._lock:
                    self._scan_results = dbus_devices
                self.logger.info(f"Pre-loaded {len(self._scan_results)} known devices via dbus")
            else:
                self.logger.debug(f"bluetoothctl devices output: {repr(result)}")
                if result:
                    with self._lock:
                        for line in result.split("\n"):
                            line = line.strip()
                            if line and line.startswith("Device"):
                                parts = line.split(None, 2)
                                if len(parts) >= 3:
                                    mac = parts[1]
                                    name = parts[2]
                                    self._scan_results[mac] = {"mac": mac, "name": name}
                                    self.logger.info(f"Pre-loaded: {name} ({mac})")
                self.logger.info(f"Pre-loaded {len(self._scan_results)} known devices")

            # Start interactive bluetoothctl process to read [NEW] Device events
            env = dict(os.environ)
            env["NO_COLOR"] = "1"
            env["TERM"] = "dumb"

            # Try with sudo first for dbus access
            self.logger.debug("Starting bluetoothctl with sudo...")
            try:
                scan_process = sp.Popen(
                    ["sudo", "bluetoothctl"],
                    stdin=sp.PIPE,
                    stdout=sp.PIPE,
                    stderr=sp.PIPE,
                    text=True,
                    bufsize=1,
                    env=env,
                )
            except Exception as e:
                self.logger.debug(f"Sudo bluetoothctl failed: {e}, trying direct...")
                scan_process = sp.Popen(
                    ["bluetoothctl"],
                    stdin=sp.PIPE,
                    stdout=sp.PIPE,
                    stderr=sp.PIPE,
                    text=True,
                    bufsize=1,
                    env=env,
                )

            # Send scan on command
            scan_process.stdin.write("scan on\n")
            scan_process.stdin.flush()
            self.logger.debug("Scan started, reading discovery events...")

            # Read [NEW] Device events in real-time for the duration
            scan_end_time = time.time() + duration
            lines_read = 0

            try:
                while time.time() < scan_end_time:
                    try:
                        # Use select to read available output with 0.5s timeout
                        ready = select.select([scan_process.stdout], [], [], 0.5)
                        if ready[0]:
                            line = scan_process.stdout.readline()
                            if not line:
                                break
                            line = line.strip()
                            lines_read += 1

                            # Parse "[NEW] Device MAC Name" format
                            if "[NEW]" in line and "Device" in line:
                                # Extract MAC and name from line like: [NEW] Device AB:CD:EF:12:34:56 Phone Name
                                parts = line.split()
                                mac_idx = None
                                for i, part in enumerate(parts):
                                    if ":" in part and len(part) == 17:  # Valid MAC format
                                        mac_idx = i
                                        break

                                if mac_idx is not None:
                                    mac = parts[mac_idx]
                                    name = " ".join(parts[mac_idx + 1:]) if mac_idx + 1 < len(parts) else "(unnamed)"
                                    with self._lock:
                                        self._scan_results[mac] = {"mac": mac, "name": name}
                                    self.logger.info(f"[NEW] {name} ({mac})")

                    except select.error:
                        pass
                    except Exception as e:
                        self.logger.debug(f"Error parsing line: {e}")
            finally:
                # Stop scan
                self.logger.debug("Stopping scan...")
                try:
                    self._run_cmd(["bluetoothctl", "scan", "off"], timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
                except Exception:
                    pass
                time.sleep(0.5)

                # Send quit to bluetoothctl
                try:
                    scan_process.stdin.write("quit\n")
                    scan_process.stdin.flush()
                    scan_process.wait(timeout=self.SUBPROCESS_TIMEOUT_MEDIUM)
                except Exception as e:
                    self.logger.debug(f"Error closing bluetoothctl: {e}")
                    try:
                        scan_process.terminate()
                        scan_process.wait(timeout=1)
                    except Exception:
                        pass

        except Exception as e:
            self.logger.error(f"Scan failed: {e}")

        with self._lock:
            device_count = len(self._scan_results)
            self.logger.info(f"Scan complete: found {device_count} total devices")
            return list(self._scan_results.values())

    def get_scan_results(self):
        """Get current scan results (for real-time progress during scan)."""
        with self._lock:
            return list(self._scan_results.values())

    def _clear_stale_acl(self, mac):
        """Tear down a half-open ACL before connecting, if one lingers.

        A failed NAP attempt can leave an ACL at the HCI layer (hcitool shows a
        connection) while BlueZ reports the device disconnected. That stale link
        makes the next ConnectProfile hang with NoReply. We clear it *before*
        starting a fresh connect (when nothing is pending), so the teardown can't
        wedge BlueZ into br-connection-busy the way a mid-connect disconnect does.
        """
        try:
            con = self._run_cmd(
                ["sudo", "hcitool", "con"],
                capture=True,
                timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
            )
            if con and con != "Timeout" and mac.upper() in con.upper():
                self.logger.info(f"Clearing stale link to {mac} before connecting")
                self._run_cmd(
                    ["bluetoothctl", "disconnect", mac],
                    capture=True,
                    timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                )
                time.sleep(self.DEVICE_OPERATION_DELAY)
        except Exception as e:
            self.logger.debug(f"Stale ACL check failed: {e}")

    def _diagnose_nap_error(self, mac, error_msg):
        """Log actionable guidance for a failed NAP connect, and clear stale pairing."""
        # Check for authentication/pairing errors
        if "Authentication Rejected" in error_msg or "Connection refused" in error_msg:
            self.logger.warning(
                "Device may have been unpaired from phone - removing stale pairing"
            )
            try:
                self._run_cmd(["bluetoothctl", "remove", mac], timeout=5)
                self.logger.info("Removed stale pairing")
            except Exception as e:
                self.logger.debug(f"Failed to remove pairing: {e}")
        elif (
            "br-connection-page-timeout" in error_msg
            or "br-connection-unknown" in error_msg
            or "Host is down" in error_msg
        ):
            self.logger.warning(
                "Phone not reachable (out of range or BT off) - will retry later"
            )

        # Provide helpful error messages
        if (
            "br-connection-create-socket" in error_msg
            or "br-connection-profile-unavailable" in error_msg
        ):
            self.logger.error("⚠️  Bluetooth tethering is NOT enabled on your phone!")
            self.logger.error(
                "Enable 'Bluetooth tethering' in phone Settings → Network & internet → Hotspot & tethering"
            )
        elif "NoReply" in error_msg or "Did not receive a reply" in error_msg:
            self.logger.error(
                "⚠️  Phone's Bluetooth is not responding to connection requests"
            )
        elif "br-connection-busy" in error_msg or "InProgress" in error_msg:
            self.logger.error(
                "⚠️  Bluetooth connection is busy, wait a moment and try again"
            )

    def connect_nap(self, mac):
        """Connect to device's NAP profile via DBus, bounded by nap_connect_timeout.

        BlueZ's ConnectProfile can block for the full ~30s page-timeout when the
        phone is off/out of range. We cap it on a wall clock so the connect/monitor
        loop can't freeze, and clear any stale half-open ACL first so the fresh
        attempt doesn't hit br-connection-busy.
        """
        try:
            import dbus
            from dbus.exceptions import DBusException
        except ImportError:
            self.logger.error("python3-dbus not installed - run: sudo apt-get install -y python3-dbus")
            return False

        # Clear a lingering half-open ACL before starting a fresh connect
        self._clear_stale_acl(mac)

        try:
            self.logger.info(f"Connecting to NAP profile for {mac}...")
            bus = dbus.SystemBus()
            manager = dbus.Interface(
                bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager"
            )

            # Find the device object path
            self.logger.info("Searching for device in BlueZ...")
            objects = manager.GetManagedObjects()
            device_path = None
            for path, interfaces in objects.items():
                if "org.bluez.Device1" in interfaces:
                    props = interfaces["org.bluez.Device1"]
                    device_mac = props.get("Address", "").upper()
                    if device_mac == mac.upper():
                        device_path = path
                        self.logger.info(f"Found device at path: {device_path}")
                        break

            if not device_path:
                self.logger.error(f"Device {mac} not found in BlueZ managed objects")
                return False

            # Connect to NAP service UUID
            NAP_UUID = "00001116-0000-1000-8000-00805f9b34fb"
            self.logger.info(f"Connecting to NAP profile (UUID: {NAP_UUID})...")
            device = dbus.Interface(
                bus.get_object("org.bluez", device_path), "org.bluez.Device1"
            )

            # Run the blocking ConnectProfile in a worker so an off/out-of-range
            # phone can't freeze us for the full BlueZ page-timeout. We abandon on
            # a wall-clock budget; the dbus call is given a slightly longer method
            # timeout so it errors out cleanly on its own afterwards.
            result = {"ok": False, "error": None}

            def _do_connect_profile():
                try:
                    device.ConnectProfile(NAP_UUID, timeout=self.nap_connect_timeout + 10)
                    result["ok"] = True
                except DBusException as dbus_err:
                    result["error"] = str(dbus_err)
                except Exception as e:
                    result["error"] = f"{type(e).__name__}: {e}"

            worker = threading.Thread(target=_do_connect_profile, daemon=True)
            worker.start()
            worker.join(self.nap_connect_timeout)

            if worker.is_alive():
                self.logger.warning(
                    f"NAP connect abandoned after {self.nap_connect_timeout}s (phone not answering)"
                )
                return False

            if result["ok"]:
                self.logger.info("✓ NAP profile connected successfully via DBus")
                return True

            error_msg = result["error"] or "unknown error"
            self.logger.error(f"DBus NAP connection failed: {error_msg}")
            self._diagnose_nap_error(mac, error_msg)
            return False

        except Exception as e:
            self.logger.error(f"NAP connection error: {type(e).__name__}: {e}")
            return False

    def pair_interactive(self, mac, name=""):
        """Pair with device - persistent agent will handle the dialog."""
        try:
            self.logger.info(f"Starting pairing with {mac}...")

            # First ensure Bluetooth is powered on and in pairable mode
            self._run_cmd(["bluetoothctl", "power", "on"], capture=True)
            time.sleep(self.DEVICE_OPERATION_DELAY)
            self._run_cmd(["bluetoothctl", "pairable", "on"], capture=True)
            self._run_cmd(["bluetoothctl", "discoverable", "on"], capture=True)
            time.sleep(self.DEVICE_OPERATION_DELAY)

            # Initiate pairing
            self.logger.info(f"Running: bluetoothctl pair {mac}")
            try:
                env = dict(os.environ)
                env["NO_COLOR"] = "1"
                env["TERM"] = "dumb"

                process = subprocess.Popen(
                    ["bluetoothctl", "pair", mac],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    bufsize=1,
                )

                output = ""
                start_time = time.time()
                timeout = self.PAIRING_PASSKEY_TIMEOUT

                # Read output with timeout
                while time.time() - start_time < timeout:
                    try:
                        line = process.stdout.readline()
                        if not line:
                            break
                        output += line
                        if "Pairing successful" in line or "Paired: yes" in line:
                            self.logger.info(f"Pairing successful for {mac}")
                            return True
                    except Exception as e:
                        self.logger.debug(f"Error reading pairing output: {e}")
                        break

                # Check final status
                process.wait(timeout=5)
                if "Pairing successful" in output or "Paired: yes" in output:
                    self.logger.info(f"Pairing successful for {mac}")
                    return True
                else:
                    self.logger.warning(f"Pairing unclear - output: {output[:200]}")
                    # Even if output is unclear, the pairing may have succeeded
                    # Check pair status to confirm
                    time.sleep(1)
                    status = self.get_status(mac)
                    if status and status.get("paired"):
                        self.logger.info(f"Pairing confirmed for {mac}")
                        return True

                self.logger.error(f"Pairing failed for {mac}")
                return False

            except subprocess.TimeoutExpired:
                self.logger.error(f"Pairing timed out for {mac}")
                return False
            except Exception as e:
                self.logger.error(f"Pairing error: {e}")
                return False

        except Exception as e:
            self.logger.error(f"Pair setup error: {e}")
            return False

    def trust_device(self, mac):
        """Mark device as trusted."""
        self._run_cmd(["bluetoothctl", "trust", mac], timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
        time.sleep(self.DEVICE_OPERATION_DELAY)

    def scan(self, duration=30):
        """Scan for Bluetooth devices using interactive bluetoothctl session - working implementation from backup."""
        try:
            self.logger.info("[bt-tether] Starting device scan...")
            self._scan_results = {}
            discovered_devices = {}
            device_types = {}

            # Pre-populate with cached paired devices
            self.logger.debug("Loading existing paired devices...")
            try:
                paired_output = self._run_cmd(
                    ["bluetoothctl", "devices", "Paired"],
                    capture=True,
                    timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                )
                if paired_output and paired_output != "Timeout":
                    for line in paired_output.split("\n"):
                        if line.strip() and line.startswith("Device"):
                            parts = line.strip().split(" ", 2)
                            if len(parts) >= 3:
                                mac = parts[1].upper()
                                name = parts[2]
                                if mac not in discovered_devices:
                                    discovered_devices[mac] = name
                                    device_types[mac] = "PAIRED"
                                    self.logger.debug(f"Pre-loaded paired device: {name} ({mac})")
            except Exception as e:
                self.logger.debug(f"Error pre-loading paired devices: {e}")

            # Update _scan_results with cached devices
            with self._lock:
                for mac in discovered_devices:
                    self._scan_results[mac] = {
                        "mac": mac,
                        "name": discovered_devices[mac]
                    }

            lines_read = 0
            try:
                # Ensure Bluetooth is powered on
                self.logger.debug("Ensuring Bluetooth is powered on...")
                self._run_cmd(
                    ["bluetoothctl", "power", "on"],
                    timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                )
                time.sleep(self.OPERATION_SHORT_DELAY)

                self.logger.debug("Starting bluetoothctl in interactive mode...")
                scan_start = time.time()
                scan_process = None
                try:
                    env = dict(os.environ)
                    env["TERM"] = "dumb"
                    scan_process = subprocess.Popen(
                        ["bluetoothctl"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        env=env,
                    )
                    # Send scan on command to start scanning
                    scan_process.stdin.write("scan on\n")
                    scan_process.stdin.flush()
                except Exception as e:
                    self.logger.error(f"Failed to start scan: {e}")
                    scan_process = None

                if scan_process:
                    self.logger.debug(f"Scanning for {duration} seconds...")
                    self.logger.debug(f"Process started, PID: {scan_process.pid}")
                    scan_end_time = time.time() + duration
                    try:
                        while time.time() < scan_end_time:
                            try:
                                import select
                                ready = select.select(
                                    [scan_process.stdout], [], [], 0.5
                                )
                                if ready[0]:
                                    line = scan_process.stdout.readline()
                                    if not line:
                                        break
                                    line = line.strip()
                                    if not line:
                                        continue
                                    lines_read += 1
                                    # Strip ANSI codes for pattern matching
                                    clean_line = self.scan_ansi_pattern.sub("", line)
                                    # Parse discovery events: "[NEW] Device MAC Name"
                                    if "[NEW]" in clean_line and "Device" in clean_line:
                                        mac_match = self.scan_mac_pattern.search(clean_line)
                                        if mac_match:
                                            mac = mac_match.group(1).upper()
                                            remainder = clean_line[mac_match.end():].strip()
                                            name = remainder if remainder else "(unnamed)"
                                            if mac not in discovered_devices:
                                                discovered_devices[mac] = name
                                                device_types[mac] = "NEW"
                                                self.logger.info(f"[NEW] {name} ({mac})")
                                                # Update real-time list
                                                with self._lock:
                                                    self._scan_results[mac] = {
                                                        "mac": mac,
                                                        "name": name
                                                    }
                            except select.error:
                                pass
                    finally:
                        # Stop scan and close bluetoothctl
                        self.logger.debug("Stopping scan...")
                        try:
                            try:
                                self._run_cmd(
                                    ["bluetoothctl", "scan", "off"],
                                    timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
                                )
                            except Exception:
                                pass
                            time.sleep(self.SCAN_STOP_DELAY)
                            scan_process.stdin.write("quit\n")
                            scan_process.stdin.flush()
                            try:
                                scan_process.wait(timeout=self.SUBPROCESS_TIMEOUT_MEDIUM)
                                self.logger.info("Bluetoothctl process exited cleanly")
                            except subprocess.TimeoutExpired:
                                self.logger.info("Force killing bluetoothctl after timeout")
                                scan_process.kill()
                                scan_process.wait(timeout=self.SUBPROCESS_TIMEOUT_SHORT)
                        except Exception as e:
                            self.logger.debug(f"Error stopping scan: {e}")
                            try:
                                scan_process.kill()
                            except Exception:
                                pass

                    elapsed = time.time() - scan_start
                    self.logger.info(
                        f"Scan completed in {elapsed:.1f}s, found {len(discovered_devices)} device(s)"
                    )
            except Exception as e:
                self.logger.error(f"Error during scan: {e}")

            # Pick up any devices that were paired during the scan
            self.logger.debug("Checking for any newly paired devices...")
            try:
                paired_output = self._run_cmd(
                    ["bluetoothctl", "devices", "Paired"],
                    capture=True,
                    timeout=self.SUBPROCESS_TIMEOUT_STANDARD,
                )
                if paired_output and paired_output != "Timeout":
                    for line in paired_output.split("\n"):
                        if line.strip() and line.startswith("Device"):
                            parts = line.strip().split(" ", 2)
                            if len(parts) >= 3:
                                mac = parts[1].upper()
                                name = parts[2]
                                if mac not in discovered_devices:
                                    discovered_devices[mac] = name
                                    device_types[mac] = "PAIRED"
                                    with self._lock:
                                        self._scan_results[mac] = {
                                            "mac": mac,
                                            "name": name
                                        }
                                    self.logger.info(f"Found device paired during scan: {name} ({mac})")
            except Exception as e:
                self.logger.debug(f"Error checking for newly paired devices: {e}")

        except Exception as e:
            self.logger.error(f"Scan error: {e}")

        with self._lock:
            result = list(self._scan_results.values())
            self.logger.info(f"Scan complete: {len(result)} devices total")
            return result

    def get_trusted_devices(self):
        """Get list of trusted Bluetooth devices with NAP support info."""
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
                    # Single `info` call covers paired/trusted/connected + NAP UUID,
                    # avoiding a second identical bluetoothctl invocation per device.
                    info = self._run_cmd(
                        ["bluetoothctl", "info", mac],
                        capture=True,
                        timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
                    )
                    if not info:
                        continue
                    if "Trusted: yes" in info:
                        devices.append(BluetoothDevice(
                            mac, name,
                            paired="Paired: yes" in info,
                            trusted=True,
                            connected="Connected: yes" in info,
                            has_nap=BluetoothDevice.NAP_UUID in info,
                        ))

        return devices
