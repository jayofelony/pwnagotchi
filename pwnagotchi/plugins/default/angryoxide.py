import glob
import logging
import os
import shutil
import signal
import subprocess
import threading
import time

import pwnagotchi.plugins as plugins
from flask import render_template_string, jsonify

WHITELIST_FILE = '/tmp/angryoxide_whitelist.txt'

STATUS_TEMPLATE = """
{% extends "base.html" %}
{% set active_page = "plugins" %}
{% block title %}AngryOxide | {{ title }}{% endblock %}
{% block styles %}
{{ super() }}
<style>
    .ao-status { padding: 16px; }
    .ao-card {
        background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px;
        padding: 16px; margin-bottom: 16px;
    }
    .ao-card h3 { margin: 0 0 12px 0; }
    .ao-grid { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
    .ao-stat {
        background: #fff; border: 1px solid #ddd; border-radius: 4px;
        padding: 12px 20px; text-align: center; min-width: 120px;
    }
    .ao-stat .num { font-size: 28px; font-weight: bold; }
    .ao-stat .label { font-size: 11px; color: #666; }
    .ao-running { color: #4CAF50; font-weight: bold; }
    .ao-stopped { color: #f44336; font-weight: bold; }
    .ao-na { color: #999; }
    table.ao-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    table.ao-table th { background: #333; color: #fff; padding: 8px; text-align: left; }
    table.ao-table td { padding: 6px 8px; border-bottom: 1px solid #ddd; }
    .ao-btn {
        padding: 8px 16px; border: 1px solid #999; background: #eee;
        cursor: pointer; border-radius: 4px; margin-right: 8px;
    }
    .ao-btn:hover { background: #ddd; }
    .ao-log { background: #111; color: #0f0; padding: 12px; font-family: monospace;
              font-size: 12px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; }
</style>
{% endblock %}
{% block script %}
function aoAction(action) {
    fetch('/plugins/angryoxide/api/' + action, {method: 'POST'})
        .then(function(r) { return r.json(); })
        .then(function() { setTimeout(function() { location.reload(); }, 1000); });
}
function refreshStatus() {
    fetch('/plugins/angryoxide/api/status')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            document.getElementById('ao-state').textContent = d.running ? 'RUNNING' : 'STOPPED';
            document.getElementById('ao-state').className = d.running ? 'ao-running' : 'ao-stopped';
            document.getElementById('ao-iface').textContent = d.interface || '-';
            document.getElementById('ao-captures').textContent = d.capture_count || 0;
            document.getElementById('ao-last').textContent = d.last_capture || '-';
            document.getElementById('ao-uptime').textContent = d.uptime || '-';
        });
}
setInterval(refreshStatus, 5000);
{% endblock %}
{% block content %}
<div class="ao-status">
    <h2>AngryOxide - WiFi Attack Engine</h2>
    <div class="ao-grid">
        <div class="ao-stat"><div class="num" id="ao-state">{{ 'RUNNING' if running else 'STOPPED' }}</div><div class="label">Status</div></div>
        <div class="ao-stat"><div class="num" id="ao-iface">{{ interface }}</div><div class="label">Interface</div></div>
        <div class="ao-stat"><div class="num" id="ao-captures">{{ capture_count }}</div><div class="label">Captures</div></div>
        <div class="ao-stat"><div class="num" id="ao-uptime">{{ uptime }}</div><div class="label">Uptime</div></div>
    </div>
    <div class="ao-card">
        <h3>Controls</h3>
        <button class="ao-btn" onclick="aoAction('start')">Start</button>
        <button class="ao-btn" onclick="aoAction('stop')">Stop</button>
        <button class="ao-btn" onclick="aoAction('restart')">Restart</button>
    </div>
    {% if captures %}
    <div class="ao-card">
        <h3>Captured Handshakes ({{ captures|length }})</h3>
        <p>Last capture: <span id="ao-last">{{ last_capture }}</span></p>
        <table class="ao-table">
            <thead><tr><th>SSID</th><th>BSSID</th><th>Type</th><th>Time</th></tr></thead>
            <tbody>
            {% for c in captures %}
                <tr><td>{{ c.ssid }}</td><td>{{ c.bssid }}</td><td>{{ c.type }}</td><td>{{ c.time }}</td></tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}
    {% if log_lines %}
    <div class="ao-card">
        <h3>Recent Log</h3>
        <div class="ao-log">{{ log_lines }}</div>
    </div>
    {% endif %}
</div>
{% endblock %}
"""


