import os
import logging
import re
import requests
import sqlite3
from datetime import datetime
from enum import Enum
from threading import Lock
from pwnagotchi.utils import remove_whitelisted
from pwnagotchi import plugins
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
from flask import render_template_string


INDEX = """
{% extends "base.html" %}
{% set active_page = "plugins" %}
{% block title %}WPA-SEC{% endblock %}

{% block styles %}
    {{ super() }}
    <style>
        .wpa-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 2rem;
            padding: 1.5rem 0;
            border-bottom: 1px solid var(--border-color);
        }
        .wpa-header > div { flex: 1; min-width: 0; }
        .wpa-header h2, .wpa-header p { margin: 0; }
        .wpa-header .btn { flex-shrink: 0; width: auto; min-width: 0; }

        .wpa-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .wpa-stat {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
        }
        .wpa-stat .num {
            font-family: var(--font-pixel);
            font-size: 2.2rem;
            line-height: 1;
            color: var(--accent);
        }
        .wpa-stat .lbl {
            margin-top: 0.4rem;
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
        }
        .wpa-actions form { margin: 0; width: 100%; }
        .wpa-actions .btn { width: 100%; }
    </style>
{% endblock %}

{% block content %}
    <div class="wpa-header">
        <div>
            <h2>WPA-SEC</h2>
            <p>Handshake uploads &amp; cracked results</p>
        </div>
        <a href="/plugins" class="btn secondary">Plugins</a>
    </div>

    <div class="wpa-stats">
        <div class="wpa-stat"><div class="num">{{ to_upload }}</div><div class="lbl">To upload</div></div>
        <div class="wpa-stat"><div class="num">{{ uploaded }}</div><div class="lbl">Uploaded</div></div>
        <div class="wpa-stat"><div class="num">{{ invalid }}</div><div class="lbl">Invalid</div></div>
        <div class="wpa-stat"><div class="num">{{ cracked }}</div><div class="lbl">Cracked</div></div>
    </div>

    <div class="card">
        <div class="card-header">Your uploads</div>
        <div class="card-body">
            <p>View and manage the handshakes you have uploaded on wpa-sec.net. Your API key is sent to open your personal dashboard.</p>
        </div>
        <div class="card-footer wpa-actions">
            <form action="{{ api_url }}" method="POST" target="_blank">
                <input type="hidden" name="key" value="{{ api_key }}">
                <button type="submit" class="btn primary">View my uploads on wpa-sec.net &rarr;</button>
            </form>
        </div>
    </div>
{% endblock %}
"""


