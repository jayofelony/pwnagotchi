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
from collections import deque
from pwnagotchi.plugins import Plugin
from pwnagotchi.bluetooth import BluetoothService
from pwnagotchi.ui.components import LabeledValue
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.view import BLACK
from flask import render_template_string, request, jsonify


class BtTether(Plugin):
    __author__ = "wsvdmeer (refactored)"
    __version__ = "2.0.0"
    __license__ = "GPL3"
    __description__ = "Bluetooth tethering with delegated core operations"

    # CSRF exempt since this is a trusted local interface
    csrf_exempt = True

    def on_loaded(self):
        """Initialize plugin configuration and core Bluetooth service."""
        self.phone_mac = ""
        self._status = "IDLE"
        self._message = "Ready"
        self._ui_logs = deque(maxlen=100)
        self._ui_log_lock = threading.Lock()
        self._ui_reference = None
        self._screen_needs_refresh = False

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

        self._log("INFO", "Plugin loaded")

    def on_ready(self, agent):
        """Start Bluetooth service when agent is ready."""
        self._log("INFO", "Starting Bluetooth service...")
        if self.bt.start():
            self._log("INFO", "Bluetooth service started")
            # Try auto-connect if auto_reconnect enabled
            if self.auto_reconnect:
                best_device = self.bt.find_best_device()
                if best_device:
                    self._log("INFO", f"Auto-connecting to {best_device.name}...")
                    self.bt.connect(best_device.mac, best_device.name)
        else:
            self._log("ERROR", "Failed to start Bluetooth service")

    def on_unload(self, ui):
        """Cleanup when plugin is unloaded."""
        try:
            self._log("INFO", "Unloading plugin...")
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
            status = self.bt.ui_cache.get()
            icon = self.bt.ui_renderer.get_status_icon(status)
            detailed = self.bt.ui_renderer.format_status(status)

            if self.show_mini_status:
                ui.set("bt-status", icon)
            if self.show_detailed_status:
                ui.set("bt-detail", detailed)

        except Exception as e:
            logging.debug(f"UI update error: {e}")
            if self.show_mini_status:
                ui.set("bt-status", "?")

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
        return jsonify({"success": result})

    def _pair_device(self, mac, name):
        """Pair with device."""
        if not mac:
            return jsonify({"success": False, "message": "No MAC specified"})

        self.phone_mac = mac
        result = self.bt.connect(mac, name)
        return jsonify({"success": result})

    def _scan_devices(self):
        """Start device scan."""
        self._scanned_devices = []
        threading.Thread(target=self._scan_thread, daemon=True).start()
        return jsonify({"success": True})

    def _scan_thread(self):
        """Background thread for scanning."""
        self._scanned_devices = self.bt.scan_devices(duration=30)
        self._log("INFO", f"Scan complete: found {len(self._scanned_devices)} devices")

    def _get_scan_progress(self):
        """Get scan progress."""
        return jsonify({
            "scanning": False,
            "devices": [
                {"mac": d.get("mac", ""), "name": d.get("name", "")}
                for d in getattr(self, "_scanned_devices", [])
            ]
        })

    def _get_status(self):
        """Get current plugin status."""
        return jsonify({
            "status": self._status,
            "message": self._message,
            "mac": self.phone_mac,
            "initialized": self.bt.initialized,
            "scanning": False,
            "connection_in_progress": False,
            "disconnecting": False,
            "untrusting": False,
            "initializing": not self.bt.initialized,
        })

    def _get_connection_status(self, mac):
        """Get connection status for a device."""
        if not mac:
            return jsonify({"success": False})

        status = self.bt.get_status(mac)
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
            "default_route_interface": self.bt.network.get_default_route_interface(),
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

    def _on_connect_success(self, data):
        """Handle successful connection event."""
        mac = data.get("mac")
        name = data.get("name", mac)
        self._log("INFO", f"Connected to {name}")
        self._status = "CONNECTED"
        self._message = f"Connected to {name}"

    def _on_connect_failed(self, data):
        """Handle failed connection event."""
        mac = data.get("mac")
        error = data.get("error", "Unknown error")
        self._log("ERROR", f"Connection failed: {error}")
        self._status = "ERROR"
        self._message = f"Connection failed: {error}"

    def _on_disconnect_success(self, data):
        """Handle successful disconnection event."""
        mac = data.get("mac")
        self._log("INFO", f"Disconnected from {mac}")
        self._status = "IDLE"
        self._message = "Ready"

    def _get_html_template(self):
        """Get HTML template (simplified version)."""
        return """<!DOCTYPE html>
<html>
<head>
    <title>Bluetooth Tether</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
        body { font-family: sans-serif; padding: 20px; background: #0d1117; color: #d4d4d4; }
        .card { background: #161b22; padding: 20px; border-radius: 8px; margin-bottom: 16px; border: 1px solid #30363d; }
        h2 { color: #58a6ff; margin: 0 0 20px 0; }
        button { padding: 10px 20px; background: transparent; color: #3fb950; border: 1px solid #3fb950; cursor: pointer; border-radius: 4px; }
        button:hover { background: rgba(63, 185, 80, 0.1); }
        input { padding: 10px; font-size: 14px; border: 1px solid #30363d; border-radius: 4px; background: #0d1117; color: #d4d4d4; }
        .status-item { padding: 8px; margin: 4px 0; border-radius: 4px; background: #0d1117; border: 1px solid #30363d; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🔷 Bluetooth Tether (Refactored)</h2>
        <div style="font-size: 12px; color: #8b949e; margin-top: 2px;">v{{ version }}</div>

        <div style="margin-top: 20px;">
            <h3>Status</h3>
            <div id="status" class="status-item">Loading...</div>
        </div>

        <div style="margin-top: 20px;">
            <h3>Trusted Devices</h3>
            <div id="devices" class="status-item">Loading...</div>
        </div>

        <div style="margin-top: 20px;">
            <h3>Actions</h3>
            <input type="text" id="mac" placeholder="Enter MAC address" value="{{ mac }}" />
            <button onclick="connect()">Connect</button>
            <button onclick="disconnect()">Disconnect</button>
        </div>

        <div style="margin-top: 20px;">
            <h3>Logs</h3>
            <div id="logs" style="background: #0d1117; padding: 12px; border-radius: 4px; font-family: monospace; font-size: 12px; max-height: 300px; overflow-y: auto;">
                <div style="color: #888;">Loading logs...</div>
            </div>
        </div>
    </div>

    <script>
        async function updateStatus() {
            try {
                const response = await fetch('/plugins/bt-tether/status');
                const data = await response.json();
                document.getElementById('status').innerHTML = `
                    Status: ${data.status}<br>
                    Message: ${data.message}
                `;
            } catch (e) { console.error(e); }
        }

        async function updateDevices() {
            try {
                const response = await fetch('/plugins/bt-tether/trusted-devices');
                const data = await response.json();
                const html = data.devices.map(d => `
                    <div style="margin: 8px 0;">
                        <b>${d.name}</b> (${d.mac})<br>
                        Paired: ${d.paired ? 'Yes' : 'No'} | Connected: ${d.connected ? 'Yes' : 'No'}
                    </div>
                `).join('');
                document.getElementById('devices').innerHTML = html || 'No devices found';
            } catch (e) { console.error(e); }
        }

        async function updateLogs() {
            try {
                const response = await fetch('/plugins/bt-tether/logs');
                const data = await response.json();
                const html = data.logs.map(log => `
                    <div><span style="color: #888;">${log.timestamp}</span> <span style="color: #58a6ff;">[${log.level}]</span> ${log.message}</div>
                `).join('');
                document.getElementById('logs').innerHTML = html || 'No logs';
            } catch (e) { console.error(e); }
        }

        async function connect() {
            const mac = document.getElementById('mac').value;
            if (!mac) { alert('Enter MAC'); return; }
            await fetch(`/plugins/bt-tether/connect?mac=${encodeURIComponent(mac)}`);
            updateStatus();
        }

        async function disconnect() {
            const mac = document.getElementById('mac').value;
            if (!mac) { alert('Enter MAC'); return; }
            await fetch(`/plugins/bt-tether/disconnect?mac=${encodeURIComponent(mac)}`);
            updateStatus();
        }

        setInterval(updateStatus, 2000);
        setInterval(updateDevices, 5000);
        setInterval(updateLogs, 5000);
        updateStatus();
        updateDevices();
        updateLogs();
    </script>
</body>
</html>"""
