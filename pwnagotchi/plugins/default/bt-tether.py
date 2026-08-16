"""
Bluetooth Tether Plugin for Pwnagotchi - Thin wrapper using core Bluetooth service

This is a refactored version that delegates Bluetooth operations to the core pwnagotchi.bluetooth
module, reducing the plugin from 5000+ lines to ~1200 lines and enabling code reuse.

Configuration (config.toml):
    [main.plugins.bt-tether]
    enabled = true
    auto_reconnect = true
    show_on_screen = true
"""

import logging
import threading
import json
import time
from collections import deque
import pwnagotchi
import pwnagotchi.plugins as plugins
from pwnagotchi.plugins import Plugin
from pwnagotchi.bluetooth import BluetoothService
from pwnagotchi.ui.components import LabeledValue
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.view import BLACK
from flask import render_template_string, request, jsonify


class BtTether(Plugin):
    __author__ = "wsvdmeer"
    __version__ = "2.0.1"
    __license__ = "GPL3"
    __description__ = "Guided Bluetooth tethering"

    # CSRF exempt since this is a trusted local interface
    csrf_exempt = True

    # If on_ready() never fires (e.g. manual mode, where pwnagotchi does not call
    # it), start the service anyway after this many seconds.
    FALLBACK_INIT_TIMEOUT = 5

    def on_loaded(self):
        """Initialize plugin configuration and core Bluetooth service."""
        # Seed from the persisted MAC so the last-used phone survives a restart
        self.phone_mac = self.options.get("mac", "")
        self._phone_name = ""
        self._status = "IDLE"
        self._message = "- -"
        self._ui_logs = deque(maxlen=100)
        self._ui_log_lock = threading.Lock()
        self._ui_reference = None
        self._screen_needs_refresh = False
        self._connection_time = None
        self._show_device_name = False

        # Configuration
        self.show_on_screen = self.options.get("show_on_screen", True)
        self.show_mini_status = self.options.get("show_mini_status", True)
        self.mini_status_position = self.options.get("mini_status_position", [110, 0])
        self.show_detailed_status = self.options.get("show_detailed_status", True)
        self.detailed_status_position = self.options.get("detailed_status_position", [0, 82])
        self.auto_reconnect = self.options.get("auto_reconnect", True)

        # Initialize core Bluetooth service
        self.bt = BluetoothService(
            options=self.options,
            logger=logging.getLogger("pwnagotchi.bluetooth")
        )

        # Register event handlers from core service
        self.bt.on_event("bt:connect_success", self._on_connect_success)
        self.bt.on_event("bt:connect_failed", self._on_connect_failed)
        self.bt.on_event("bt:disconnect_success", self._on_disconnect_success)

        # Start the service without depending on on_ready() - pwnagotchi only
        # calls on_ready() in auto mode, so in manual mode we self-start after a
        # short grace period.
        self._initialization_done = threading.Event()
        self._init_lock = threading.Lock()
        threading.Thread(target=self._fallback_initialization, daemon=True).start()

        self._log("INFO", "Plugin loaded")

    def on_ready(self, agent):
        """Start Bluetooth service when agent is ready (auto mode)."""
        self._start_service("on_ready")

    def _fallback_initialization(self):
        """Start the service even if on_ready() never fires (e.g. manual mode)."""
        if not self._initialization_done.wait(timeout=self.FALLBACK_INIT_TIMEOUT):
            self._log("WARNING", "on_ready() not called - using fallback initialization")
            self._start_service("fallback")

    def _start_service(self, source):
        """Start the core Bluetooth service exactly once, then auto-connect."""
        with self._init_lock:
            if self._initialization_done.is_set():
                return
            self._initialization_done.set()

        self._log("INFO", f"Starting Bluetooth service ({source})...")
        if self.bt.start():
            self._log("INFO", "Bluetooth service started")
            # Try auto-connect if auto_reconnect enabled, preferring the last phone
            if self.auto_reconnect:
                best_device = self.bt.find_best_device(prefer_mac=self.phone_mac or None)
                if best_device:
                    self._log("INFO", f"Auto-connecting to {best_device.name}...")
                    self.bt.connect(best_device.mac, best_device.name)
        else:
            self._log("ERROR", "Failed to start Bluetooth service")

    def on_unload(self, ui):
        """Cleanup when plugin is unloaded."""
        try:
            self._log("INFO", "Unloading plugin...")
            # Prevent a pending fallback thread from starting the service post-unload
            self._initialization_done.set()
            self.bt.stop()
            self._log("INFO", "Plugin unloaded")
        except Exception as e:
            logging.error(f"Error during unload: {e}")

    def on_ui_setup(self, ui):
        """Setup UI elements for status display."""
        self._ui_reference = ui

        if self.show_on_screen and self.show_mini_status:
            pos = tuple(self.mini_status_position) if isinstance(self.mini_status_position, (list, tuple)) else self.mini_status_position
            ui.add_element(
                "bt-status",
                LabeledValue(
                    color=BLACK,
                    label="BT",
                    value="I",
                    position=pos,
                    label_font=fonts.Bold,
                    text_font=fonts.Medium,
                ),
            )

        if self.show_on_screen and self.show_detailed_status:
            ui.add_element(
                "bt-detail",
                LabeledValue(
                    color=BLACK,
                    label="",
                    value="BT:Init",
                    position=tuple(self.detailed_status_position),
                    label_font=fonts.Small,
                    text_font=fonts.Small,
                ),
            )

    def on_ui_update(self, ui):
        """Update UI display elements with current status."""
        if not self.show_on_screen:
            return

        try:
            # Try to get status for stored phone_mac first, then check for any connected tethering device
            cached_status = None
            connected_device = None

            if self.phone_mac:
                cached_status = self.bt.connection.get_full_status(self.phone_mac)
                # Try to get the device name if we have a MAC
                if cached_status and not self._phone_name:
                    trusted_devices = self.bt.connection.get_trusted_devices()
                    for device in trusted_devices:
                        if device.mac == self.phone_mac:
                            self._phone_name = device.name
                            connected_device = device
                            break

            # Rescan the trusted devices when we have no status OR the stored device
            # is disconnected. get_full_status() returns a (disconnected) dict for
            # any paired device, so keying only on "not cached_status" latches onto
            # the first device forever - the indicator would keep showing that one
            # even after tethering moves to another host. Copy the rescan result
            # over only on success so a scan that finds nothing leaves the previous
            # status intact (preserves the P vs X distinction).
            if not cached_status or not cached_status.get("connected"):
                trusted_devices = self.bt.connection.get_trusted_devices()
                for device in trusted_devices:
                    if device.connected and device.has_nap:
                        new_status = self.bt.connection.get_full_status(device.mac)
                        if new_status and new_status.get("connected"):
                            cached_status = new_status
                            self.phone_mac = device.mac
                            self._phone_name = device.name
                            connected_device = device
                            break

            cached_status = cached_status or {}

            # Track connection state for status reporting
            if cached_status.get("connected", False):
                self._status = "CONNECTED"
            elif self._status == "CONNECTED":
                self._status = "IDLE"

            if connected_device and connected_device.name:
                self._phone_name = connected_device.name

            # Determine display character based on connection state
            if cached_status.get("pan_active", False):
                # Pan active - tethering is working
                display = "C"
            elif cached_status.get("connected", False) and cached_status.get("trusted", False):
                # Connected and trusted
                display = "T"
            elif cached_status.get("connected", False):
                # Just connected (not trusted)
                display = "N"
            elif cached_status.get("paired", False):
                # Paired but not connected
                display = "P"
            else:
                # No device or not paired
                display = "X"

            # Detailed line: show the IP once tethering is up (prefer IPv4, then
            # IPv6 for v6-only tethering). No name/IP toggle - the IP is the useful
            # info, matching the standalone plugin.
            if cached_status.get("pan_active", False):
                ip_address = cached_status.get("ip_address") or cached_status.get("ipv6")
                self._message = ip_address if ip_address else "Connected"
            elif cached_status.get("connected", False) and cached_status.get("trusted", False):
                self._message = "Trusted"
            elif cached_status.get("connected", False):
                self._message = "Connected"
            elif cached_status.get("paired", False):
                self._message = "Paired"
            else:
                self._message = "- -"

            if self.show_mini_status:
                ui.set("bt-status", display)

            if self.show_detailed_status:
                detailed = f"BT:{self._message}" if self._message else "BT:- -"
                ui.set("bt-detail", detailed)

        except Exception as e:
            logging.debug(f"UI update error: {e}")
            if self.show_mini_status:
                ui.set("bt-status", "?")
            if self.show_detailed_status:
                ui.set("bt-detail", "BT:Error")

    def on_webhook(self, path, request):
        """Handle webhook requests for web UI."""
        subpath = path.split("/")[-1] if path else ""

        if subpath == "" or subpath == "index":
            return self._render_html()

        elif subpath == "trusted-devices":
            return self._get_trusted_devices()

        elif subpath == "connect":
            mac = request.args.get("mac", "")
            return self._connect_device(mac)

        elif subpath == "disconnect":
            mac = request.args.get("mac", "")
            return self._disconnect_device(mac)

        elif subpath == "unpair":
            mac = request.args.get("mac", "")
            return self._unpair_device(mac)

        elif subpath == "pair-device":
            mac = request.args.get("mac", "")
            name = request.args.get("name", "")
            return self._pair_device(mac, name)

        elif subpath == "scan":
            return self._scan_devices()

        elif subpath == "scan-progress":
            return self._get_scan_progress()

        elif subpath == "status":
            return self._get_status()

        elif subpath == "connection-status":
            mac = request.args.get("mac", "")
            return self._get_connection_status(mac)

        elif subpath == "pair-status":
            mac = request.args.get("mac", "")
            return self._get_pair_status(mac)

        elif subpath == "test-internet":
            return self._test_internet()

        elif subpath == "logs":
            return self._get_logs()

        return jsonify({"error": "Not found"}), 404

    def _render_html(self):
        """Render the main HTML interface."""
        version = self.__version__
        mac = self.phone_mac
        template = self._get_html_template()
        return render_template_string(template, version=version, mac=mac)

    def _get_trusted_devices(self):
        """Return list of trusted devices."""
        devices = self.bt.get_trusted_devices()
        return jsonify({
            "devices": [
                {
                    "mac": d.mac,
                    "name": d.name,
                    "paired": d.paired,
                    "trusted": d.trusted,
                    "connected": d.connected,
                    "has_nap": d.has_nap,
                }
                for d in devices
            ]
        })

    def _connect_device(self, mac):
        """Start connection to device."""
        if not mac:
            return jsonify({"success": False, "message": "No MAC specified"})

        self.phone_mac = mac
        result = self.bt.connect(mac)
        return jsonify({"success": result})

    def _disconnect_device(self, mac):
        """Disconnect from device."""
        result = self.bt.disconnect(mac)
        self.phone_mac = ""
        self.options["mac"] = ""
        return jsonify({"success": result})

    def _unpair_device(self, mac):
        """Remove pairing with a device."""
        if not mac:
            return jsonify({"success": False, "message": "No MAC specified"})
        result = self.bt.unpair(mac)
        if self.phone_mac == mac:
            self.phone_mac = ""
            self.options["mac"] = ""
        return jsonify({"success": result})

    def _pair_device(self, mac, name):
        """Pair with device."""
        if not mac:
            return jsonify({"success": False, "message": "No MAC specified"})

        self.phone_mac = mac
        result = self.bt.connect(mac, name)
        return jsonify({"success": result})

    def _scan_devices(self):
        """Start device scan in background."""
        threading.Thread(target=self._scan_thread, daemon=True).start()
        return jsonify({"success": True})

    def _scan_thread(self):
        """Background thread for scanning."""
        try:
            self._log("INFO", "Starting Bluetooth device scan...")
            self.bt.scan_devices(duration=30)
            progress = self.bt.get_scan_progress()
            self._log("INFO", f"Scan complete: found {len(progress['devices'])} devices")
        except Exception as e:
            self._log("ERROR", f"Scan failed: {e}")

    def _get_scan_progress(self):
        """Get scan progress and discovered devices."""
        progress = self.bt.get_scan_progress()
        return jsonify({
            "scanning": progress["scanning"],
            "devices": [
                {"mac": d.get("mac", ""), "name": d.get("name", "")}
                for d in progress["devices"]
            ]
        })

    def _get_status(self):
        """Get current plugin status."""
        # Auto-detect connected device if phone_mac not set
        current_mac = self.phone_mac
        if not current_mac:
            trusted_devices = self.bt.connection.get_trusted_devices()
            for device in trusted_devices:
                if device.connected and device.has_nap:
                    current_mac = device.mac
                    break

        return jsonify({
            "status": self._status,
            "message": self._message,
            "mac": current_mac,
            "initialized": self.bt.initialized,
            "scanning": False,
            "connection_in_progress": False,
            "disconnecting": False,
            "untrusting": False,
            "initializing": not self.bt.initialized,
        })

    def _get_connection_status(self, mac):
        """Get full connection status for a device."""
        if not mac:
            return jsonify({"success": False})

        try:
            status = self.bt.connection.get_full_status(mac)
            if not status:
                return jsonify({"success": False})

            return jsonify({
                "success": True,
                "paired": status.get("paired", False),
                "trusted": status.get("trusted", False),
                "connected": status.get("connected", False),
                "pan_active": status.get("pan_active", False),
                "interface": status.get("interface"),
                "ip_address": status.get("ip_address"),
                "ipv6": status.get("ipv6"),
                "default_route_interface": self.bt.network.get_default_route_interface(),
            })
        except Exception as e:
            self._log("ERROR", f"Failed to get connection status: {e}")
            return jsonify({"success": False, "error": str(e)})

    def _get_pair_status(self, mac):
        """Return basic pair/connect status for a device."""
        if not mac:
            return jsonify({"paired": False, "connected": False})
        status = self.bt.connection.get_status(mac)
        return jsonify({
            "paired": status.get("paired", False),
            "connected": status.get("connected", False),
        })

    def _test_internet(self):
        """Test internet connectivity."""
        results = self.bt.network.test_internet_connectivity()
        return jsonify(results)

    def _get_logs(self):
        """Return UI logs."""
        with self._ui_log_lock:
            logs = list(self._ui_logs)
        return jsonify({"logs": logs})

    def _log(self, level, message):
        """Log to both system logger and UI buffer."""
        full_message = f"[bt-tether] {message}"
        level_upper = level.upper()

        if level_upper == "ERROR":
            logging.error(full_message)
        elif level_upper == "WARNING":
            logging.warning(full_message)
        elif level_upper == "DEBUG":
            logging.debug(full_message)
        else:
            logging.info(full_message)

        # Add to UI log buffer
        import datetime
        with self._ui_log_lock:
            self._ui_logs.append({
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                "level": level_upper,
                "message": message,
            })

    def _get_pwnagotchi_name(self):
        """Get pwnagotchi name."""
        try:
            return pwnagotchi.name()
        except Exception as e:
            self._log("DEBUG", f"Failed to get pwnagotchi name: {e}")
        return "pwnagotchi"

    def _emit_plugin_event(self, event_name, event_data):
        """Emit a public event to other plugins (e.g. pwn-companion, bt-tether-discord)."""
        try:
            event_data.setdefault("pwnagotchi_name", self._get_pwnagotchi_name())
            plugins.on(event_name, None, event_data)
            self._log("DEBUG", f"Event emitted: {event_name}")
        except Exception as e:
            self._log("WARNING", f"Failed to emit event {event_name}: {e}")

    def _on_connect_success(self, data):
        """Handle successful connection event."""
        mac = data.get("mac")
        name = data.get("name") or mac
        self._log("INFO", f"Connected to {name}")
        self._status = "CONNECTED"
        self._message = f"Connected to {name}"
        self._screen_needs_refresh = True

        # Persist the MAC so the last-used phone survives a restart
        if mac:
            self.phone_mac = mac
            self.options["mac"] = mac
        if name:
            self._phone_name = name

        # Notify external consumers (IPv4 stays in `ip` for back-compat; `ipv6` is additive)
        self._emit_plugin_event("bt_tether_connected", {
            "mac": mac,
            "device": name,
            "ip": data.get("ip") or "unknown",
            "ipv6": data.get("ipv6"),
            "interface": data.get("interface"),
        })

    def _on_connect_failed(self, data):
        """Handle failed connection event."""
        mac = data.get("mac")
        error = data.get("error", "Unknown error")
        self._log("ERROR", f"Connection failed: {error}")
        self._status = "ERROR"
        self._message = f"Connection failed: {error}"
        self._screen_needs_refresh = True

    def _on_disconnect_success(self, data):
        """Handle successful disconnection event."""
        mac = data.get("mac")
        reason = data.get("reason", "user_request")
        device = self._phone_name or mac
        self._log("INFO", f"Disconnected from {mac}")
        self._status = "IDLE"
        self._message = "Ready"
        self._screen_needs_refresh = True

        # Clear the persisted MAC on an explicit disconnect
        self.phone_mac = ""
        self.options["mac"] = ""

        self._emit_plugin_event("bt_tether_disconnected", {
            "mac": mac,
            "device": device,
            "reason": reason,
        })

    def _get_html_template(self):
        """Get the original full-featured HTML template."""
        # This template is extracted from the original bt-tether.py.disabled
        # It provides the full UI with device discovery, status monitoring, and internet testing
        template = """<!DOCTYPE html>
<html>
  <head>
    <title>Bluetooth Tether</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Cpath fill='%2358a6ff' d='M50 10 L70 25 L70 45 L50 60 L50 90 L30 75 L30 55 L50 40 L50 10 M50 40 L50 60'/%3E%3C/svg%3E" />
    <style>
      body { font-family: sans-serif; padding: 20px; max-width: 600px; margin: 0 auto; background: #0d1117; color: #d4d4d4; }
      .card { background: #161b22; padding: 20px; border-radius: 8px; margin-bottom: 16px; box-shadow: 0 2px 4px rgba(0,0,0,0.3); border: 1px solid #30363d; }
      h2 { margin: 0 0 20px 0; color: #58a6ff; }
      h3 { color: #d4d4d4; }
      h4 { color: #8b949e; }
      input { padding: 10px; font-size: 14px; border: 1px solid #30363d; border-radius: 4px; text-transform: uppercase; background: #0d1117; color: #d4d4d4; }
      input:focus { outline: none; border-color: #58a6ff; background: #161b22; }
      button { padding: 10px 20px; background: transparent; color: #3fb950; border: 1px solid #3fb950; cursor: pointer; font-size: 14px; border-radius: 4px; margin-right: 8px; min-height: 42px; display: inline-flex; align-items: center; justify-content: center; }
      button:hover { background: rgba(63, 185, 80, 0.1); border-color: #3fb950; }
      button.danger { color: #f85149; border-color: #f85149; background: transparent; }
      button.danger:hover { background: rgba(248, 81, 73, 0.1); border-color: #f85149; }
      button.success { color: #3fb950; border-color: #3fb950; background: transparent; }
      button.success:hover { background: rgba(63, 185, 80, 0.1); border-color: #3fb950; }
      button:disabled { background: transparent; color: #8b949e; cursor: not-allowed; border-color: #30363d; }
      .status-item { padding: 8px; margin: 4px 0; border-radius: 4px; background: #161b22; border: 1px solid #30363d; color: #d4d4d4; }
      .status-good { background: rgba(46, 160, 67, 0.15); color: #3fb950; border-color: #3fb950; }
      .status-bad { background: rgba(248, 81, 73, 0.15); color: #f85149; border-color: #f85149; }
      .device-item { padding: 12px; margin: 8px 0; border: 1px solid #30363d; border-radius: 4px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; background: #0d1117; color: #d4d4d4; }
      .device-item:hover { background: #161b22; border-color: #58a6ff; }
      .message-box { padding: 12px; border-radius: 4px; margin: 12px 0; border-left: 4px solid; }
      .message-info { background: rgba(88, 166, 255, 0.1); color: #79c0ff; border-color: #79c0ff; }
      .message-success { background: rgba(63, 185, 80, 0.1); color: #3fb950; border-color: #3fb950; }
      .message-warning { background: rgba(214, 159, 0, 0.1); color: #d29922; border-color: #d29922; }
      .message-error { background: rgba(248, 81, 73, 0.1); color: #f85149; border-color: #f85149; }
      .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #30363d; border-top: 2px solid #58a6ff; border-radius: 50%; animation: spin 1s linear infinite; margin-right: 8px; vertical-align: middle; }
      @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
      .mac-editor { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
      .mac-editor input { flex: 1; min-width: 200px; }
      .mac-editor button { white-space: nowrap; }
      .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
      .header h2 { margin: 0; flex: 1; }
      .header button { margin-left: 12px; }
      button.outline { color: #ffffff; border-color: #ffffff; }
      button.outline:hover { background: rgba(255, 255, 255, 0.1); border-color: #ffffff; }
      @media (max-width: 600px) {
        .mac-editor { flex-direction: column; align-items: stretch; }
        .mac-editor input { width: 100%; }
        .mac-editor button { width: 100%; margin: 0 !important; }
      }
    </style>
  </head>
  <body>
    <div class="header">
      <div>
        <h2>🔷 Bluetooth Tether</h2>
        <div style="font-size: 12px; color: #8b949e; margin-top: 2px;">v{{ version }}</div>
      </div>
      <button class="outline" onclick="window.location.href='/plugins'" style="margin: 0;">Plugins</button>
    </div>

    <div class="card" id="phoneConnectionCard">
      <h3 style="margin: 0 0 12px 0;">📱 Connection Status</h3>
      <div style="background: #0d1117; color: #d4d4d4; padding: 12px; border-radius: 4px; margin-bottom: 12px; font-family: 'Courier New', monospace; font-size: 12px; line-height: 1.5;">
        <div style="color: #888; margin-bottom: 4px;">Trusted Devices:</div>
        <div id="trustedDevicesSummary" style="color: #4ec9b0; font-size: 14px;">Loading...</div>
      </div>

      <div style="background: #0d1117; color: #d4d4d4; padding: 12px; border-radius: 4px; margin-bottom: 12px; font-family: 'Courier New', monospace; font-size: 12px; line-height: 1.5;">
        <div style="color: #888; margin-bottom: 8px;">Connection Status:</div>
        <div id="statusPaired" style="margin: 4px 0;">📱 Paired: <span>Checking...</span></div>
        <div id="statusTrusted" style="margin: 4px 0;">🔐 Trusted: <span>Checking...</span></div>
        <div id="statusConnected" style="margin: 4px 0;">🔵 Connected: <span>Checking...</span></div>
        <div id="statusInternet" style="margin: 4px 0;">🌐 Internet: <span>Checking...</span></div>
        <div id="statusIP" style="display: none; margin: 4px 0;">🔢 IP Address: <span></span></div>
      </div>

      <input type="hidden" id="macInput" value="{{ mac }}" />

      <div style="margin-bottom: 12px;">
        <h4 style="margin: 0 0 8px 0; color: #8b949e; font-size: 14px;">📋 Output</h4>
        <div id="logViewer">
          <div style="background: #0d1117; color: #d4d4d4; padding: 12px; padding-right: 16px; border-radius: 4px; font-family: 'Courier New', monospace; font-size: 12px; max-height: 300px; overflow-y: auto; line-height: 1.5;" id="logContent">
            <div style="color: #888;">Fetching logs...</div>
          </div>
        </div>
      </div>

      <div id="connectActions">
        <button class="success" onclick="quickConnect()" id="quickConnectBtn" style="width: 100%; margin: 0 0 8px 0;">
          ⚡ Connect to Phone
        </button>
      </div>

      <div id="disconnectSection" style="display: none;">
        <button class="danger" onclick="disconnectDevice()" id="disconnectBtn" style="width: 100%; margin: 0 0 8px 0;">
          🔌 Disconnect
        </button>
      </div>

      <div id="deviceDiscoverySection" style="display: none; margin-top: 16px; padding-top: 16px; border-top: 1px solid #30363d;">
        <h4 style="margin: 0 0 12px 0;">🔍 Discover Devices</h4>
        <button class="success" onclick="scanDevices()" id="scanBtn" style="width: 100%; margin: 0 0 12px 0;">
          🔍 Scan
        </button>
        <div id="scanResults" style="display: none;">
          <h5 style="margin: 0 0 8px 0; color: #8b949e;">Discovered Devices:</h5>
          <div id="scanStatus" style="color: #8b949e; margin: 8px 0; font-size: 13px;">Scanning...</div>
          <div id="deviceList"></div>
        </div>
      </div>
    </div>

    <div class="card" id="testInternetCard" style="display: none;">
      <h3 style="margin: 0 0 12px 0;">🔍 Test Internet Connectivity</h3>
      <button onclick="testInternet()" id="testInternetBtn" style="width: 100%;">
        🔍 Test Internet Connectivity
      </button>
      <div id="testResults" style="display: none;">
        <div id="testResultsMessage" class="message-box message-info"></div>
      </div>
    </div>

    <script>
      const macInput = document.getElementById("macInput");
      let statusInterval = null;
      let logInterval = null;

      // Show initializing state first
      setInitializingStatus();

      // Load trusted devices on page load
      loadTrustedDevicesSummary();

      // Then check actual connection status
      setTimeout(checkConnectionStatus, 1000);

      // Start log polling immediately
      refreshLogs();
      startLogPolling();

      function setInitializingStatus() {
        document.getElementById("statusPaired").innerHTML =
          `📱 Paired: <span style="color: #8b949e;">🔄 Initializing...</span>`;

        document.getElementById("statusTrusted").innerHTML =
          `🔐 Trusted: <span style="color: #8b949e;">🔄 Initializing...</span>`;

        document.getElementById("statusConnected").innerHTML =
          `🔵 Connected: <span style="color: #8b949e;">🔄 Initializing...</span>`;

        document.getElementById("statusInternet").innerHTML =
          `🌐 Internet: <span style="color: #8b949e;">🔄 Initializing...</span>`;

        document.getElementById('statusIP').style.display = 'none';

        const connectBtn = document.getElementById('quickConnectBtn');
        connectBtn.disabled = true;
        connectBtn.innerHTML = '<span class="spinner"></span> Initializing...';
      }

      async function checkConnectionStatus() {
        let mac = macInput.value.trim();

        // If no MAC in input, try to get it from backend status
        if (!mac || !/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(mac)) {
          try {
            const statusResponse = await fetch(`/plugins/bt-tether/status`);
            const statusData = await statusResponse.json();

            // If backend has a current MAC, use it
            if (statusData.mac && /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(statusData.mac)) {
              mac = statusData.mac;
              macInput.value = mac;
            } else {
              // No valid MAC - show disconnected state
              document.getElementById("statusPaired").innerHTML =
                `📱 Paired: <span style="color: #f48771;">✗ No</span>`;

              document.getElementById("statusTrusted").innerHTML =
                `🔐 Trusted: <span style="color: #f48771;">✗ No</span>`;

              document.getElementById("statusConnected").innerHTML =
                `🔵 Connected: <span style="color: #f48771;">✗ No</span>`;

              document.getElementById("statusInternet").innerHTML =
                `🌐 Internet: <span style="color: #f48771;">✗ Not Active</span>`;

              const connectBtn = document.getElementById('quickConnectBtn');
              connectBtn.style.display = 'none';
              document.getElementById('disconnectSection').style.display = 'none';
              return;
            }
          } catch (err) {
            console.error('Failed to get backend status:', err);
            // Still show buttons even if status fetch fails
            const connectBtn = document.getElementById('quickConnectBtn');
            connectBtn.disabled = false;
            connectBtn.innerHTML = '⚡ Connect to Phone';
            return;
          }
        }

        try {
          // Fetch both backend status and connection status
          const statusResponse = await fetch(`/plugins/bt-tether/status`);
          const statusData = await statusResponse.json();

          const response = await fetch(`/plugins/bt-tether/connection-status?mac=${encodeURIComponent(mac)}`);
          const data = await response.json();

          updateStatusDisplay(statusData, data);
        } catch (error) {
          console.error('Status check failed:', error);
        }
      }

      function updateStatusDisplay(statusData, data) {
        try {
          // Ensure data objects exist with defaults
          statusData = statusData || {};
          data = data || {};

          const paired = data.paired || false;
          const trusted = data.trusted || false;
          const connected = data.connected || false;
          const pan_active = data.pan_active || false;
          const ip_address = data.ip_address || null;

          document.getElementById("statusPaired").innerHTML =
            `📱 Paired: <span style="color: ${paired ? '#4ec9b0' : '#f48771'};">${paired ? '✓ Yes' : '✗ No'}</span>`;
          document.getElementById("statusTrusted").innerHTML =
            `🔐 Trusted: <span style="color: ${trusted ? '#4ec9b0' : '#f48771'};">${trusted ? '✓ Yes' : '✗ No'}</span>`;
          document.getElementById("statusConnected").innerHTML =
            `🔵 Connected: <span style="color: ${connected ? '#4ec9b0' : '#f48771'};">${connected ? '✓ Yes' : '✗ No'}</span>`;
          document.getElementById("statusInternet").innerHTML =
            `🌐 Internet: <span style="color: ${pan_active ? '#4ec9b0' : '#f48771'};">${pan_active ? '✓ Active' : '✗ Not Active'}</span>${data.interface ? ` <span style="color: #888;">(${data.interface})</span>` : ''}`;

          const statusIPElement = document.getElementById('statusIP');
          if (ip_address && pan_active) {
            statusIPElement.style.display = 'block';
            statusIPElement.innerHTML = `🔢 IP Address: <span style="color: #4ec9b0;">${ip_address}</span>`;
          } else {
            statusIPElement.style.display = 'none';
          }

          const testInternetCard = document.getElementById('testInternetCard');
          if (pan_active) {
            testInternetCard.style.display = 'block';
          } else {
            testInternetCard.style.display = 'none';
          }

          const connectBtn = document.getElementById('quickConnectBtn');
          const disconnectSection = document.getElementById('disconnectSection');

          // Check if operation is in progress
          const operationInProgress = statusData.status === 'PAIRING' || statusData.status === 'CONNECTING' || statusData.status === 'RECONNECTING';

          if (operationInProgress) {
            // Show connecting state
            connectBtn.disabled = true;
            connectBtn.innerHTML = '<span class="spinner"></span> Connecting...';
            connectBtn.style.display = 'block';
            disconnectSection.style.display = 'none';
          } else {
            connectBtn.disabled = false;
            connectBtn.innerHTML = '⚡ Connect to Phone';

            // Show/hide based on connection status
            if (connected) {
              connectBtn.style.display = 'none';
              disconnectSection.style.display = 'block';
            } else if (paired && trusted) {
              connectBtn.style.display = 'block';
              disconnectSection.style.display = 'block';
            } else if (paired) {
              connectBtn.style.display = 'none';
              disconnectSection.style.display = 'block';
            } else {
              connectBtn.style.display = 'none';
              disconnectSection.style.display = 'none';
            }
          }

          // Manage polling based on connection state
          if (operationInProgress) {
            if (!statusInterval || statusInterval._interval !== 2000) {
              if (statusInterval) clearInterval(statusInterval);
              statusInterval = setInterval(checkConnectionStatus, 2000);
              statusInterval._interval = 2000;
            }
          } else if (connected || paired) {
            if (!statusInterval || statusInterval._interval !== 10000) {
              if (statusInterval) clearInterval(statusInterval);
              statusInterval = setInterval(checkConnectionStatus, 10000);
              statusInterval._interval = 10000;
            }
          } else {
            if (!statusInterval || statusInterval._interval !== 30000) {
              if (statusInterval) clearInterval(statusInterval);
              statusInterval = setInterval(checkConnectionStatus, 30000);
              statusInterval._interval = 30000;
            }
          }

          // Refresh trusted devices summary if connection state changed
          if (!window.lastStatusUpdate ||
              (window.lastStatusUpdate.connected !== (statusData.mac && connected))) {
            loadTrustedDevicesSummary();
            window.lastStatusUpdate = {
              connected: statusData.mac && connected
            };
          }
        } catch (error) {
          console.error('Error updating status display:', error);
        }
      }

      async function quickConnect() {
        const mac = macInput.value.trim();
        if (!mac || !/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(mac)) {
          alert("Enter valid MAC address");
          return;
        }
        try {
          const response = await fetch(`/plugins/bt-tether/connect?mac=${encodeURIComponent(mac)}`);
          const data = await response.json();
          if (data.success) {
            // Start fast polling to show connection progress
            if (statusInterval) clearInterval(statusInterval);
            statusInterval = setInterval(checkConnectionStatus, 2000);
            statusInterval._interval = 2000;
          }
        } catch (error) {
          console.error('Connection request failed:', error);
        }
      }

      async function scanDevices() {
        const scanBtn = document.getElementById('scanBtn');
        const scanResults = document.getElementById('scanResults');
        const scanStatus = document.getElementById('scanStatus');
        const deviceList = document.getElementById('deviceList');

        scanBtn.disabled = true;
        scanBtn.innerHTML = '<span class="spinner"></span> Scanning...';
        scanResults.style.display = 'block';
        deviceList.innerHTML = '';
        scanStatus.innerHTML = '<span class="spinner"></span> Scanning for devices...';

        try {
          await fetch('/plugins/bt-tether/scan', { method: 'GET' });

          // Poll /scan-progress every 1 second to show devices as they appear
          let pollCount = 0;
          const maxPolls = 30;
          let lastDeviceCount = 0;
          let scanProgressInterval = setInterval(async () => {
            pollCount++;

            try {
              const progressResponse = await fetch('/plugins/bt-tether/scan-progress');
              const progressData = await progressResponse.json();

              if (progressData && progressData.devices) {
                const deviceCount = progressData.devices.length;

                // Update if device count changed or first poll
                if (deviceCount > lastDeviceCount) {
                  lastDeviceCount = deviceCount;
                  deviceList.innerHTML = '';
                  progressData.devices.forEach(device => {
                    const div = document.createElement('div');
                    div.className = 'device-item';
                    div.innerHTML = `
                      <div style="flex: 1; font-family: 'Courier New', monospace; font-size: 12px;">
                        <b>${device.name}</b><br>
                        <small style="color: #888;">${device.mac}</small>
                      </div>
                      <button onclick="pairAndConnectDevice('${device.mac}', '${device.name.replace(/'/g, "\\'")}'); return false;" class="success" style="margin: 0; padding: 6px 12px; font-size: 12px;">Pair</button>
                    `;
                    deviceList.appendChild(div);
                  });
                }

                // Update status
                if (progressData.scanning) {
                  scanStatus.innerHTML = `<span class="spinner"></span> Found ${deviceCount} device(s)... still scanning`;
                } else {
                  clearInterval(scanProgressInterval);
                  if (deviceCount > 0) {
                    scanStatus.textContent = `Scan complete - Found ${deviceCount} device(s):`;
                  } else {
                    scanStatus.textContent = 'Scan complete - No devices found';
                    deviceList.innerHTML = '';
                  }
                  scanBtn.disabled = false;
                  scanBtn.innerHTML = '🔍 Scan';
                }
              }

              if (pollCount >= maxPolls) {
                clearInterval(scanProgressInterval);
                if (lastDeviceCount === 0) {
                  scanStatus.textContent = 'Scan timeout - No devices found';
                }
                scanBtn.disabled = false;
                scanBtn.innerHTML = '🔍 Scan';
              }
            } catch (e) {
              console.error('Scan progress poll error:', e);
            }
          }, 1000);
        } catch (error) {
          scanStatus.textContent = 'Scan failed: ' + error.message;
          scanBtn.disabled = false;
          scanBtn.innerHTML = '🔍 Scan';
          console.error('Scan failed:', error);
        }
      }

      async function pairAndConnectDevice(mac, name) {
        await fetch(`/plugins/bt-tether/pair-device?mac=${encodeURIComponent(mac)}&name=${encodeURIComponent(name)}`);
        macInput.value = mac;
        setTimeout(checkConnectionStatus, 1000);
      }

      async function loadTrustedDevicesSummary() {
        try {
          const response = await fetch('/plugins/bt-tether/trusted-devices');
          const data = await response.json();
          const summaryDiv = document.getElementById('trustedDevicesSummary');
          const deviceDiscoverySection = document.getElementById('deviceDiscoverySection');

          if (data.devices && data.devices.length > 0) {
            const napDevices = data.devices.filter(d => d.has_nap);
            const connectedDevice = napDevices.find(d => d.connected);

            // Hide device discovery section only if a device is actively connected
            if (connectedDevice) {
              deviceDiscoverySection.style.display = 'none';
              summaryDiv.innerHTML = `<span style="color: #3fb950;">🔵 Connected to ${connectedDevice.name}</span><br><small style="color: #888;">${connectedDevice.mac}</small>`;
            } else if (napDevices.length > 0) {
              // Show device list and discovery section if not connected
              deviceDiscoverySection.style.display = 'block';
              summaryDiv.innerHTML = napDevices.map(d =>
                `<div style="margin: 4px 0;">📱 ${d.name}<br><small style="color: #888;">${d.mac}</small></div>`
              ).join('');
            } else {
              // No tethering support
              deviceDiscoverySection.style.display = 'block';
              summaryDiv.innerHTML = `<span style="color: #f85149;">${data.devices.length} paired but no tethering support</span>`;
            }
          } else {
            deviceDiscoverySection.style.display = 'block';
            summaryDiv.innerHTML = '<span style="color: #8b949e;">No paired devices - scan to pair</span>';
          }
        } catch (error) {
          document.getElementById('trustedDevicesSummary').innerHTML = '<span style="color: #f85149;">Error loading devices</span>';
        }
      }

      async function testInternet() {
        const testBtn = document.getElementById('testInternetBtn');
        testBtn.disabled = true;
        const response = await fetch('/plugins/bt-tether/test-internet');
        const data = await response.json();
        const msg = document.getElementById('testResultsMessage');
        msg.innerHTML = `Ping: ${data.ping_success ? '✓' : '✗'} | DNS: ${data.dns_success ? '✓' : '✗'} | IP: ${data.bnep0_ip || 'None'}`;
        testBtn.disabled = false;
      }

      async function disconnectDevice() {
        const mac = macInput.value.trim();
        if (!mac) return;
        await fetch(`/plugins/bt-tether/disconnect?mac=${encodeURIComponent(mac)}`);
        macInput.value = '';
        setTimeout(checkConnectionStatus, 1000);
      }

      async function refreshLogs() {
        try {
          const response = await fetch('/plugins/bt-tether/logs');
          const data = await response.json();
          const logContent = document.getElementById('logContent');
          if (data.logs && data.logs.length > 0) {
            logContent.innerHTML = data.logs.map(log => {
              let color = '#d4d4d4';
              if (log.level === 'ERROR') color = '#f48771';
              else if (log.level === 'WARNING') color = '#dcdcaa';
              else if (log.level === 'INFO') color = '#4fc1ff';
              return `<div><span style="color: #888;">${log.timestamp}</span> <span style="color: ${color};">[${log.level}]</span> ${log.message}</div>`;
            }).join('');
          }
        } catch (error) {
          console.error('Failed to fetch logs:', error);
        }
      }

      function startLogPolling() {
        if (logInterval) clearInterval(logInterval);
        logInterval = setInterval(refreshLogs, 5000);
      }
    </script>
  </body>
</html>"""
        return template
