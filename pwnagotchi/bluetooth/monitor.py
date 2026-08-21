import threading
import time
import logging
from .connection import ConnectionManager
from .device import BluetoothDevice


class ConnectionMonitor:
    """Monitors connection status and handles auto-reconnect."""

    # Reconnect configuration
    DEFAULT_RECONNECT_INTERVAL = 60
    DEFAULT_RECONNECT_FAST_INTERVAL = 15
    RECONNECT_FAST_CYCLES = 6
    MAX_RECONNECT_FAILURES = 5
    DEFAULT_RECONNECT_FAILURE_COOLDOWN = 300
    MONITOR_INITIAL_DELAY = 5
    MONITOR_PAUSED_CHECK_INTERVAL = 10
    OPERATION_SHORT_DELAY = 0.5

    def __init__(self, connection_manager, logger=None, options=None):
        self.logger = logger or logging.getLogger(__name__)
        self.connection = connection_manager
        self.options = options or {}

        self._thread = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._lock = threading.Lock()

        # Full-flow reconnect (NAP + PAN + DHCP + verify). Set by BluetoothService
        # to its connect(); falls back to a NAP-only reconnect if unset.
        self.reconnect_callback = None
        self.RECONNECT_VERIFY_TIMEOUT = 30
        # NetworkManager, set by BluetoothService; used by the half-open watchdog
        # to probe whether the phone is actually reachable over the PAN link.
        self.network = None
        # Recovery entry point, set by BluetoothService. Routes a watchdog heal
        # through the service's ladder (restart -> module reload -> opt-in reboot)
        # with its shared rate limit and pairing-agent handling; falls back to a
        # bare bluetooth restart if unset.
        self.heal_callback = None

        self._current_mac = None
        self.last_known_connected = False
        self.reconnect_failure_count = 0
        self.max_reconnect_failures = self.MAX_RECONNECT_FAILURES
        self.reconnect_failure_cooldown = self.options.get("reconnect_failure_cooldown", self.DEFAULT_RECONNECT_FAILURE_COOLDOWN)
        self.first_failure_time = None
        self.reconnect_interval = self.options.get("reconnect_interval", self.DEFAULT_RECONNECT_INTERVAL)
        self.reconnect_fast_interval = self.options.get("reconnect_fast_interval", self.DEFAULT_RECONNECT_FAST_INTERVAL)
        self._disconnected_cycles = 0

        # Half-open PAN watchdog: the link can report "connected" while no traffic
        # actually passes (combo-chip coexistence). Detect it by probing the phone
        # over the PAN and, unless dry-run, reset Bluetooth to recover.
        self.watchdog_enabled = self.options.get("watchdog_enabled", True)
        self.watchdog_dry_run = self.options.get("watchdog_dry_run", True)
        self.watchdog_fail_threshold = self.options.get("watchdog_fail_threshold", 3)
        self._half_open_count = 0

    def start(self):
        """Start the monitoring thread."""
        try:
            if self._thread and self._thread.is_alive():
                self.logger.info("Monitor thread already running")
                return True

            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            self.logger.info(f"Started connection monitoring (interval: {self.reconnect_interval}s)")
            return True
        except Exception as e:
            self.logger.error(f"Failed to start monitor: {e}")
            return False

    @property
    def link_stalled(self):
        """True while the watchdog has unanswered peer probes on a live link -
        the connection LOOKS up but may be half-open. Cleared by a healthy probe."""
        return self._half_open_count > 0

    def set_device(self, mac):
        """Tell the monitor which device to watch for drops (called after a successful connect)."""
        with self._lock:
            self._current_mac = mac
            self.last_known_connected = True
            self.reconnect_failure_count = 0
            self.first_failure_time = None
            self._disconnected_cycles = 0
        self._paused.clear()

    def clear_device(self):
        """Stop watching a device, e.g. after an explicit disconnect/unpair."""
        with self._lock:
            self._current_mac = None
            self.last_known_connected = False

    def stop(self):
        """Stop the monitoring thread."""
        try:
            if self._thread and self._thread.is_alive():
                self._stop.set()
                self._thread.join(timeout=5)
            self.logger.info("Monitor stopped")
        except Exception as e:
            self.logger.debug(f"Error stopping monitor: {e}")

    def _adaptive_wait(self):
        """Interruptible monitor wait with adaptive reconnect backoff.

        Right after a drop, retry quickly (reconnect_fast_interval) to catch a
        phone that only briefly left range, then back off to reconnect_interval
        if it stays down. When connected (steady health check) or paused (no
        trusted device) always use the full interval - no point fast-polling.
        Returns immediately if shutdown was requested.
        """
        if self.last_known_connected or self._paused.is_set():
            self._disconnected_cycles = 0
            interval = self.reconnect_interval
        elif self.reconnect_fast_interval >= self.reconnect_interval:
            # Fast-retry disabled or misconfigured - use the normal interval.
            interval = self.reconnect_interval
        else:
            # Clean/fast failure (phone off or out of range) - retry quickly to
            # catch it the moment it returns.
            self._disconnected_cycles += 1
            interval = (
                self.reconnect_fast_interval
                if self._disconnected_cycles <= self.RECONNECT_FAST_CYCLES
                else self.reconnect_interval
            )
        self._stop.wait(interval)

    def _pick_device(self):
        """Choose which trusted device to keep connected.

        Prefers the current target (set after a connect), otherwise the first
        trusted NAP-capable device. A user-disconnected device is unpaired, so it
        won't appear here and the monitor won't fight the disconnect.
        """
        with self._lock:
            preferred = self._current_mac
        try:
            devices = self.connection.get_trusted_devices()
        except Exception as e:
            self.logger.debug(f"Could not list trusted devices: {e}")
            return preferred

        if preferred and any(d.mac == preferred for d in devices):
            return preferred
        for d in devices:
            if getattr(d, "has_nap", False):
                return d.mac
        return devices[0].mac if devices else None

    def _loop(self):
        """Background monitoring loop."""
        self.logger.info("Connection monitor started")

        # Interruptible initial delay so shutdown isn't blocked at startup
        if self._stop.wait(self.MONITOR_INITIAL_DELAY):
            return

        while not self._stop.is_set():
            try:
                if self._paused.is_set():
                    self._stop.wait(self.MONITOR_PAUSED_CHECK_INTERVAL)
                    continue

                mac = self._pick_device()
                if not mac:
                    self._adaptive_wait()
                    continue

                with self._lock:
                    self._current_mac = mac

                status = self.connection.get_full_status(mac)
                if not status:
                    self._adaptive_wait()
                    continue

                if status["connected"]:
                    self.last_known_connected = True
                    self.reconnect_failure_count = 0
                    self.first_failure_time = None
                    # Link reports connected - but on combo chips it can be
                    # half-open (bnep up, no traffic). Probe the phone and heal.
                    if status.get("pan_active"):
                        self._check_half_open_link()
                    else:
                        self._half_open_count = 0
                else:
                    # Not connected: reconnect. Covers both a dropped link and an
                    # initial connect that hasn't succeeded yet (e.g. phone wasn't
                    # in range at boot). A stale half-open count must not carry
                    # over into the next connection.
                    self._half_open_count = 0
                    if self.last_known_connected:
                        self.logger.warning(f"Connection to {mac} dropped! Reconnecting...")
                    else:
                        self.logger.info(f"{mac} paired but not connected - attempting connect...")
                    self.last_known_connected = self.reconnect(mac)

                self._adaptive_wait()

            except Exception as e:
                self.logger.debug(f"Monitor loop error: {e}")
                self._adaptive_wait()

    def reconnect(self, mac):
        """Attempt to (re)connect to a device using the full connect flow."""
        try:
            with self._lock:
                self._current_mac = mac

            self.logger.info(f"Attempting to reconnect to {mac}...")

            if self.reconnect_callback:
                # Full flow (pair-if-needed -> trust -> NAP -> DHCP -> verify) runs
                # on its own thread; poll for it to establish.
                self.reconnect_callback(mac)
                deadline_cycles = self.RECONNECT_VERIFY_TIMEOUT
                for _ in range(deadline_cycles):
                    if self._stop.wait(1):
                        return self.last_known_connected
                    status = self.connection.get_full_status(mac)
                    if status and status.get("connected"):
                        self.logger.info(f"Successfully reconnected to {mac}")
                        self.reconnect_failure_count = 0
                        self.first_failure_time = None
                        return True
                self._handle_reconnect_failure(mac)
                return False

            # Fallback: NAP-only reconnect (no full network setup)
            self.connection.connect_nap(mac)
            time.sleep(self.OPERATION_SHORT_DELAY)
            status = self.connection.get_full_status(mac)
            if status and status["connected"]:
                self.logger.info(f"Successfully reconnected to {mac}")
                self.reconnect_failure_count = 0
                self.first_failure_time = None
                return True
            self._handle_reconnect_failure(mac)
            return False

        except Exception as e:
            self.logger.error(f"Reconnect failed: {e}")
            self._handle_reconnect_failure(mac)
            return False

    def _check_half_open_link(self):
        """Detect a half-open PAN link (bnep up but phone unreachable) and, unless
        in dry-run, reset Bluetooth to recover. Called only while the link reports
        connected and a PAN interface is up. Honours the watchdog config."""
        if not self.watchdog_enabled or self.network is None:
            return

        reachable = self.network.pan_peer_reachable()
        if reachable is None:
            # No peer to probe. That's expected briefly while DHCP runs, but a PAN
            # that stays addressless is just as dead as a failed probe (over a
            # half-open link the DHCP request itself gets no reply) - and with no
            # address the monitor sees "connected" and would never intervene.
            # Count it; the threshold gives DHCP minutes of grace to land.
            iface = self.network.get_pan_interface()
            if not iface:
                return
            ip = self.network.get_interface_ip(iface)
            if (ip and not ip.startswith("169.254.")) or self.network.get_global_ipv6(iface):
                # Link has an address, just no probeable peer - don't act (and a
                # lease landing means any addressless streak is over).
                self._half_open_count = 0
                return
            reachable = False
        if reachable:
            # Decay rather than hard-reset: a flapping link (bad,bad,good,bad,bad)
            # would otherwise reset on every stray good probe and never reach the
            # threshold to heal. Decrementing lets a persistently-bad-but-flapping
            # link still climb, while a genuinely healthy link (all good) decays to
            # 0 and stays there.
            if self._half_open_count:
                self._half_open_count -= 1
                if self._half_open_count == 0:
                    self.logger.debug("Watchdog: PAN link healthy again")
            return

        # bnep up but phone unreachable -> half-open
        self._half_open_count += 1
        self.logger.warning(
            f"Watchdog: PAN link looks half-open (bnep up, phone unreachable) "
            f"[{self._half_open_count}/{self.watchdog_fail_threshold}]"
        )
        if self._half_open_count < self.watchdog_fail_threshold:
            return

        self._half_open_count = 0
        if self.watchdog_dry_run:
            self.logger.warning(
                "Watchdog: DRY-RUN - would reset Bluetooth now to clear the "
                "half-open link (set watchdog_dry_run = false to enable recovery)"
            )
            return

        # Active heal: the controller is responsive (so the busy self-heal never
        # fires) but the link is dead. Route through the service's recovery ladder
        # (restart -> module reload -> opt-in reboot), which shares its rate limit
        # and restores the pairing agent; then let the loop reconnect.
        self.logger.warning("Watchdog: resetting Bluetooth to clear the half-open link")
        try:
            if self.heal_callback:
                self.heal_callback("half-open PAN link")
            else:
                self.connection.force_restart_bluetooth()
        except Exception as e:
            self.logger.error(f"Watchdog: Bluetooth reset failed: {e}")
        self.last_known_connected = False

    def _handle_reconnect_failure(self, mac):
        """Handle a reconnection failure."""
        self.reconnect_failure_count += 1
        if self.first_failure_time is None:
            self.first_failure_time = time.time()

        if self.reconnect_failure_count >= self.max_reconnect_failures:
            self.logger.warning(f"⚠️ Auto-reconnect paused after {self.max_reconnect_failures} failed attempts")
            self.logger.info(f"📱 Will retry after {self.reconnect_failure_cooldown}s cooldown")
            self._paused.set()

            def cooldown_timer():
                time.sleep(self.reconnect_failure_cooldown)
                self._paused.clear()
                self.reconnect_failure_count = 0
                self.first_failure_time = None

            threading.Thread(target=cooldown_timer, daemon=True).start()