class WpaSec(plugins.Plugin):
    __author__ = '33197631+dadav@users.noreply.github.com'
    __editor__ = 'jayofelony'
    __version__ = '2.2.1'
    __license__ = 'GPL3'
    __description__ = 'This plugin automatically uploads handshakes to https://wpa-sec.stanev.org'
    
    class Status(Enum):
        TOUPLOAD = 0
        INVALID = 1
        SUCCESSFULL = 2

    def __init__(self):
        self.ready = False
        self.lock = Lock()
        
        self.options = dict()
        
        self._init_db()
        
    def _init_db(self):
        db_conn = sqlite3.connect('/etc/pwnagotchi/.wpa_sec_db')
        db_conn.execute('pragma journal_mode=wal')
        with db_conn:
            db_conn.execute('''
                CREATE TABLE IF NOT EXISTS handshakes (
                    path TEXT PRIMARY KEY,
                    status INTEGER
                )
            ''')
            db_conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_handshakes_status
                ON handshakes (status)
            ''')
        db_conn.close()

    def on_loaded(self):
        """
        Gets called when the plugin gets loaded
        """
        if 'api_key' not in self.options or ('api_key' in self.options and not self.options['api_key']):
            logging.error("WPA_SEC: API-KEY isn't set. Can't upload.")
            return

        if 'api_url' not in self.options or ('api_url' in self.options and not self.options['api_url']):
            logging.error("WPA_SEC: API-URL isn't set. Can't upload.")
            return

        self.skip_until_reload = set()

        self.ready = True
        logging.info("WPA_SEC: plugin loaded.")
        
    def on_handshake(self, agent, filename, access_point, client_station):
        config = agent.config()
        
        if not remove_whitelisted([filename], config['main']['whitelist']):
            return
        
        db_conn = sqlite3.connect('/etc/pwnagotchi/.wpa_sec_db')
        with db_conn:
            db_conn.execute('''
                INSERT INTO handshakes (path, status)
                VALUES (?, ?)
                ON CONFLICT(path) DO UPDATE SET status = excluded.status
                WHERE handshakes.status = ?
            ''', (filename, self.Status.TOUPLOAD.value, self.Status.INVALID.value))
        db_conn.close()

    def on_internet_available(self, agent):
        """
        Called when there's internet connectivity
        """
        if not self.ready or self.lock.locked():
            return

        with self.lock:
            display = agent.view()
            
            try:
                db_conn = sqlite3.connect('/etc/pwnagotchi/.wpa_sec_db')
                cursor = db_conn.cursor()

                cursor.execute('SELECT path FROM handshakes WHERE status = ?', (self.Status.TOUPLOAD.value,))
                handshakes_toupload = [row[0] for row in cursor.fetchall()]
                handshakes_toupload = set(handshakes_toupload) - self.skip_until_reload

                if handshakes_toupload:
                    logging.info("WPA_SEC: Internet connectivity detected. Uploading new handshakes...")
                    for idx, handshake in enumerate(handshakes_toupload):
                        display.on_uploading(f"WPA-SEC ({idx + 1}/{len(handshakes_toupload)})")
                        logging.info("WPA_SEC: Uploading %s...", handshake)

                        try:
                            upload_response = self._upload_to_wpasec(handshake)
                            
                            if upload_response.startswith("hcxpcapngtool"):
                                logging.info(f"WPA_SEC: {handshake} successfully uploaded.")
                                new_status = self.Status.SUCCESSFULL.value
                            else:
                                logging.info(f"WPA_SEC: {handshake} uploaded, but it was invalid.")
                                new_status = self.Status.INVALID.value

                            cursor.execute('''
                                INSERT INTO handshakes (path, status)
                                VALUES (?, ?)
                                ON CONFLICT(path) DO UPDATE SET status = excluded.status
                            ''', (handshake, new_status))
                            db_conn.commit()
                            
                        except requests.exceptions.RequestException:
                            logging.exception("WPA_SEC: RequestException uploading %s, skipping until reload.", handshake)
                            self.skip_until_reload.add(handshake)
                        except OSError:
                            logging.exception("WPA_SEC: OSError uploading %s, deleting from db.", handshake)
                            cursor.execute('DELETE FROM handshakes WHERE path = ?', (handshake,))
                            db_conn.commit()
                        except Exception:
                            logging.exception("WPA_SEC: Exception uploading %s.", handshake)

                    display.on_normal()
                    
                cursor.close()
                db_conn.close()
            except Exception:
                logging.exception("WPA_SEC: Exception uploading results.")

            try:
                if 'download_results' in self.options and self.options['download_results']:
                    config = agent.config()
                    handshake_dir = config['bettercap']['handshakes']
                    
                    cracked_file_path = os.path.join(handshake_dir, 'wpa-sec.cracked.potfile')

                    if os.path.exists(cracked_file_path):
                        last_check = datetime.fromtimestamp(os.path.getmtime(cracked_file_path))
                        download_interval = int(self.options.get('download_interval', 3600))
                        if last_check is not None and ((datetime.now() - last_check).seconds / download_interval) < 1:
                            return

                    self._download_from_wpasec(cracked_file_path)
                    if 'single_files' in self.options and self.options['single_files']:
                        self._write_cracked_single_files(cracked_file_path, handshake_dir)
            except Exception:
                logging.exception("WPA_SEC: Exception downloading results.")

    def _upload_to_wpasec(self, path, timeout=30):
        """
        Uploads the file to wpasec
        """
        with open(path, 'rb') as file_to_upload:
            cookie = {'key': self.options['api_key']}
            payload = {'file': file_to_upload}
            headers = {"HTTP_USER_AGENT": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:15.0) Gecko/20100101 Firefox/15.0.1"}

            result = requests.post(
                self.options['api_url'],
                cookies=cookie,
                files=payload,
                headers=headers,
                timeout=timeout
            )
            result.raise_for_status()
            
            response = result.text.partition('\n')[0]

            logging.debug("WPA_SEC: Response uploading %s: %s.", path, response)

            return response

    def _download_from_wpasec(self, output, timeout=30):
        """
        Downloads the results from wpasec and saves them to output

        Output-Format: bssid, station_mac, ssid, password
        """
        api_url = self.options['api_url']
        if not api_url.endswith('/'):
            api_url = f"{api_url}/"
        api_url = f"{api_url}?api&dl=1"

        cookie = {'key': self.options['api_key']}
        headers = {"HTTP_USER_AGENT": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:15.0) Gecko/20100101 Firefox/15.0.1"}

        logging.info("WPA_SEC: Downloading cracked passwords...")

        result = requests.get(api_url, cookies=cookie, headers=headers, timeout=timeout)
        result.raise_for_status()

        with open(output, 'wb') as output_file:
            output_file.write(result.content)

        logging.info("WPA_SEC: Downloaded cracked passwords.")

    def _write_cracked_single_files(self, cracked_file_path, handshake_dir):
        """
        Splits download results from wpasec into individual .pcapng.cracked files in handshake_dir

        Each .pcapng.cracked file will contain the cracked handshake password
        """
        logging.info("WPA_SEC: Writing cracked single files...")

        with open(cracked_file_path, 'r') as cracked_file:
            for line in cracked_file:
                try:
                    bssid,station_mac,ssid,password = line.split(":")
                    if password:
                        handshake_filename = re.sub(r'[^a-zA-Z0-9]', '', ssid) + '_' + bssid
                        pcap_path = os.path.join(handshake_dir, handshake_filename+'.pcapng')
                        pcap_cracked_path = os.path.join(handshake_dir, handshake_filename+'.pcapng.cracked')
                        if os.path.exists(pcap_path) and not os.path.exists(pcap_cracked_path):
                            with open(pcap_cracked_path, 'w') as f:
                                f.write(password)
                except Exception:
                    logging.exception(f"WPA_SEC: Exception writing cracked single file, parsing line {line}.")
    
        logging.info("WPA_SEC: Wrote cracked single files.")

    def on_webhook(self, path, request):
        # Themed page: show upload/cracked stats + a button to open wpa-sec.net.
        counts = {'toupload': 0, 'uploaded': 0, 'invalid': 0}
        cracked = 0
        try:
            db_conn = sqlite3.connect('/etc/pwnagotchi/.wpa_sec_db')
            cursor = db_conn.cursor()
            for label, status in (('toupload', self.Status.TOUPLOAD.value),
                                  ('uploaded', self.Status.SUCCESSFULL.value),
                                  ('invalid', self.Status.INVALID.value)):
                cursor.execute('SELECT COUNT(*) FROM handshakes WHERE status = ?', (status,))
                counts[label] = cursor.fetchone()[0]
            cursor.close()
            db_conn.close()
        except Exception:
            logging.exception("WPA_SEC: could not read stats for web page")
        try:
            potfile = '/etc/pwnagotchi/handshakes/wpa-sec.cracked.potfile'
            if os.path.exists(potfile):
                with open(potfile) as f:
                    cracked = sum(1 for _ in f)
        except Exception:
            pass

        return render_template_string(
            INDEX,
            to_upload=counts['toupload'],
            uploaded=counts['uploaded'],
            invalid=counts['invalid'],
            cracked=cracked,
            api_url=self.options.get('api_url', ''),
            api_key=self.options.get('api_key', ''),
        )

    def on_ui_setup(self, ui):
        if 'show_pwd' in self.options and self.options['show_pwd'] and 'download_results' in self.options and self.options['download_results']:
            # Setup for horizontal orientation with adjustable positions
            x_position = 0  # X position for both SSID and password
            ssid_y_position = 95  # Y position for SSID
            ssid_position = (x_position, ssid_y_position)
            ui.add_element('pass', LabeledValue(color=BLACK, label='', value='', position=ssid_position,
                                                label_font=fonts.Bold, text_font=fonts.Small))

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element('pass')

    def on_ui_update(self, ui):
        if 'show_pwd' in self.options and self.options['show_pwd'] and 'download_results' in self.options and self.options['download_results']:
            file_path = '/etc/pwnagotchi/handshakes/wpa-sec.cracked.potfile'
            try:
                with open(file_path, 'r') as file:
                    # Read all lines and extract the required fields
                    lines = file.readlines()
                    if lines:  # Check if file is not empty
                        last_line = lines[-1]
                        parts = last_line.split(':')  # Split line into fields using ':' as a delimiter
                        if len(parts) >= 4:
                            result = f"{parts[2]} - {parts[3].strip()}"
                        else:
                            result = "Malformed line format"
                    else:
                        result = "File is empty"
            except FileNotFoundError:
                result = "File not found"
            except OSError as e:
                result = f"Error reading file: {e}"
            ui.set('pass', result)
