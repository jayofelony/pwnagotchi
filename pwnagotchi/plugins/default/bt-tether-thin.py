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
        """Get the original full-featured HTML template."""
        # This template is extracted from the original bt-tether.py
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

      loadTrustedDevicesSummary();
      setTimeout(checkConnectionStatus, 1000);
      refreshLogs();
      startLogPolling();

      async function checkConnectionStatus() {
        const mac = macInput.value.trim();
        if (!mac || !/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(mac)) {
          const connectBtn = document.getElementById('quickConnectBtn');
          connectBtn.style.display = 'none';
          return;
        }

        try {
          const response = await fetch(`/plugins/bt-tether/connection-status?mac=${encodeURIComponent(mac)}`);
          const data = await response.json();
          updateStatusDisplay(data);
        } catch (error) {
          console.error('Status check failed:', error);
        }
      }

      function updateStatusDisplay(data) {
        document.getElementById("statusPaired").innerHTML =
          `📱 Paired: <span style="color: ${data.paired ? '#4ec9b0' : '#f48771'};">${data.paired ? '✓ Yes' : '✗ No'}</span>`;
        document.getElementById("statusTrusted").innerHTML =
          `🔐 Trusted: <span style="color: ${data.trusted ? '#4ec9b0' : '#f48771'};">${data.trusted ? '✓ Yes' : '✗ No'}</span>`;
        document.getElementById("statusConnected").innerHTML =
          `🔵 Connected: <span style="color: ${data.connected ? '#4ec9b0' : '#f48771'};">${data.connected ? '✓ Yes' : '✗ No'}</span>`;
        document.getElementById("statusInternet").innerHTML =
          `🌐 Internet: <span style="color: ${data.pan_active ? '#4ec9b0' : '#f48771'};">${data.pan_active ? '✓ Active' : '✗ Not Active'}</span>`;

        const statusIPElement = document.getElementById('statusIP');
        if (data.ip_address && data.pan_active) {
          statusIPElement.style.display = 'block';
          statusIPElement.innerHTML = `🔢 IP Address: <span style="color: #4ec9b0;">${data.ip_address}</span>`;
        } else {
          statusIPElement.style.display = 'none';
        }

        const testInternetCard = document.getElementById('testInternetCard');
        if (data.pan_active) {
          testInternetCard.style.display = 'block';
        } else {
          testInternetCard.style.display = 'none';
        }

        const connectBtn = document.getElementById('quickConnectBtn');
        const disconnectSection = document.getElementById('disconnectSection');

        if (data.connected) {
          connectBtn.style.display = 'none';
          disconnectSection.style.display = 'block';
        } else if (data.paired) {
          connectBtn.style.display = 'block';
          disconnectSection.style.display = 'block';
        } else {
          connectBtn.style.display = 'block';
          disconnectSection.style.display = 'none';
        }

        if (!statusInterval || statusInterval._interval !== 10000) {
          if (statusInterval) clearInterval(statusInterval);
          statusInterval = setInterval(checkConnectionStatus, 10000);
          statusInterval._interval = 10000;
        }
      }

      async function quickConnect() {
        const mac = macInput.value.trim();
        if (!mac || !/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(mac)) {
          alert("Enter valid MAC address");
          return;
        }
        await fetch(`/plugins/bt-tether/connect?mac=${encodeURIComponent(mac)}`);
        setTimeout(checkConnectionStatus, 1000);
      }

      async function scanDevices() {
        const scanBtn = document.getElementById('scanBtn');
        const deviceList = document.getElementById('deviceList');
        scanBtn.disabled = true;
        scanBtn.innerHTML = '<span class="spinner"></span> Scanning...';
        deviceList.innerHTML = '';
        await fetch('/plugins/bt-tether/scan');
        await new Promise(r => setTimeout(r, 1000));
        const response = await fetch('/plugins/bt-tether/scan-progress');
        const data = await response.json();
        deviceList.innerHTML = data.devices.map(d =>
          `<div class="device-item"><div><b>${d.name}</b><br><small style="color: #888;">${d.mac}</small></div>
           <button class="success" onclick="pairAndConnectDevice('${d.mac}', '${d.name}'); return false;">Pair</button></div>`
        ).join('');
        scanBtn.disabled = false;
        scanBtn.innerHTML = '🔍 Scan';
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
            deviceDiscoverySection.style.display = 'none';
            const napDevices = data.devices.filter(d => d.has_nap);
            if (napDevices.length > 0) {
              summaryDiv.innerHTML = napDevices.map(d =>
                `<div style="margin: 4px 0;">📱 ${d.name}<br><small style="color: #888;">${d.mac}</small></div>`
              ).join('');
            } else {
              summaryDiv.innerHTML = `<span style="color: #f85149;">${data.devices.length} paired but no tethering support</span>`;
              deviceDiscoverySection.style.display = 'block';
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
