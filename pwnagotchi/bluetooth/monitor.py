import threading
import time
import logging
from .connection import ConnectionManager
from .device import BluetoothDevice


class ConnectionMonitor:
    """Monitors connection status and handles auto-reconnect."""

    # Reconnect configuration
    DEFAULT_RECONNECT_INTERVAL = 60
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

        self._current_mac = None
        self.last_known_connected = False
        self.reconnect_failure_count = 0
        self.max_reconnect_failures = self.MAX_RECONNECT_FAILURES
        self.reconnect_failure_cooldown = self.options.get("reconnect_failure_cooldown", self.DEFAULT_RECONNECT_FAILURE_COOLDOWN)
        self.first_failure_time = None
        self.reconnect_interval = self.options.get("reconnect_interval", self.DEFAULT_RECONNECT_INTERVAL)

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

    def set_device(self, mac):
        """Tell the monitor which device to watch for drops (called after a successful connect)."""
        with self._lock:
            self._current_mac = mac
            self.last_known_connected = True
            self.reconnect_failure_count = 0
            self.first_failure_time = None
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

    def _loop(self):
        """Background monitoring loop."""
        self.logger.info("Connection monitor started")
        time.sleep(self.MONITOR_INITIAL_DELAY)

        while not self._stop.is_set():
            try:
                if self._paused.is_set():
                    time.sleep(self.MONITOR_PAUSED_CHECK_INTERVAL)
                    continue

                # Check current connection status
                with self._lock:
                    last_mac = getattr(self, "_current_mac", None)

                if not last_mac:
                    time.sleep(self.reconnect_interval)
                    continue

                status = self.connection.get_full_status(last_mac)
                if not status:
                    time.sleep(self.reconnect_interval)
                    continue

                # Track connection drops and actually attempt to reconnect
                if self.last_known_connected and not status["connected"]:
                    self.logger.warning(f"Connection to {last_mac} dropped! Reconnecting...")
                    self.last_known_connected = self.reconnect(last_mac)
                else:
                    self.last_known_connected = status["connected"]

                time.sleep(self.reconnect_interval)

            except Exception as e:
                self.logger.debug(f"Monitor loop error: {e}")
                time.sleep(self.reconnect_interval)

    def reconnect(self, mac):
        """Attempt to reconnect to a device."""
        try:
            with self._lock:
                self._current_mac = mac

            self.logger.info(f"Attempting to reconnect to {mac}...")
            self.connection.connect_nap(mac)
            time.sleep(self.OPERATION_SHORT_DELAY)

            status = self.connection.get_full_status(mac)
            if status and status["connected"]:
                self.logger.info(f"Successfully reconnected to {mac}")
                self.reconnect_failure_count = 0
                self.first_failure_time = None
                return True
            else:
                self._handle_reconnect_failure(mac)
                return False

        except Exception as e:
            self.logger.error(f"Reconnect failed: {e}")
            self._handle_reconnect_failure(mac)
            return False

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
