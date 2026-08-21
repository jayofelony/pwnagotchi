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
    # After this many consecutive br-connection-busy errors, the controller is
    # wedged and only a bluetooth restart clears it.
    RECOVER_BUSY_THRESHOLD = 3
    BLUETOOTH_RESTART_TIMEOUT = 15
    # `systemctl restart bluetooth` on a wedged controller can take well over 5s
    # (bluetoothd hangs on stop until systemd's stop timeout), so give it room.
    BLUETOOTH_RESTART_CMD_TIMEOUT = 30
    # Kernel transport module for the built-in Broadcom controller. Reloading it
    # re-downloads the BT firmware, which clears a wedge that survives both a
    # daemon restart and a full reboot. (Serial-attached combo chips: hci_uart.)
    BT_MODULE = "hci_uart"

    def __init__(self, logger=None, options=None):
        self.logger = logger or logging.getLogger(__name__)
        self.options = options or {}
        self.nap_connect_timeout = self.options.get("nap_connect_timeout", self.NAP_CONNECT_TIMEOUT)
        self._lock = threading.Lock()
        self.scan_mac_pattern = re.compile(r"([0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2})")
        self.scan_ansi_pattern = re.compile(r"(\x1b\[[0-9;]*m|\x08)")
        self._scan_results = {}  # Track scan results in real-time
        self._stop_scan = threading.Event()  # Signal an in-progress scan to end early
        self.current_passkey = None  # Last passkey shown during pairing (for UI)
        self.pairing_agent = None  # Set by BluetoothService; auto-confirms passkeys
        self._consecutive_busy = 0  # Consecutive br-connection-busy errors (wedge detector)

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

    def force_restart_bluetooth(self):
        """Force-restart bluetooth to clear a wedged/busy controller, then wait
        for it to become responsive.

        Unlike restart_if_needed(), this restarts even when the service is
        'responsive' but stuck rejecting connects with br-connection-busy - the
        only thing that reliably clears that state.
        """
        self.logger.warning("Restarting Bluetooth to clear a stuck (br-connection-busy) state")
        try:
            subprocess.run(
                ["systemctl", "restart", "bluetooth"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.BLUETOOTH_RESTART_CMD_TIMEOUT,
            )
        except Exception as e:
            # A restart that can't even complete means the controller is badly
            # wedged - only a power-cycle will clear it. Signal that to the caller.
            self.logger.warning(f"Failed to restart bluetooth: {e}")
            return False

        deadline = time.time() + self.BLUETOOTH_RESTART_TIMEOUT
        while time.time() < deadline:
            time.sleep(1)
            if self.is_responsive():
                self._run_cmd(["bluetoothctl", "power", "on"], capture=True, timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
                self._consecutive_busy = 0
                self.logger.info("Bluetooth restarted and responsive")
                return True
        self.logger.warning("Bluetooth still not responsive after restart")
        return False

    def reload_bt_module(self):
        """Reload the Bluetooth transport module to force a firmware re-download.

        The rung between a daemon restart and a full reboot: on combo WiFi+BT
        chips the controller firmware can wedge (HCI commands time out - the
        kernel logs 'command tx timeout' / opcode failures with -110) in a way
        that survives both 'systemctl restart bluetooth' AND a reboot, yet is
        cleared by unloading and reloading the module. Runs as root (pwnagotchi
        already runs as root, so no sudo); returns True if the controller comes
        back responsive.
        """
        self.logger.warning(f"Reloading Bluetooth module ({self.BT_MODULE}) to reset a wedged controller")
        try:
            subprocess.run(
                ["modprobe", "-r", self.BT_MODULE],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.BLUETOOTH_RESTART_CMD_TIMEOUT,
            )
            time.sleep(self.SUBPROCESS_TIMEOUT_MEDIUM)
            subprocess.run(
                ["modprobe", self.BT_MODULE],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.BLUETOOTH_RESTART_CMD_TIMEOUT,
            )
            time.sleep(self.SUBPROCESS_TIMEOUT_NORMAL)
            subprocess.run(
                ["systemctl", "restart", "bluetooth"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.BLUETOOTH_RESTART_CMD_TIMEOUT,
            )
        except Exception as e:
            self.logger.warning(f"Bluetooth module reload failed: {e}")
            return False

        deadline = time.time() + self.BLUETOOTH_RESTART_TIMEOUT
        while time.time() < deadline:
            time.sleep(1)
            if self.is_responsive():
                self._run_cmd(["bluetoothctl", "power", "on"], capture=True, timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
                self._consecutive_busy = 0
                self.logger.info("Bluetooth module reloaded and controller responsive")
                return True
        self.logger.warning("Bluetooth still not responsive after module reload")
        return False

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

        The ConnectProfile call is bounded by its own dbus method timeout, so an
        off/out-of-range phone raises NoReply after nap_connect_timeout instead of
        blocking for the full ~30s BlueZ page-timeout. The call is synchronous so a
        retry never overlaps a still-pending attempt (which would hit
        br-connection-busy). Any stale half-open ACL is cleared first.
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

            try:
                device.ConnectProfile(NAP_UUID, timeout=self.nap_connect_timeout)
                self.logger.info("✓ NAP profile connected successfully via DBus")
                self._consecutive_busy = 0
                return True
            except DBusException as dbus_err:
                error_msg = str(dbus_err)
                self.logger.error(f"DBus NAP connection failed: {error_msg}")
                # Track a wedged controller: repeated br-connection-busy means BlueZ
                # thinks a connect is still pending and only a restart clears it.
                if "br-connection-busy" in error_msg or "InProgress" in error_msg:
                    self._consecutive_busy += 1
                else:
                    self._consecutive_busy = 0
                self._diagnose_nap_error(mac, error_msg)
                return False

        except Exception as e:
            self.logger.error(f"NAP connection error: {type(e).__name__}: {e}")
            return False

    def _ensure_device_visible(self, mac):
        """Make sure BlueZ knows about <mac>, scanning briefly if it doesn't.

        BlueZ refuses to pair a device it has not seen in the current session
        ("Device ... not available"). If the device isn't already cached, open an
        interactive bluetoothctl scan and wait for the "[NEW] Device <mac>" event
        (up to PAIRING_SCAN_WAIT_TIMEOUT). Returns True once visible.
        """
        target = mac.upper()

        # Already known (freshly scanned or cached device shows up here)?
        known = self._run_cmd(
            ["bluetoothctl", "devices"],
            capture=True,
            timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
        )
        if known and known != "Timeout" and target in known.upper():
            return True

        # Or already bonded/known to BlueZ (info returns real properties even when
        # the device isn't in the plain `devices` listing)?
        info = self._run_cmd(
            ["bluetoothctl", "info", mac],
            capture=True,
            timeout=self.SUBPROCESS_TIMEOUT_NORMAL,
        )
        if info and info != "Timeout" and ("Paired:" in info or "Trusted:" in info):
            return True

        self.logger.info(f"Discovering {mac} before pairing (up to {self.PAIRING_SCAN_WAIT_TIMEOUT}s)...")
        import select

        scan_process = None
        try:
            env = dict(os.environ, TERM="dumb", NO_COLOR="1")
            scan_process = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
            scan_process.stdin.write("scan on\n")
            scan_process.stdin.flush()

            deadline = time.time() + self.PAIRING_SCAN_WAIT_TIMEOUT
            while time.time() < deadline:
                ready = select.select([scan_process.stdout], [], [], 0.5)
                if ready[0]:
                    line = scan_process.stdout.readline()
                    if not line:
                        break
                    clean_line = self.scan_ansi_pattern.sub("", line.strip())
                    if "[NEW]" in clean_line and "Device" in clean_line:
                        m = self.scan_mac_pattern.search(clean_line)
                        if m and m.group(1).upper() == target:
                            self.logger.info(f"Device {mac} discovered")
                            return True
            return False
        except Exception as e:
            self.logger.debug(f"Discovery error: {e}")
            return False
        finally:
            try:
                self._run_cmd(["bluetoothctl", "scan", "off"], capture=True, timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
                time.sleep(self.SCAN_STOP_DELAY)
            except Exception:
                pass
            if scan_process:
                try:
                    scan_process.stdin.write("quit\n")
                    scan_process.stdin.flush()
                    scan_process.wait(timeout=self.SUBPROCESS_TIMEOUT_MEDIUM)
                except Exception:
                    try:
                        scan_process.kill()
                        scan_process.wait(timeout=self.SUBPROCESS_TIMEOUT_SHORT)
                    except Exception:
                        pass

    def pair_interactive(self, mac, name=""):
        """Pair with device: discover it first, then pair via the persistent agent.

        The persistent KeyboardDisplay agent handles the dialog - the Pi displays
        the passkey and the phone confirms - so no interactive input is needed
        here. We ensure the device is visible to BlueZ first, otherwise `pair`
        fails immediately with "Device not available".
        """
        try:
            self.logger.info(f"Starting pairing with {mac}...")

            # Ensure Bluetooth is powered on and in pairable mode
            self._run_cmd(["bluetoothctl", "power", "on"], capture=True)
            time.sleep(self.DEVICE_OPERATION_DELAY)
            self._run_cmd(["bluetoothctl", "pairable", "on"], capture=True)
            self._run_cmd(["bluetoothctl", "discoverable", "on"], capture=True)
            time.sleep(self.DEVICE_OPERATION_DELAY)

            # Clear a block and any stale/partial bond so a fresh pair can succeed.
            # A device that is known to BlueZ but "Paired: no" (e.g. the phone
            # forgot us, or a prior bond went half-formed) otherwise fails with
            # authentication error 0x05 and can't self-recover.
            self._run_cmd(["bluetoothctl", "unblock", mac], capture=True, timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
            info = self._run_cmd(["bluetoothctl", "info", mac], capture=True, timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
            if info and info != "Timeout" and "Paired: no" in info:
                self.logger.info(f"Removing stale bond for {mac} before pairing")
                self._run_cmd(["bluetoothctl", "remove", mac], capture=True, timeout=self.SUBPROCESS_TIMEOUT_LONG)
                time.sleep(self.DEVICE_OPERATION_DELAY)

            # BlueZ won't pair a device it hasn't seen this session - discover first
            if not self._ensure_device_visible(mac):
                self.logger.warning(f"Device {mac} not seen during discovery - attempting pair anyway")

            self.logger.info(f"Running: bluetoothctl pair {mac}")
            self.logger.info("⚠️  A pairing dialog will appear on your phone - confirm the passkey!")

            # Numeric-comparison pairing needs the Pi side to confirm the passkey.
            # The persistent agent tails its log and answers 'yes' automatically.
            stop_confirm = threading.Event()
            if self.pairing_agent is not None:
                threading.Thread(
                    target=self.pairing_agent.watch_and_confirm,
                    args=(stop_confirm, self.PAIRING_PASSKEY_TIMEOUT),
                    daemon=True,
                ).start()

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

            output_lines = []
            passkey_seen = False
            try:
                # Read output in real time so we can surface the passkey immediately
                while True:
                    line = process.stdout.readline()
                    if not line:
                        break
                    output_lines.append(line)
                    clean_line = self._strip_ansi_codes(line.strip())
                    if not passkey_seen:
                        m = re.search(r"passkey\s+(\d{6})", clean_line, re.IGNORECASE)
                        if m:
                            passkey_seen = True
                            self.current_passkey = m.group(1)
                            self.logger.warning(f"🔑 PASSKEY: {self.current_passkey} - confirm on phone!")

                returncode = process.wait(timeout=self.PAIRING_PASSKEY_TIMEOUT)
            except subprocess.TimeoutExpired:
                self.logger.error(
                    f"Pairing timeout ({self.PAIRING_PASSKEY_TIMEOUT}s) - phone didn't confirm the passkey"
                )
                return False
            finally:
                stop_confirm.set()
                try:
                    if process.stdout:
                        process.stdout.close()
                except Exception:
                    pass
                try:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=self.SUBPROCESS_TIMEOUT_MEDIUM)
                except Exception:
                    pass

            clean_output = self._strip_ansi_codes("".join(output_lines))

            if "Pairing successful" in clean_output or "AlreadyExists" in clean_output:
                self.logger.info(f"✓ Pairing successful for {mac}")
                self.current_passkey = None
                return True

            if returncode == 0:
                # Command returned success but output was unclear - confirm via status
                time.sleep(self.DEVICE_OPERATION_LONGER_DELAY)
                status = self.get_status(mac)
                if status and status.get("paired"):
                    self.logger.info(f"✓ Pairing confirmed for {mac}")
                    self.current_passkey = None
                    return True

            # Diagnose the failure
            if "Authentication failed" in clean_output or "0x05" in clean_output:
                self.logger.error(
                    "Pairing failed - forget/unpair this device on your phone first, then retry "
                    "(0x05 = phone has stale cached credentials)"
                )
            elif "Connection refused" in clean_output:
                self.logger.error("Pairing failed - ensure the phone's Bluetooth is on and discoverable")
            elif not passkey_seen:
                self.logger.error(f"Pairing failed - no passkey appeared: {clean_output[:200]}")
            else:
                self.logger.error(f"Pairing failed - passkey {self.current_passkey} not confirmed on phone")
            return False

        except Exception as e:
            self.logger.error(f"Pair error: {e}")
            return False

    def trust_device(self, mac):
        """Mark device as trusted."""
        self._run_cmd(["bluetoothctl", "trust", mac], timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
        time.sleep(self.DEVICE_OPERATION_DELAY)

    def set_device_name(self, name):
        """Set the *controller* alias so the phone shows the pwnagotchi's name.

        Uses `system-alias` (controller) - NOT `set-alias`, which sets the alias of
        the selected *remote* device and would rename the phone in BlueZ.
        """
        try:
            self._run_cmd(["bluetoothctl", "system-alias", name], capture=True, timeout=self.SUBPROCESS_TIMEOUT_NORMAL)
            self.logger.info(f"Set Bluetooth controller name to: {name}")
        except Exception as e:
            self.logger.debug(f"Failed to set device name: {e}")

    def scan(self, duration=30):
        """Scan for Bluetooth devices using an interactive bluetoothctl session."""
        try:
            self.logger.debug("Starting device scan...")
            self._scan_results = {}
            self._stop_scan.clear()
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
                        while time.time() < scan_end_time and not self._stop_scan.is_set():
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

    def stop_scan(self):
        """Signal an in-progress background scan to end early (e.g. before pairing)."""
        self._stop_scan.set()
        # Also stop discovery at the BlueZ level so it can't collide with pairing
        self._run_cmd(["bluetoothctl", "scan", "off"], capture=True, timeout=self.SUBPROCESS_TIMEOUT_NORMAL)

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
