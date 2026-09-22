import threading
import time
import logging
from collections import deque
from .connection import ConnectionManager
from .device import BluetoothDevice


class ConnectionMonitor:
    """Monitors connection status and handles auto-reconnect."""

    # Reconnect configuration
    DEFAULT_RECONNECT_INTERVAL = 60
    DEFAULT_RECONNECT_FAST_INTERVAL = 15
    RECONNECT_FAST_CYCLES = 6
    # After this many consecutive failures the phone is probably gone, so back off
    # to a slow retry (reconnect_failure_cooldown) - but NEVER stop: keep trying so
    # we always recover the moment it comes back.
    MAX_RECONNECT_FAILURES = 5
    DEFAULT_RECONNECT_FAILURE_COOLDOWN = 120
    MONITOR_INITIAL_DELAY = 5
    OPERATION_SHORT_DELAY = 0.5
    # While connected the health/watchdog check only needs to run once per
    # reconnect_interval, but the display reads the poll cache - so re-poll it this
    # often in between so a just-connected link stops showing "Paired" and the
    # tether IP appears within seconds instead of after a full minute.
    UI_REFRESH_INTERVAL = 10
    # Right after a connect the link is up but DHCP hasn't leased yet ("No IP").
    # Poll fast during that settle so the address shows within a few seconds, but
    # only for a bounded window so an address-less link doesn't poll forever.
    UI_SETTLE_INTERVAL = 2
    UI_SETTLE_WINDOW = 12

    def __init__(self, connection_manager, logger=None, options=None):
        self.logger = logger or logging.getLogger(__name__)
        self.connection = connection_manager
        self.options = options or {}

        self._thread = None
        self._stop = threading.Event()
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
        # Sliding window of recent probe results (True/False). Heal when at least
        # watchdog_fail_threshold of the last (threshold+1) probes failed - fast on
        # a dead link AND a flapping one, while a single stray ping loss can't trip
        # it. Beats a running counter, which a flapping link dilutes indefinitely.
        self._probe_history = deque(maxlen=self.watchdog_fail_threshold + 1)

        # Latest poll snapshot for the UI thread (see get_ui_status). Written by
        # the monitor thread every cycle and read by the plugin's on_ui_update so
        # the display never makes its own blocking bluetoothctl/ip calls on the
        # main loop. _picked_device caches the device chosen by _pick_device so
        # the UI can show its name without a second trusted-devices lookup.
        self._status_cache_lock = threading.Lock()
        self._status_cache = None
        self._picked_device = None

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
        """True when the most recent peer probe failed on a live link - the
        connection LOOKS up but may be half-open. Reflects the latest probe so it
        clears as soon as one succeeds, rather than lingering for the whole window."""
        # Single indexing op so a concurrent clear() on the monitor thread can't
        # wedge between a truthiness check and the [-1] read (would IndexError).
        try:
            return self._probe_history[-1] is False
        except IndexError:
            return False

    def _cache_ui_status(self, mac, status):
        """Store the latest poll so the UI thread can render it without blocking.
        Called from the monitor thread each cycle."""
        dev = self._picked_device
        name = dev.name if (dev is not None and dev.mac == mac) else None
        with self._status_cache_lock:
            self._status_cache = {
                "mac": mac,
                "name": name,
                "status": dict(status) if status else {},
            }

    def get_ui_status(self):
        """Latest connection snapshot for the display, or None before the first
        poll. Cheap and non-blocking - never triggers bluetoothctl/ip, so it is
        safe to call from on_ui_update on the main loop (under the view lock)."""
        with self._status_cache_lock:
            return dict(self._status_cache) if self._status_cache else None

    def set_device(self, mac):
        """Tell the monitor which device to watch for drops (called after a successful connect)."""
        with self._lock:
            self._current_mac = mac
            self.last_known_connected = True
            self.reconnect_failure_count = 0
            self.first_failure_time = None
            self._disconnected_cycles = 0

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
        phone that only briefly left range, then back off to reconnect_interval if
        it stays down, and finally to a slow retry (reconnect_failure_cooldown) once
        it's clearly gone. Crucially it never fully stops - it keeps trying at the
        slow cadence so it always recovers when the phone returns. Returns
        immediately if shutdown was requested.
        """
        if self.last_known_connected:
            self._disconnected_cycles = 0
            interval = self.reconnect_interval
        elif self.reconnect_failure_count >= self.max_reconnect_failures:
            # Sustained failure (phone likely gone) - slow retry, but keep going.
            interval = self.reconnect_failure_cooldown
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

    def _refresh_wait(self, mac, total):
        """Wait up to ``total`` seconds while keeping the UI snapshot fresh.

        Re-polls status and updates the display cache so a freshly-established link
        stops showing "Paired" and the tether IP appears within seconds - without
        re-running the reconnect/half-open logic, which stays on the
        reconnect_interval cadence. Polls fast while the link is still settling
        (connected, no IP yet), then backs off once it has an address. Returns early
        on shutdown, or if the link drops, so the main loop reconnects promptly."""
        waited = 0
        settled = False
        while waited < total:
            step = self.UI_REFRESH_INTERVAL if settled else self.UI_SETTLE_INTERVAL
            step = min(step, total - waited)
            if self._stop.wait(step):
                return
            waited += step
            try:
                status = self.connection.get_full_status(mac)
            except Exception:
                continue
            if not status:
                continue
            self._cache_ui_status(mac, status)
            if not status.get("connected"):
                return
            # Back off once we have an address, or after the settle window elapses
            # so an address-less link doesn't keep polling fast indefinitely.
            has_ip = bool(status.get("ip_address") or status.get("ipv6"))
            if has_ip or waited >= self.UI_SETTLE_WINDOW:
                settled = True

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
            self._picked_device = None
            return preferred

        if preferred and any(d.mac == preferred for d in devices):
            self._picked_device = next((d for d in devices if d.mac == preferred), None)
            return preferred
        for d in devices:
            if getattr(d, "has_nap", False):
                self._picked_device = d
                return d.mac
        if devices:
            self._picked_device = devices[0]
            return devices[0].mac
        self._picked_device = None
        return None

    def _loop(self):
        """Background monitoring loop."""
        self.logger.info("Connection monitor started")

        # Interruptible initial delay so shutdown isn't blocked at startup
        if self._stop.wait(self.MONITOR_INITIAL_DELAY):
            return

        while not self._stop.is_set():
            try:
                mac = self._pick_device()
                if not mac:
                    # No trusted device to watch (e.g. the last one was unpaired) -
                    # clear the UI snapshot so the display drops to "no device"
                    # instead of lingering on a stale connected/paired state.
                    self._cache_ui_status(None, {})
                    self._adaptive_wait()
                    continue

                with self._lock:
                    self._current_mac = mac

                status = self.connection.get_full_status(mac)
                self._cache_ui_status(mac, status)
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
                        self._probe_history.clear()
                    # Idle the rest of the cycle but keep the display current so the
                    # tether IP / "Connected" state show up promptly (not next poll).
                    self._refresh_wait(mac, self.reconnect_interval)
                    continue

                # Not connected: reconnect. Covers both a dropped link and an
                # initial connect that hasn't succeeded yet (e.g. phone wasn't
                # in range at boot). A stale probe history must not carry
                # over into the next connection.
                self._probe_history.clear()
                if self.last_known_connected:
                    self.logger.warning(f"Connection to {mac} dropped! Reconnecting...")
                else:
                    self.logger.info(f"{mac} paired but not connected - attempting connect...")
                self.last_known_connected = self.reconnect(mac)

                if self.last_known_connected:
                    # Reconnected: keep the display fresh so the tether IP appears
                    # promptly, instead of sleeping the whole interval the way a
                    # failed attempt does. Mirrors the steady-connected branch.
                    self._refresh_wait(mac, self.reconnect_interval)
                else:
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
                    if status:
                        # Track connect progress on the display in near-real-time
                        # so it doesn't sit on the stale "Paired" snapshot.
                        self._cache_ui_status(mac, status)
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
                # lease landing clears any recent failures).
                self._probe_history.clear()
                return
            reachable = False

        # Record this probe in the sliding window and heal when too many of the
        # recent probes failed. Unlike a running counter, a window can't be diluted
        # forever by a flapping link, and one stray good/bad read never dominates.
        self._probe_history.append(bool(reachable))
        fails = sum(1 for r in self._probe_history if r is False)
        if reachable:
            if fails == 0:
                pass  # fully healthy window - nothing to log
            return
        self.logger.warning(
            f"Watchdog: PAN link looks half-open (bnep up, phone unreachable) "
            f"[{fails}/{self.watchdog_fail_threshold} in last {len(self._probe_history)}]"
        )
        if fails < self.watchdog_fail_threshold:
            return

        self._probe_history.clear()
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
        """Count a reconnection failure and, past the threshold, slow the retry
        cadence - without ever stopping. The loop keeps attempting every
        reconnect_failure_cooldown seconds, so it recovers whenever the phone
        returns; the count resets to fast retries on the next successful connect."""
        self.reconnect_failure_count += 1
        if self.first_failure_time is None:
            self.first_failure_time = time.time()

        # Log once, on the transition into slow-retry, so the log isn't spammed.
        if self.reconnect_failure_count == self.max_reconnect_failures:
            self.logger.warning(
                "⚠️ Auto-reconnect: %d attempts failed - backing off to a slow retry "
                "every %ds (will keep trying)"
                % (self.max_reconnect_failures, self.reconnect_failure_cooldown))