class AngryOxide(plugins.Plugin):
    __author__ = "pwnagotchi community"
    __version__ = "2.0.0"
    __license__ = "GPL3"
    __description__ = "Replace bettercap with AngryOxide for WiFi attacks (PMKID/deauth/CSA/rogue)."

    def __init__(self):
        self.ready = False
        self._available = False
        self._binary = None
        self._agent = None
        self._process = None
        self._running = False
        self._iface = None
        self._captures = {}
        self._last_capture = None
        self._start_time = None
        self._monitor_thread = None
        self._monitor_stop = threading.Event()
        self._log_thread = None
        self._log_lines = []
        self._log_lock = threading.Lock()
        self._processed_hashes = set()
        self._crash_count = 0
        self._max_crashes = 5

    def on_loaded(self):
        logging.info("[angryoxide] plugin loaded")

    def on_config_changed(self, config):
        self.config = config
        self.ready = True

    def on_ready(self, agent):
        self._agent = agent

        # find binary
        binary = self.options.get('binary', '/usr/bin/angryoxide')
        if os.path.isfile(binary):
            self._binary = binary
        else:
            found = shutil.which('angryoxide')
            if found:
                self._binary = found
            else:
                logging.warning("[angryoxide] binary not found at %s or in PATH — plugin disabled", binary)
                self._set_status(agent, 'AO not installed')
                return

        self._available = True
        logging.info("[angryoxide] binary found at %s", self._binary)

        # resolve interface
        self._iface = self._resolve_interface()
        if not self._iface:
            logging.error("[angryoxide] no monitor interface found — plugin disabled")
            self._available = False
            self._set_status(agent, 'AO: no monitor iface')
            return

        # create output directory
        output_dir = self.options.get('output_dir', '/tmp/angryoxide')
        os.makedirs(output_dir, exist_ok=True)

        # write whitelist file from pwnagotchi config
        self._write_whitelist()

        # disable bettercap wifi to free the interface for AO
        self._disable_bettercap_wifi(agent)

        # kill any orphaned angryoxide processes
        self._kill_orphans()

        # start angryoxide
        self._start_angryoxide()

        # start monitoring thread
        self._monitor_stop.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def on_unload(self):
        logging.info("[angryoxide] unloading — stopping AO, restoring bettercap wifi")
        self._monitor_stop.set()
        self._stop_angryoxide()
        self._enable_bettercap_wifi()

    # --- Interface ---

    def _resolve_interface(self):
        """Find the monitor interface to use."""
        iface_opt = self.options.get('interface', 'auto')

        if iface_opt != 'auto':
            if os.path.exists('/sys/class/net/%s' % iface_opt):
                return iface_opt
            logging.warning("[angryoxide] configured interface %s not found", iface_opt)

        # auto-detect: prefer wlan0mon, then any monitor interface
        bcap_iface = self.config.get('main', {}).get('iface', 'wlan0mon')
        if os.path.exists('/sys/class/net/%s' % bcap_iface):
            return bcap_iface

        # scan for any monitor interface
        for name in os.listdir('/sys/class/net'):
            type_path = '/sys/class/net/%s/type' % name
            try:
                with open(type_path) as f:
                    if f.read().strip() == '803':
                        return name
            except Exception:
                pass

        return None

    # --- Bettercap control ---

    def _disable_bettercap_wifi(self, agent):
        """Tell bettercap to release the WiFi interface so AO can use it."""
        try:
            agent.run('wifi.recon off')
            time.sleep(1)
            agent.run('wifi.clear')
            logging.info("[angryoxide] disabled bettercap wifi recon — interface freed for AO")
        except Exception as e:
            logging.warning("[angryoxide] failed to disable bettercap wifi: %s", e)

    def _enable_bettercap_wifi(self):
        """Restore bettercap wifi recon."""
        try:
            if self._agent:
                self._agent.run('wifi.recon on')
                logging.info("[angryoxide] restored bettercap wifi recon")
        except Exception as e:
            logging.warning("[angryoxide] failed to restore bettercap wifi: %s", e)

    # --- Whitelist ---

    def _write_whitelist(self):
        """Write pwnagotchi whitelist to file for angryoxide --whitelist."""
        entries = self.config.get('main', {}).get('whitelist', [])
        if not entries:
            return
        try:
            with open(WHITELIST_FILE, 'w') as f:
                for entry in entries:
                    e = entry.strip()
                    if e:
                        f.write(e + '\n')
            logging.info("[angryoxide] wrote %d whitelist entries", len(entries))
        except Exception as e:
            logging.debug("[angryoxide] whitelist write error: %s", e)

    # --- Process management ---

    def _kill_orphans(self):
        """Kill any orphaned angryoxide processes."""
        try:
            subprocess.run(['pkill', '-9', '-f', 'angryoxide'], capture_output=True, timeout=5)
            time.sleep(1)
        except Exception:
            pass

    def _build_command(self):
        """Build the angryoxide CLI command."""
        output_dir = self.options.get('output_dir', '/tmp/angryoxide')
        rate = self.options.get('rate', 2)

        cmd = [
            self._binary,
            '-i', self._iface,
            '--headless',
            '--notar',
            '--autohunt',
            '-o', os.path.join(output_dir, 'capture'),
            '-r', str(rate),
        ]

        # whitelist
        if os.path.isfile(WHITELIST_FILE):
            cmd.extend(['--whitelist', WHITELIST_FILE])

        # target list (optional static targets)
        target_list = self.options.get('target_list', '')
        if target_list and os.path.isfile(target_list):
            cmd.extend(['--targetlist', target_list])

        # attack toggles
        if self.options.get('disable_deauth', False):
            cmd.append('--disable-deauth')
        if self.options.get('disable_pmkid', False):
            cmd.append('--disable-pmkid')

        # channels
        channels = self.options.get('channels', '')
        if channels:
            cmd.extend(['-c', str(channels)])

        # combine hc22000 files
        cmd.append('--combine')

        return cmd

    def _start_angryoxide(self):
        """Launch angryoxide subprocess."""
        if self._running:
            return

        cmd = self._build_command()
        logging.info("[angryoxide] starting: %s", ' '.join(cmd))

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid
            )
            self._running = True
            self._start_time = time.time()

            # start log reader thread
            self._log_thread = threading.Thread(target=self._read_output, daemon=True)
            self._log_thread.start()

            self._set_status(self._agent, 'AO hunting...', '(⌐■_■)')
            logging.info("[angryoxide] started (PID %d) on %s", self._process.pid, self._iface)

        except Exception as e:
            logging.error("[angryoxide] failed to start: %s", e)
            self._running = False
            self._set_status(self._agent, 'AO start failed: %s' % e)

    def _stop_angryoxide(self):
        """Stop angryoxide subprocess."""
        if not self._process:
            self._running = False
            return

        try:
            os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                self._process.wait(timeout=3)
            logging.info("[angryoxide] stopped (exit code %s)", self._process.returncode)
        except ProcessLookupError:
            pass
        except Exception as e:
            logging.debug("[angryoxide] stop error: %s", e)
        finally:
            self._process = None
            self._running = False

    def _read_output(self):
        """Read angryoxide stdout/stderr and log key events."""
        try:
            proc = self._process
            if not proc or not proc.stdout:
                return
            for line in iter(proc.stdout.readline, b''):
                text = line.decode('utf-8', errors='replace').strip()
                if not text:
                    continue

                # store recent log lines for web UI
                with self._log_lock:
                    self._log_lines.append(text)
                    if len(self._log_lines) > 200:
                        self._log_lines = self._log_lines[-200:]

                # log key events at info level
                lower = text.lower()
                if any(k in lower for k in ['pmkid', 'handshake', 'captured', 'hash', 'eapol', 'found']):
                    logging.info("[angryoxide] %s", text)
                elif 'error' in lower or 'failed' in lower:
                    logging.warning("[angryoxide] %s", text)
                else:
                    logging.debug("[angryoxide] %s", text)
        except Exception:
            pass

    # --- Monitoring ---

    def _monitor_loop(self):
        """Background thread: monitor AO health, process captures, update display."""
        output_dir = self.options.get('output_dir', '/tmp/angryoxide')

        while not self._monitor_stop.is_set():
            try:
                # check if AO is still alive
                if self._running and self._process:
                    ret = self._process.poll()
                    if ret is not None:
                        self._running = False
                        logging.warning("[angryoxide] process exited (code %s)", ret)

                        # check for known errors
                        with self._log_lock:
                            recent = '\n'.join(self._log_lines[-20:])
                        if 'Interface not found' in recent:
                            logging.error("[angryoxide] interface %s not available — is another process using it?", self._iface)
                            self._set_status(self._agent, 'AO: interface busy')
                            self._crash_count = self._max_crashes  # don't retry
                        elif self._crash_count < self._max_crashes:
                            self._crash_count += 1
                            logging.info("[angryoxide] restarting (attempt %d/%d)...",
                                        self._crash_count, self._max_crashes)
                            time.sleep(5)
                            self._start_angryoxide()
                        else:
                            logging.error("[angryoxide] max restarts reached, giving up")
                            self._set_status(self._agent, 'AO crashed — check logs')

                # process new captures
                self._process_captures(output_dir)

            except Exception as e:
                logging.debug("[angryoxide] monitor error: %s", e)

            self._monitor_stop.wait(10)

    def _process_captures(self, output_dir=None):
        """Scan output directory for new .hc22000 files and import handshakes."""
        if output_dir is None:
            output_dir = self.options.get('output_dir', '/tmp/angryoxide')

        hs_dir = self.config.get('bettercap', {}).get('handshakes', '/etc/pwnagotchi/handshakes')

        for hc_file in glob.glob(os.path.join(output_dir, '**', '*.hc22000'), recursive=True):
            try:
                with open(hc_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line in self._processed_hashes:
                            continue

                        parsed = self._parse_hc22000_line(line)
                        if not parsed:
                            continue

                        ssid, bssid, sta_mac, htype = parsed
                        self._processed_hashes.add(line)

                        bssid_clean = bssid.replace(':', '').lower()
                        dest_name = '%s_%s.pcap' % (ssid, bssid_clean)
                        dest_path = os.path.join(hs_dir, dest_name)

                        # skip if already captured
                        if os.path.isfile(dest_path):
                            key = bssid.lower()
                            if key not in self._captures:
                                self._captures[key] = {
                                    'ssid': ssid, 'bssid': bssid, 'sta_mac': sta_mac,
                                    'type': htype, 'time': 'pre-existing',
                                    'source': 'angryoxide'
                                }
                            continue

                        # find corresponding pcapng
                        pcapng_files = glob.glob(os.path.join(output_dir, '**', '*.pcapng'), recursive=True)
                        if pcapng_files:
                            newest = max(pcapng_files, key=os.path.getmtime)
                            shutil.copy2(newest, dest_path)
                        else:
                            with open(dest_path, 'wb') as pf:
                                pf.write(b'')

                        # copy hc22000 alongside for cracking
                        hc_dest = dest_path.replace('.pcap', '.hc22000')
                        with open(hc_dest, 'w') as hf:
                            hf.write(line + '\n')

                        # record capture
                        now = time.strftime('%Y-%m-%d %H:%M:%S')
                        key = bssid.lower()
                        self._captures[key] = {
                            'ssid': ssid, 'bssid': bssid, 'sta_mac': sta_mac,
                            'type': htype, 'time': now, 'source': 'angryoxide'
                        }
                        self._last_capture = now
                        self._crash_count = 0  # reset crash counter on success

                        # fire handshake event into pwnagotchi plugin chain
                        try:
                            plugins.on('handshake', self._agent, dest_path, bssid, sta_mac)
                            logging.info("[angryoxide] NEW handshake: %s (%s) [%s]",
                                        ssid, bssid, htype)
                            self._set_status(self._agent, 'AO got %s!' % ssid, '(ᵔ◡◡ᵔ)')
                        except Exception as e:
                            logging.debug("[angryoxide] handshake event error: %s", e)

            except Exception as e:
                logging.debug("[angryoxide] capture processing error: %s", e)

    def _parse_hc22000_line(self, line):
        """Parse a hashcat 22000 format line.
        Format: WPA*TYPE*PMKID/MIC*MACAP*MACCLIENT*ESSID_HEX*...
        Returns: (ssid, bssid, sta_mac, type_str) or None
        """
        try:
            parts = line.split('*')
            if len(parts) < 6 or parts[0] != 'WPA':
                return None

            htype_code = parts[1]
            htype = 'PMKID' if htype_code == '01' else '4-Way HS'

            mac_ap_raw = parts[3]
            mac_sta_raw = parts[4]
            essid_hex = parts[5]

            if len(mac_ap_raw) != 12 or len(mac_sta_raw) != 12:
                return None

            bssid = ':'.join(mac_ap_raw[i:i+2] for i in range(0, 12, 2))
            sta_mac = ':'.join(mac_sta_raw[i:i+2] for i in range(0, 12, 2))
            ssid = bytes.fromhex(essid_hex).decode('utf-8', errors='replace')

            return (ssid, bssid, sta_mac, htype)
        except Exception:
            return None

    # --- Display ---

    def _set_status(self, agent, msg, face=None):
        """Set pwnagotchi status message and optionally face."""
        try:
            if agent:
                agent.view().set('status', msg)
                if face:
                    agent.view().set('face', face)
        except Exception:
            pass

    def on_ui_setup(self, ui):
        pass

    def on_ui_update(self, ui):
        pass

    # --- Epoch hook (no-op, AO runs independently) ---

    def on_epoch(self, agent, epoch, epoch_data):
        # AO runs continuously, no per-epoch action needed
        # but update the face periodically if AO is running
        if self._running:
            count = len(self._captures)
            if count:
                self._set_status(agent, 'AO: %d captures' % count, '(⌐■_■)')
            else:
                self._set_status(agent, 'AO hunting...', '(⌐■_■)')

    # --- Web UI ---

    def on_webhook(self, path, request):
        if not self.ready:
            return "Plugin not ready"

        if path == '/' or not path:
            captures_list = sorted(
                self._captures.values(),
                key=lambda c: c.get('time', ''),
                reverse=True
            )
            with self._log_lock:
                log_text = '\n'.join(self._log_lines[-50:])

            uptime = '-'
            if self._start_time and self._running:
                secs = int(time.time() - self._start_time)
                mins, secs = divmod(secs, 60)
                hours, mins = divmod(mins, 60)
                uptime = '%dh %dm %ds' % (hours, mins, secs)

            return render_template_string(
                STATUS_TEMPLATE,
                title='AngryOxide',
                running=self._running,
                interface=self._iface or '-',
                capture_count=len(self._captures),
                captures=captures_list,
                last_capture=self._last_capture or '-',
                uptime=uptime,
                log_lines=log_text,
            )

        elif path == 'api/status':
            uptime = None
            if self._start_time and self._running:
                secs = int(time.time() - self._start_time)
                mins, secs = divmod(secs, 60)
                hours, mins = divmod(mins, 60)
                uptime = '%dh %dm %ds' % (hours, mins, secs)

            return jsonify({
                'available': self._available,
                'running': self._running,
                'interface': self._iface,
                'capture_count': len(self._captures),
                'last_capture': self._last_capture,
                'uptime': uptime,
                'crash_count': self._crash_count,
            })

        elif path == 'api/captures':
            return jsonify(list(self._captures.values()))

        elif path == 'api/start':
            if self._available and not self._running:
                self._disable_bettercap_wifi(self._agent)
                time.sleep(1)
                self._kill_orphans()
                self._start_angryoxide()
            return jsonify({'ok': True, 'running': self._running})

        elif path == 'api/stop':
            self._stop_angryoxide()
            self._enable_bettercap_wifi()
            return jsonify({'ok': True, 'running': False})

        elif path == 'api/restart':
            self._stop_angryoxide()
            time.sleep(2)
            self._kill_orphans()
            self._crash_count = 0
            self._start_angryoxide()
            return jsonify({'ok': True, 'running': self._running})

        elif path == 'api/log':
            with self._log_lock:
                return jsonify({'lines': self._log_lines[-100:]})

        else:
            return "Not found", 404
