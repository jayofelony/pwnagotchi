"""Pwnagotchi Bluetooth service - core module for Bluetooth operations."""

import logging
import threading
import time
import os
import subprocess
from .device import BluetoothDevice
from .connection import ConnectionManager
from .network import NetworkManager
from .agent import PairingAgent
from .monitor import ConnectionMonitor
from .ui import UIRenderer


class BluetoothService:
    """Main facade for Bluetooth operations."""

    # State constants
    STATE_IDLE = "IDLE"
    STATE_INITIALIZING = "INITIALIZING"
    STATE_SCANNING = "SCANNING"
    STATE_PAIRING = "PAIRING"
    STATE_TRUSTING = "TRUSTING"
    STATE_CONNECTING = "CONNECTING"
    STATE_CONNECTED = "CONNECTED"
    STATE_RECONNECTING = "RECONNECTING"
    STATE_DISCONNECTING = "DISCONNECTING"
    STATE_DISCONNECTED = "DISCONNECTED"
    STATE_ERROR = "ERROR"

    # Bluetooth timing constants
    BLUETOOTH_SERVICE_STARTUP_DELAY = 3
    # Don't restart the stack more than once per this window (avoid restart loops)
    RECOVER_MIN_INTERVAL = 120
    # Don't auto-reboot for a stuck controller more than once per this window
    STUCK_REBOOT_MIN_INTERVAL = 1800
    # Persisted last-reboot timestamp (survives the reboot to break loops)
    REBOOT_STAMP = "/root/.bt-tether-last-reboot"
    # Don't reload the BT kernel module more than once per this window. Kept well
    # below the reboot cadence: on combo chips the reload clears the wedge (a
    # reboot often doesn't), so it should get first crack on every recurrence.
    BT_MODULE_RELOAD_MIN_INTERVAL = 120

    def __init__(self, options=None, logger=None):
        self.options = options or {}
        self.logger = logger or logging.getLogger(__name__)

        # Initialize components
        self.connection = ConnectionManager(logger=self.logger, options=self.options)
        self.network = NetworkManager(logger=self.logger, options=self.options)
        self.agent = PairingAgent(logger=self.logger)
        # Let the connection manager auto-confirm passkeys via the persistent agent
        self.connection.pairing_agent = self.agent
        self.monitor = ConnectionMonitor(self.connection, logger=self.logger, options=self.options)
        # Let the monitor reconnect using the full connect flow (NAP + DHCP + verify)
        self.monitor.reconnect_callback = self.connect
        # Give the monitor the network layer so its half-open watchdog can probe
        # whether the phone is actually reachable over the PAN, and the recovery
        # ladder so a watchdog heal shares the rate limit and agent handling.
        self.monitor.network = self.network
        self.monitor.heal_callback = self._heal_bluetooth
        self.ui_renderer = UIRenderer()

        # State
        self._lock = threading.Lock()
        self._status = self.STATE_IDLE
        self._message = "Ready"
        self._initialized = False
        self._event_handlers = {}
        self._last_recover_time = 0
        self._last_module_reload_time = 0
        # Wedged-controller ("stuck") tracking: set only when a bluetooth restart
        # did NOT clear the busy state (distinct from "phone tethering off").
        self._bt_stuck = False
        # True while the recovery ladder is actively resetting Bluetooth, so the
        # display can say "Recovering..." instead of a confusing Paired/Connected.
        self._recovering = False
        self._connected_since_boot = False

        # Scan state tracking
        self._scanning = False
        self._scan_devices = []
        self._scan_start_time = None

    def start(self):
        """Initialize and start the Bluetooth service."""
        try:
            with self._lock:
                if self._initialized:
                    self.logger.info("Bluetooth service already initialized")
                    return True
                self._status = self.STATE_INITIALIZING
                self._message = "Starting Bluetooth service..."

            self.logger.info("Starting Bluetooth service...")

            # Start pairing agent
            if not self.agent.start():
                self.logger.warning("Failed to start pairing agent")

            # Verify Bluetooth is responsive
            if not self.connection.is_responsive():
                self.logger.warning("Bluetooth not responsive, attempting restart...")
                self.connection.restart_if_needed()
                time.sleep(self.BLUETOOTH_SERVICE_STARTUP_DELAY)

            # Advertise the pwnagotchi's name so it's identifiable when pairing
            try:
                import pwnagotchi
                self.connection.set_device_name(pwnagotchi.name())
            except Exception as e:
                self.logger.debug(f"Could not set device name: {e}")

            # Make sure loopback routing is intact for bettercap's localhost API
            self.network.verify_localhost()

            # Start monitoring if auto-reconnect enabled
            if self.options.get("auto_reconnect", True):
                self.monitor.start()

            with self._lock:
                self._initialized = True
                self._status = self.STATE_IDLE
                self._message = "Ready"

            self.logger.info("Bluetooth service initialized")
            self._emit_event("bt:service_ready", {})
            return True

        except Exception as e:
            self.logger.error(f"Failed to start Bluetooth service: {e}")
            with self._lock:
                self._status = self.STATE_ERROR
                self._message = f"Initialization failed: {e}"
            return False

    def stop(self):
        """Stop the Bluetooth service and cleanup."""
        try:
            self.logger.info("Stopping Bluetooth service...")
            self.monitor.stop()
            self.agent.stop()
            with self._lock:
                self._initialized = False
                self._status = self.STATE_IDLE
            self.logger.info("Bluetooth service stopped")
        except Exception as e:
            self.logger.error(f"Error stopping service: {e}")

    def get_status(self, mac):
        """Get connection status for a device."""
        return self.connection.get_full_status(mac)

    def get_trusted_devices(self):
        """Get list of trusted devices."""
        return self.connection.get_trusted_devices()

    def find_best_device(self, prefer_mac=None):
        """Find the best device to connect to."""
        devices = self.get_trusted_devices()
        if prefer_mac:
            for device in devices:
                if device.mac == prefer_mac:
                    return device
        return devices[0] if devices else None

    def scan_devices(self, duration=30):
        """Scan for Bluetooth devices and track progress."""
        with self._lock:
            self._status = self.STATE_SCANNING
            self._message = f"Scanning for {duration}s..."
            self._scanning = True
            self._scan_devices = []
            self._scan_start_time = time.time()

        try:
            devices = self.connection.scan(duration)

            # Merge final results with what we've collected
            with self._lock:
                self._scan_devices = devices if devices else self.connection.get_scan_results()
                self._scanning = False
                self._status = self.STATE_IDLE

            self._emit_event("bt:scan_complete", {"devices": self._scan_devices})
            return self._scan_devices
        except Exception as e:
            self.logger.error(f"Scan failed: {e}")
            with self._lock:
                self._scanning = False
                self._status = self.STATE_ERROR
                self._message = f"Scan failed: {e}"
            return []

    def get_scan_progress(self):
        """Get current scan progress and discovered devices."""
        with self._lock:
            # During active scan, also check connection's real-time results
            scan_devices = self._scan_devices.copy()
            if self._scanning:
                # Merge with real-time results from connection
                real_time_devices = self.connection.get_scan_results()
                if real_time_devices:
                    scan_devices = real_time_devices

            return {
                "scanning": self._scanning,
                "devices": scan_devices,
                "elapsed": time.time() - self._scan_start_time if self._scan_start_time else 0,
            }

    def connect(self, mac, name=""):
        """Initiate full connection to a device with pairing, trusting, NAP, and PAN setup."""
        if not BluetoothDevice.validate_mac(mac):
            self.logger.error(f"Invalid MAC: {mac}")
            return False

        # Stop any ongoing background scan so it can't collide with pairing/connect
        self.connection.stop_scan()

        with self._lock:
            if self._status in (self.STATE_PAIRING, self.STATE_TRUSTING, self.STATE_CONNECTING):
                self.logger.warning(f"Connection already in progress ({self._status}), ignoring request for {mac}")
                return False
            self._scanning = False
            self._status = self.STATE_CONNECTING
            self._message = f"Connecting to {name or mac}..."

        def connect_thread():
            try:
                self.logger.info(f"Starting connection to {name} ({mac})...")

                # Check if Bluetooth is responsive
                if not self.connection.is_responsive():
                    self.logger.warning("Bluetooth not responsive, attempting restart...")
                    self.connection.restart_if_needed()
                    time.sleep(3)

                # Make Pwnagotchi discoverable and pairable
                self.logger.info("Making Pwnagotchi discoverable...")
                with self._lock:
                    self._message = f"Making Pwnagotchi discoverable for {name}..."
                self.connection._run_cmd(["bluetoothctl", "discoverable", "on"], capture=True)
                self.connection._run_cmd(["bluetoothctl", "pairable", "on"], capture=True)
                time.sleep(2)

                # Check current pairing status
                with self._lock:
                    self._message = f"Checking pairing status with {name}..."

                status = self.connection.get_status(mac)

                # If device is not paired, pair first
                if not status or not status.get("paired"):
                    self.logger.info(f"Device not paired. Starting pairing process with {name}...")
                    with self._lock:
                        self._status = self.STATE_PAIRING
                        self._message = f"Pairing with {name}..."

                    time.sleep(0.5)

                    # Attempt pairing
                    if not self.connection.pair_interactive(mac, name):
                        self.logger.error(f"Pairing with {name} failed!")
                        with self._lock:
                            self._status = self.STATE_ERROR
                            self._message = f"Pairing with {name} failed. Did you accept the dialog?"
                        self._emit_event("bt:connect_failed", {"mac": mac, "error": "Pairing failed"})
                        return False

                    self.logger.info(f"Pairing with {name} successful!")
                else:
                    self.logger.info(f"Device {name} already paired")
                    with self._lock:
                        self._message = f"Device {name} already paired ✓"

                # Trust the device
                self.logger.info(f"Trusting device {name}...")
                with self._lock:
                    self._status = self.STATE_TRUSTING
                    self._message = f"Trusting {name}..."
                time.sleep(0.5)
                self.connection.trust_device(mac)

                # Wait for NAP UUID to appear
                NAP_UUID = "00001116"
                NAP_WAIT_TIMEOUT = 15
                self.logger.info(f"Waiting for {name} NAP service to be ready...")
                with self._lock:
                    self._message = f"Waiting for {name} to be ready..."

                nap_ready = False
                nap_wait_start = time.time()
                while time.time() - nap_wait_start < NAP_WAIT_TIMEOUT:
                    info = self.connection._run_cmd(
                        ["bluetoothctl", "info", mac],
                        capture=True,
                        timeout=3,
                    )
                    if info and NAP_UUID in info:
                        elapsed = time.time() - nap_wait_start
                        self.logger.info(f"NAP service ready after {elapsed:.1f}s")
                        nap_ready = True
                        break
                    time.sleep(1)

                if not nap_ready:
                    self.logger.warning(f"NAP UUID not seen after {NAP_WAIT_TIMEOUT}s - proceeding anyway")

                # If the link is already up, skip the NAP connect. The BT connection
                # survives a pwnagotchi restart, so re-running ConnectProfile on a
                # live link just returns br-connection-busy - which would needlessly
                # trigger the self-heal (bluetooth restart), recreate bnep0, and break
                # consumers bound to it (e.g. pwn-companion's discovery socket).
                nap_connected = False
                pre_status = self.connection.get_full_status(mac)
                if pre_status and pre_status.get("connected") and pre_status.get("pan_active"):
                    self.logger.info("Device already connected with active PAN - skipping NAP connect")
                    nap_connected = True
                else:
                    # Connect to NAP profile
                    self.logger.info("Connecting to NAP profile...")
                    with self._lock:
                        self._status = self.STATE_CONNECTING
                        self._message = "Connecting to NAP profile for internet..."
                    time.sleep(0.5)

                    # Try NAP connection with retries
                    for retry in range(3):
                        if retry > 0:
                            self.logger.info(f"Retrying NAP connection (attempt {retry + 1}/3)...")
                            with self._lock:
                                self._message = f"NAP retry {retry + 1}/3..."
                            time.sleep(3)

                        nap_connected = self.connection.connect_nap(mac)
                        if nap_connected:
                            break
                        else:
                            self.logger.warning(f"NAP attempt {retry + 1} failed")
                            with self._lock:
                                self._message = f"NAP attempt {retry + 1}/3 failed..."
                            # Self-heal a wedged controller: after repeated
                            # br-connection-busy, restart Bluetooth + agent and retry once.
                            if self.connection._consecutive_busy >= self.connection.RECOVER_BUSY_THRESHOLD:
                                with self._lock:
                                    self._message = "Bluetooth busy - recovering..."
                                outcome = self._recover_bluetooth()
                                if outcome == "recovered":
                                    nap_connected = self.connection.connect_nap(mac)
                                    if nap_connected:
                                        break
                                    # A restart completed but the connect still fails
                                    # -> wedged in a way only a power-cycle clears.
                                    self._handle_bt_stuck()
                                    break
                                elif outcome == "failed":
                                    # The restart itself couldn't complete (e.g. bluetooth
                                    # hung on stop) - the controller is badly wedged, so
                                    # escalate straight to the power-cycle path.
                                    self._handle_bt_stuck()
                                    break
                                # "rate_limited": restarted very recently - don't hammer
                                # or reboot-loop; let the monitor's backoff retry later.
                                break

                if nap_connected:
                    self.logger.info("NAP connection successful!")

                    # Poll for the PAN interface - the kernel creates it a moment
                    # after NAP connects, so a single immediate check can miss it.
                    iface = self.network.wait_for_pan_interface(timeout=6)
                    if iface:
                        self.logger.info(f"✓ PAN interface active: {iface}")

                        # Request a DHCP lease
                        self.logger.info(f"Setting up {iface} for DHCP...")
                        if self.network.setup_dhcp(iface):
                            self.logger.info("✓ Network setup successful")
                        else:
                            self.logger.warning("Network setup may have failed, continuing...")

                        # Poll for the lease (IPv4 or global IPv6) instead of sleeping blindly
                        self.network.wait_for_interface_ip(iface, timeout=8)

                        # A PAN/DHCP route can shadow loopback - keep bettercap's
                        # localhost API reachable by repairing the lo route.
                        self.network.verify_localhost()

                        # Verify internet connectivity
                        self.logger.info("Checking internet connectivity...")
                        with self._lock:
                            self._message = "Verifying internet connection..."

                        if self.network.check_internet_connectivity():
                            self.logger.info("✓ Internet connectivity verified!")

                            # Get current IP
                            ip = self.network.get_current_ip()
                            if ip:
                                self.logger.info(f"Current IP address: {ip}")

                            with self._lock:
                                self._status = self.STATE_CONNECTED
                                self._message = f"✓ Connected! Internet via {iface}"
                                self._bt_stuck = False
                                self._connected_since_boot = True

                            self.monitor.set_device(mac)
                            self._emit_event("bt:connect_success", {
                                "mac": mac,
                                "name": name,
                                "ip": ip,
                                "ipv6": self.network.get_global_ipv6(iface),
                                "interface": iface,
                            })
                            return True
                        else:
                            self.logger.warning("No internet connectivity detected")
                            # Still report as connected if we have an IP
                            ip = self.network.get_current_ip()
                            if ip:
                                self.logger.info(f"Connected via {iface} but no internet access")
                                with self._lock:
                                    self._status = self.STATE_CONNECTED
                                    self._message = f"Connected via {iface} but no internet access"
                                    self._bt_stuck = False
                                    self._connected_since_boot = True

                                self.monitor.set_device(mac)
                                self._emit_event("bt:connect_success", {
                                    "mac": mac,
                                    "name": name,
                                    "ip": ip,
                                    "interface": iface,
                                })
                                return True
                    else:
                        self.logger.warning("NAP connected but no interface detected")

                # If we got here, connection partially succeeded or failed
                with self._lock:
                    self._status = self.STATE_CONNECTED
                    self._message = "Bluetooth connected but tethering setup incomplete"
                self._emit_event("bt:connect_failed", {
                    "mac": mac,
                    "error": "NAP/PAN setup incomplete - enable tethering on phone"
                })
                return False

            except Exception as e:
                self.logger.error(f"Connection thread error: {e}")
                with self._lock:
                    self._status = self.STATE_ERROR
                    self._message = f"Connection error: {str(e)}"
                self._emit_event("bt:connect_failed", {"mac": mac, "error": str(e)})
                return False

        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()
        return True

    def _heal_bluetooth(self, reason):
        """Watchdog entry point into the recovery ladder: restart the stack and,
        if that doesn't clear the wedge, escalate through the stuck path (module
        reload -> opt-in reboot). Shares _recover_bluetooth's rate limit."""
        outcome = self._recover_bluetooth(reason)
        if outcome == "failed":
            self._handle_bt_stuck()
        return outcome

    def _recover_bluetooth(self, reason="repeated br-connection-busy"):
        """Clear a wedged controller: restart the Bluetooth stack and re-register
        the pairing agent.

        Rate-limited so a persistent fault can't turn into a restart loop. Returns
        one of: "recovered" (restart completed, controller responsive),
        "failed" (restart couldn't complete - controller badly wedged, only a
        power-cycle will clear it), or "rate_limited" (restarted too recently).
        """
        now = time.time()
        if now - self._last_recover_time < self.RECOVER_MIN_INTERVAL:
            return "rate_limited"
        self._last_recover_time = now

        self.logger.warning(f"Recovering the Bluetooth stack ({reason})")
        with self._lock:
            self._recovering = True
        try:
            try:
                self.agent.stop()
            except Exception as e:
                self.logger.debug(f"Agent stop during recovery failed: {e}")

            ok = self.connection.force_restart_bluetooth()

            # The restart drops the agent's bluetoothctl session - bring it back up
            try:
                self.agent.start()
            except Exception as e:
                self.logger.debug(f"Agent restart during recovery failed: {e}")
            try:
                import pwnagotchi
                self.connection.set_device_name(pwnagotchi.name())
            except Exception:
                pass
            return "recovered" if ok else "failed"
        finally:
            with self._lock:
                self._recovering = False

    def _handle_bt_stuck(self):
        """A bluetooth daemon restart did NOT clear the busy wedge. Escalate:
        first try reloading the BT kernel module (re-downloads the firmware, which
        clears wedges that survive both a restart AND a reboot); only if that fails
        flag the controller stuck (surfaced on screen/web and in /status) and, if
        opted in, reboot as the true last resort.
        """
        # Rung 2: module reload. Rate-limited so a persistent fault can't turn into
        # a reload loop.
        now = time.time()
        if now - self._last_module_reload_time < self.BT_MODULE_RELOAD_MIN_INTERVAL:
            # We reloaded very recently and it wedged again. A reboot doesn't clear
            # this wedge on combo chips (the module reload does), so don't reboot on
            # a fresh recurrence - flag it and let the next cycle retry the reload
            # once the window opens, rather than reboot-looping.
            with self._lock:
                self._bt_stuck = True
                self._message = "Bluetooth wedged - will retry module reload"
            self.logger.warning("Controller wedged again shortly after a module reload - waiting to retry (not rebooting)")
            self._emit_event("bt:stuck", {})
            return

        self._last_module_reload_time = now
        with self._lock:
            self._recovering = True
            self._message = "Bluetooth wedged - reloading module..."
        # The reload restarts bluetooth, dropping the agent's bluetoothctl
        # session - stop it first, bring it back after.
        try:
            try:
                self.agent.stop()
            except Exception as e:
                self.logger.debug(f"Agent stop during module reload failed: {e}")

            recovered = self.connection.reload_bt_module()

            try:
                self.agent.start()
                import pwnagotchi
                self.connection.set_device_name(pwnagotchi.name())
            except Exception as e:
                self.logger.debug(f"Agent/name restore after module reload failed: {e}")
        finally:
            with self._lock:
                self._recovering = False

        if recovered:
            with self._lock:
                self._bt_stuck = False
                self._message = "Bluetooth recovered (module reload)"
            self.logger.info("Controller recovered via module reload - link will re-establish")
            self._emit_event("bt:recovered", {"method": "module_reload"})
            return

        # Rung 3: the module reload actually RAN and FAILED - genuinely wedged.
        with self._lock:
            self._bt_stuck = True
            self._message = "Bluetooth stuck - power-cycle the Pi"
        self.logger.error("Bluetooth controller stuck - module reload didn't clear it, a power-cycle is needed")
        self._emit_event("bt:stuck", {})

        if self.options.get("reboot_on_stuck_bluetooth", False):
            self._maybe_reboot_for_stuck()

    def _maybe_reboot_for_stuck(self):
        """Reboot to clear a truly wedged controller, guarded against reboot loops:
        only if we actually connected since boot (so a phone that's simply off can't
        loop-reboot the Pi) and at most once per STUCK_REBOOT_MIN_INTERVAL. The
        last-reboot time is persisted to disk so the guard survives the reboot.
        """
        if not self._connected_since_boot:
            self.logger.warning("Controller stuck, but never connected since boot - not rebooting")
            return

        # Persisted guard: a bluetooth restart doesn't clear this wedge on some
        # combo chips - only a power-cycle does - so the timestamp must outlive the
        # reboot to prevent a boot loop.
        try:
            if os.path.exists(self.REBOOT_STAMP):
                age = time.time() - os.path.getmtime(self.REBOOT_STAMP)
                if age < self.STUCK_REBOOT_MIN_INTERVAL:
                    self.logger.warning(
                        f"Controller stuck, but rebooted {int(age)}s ago - not rebooting again yet"
                    )
                    return
        except Exception as e:
            self.logger.debug(f"Could not read reboot stamp: {e}")

        try:
            with open(self.REBOOT_STAMP, "w") as f:
                f.write(str(int(time.time())))
        except Exception as e:
            self.logger.debug(f"Could not write reboot stamp: {e}")

        self.logger.warning("reboot_on_stuck_bluetooth enabled - rebooting to power-cycle the controller")
        try:
            subprocess.run(["systemctl", "reboot"], timeout=10)
        except Exception as e:
            self.logger.error(f"Reboot command failed: {e}")

    @property
    def bt_stuck(self):
        with self._lock:
            return self._bt_stuck

    @property
    def bt_recovering(self):
        with self._lock:
            return self._recovering

    def disconnect(self, mac):
        """Disconnect from a device."""
        with self._lock:
            self._status = self.STATE_DISCONNECTING
            self._message = f"Disconnecting {mac}..."

        try:
            # Stop the monitor from watching this device BEFORE teardown so it
            # can't race a reconnect during the disconnect/unpair window.
            self.monitor.clear_device()
            self.connection.disconnect(mac)
            time.sleep(0.5)
            self.connection.unpair(mac)
            with self._lock:
                self._status = self.STATE_DISCONNECTED
            self._emit_event("bt:disconnect_success", {"mac": mac, "reason": "user_request"})
            return True
        except Exception as e:
            self.logger.error(f"Disconnect failed: {e}")
            with self._lock:
                self._status = self.STATE_ERROR
            return False

    def unpair(self, mac):
        """Remove pairing with a device."""
        try:
            self.connection.unpair(mac)
            self._emit_event("bt:unpair_success", {"mac": mac})
            return True
        except Exception as e:
            self.logger.error(f"Unpair failed: {e}")
            return False

    def on_event(self, event_name, callback):
        """Register an event handler."""
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(callback)

    def _emit_event(self, event_name, data):
        """Emit an event to registered handlers."""
        handlers = self._event_handlers.get(event_name, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                self.logger.debug(f"Event handler error for {event_name}: {e}")

    # Public constants and utilities
    @property
    def status(self):
        with self._lock:
            return self._status

    @property
    def message(self):
        with self._lock:
            return self._message

    @property
    def initialized(self):
        with self._lock:
            return self._initialized


# Export public API
__all__ = [
    "BluetoothService",
    "BluetoothDevice",
    "ConnectionManager",
    "NetworkManager",
    "UIRenderer",
]
