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
    __version__ = "2.2.0"
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

            # Look for a connected device with NAP when the stored MAC has none.
            # A paired but absent device still answers with a status dict, so
            # testing the dict alone latches onto the first device ever seen and
            # keeps reporting it after tethering moved to another one.
            # The rescan result is copied over only when it is actually connected,
            # so a scan that finds nothing leaves the previous status in place and
            # the display keeps the P (paired) vs X (no device) distinction.
            if not cached_status or not cached_status.get("connected", False):
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

            # Rendering (glyph + detailed line) lives in the core UIRenderer so the
            # logic is shared and testable. Transient flags: bt_stuck is a wedged
            # controller needing a power-cycle, bt_recovering an active recovery
            # (restart/module reload) and link_stalled a suspect half-open link -
            # each shown instead of a misleading Paired/Connected/IP.
            bt_stuck = self.bt.bt_stuck
            recovering = self.bt.bt_recovering
            stalled = self.bt.monitor.link_stalled
            renderer = self.bt.ui_renderer
            detailed = renderer.format_status(cached_status, bt_stuck=bt_stuck, recovering=recovering, stalled=stalled)
            # Keep the bare text for /status (the "BT:" prefix is display-only)
            self._message = detailed[3:] if detailed.startswith("BT:") else detailed

            if self.show_mini_status:
                ui.set("bt-status", renderer.get_status_icon(cached_status, bt_stuck=bt_stuck, recovering=recovering, stalled=stalled))

            if self.show_detailed_status:
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

        # Report the CORE service state (CONNECTING/PAIRING/TRUSTING/...), not the
        # plugin's IDLE/CONNECTED/ERROR shadow - the web UI gates its live refresh
        # on this to show in-progress pair/connect operations.
        core_status = self.bt.status
        in_progress = core_status in ("PAIRING", "TRUSTING", "CONNECTING", "RECONNECTING")
        return jsonify({
            "status": core_status,
            "message": self._message,
            "mac": current_mac,
            "initialized": self.bt.initialized,
            "scanning": core_status == "SCANNING",
            "connection_in_progress": in_progress,
            "disconnecting": core_status == "DISCONNECTING",
            "untrusting": False,
            "initializing": not self.bt.initialized,
            "bt_stuck": self.bt.bt_stuck,
            "bt_recovering": self.bt.bt_recovering,
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
        template = """{% extends "base.html" %}
{% set active_page = "plugins" %}
{% block title %}Bluetooth Tether{% endblock %}

{% block styles %}
    {{ super() }}
    <style>
      .bt-chips { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:0.8rem; margin-bottom:1.5rem; }
      .bt-chip { background:var(--card-bg); border:1px solid var(--border-color); border-radius:12px; padding:0.9rem 1rem; display:flex; flex-direction:column; gap:0.35rem; }
      .bt-chip .k { font-size:0.66rem; text-transform:uppercase; letter-spacing:0.6px; color:var(--text-muted); }
      .bt-chip .v { font-family:var(--font-pixel); font-size:1.35rem; letter-spacing:0.5px; display:flex; align-items:center; gap:0.45rem; min-height:1.5rem; }
      .bt-chip .v svg { width:19px; height:19px; flex:0 0 auto; }
      .bt-ok { color:var(--accent); } .bt-no { color:var(--danger); } .bt-warn { color:#f0b03c; } .bt-dim { color:var(--text-muted); }
      .bt-banner { padding:0.7rem 1rem; border-radius:8px; margin-bottom:1.5rem; font-size:0.9rem; font-weight:600; color:#fff; }
      .bt-summary { color:var(--text-main); font-size:0.9rem; line-height:1.6; }
      .bt-summary small { color:var(--text-muted); font-family:monospace; }
      .bt-ip { margin-top:0.7rem; padding-top:0.7rem; border-top:1px solid var(--border-color); color:var(--text-secondary); font-size:0.85rem; }
      .bt-ip strong { color:var(--accent); font-family:monospace; }
      .bt-log { background:#0d0d0d; border:1px solid var(--border-color); border-radius:8px; padding:0.8rem 1rem; font-family:monospace; font-size:0.78rem; line-height:1.7; max-height:220px; overflow-y:auto; overscroll-behavior:contain; -webkit-overflow-scrolling:touch; }
      .bt-actions { display:flex; flex-wrap:wrap; gap:10px; margin:1.5rem 0; }
      .bt-actions > * { flex:1 1 45%; }
      .bt-actions button { width:100%; }
      .bt-hint { color:var(--text-muted); font-size:0.85rem; margin-bottom:1rem; }
      .bt-scan form { margin:0; } .bt-scan .btn { width:100%; }
      #testInternetCard form { margin:0; } #testInternetBtn { width:100%; }
      .device-item { display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:0.7rem 0.9rem; margin:0.5rem 0; border:1px solid var(--border-color); border-radius:10px; background:var(--bg-secondary); font-family:monospace; font-size:0.8rem; }
      .device-item small { color:var(--text-muted); }
      .device-item .btn { min-width:0; padding:6px 16px; font-size:0.9rem; }
      .bt-msg { padding:0.8rem 1rem; border-radius:8px; background:var(--bg-secondary); border:1px solid var(--border-color); color:var(--text-main); font-family:monospace; font-size:0.85rem; }
      .spinner { display:inline-block; width:14px; height:14px; border:2px solid var(--border-color); border-top:2px solid var(--accent); border-radius:50%; animation:btspin 1s linear infinite; margin-right:8px; vertical-align:middle; }
      @keyframes btspin { 0% { transform:rotate(0deg); } 100% { transform:rotate(360deg); } }
    </style>
{% endblock %}

{% block content %}
    <div class="plugin-page-header">
      <div class="header-nav"><a href="/plugins" class="btn ghost">&#8592; Plugins</a><span class="header-version">v{{ version }}</span></div>
      <h2>Bluetooth Tether</h2>
      <p>Share your phone's internet over Bluetooth</p>
    </div>

    <input type="hidden" id="macInput" value="{{ mac }}" />

    <div class="bt-chips">
      <div class="bt-chip"><span class="k">Paired</span><span class="v bt-dim" id="statusPaired">Checking&#8230;</span></div>
      <div class="bt-chip"><span class="k">Trusted</span><span class="v bt-dim" id="statusTrusted">Checking&#8230;</span></div>
      <div class="bt-chip"><span class="k">Connected</span><span class="v bt-dim" id="statusConnected">Checking&#8230;</span></div>
      <div class="bt-chip"><span class="k">Internet</span><span class="v bt-dim" id="statusInternet">Checking&#8230;</span></div>
    </div>

    <div id="statusBanner" class="bt-banner" style="display:none;"></div>

    <div class="card">
      <div class="card-header">Trusted device</div>
      <div class="card-body">
        <div id="trustedDevicesSummary" class="bt-summary">Initializing&#8230;</div>
        <div id="statusIP" class="bt-ip" style="display:none;"></div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">Output</div>
      <div class="card-body"><div class="bt-log" id="logContent"><div class="bt-dim">Fetching logs&#8230;</div></div></div>
    </div>

    <div class="bt-actions">
      <button type="button" class="btn" onclick="quickConnect()" id="quickConnectBtn">Connect</button>
      <div id="disconnectSection" style="display:none;"><button type="button" class="btn danger" onclick="disconnectDevice()" id="disconnectBtn">Disconnect</button></div>
    </div>

    <div class="card bt-scan" id="deviceDiscoverySection" style="display:none;">
      <div class="card-header">Discover devices</div>
      <div class="card-body">
        <p class="bt-hint">Scan for nearby Bluetooth devices to pair a new phone.</p>
        <form><button type="button" class="btn ghost" onclick="scanDevices()" id="scanBtn">Scan</button></form>
        <div id="scanResults" style="display:none; margin-top:1rem;">
          <div id="scanStatus" class="bt-dim" style="margin-bottom:0.5rem; font-size:0.85rem;">Scanning&#8230;</div>
          <div id="deviceList"></div>
        </div>
      </div>
    </div>

    <div class="card" id="testInternetCard" style="display:none;">
      <div class="card-header">Test internet</div>
      <div class="card-body">
        <form><button type="button" class="btn" onclick="testInternet()" id="testInternetBtn">Test internet</button></form>
        <div id="testResults" style="display:none; margin-top:1rem;"><div id="testResultsMessage" class="bt-msg"></div></div>
      </div>
    </div>

    <div class="plugin-footer">Built by <a href="https://github.com/wsvdmeer" target="_blank" rel="noopener">wsvdmeer</a></div>
{% endblock %}

{% block script %}
      const macInput = document.getElementById("macInput");
      let statusInterval = null;
      let logInterval = null;

      const BT_CHK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
      const BT_CRS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

      // Bluetooth device names are attacker-controllable - escape before inserting
      // into innerHTML so a crafted name can't inject markup/script.
      function escapeHtml(s) {
        return String(s == null ? '' : s)
          .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
      }

      // Update a status tile's value span: kind = ok | no | warn | dim.
      // `text` is treated as trusted markup (callers pass fixed labels or
      // pre-escaped values).
      function setStat(id, kind, text) {
        const el = document.getElementById(id);
        if (!el) return;
        const icon = kind === 'ok' ? BT_CHK : (kind === 'no' ? BT_CRS : '');
        el.className = 'v bt-' + kind;
        el.innerHTML = icon + '<span>' + text + '</span>';
      }

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
        setStat('statusPaired', 'dim', 'Initializing…');
        setStat('statusTrusted', 'dim', 'Initializing…');
        setStat('statusConnected', 'dim', 'Initializing…');
        setStat('statusInternet', 'dim', 'Initializing…');
        document.getElementById('statusIP').style.display = 'none';

        const connectBtn = document.getElementById('quickConnectBtn');
        connectBtn.disabled = true;
        connectBtn.innerHTML = '<span class="spinner"></span> Initializing…';
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
              setStat('statusPaired', 'no', 'No');
              setStat('statusTrusted', 'no', 'No');
              setStat('statusConnected', 'no', 'No');
              setStat('statusInternet', 'no', 'Not Active');

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
            connectBtn.innerHTML = 'Connect';
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

          setStat('statusPaired', paired ? 'ok' : 'no', paired ? 'Yes' : 'No');
          setStat('statusTrusted', trusted ? 'ok' : 'no', trusted ? 'Yes' : 'No');
          setStat('statusConnected', connected ? 'ok' : 'no', connected ? 'Yes' : 'No');
          // A PAN that's up but has no IP is half-open, not "Active" - show No IP.
          const online = pan_active && !!ip_address;
          const netKind = online ? 'ok' : (pan_active ? 'warn' : 'no');
          const netLabel = online ? 'Active' : (pan_active ? 'No IP' : 'Not Active');
          const netText = netLabel + (data.interface ? ' (' + escapeHtml(data.interface) + ')' : '');
          setStat('statusInternet', netKind, netText);

          // Trouble banner: surface stuck/recovering/stalled/messages the boolean
          // rows can't convey, so the page explains what's happening.
          const banner = document.getElementById('statusBanner');
          if (banner) {
            let text = '', bg = '';
            if (statusData.bt_stuck) {
              text = 'Bluetooth controller stuck &#8212; a power-cycle may be needed'; bg = '#5a1e1e';
            } else if (statusData.bt_recovering) {
              text = 'Recovering Bluetooth&#8230;'; bg = '#5a4a1e';
            } else if (pan_active && !ip_address) {
              text = 'Link up but no IP (DHCP not completed / half-open)'; bg = '#5a4a1e';
            } else if (!online && statusData.message && /stall|half-open|recover|wedge|stuck/i.test(statusData.message)) {
              // Only surface a stall/recover message when we're NOT actually online.
              // A link that's up with a leased IP shouldn't show a stale "Stalled?" banner.
              text = escapeHtml(statusData.message); bg = '#5a4a1e';
            }
            if (text) { banner.style.display = 'block'; banner.style.background = bg; banner.innerHTML = text; }
            else { banner.style.display = 'none'; }
          }

          const statusIPElement = document.getElementById('statusIP');
          if (ip_address && pan_active) {
            statusIPElement.style.display = 'block';
            statusIPElement.innerHTML = 'IP address: <strong>' + escapeHtml(ip_address) + '</strong>';
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
            connectBtn.innerHTML = '<span class="spinner"></span> Connecting…';
            connectBtn.style.display = 'block';
            disconnectSection.style.display = 'none';
          } else {
            connectBtn.disabled = false;
            connectBtn.innerHTML = 'Connect';

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
        scanBtn.innerHTML = '<span class="spinner"></span> Scanning…';
        scanResults.style.display = 'block';
        deviceList.innerHTML = '';
        scanStatus.innerHTML = '<span class="spinner"></span> Scanning for devices…';

        try {
          await fetch('/plugins/bt-tether/scan', { method: 'GET' });

          let pollCount = 0;
          const maxPolls = 40;
          let lastDeviceCount = 0;
          let scanProgressInterval = setInterval(async () => {
            pollCount++;

            try {
              const progressResponse = await fetch('/plugins/bt-tether/scan-progress');
              const progressData = await progressResponse.json();

              if (progressData && progressData.devices) {
                const deviceCount = progressData.devices.length;

                if (deviceCount > lastDeviceCount) {
                  lastDeviceCount = deviceCount;
                  deviceList.innerHTML = '';
                  progressData.devices.forEach(device => {
                    const div = document.createElement('div');
                    div.className = 'device-item';
                    const encName = encodeURIComponent(device.name || '');
                    const encMac = encodeURIComponent(device.mac || '');
                    div.innerHTML = `
                      <div style="flex: 1;">
                        <b>${escapeHtml(device.name)}</b><br>
                        <small>${escapeHtml(device.mac)}</small>
                      </div>
                      <button onclick="pairAndConnectDevice(decodeURIComponent('${encMac}'), decodeURIComponent('${encName}')); return false;" class="btn">Pair</button>
                    `;
                    deviceList.appendChild(div);
                  });
                }

                if (progressData.scanning) {
                  scanStatus.innerHTML = `<span class="spinner"></span> Found ${deviceCount} device(s)… still scanning`;
                } else {
                  clearInterval(scanProgressInterval);
                  if (deviceCount > 0) {
                    scanStatus.textContent = `Scan complete - Found ${deviceCount} device(s):`;
                  } else {
                    scanStatus.textContent = 'Scan complete - No devices found';
                    deviceList.innerHTML = '';
                  }
                  scanBtn.disabled = false;
                  scanBtn.innerHTML = 'Scan';
                }
              }

              if (pollCount >= maxPolls) {
                clearInterval(scanProgressInterval);
                if (lastDeviceCount > 0) {
                  scanStatus.textContent = `Scan complete - Found ${lastDeviceCount} device(s):`;
                } else {
                  scanStatus.textContent = 'Scan timeout - No devices found';
                }
                scanBtn.disabled = false;
                scanBtn.innerHTML = 'Scan';
              }
            } catch (e) {
              console.error('Scan progress poll error:', e);
            }
          }, 1000);
        } catch (error) {
          scanStatus.textContent = 'Scan failed: ' + error.message;
          scanBtn.disabled = false;
          scanBtn.innerHTML = 'Scan';
          console.error('Scan failed:', error);
        }
      }

      async function pairAndConnectDevice(mac, name) {
        macInput.value = mac;
        const scanStatus = document.getElementById('scanStatus');
        const deviceList = document.getElementById('deviceList');
        const scanResults = document.getElementById('scanResults');
        if (scanStatus) scanStatus.innerHTML = `<span class="spinner"></span> Pairing with ${escapeHtml(name)}…`;
        if (deviceList) deviceList.innerHTML = '';
        try {
          await fetch(`/plugins/bt-tether/pair-device?mac=${encodeURIComponent(mac)}&name=${encodeURIComponent(name)}`);
        } catch (e) {
          console.error('Pair failed:', e);
        }
        if (scanResults) scanResults.style.display = 'none';
        loadTrustedDevicesSummary();
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

            if (connectedDevice) {
              deviceDiscoverySection.style.display = 'none';
              summaryDiv.innerHTML = `<span style="color: var(--accent);">Connected to ${escapeHtml(connectedDevice.name)}</span><br><small>${escapeHtml(connectedDevice.mac)}</small>`;
            } else if (napDevices.length > 0) {
              deviceDiscoverySection.style.display = 'block';
              summaryDiv.innerHTML = napDevices.map(d =>
                `<div style="margin: 4px 0;">${escapeHtml(d.name)}<br><small>${escapeHtml(d.mac)}</small></div>`
              ).join('');
            } else {
              deviceDiscoverySection.style.display = 'block';
              summaryDiv.innerHTML = `<span style="color: var(--danger);">${data.devices.length} paired but no tethering support</span>`;
            }
          } else {
            deviceDiscoverySection.style.display = 'block';
            summaryDiv.innerHTML = '<span style="color: var(--text-muted);">No paired devices - scan to pair</span>';
          }
        } catch (error) {
          document.getElementById('trustedDevicesSummary').innerHTML = '<span style="color: var(--danger);">Error loading devices</span>';
        }
      }

      async function testInternet() {
        const testBtn = document.getElementById('testInternetBtn');
        testBtn.disabled = true;
        const response = await fetch('/plugins/bt-tether/test-internet');
        const data = await response.json();
        const msg = document.getElementById('testResultsMessage');
        document.getElementById('testResults').style.display = 'block';
        msg.innerHTML = `Ping: ${data.ping_success ? '✓' : '✗'} | DNS: ${data.dns_success ? '✓' : '✗'} | IP: ${escapeHtml(data.bnep0_ip || 'None')}`;
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
            // Preserve the reader's scroll position across the 5s refresh; only
            // snap to the bottom if they were already at the bottom (tailing).
            var atBottom = logContent.scrollTop + logContent.clientHeight >= logContent.scrollHeight - 4;
            var prevTop = logContent.scrollTop;
            logContent.innerHTML = data.logs.map(log => {
              let color = 'var(--text-main)';
              if (log.level === 'ERROR') color = 'var(--danger)';
              else if (log.level === 'WARNING') color = '#f0b03c';
              else if (log.level === 'INFO') color = 'var(--info)';
              return `<div><span style="color: var(--text-muted);">${escapeHtml(log.timestamp)}</span> <span style="color: ${color};">[${escapeHtml(log.level)}]</span> ${escapeHtml(log.message)}</div>`;
            }).join('');
            logContent.scrollTop = atBottom ? logContent.scrollHeight : prevTop;
          }
        } catch (error) {
          console.error('Failed to fetch logs:', error);
        }
      }

      function startLogPolling() {
        if (logInterval) clearInterval(logInterval);
        logInterval = setInterval(refreshLogs, 5000);
      }
{% endblock %}"""
        return template
