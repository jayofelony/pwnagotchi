"""Pwnagotchi Bluetooth service - core module for Bluetooth operations."""

import logging
import threading
import time
from .device import BluetoothDevice
from .connection import ConnectionManager
from .network import NetworkManager
from .agent import PairingAgent
from .monitor import ConnectionMonitor
from .ui import UIRenderer, UICache


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

    def __init__(self, options=None, logger=None):
        self.options = options or {}
        self.logger = logger or logging.getLogger(__name__)

        # Initialize components
        self.connection = ConnectionManager(logger=self.logger)
        self.network = NetworkManager(logger=self.logger)
        self.agent = PairingAgent(logger=self.logger)
        self.monitor = ConnectionMonitor(self.connection, logger=self.logger, options=self.options)
        self.ui_cache = UICache()
        self.ui_renderer = UIRenderer()

        # State
        self._lock = threading.Lock()
        self._status = self.STATE_IDLE
        self._message = "Ready"
        self._initialized = False
        self._event_handlers = {}

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
        """Scan for Bluetooth devices."""
        with self._lock:
            self._status = self.STATE_SCANNING
            self._message = f"Scanning for {duration}s..."

        try:
            devices = self.connection.scan(duration)
            self._emit_event("bt:scan_complete", {"devices": devices})
            with self._lock:
                self._status = self.STATE_IDLE
            return devices
        except Exception as e:
            self.logger.error(f"Scan failed: {e}")
            with self._lock:
                self._status = self.STATE_ERROR
                self._message = f"Scan failed: {e}"
            return []

    def connect(self, mac, name=""):
        """Initiate connection to a device."""
        if not BluetoothDevice.validate_mac(mac):
            self.logger.error(f"Invalid MAC: {mac}")
            return False

        with self._lock:
            self._status = self.STATE_CONNECTING
            self._message = f"Connecting to {name or mac}..."

        def connect_thread():
            try:
                # Pair if needed
                status = self.connection.get_status(mac)
                if not status or not status["paired"]:
                    self.logger.info(f"Pairing with {mac}...")
                    with self._lock:
                        self._status = self.STATE_PAIRING
                    self.connection.pair_interactive(mac, name)
                    with self._lock:
                        self._status = self.STATE_TRUSTING
                    self.connection.trust_device(mac)

                # Connect NAP
                with self._lock:
                    self._status = self.STATE_CONNECTING
                if self.connection.connect_nap(mac):
                    time.sleep(self.network.SUBPROCESS_TIMEOUT_MEDIUM)
                    if self.network.is_pan_active():
                        with self._lock:
                            self._status = self.STATE_CONNECTED
                        self._emit_event("bt:connect_success", {"mac": mac, "name": name})
                        return True

                with self._lock:
                    self._status = self.STATE_ERROR
                self._emit_event("bt:connect_failed", {"mac": mac, "error": "Failed to establish NAP"})
                return False

            except Exception as e:
                self.logger.error(f"Connection failed: {e}")
                with self._lock:
                    self._status = self.STATE_ERROR
                    self._message = f"Connection failed: {e}"
                self._emit_event("bt:connect_failed", {"mac": mac, "error": str(e)})
                return False

        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()
        return True

    def disconnect(self, mac):
        """Disconnect from a device."""
        with self._lock:
            self._status = self.STATE_DISCONNECTING
            self._message = f"Disconnecting {mac}..."

        try:
            self.connection.disconnect(mac)
            time.sleep(0.5)
            self.connection.unpair(mac)
            with self._lock:
                self._status = self.STATE_DISCONNECTED
            self._emit_event("bt:disconnect_success", {"mac": mac})
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
    "UICache",
]
