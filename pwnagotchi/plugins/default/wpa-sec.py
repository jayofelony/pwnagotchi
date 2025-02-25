import os
import logging
import requests
from datetime import datetime
from threading import Lock
from pwnagotchi.utils import StatusFile, remove_whitelisted
from pwnagotchi import plugins
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
from json.decoder import JSONDecodeError


class WpaSec(plugins.Plugin):
    __author__ = '33197631+dadav@users.noreply.github.com'
    __editor__ = 'jayofelony'
    __version__ = '2.1.1'
    __license__ = 'GPL3'
    __description__ = 'This plugin automatically uploads handshakes to https://wpa-sec.stanev.org'

    def __init__(self):
        self.ready = False
        self.lock = Lock()
        try:
            self.report = StatusFile('/home/pi/.wpa_sec_uploads', data_format='json')
        except JSONDecodeError:
            os.remove("/home/pi/.wpa_sec_uploads")
            self.report = StatusFile('/home/pi/.wpa_sec_uploads', data_format='json')
        self.options = dict()
        self.skip = list()

    def _upload_to_wpasec(self, path, timeout=30):
        """
        Uploads the file to https://wpa-sec.stanev.org, or another endpoint.
        """
        with open(path, 'rb') as file_to_upload:
            cookie = {"key": self.options['api_key']}
            payload = {"file": file_to_upload}
            headers = {"HTTP_USER_AGENT": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:15.0) Gecko/20100101 Firefox/15.0.1"}
            try:
                result = requests.post(self.options['api_url'],
                                       cookies=cookie,
                                       files=payload,
                                       headers=headers,
                                       timeout=timeout)
                if result.status_code == 200:
                    if ' already submitted' in result.text:
                        logging.info("%s was already submitted.", path)
                        return False
                    return True
                elif result.status_code != 200:
                    logging.error("WPA_SEC: Error code: %s", result.text)
                    return False
            except requests.exceptions.RequestException as req_e:
                raise req_e

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
        try:
            result = requests.get(api_url, cookies=cookie, timeout=timeout)
            with open(output, 'wb') as output_file:
                output_file.write(result.content)
        except requests.exceptions.RequestException as req_e:
            raise req_e
        except OSError as os_e:
            raise os_e

    def on_loaded(self):
        """
        Gets called when the plugin gets loaded
        """
        if 'api_key' not in self.options or ('api_key' in self.options and not self.options['api_key']):
            logging.error("WPA_SEC: API-KEY isn't set. Can't upload to wpa-sec.stanev.org")
            return

        if 'api_url' not in self.options or ('api_url' in self.options and not self.options['api_url']):
            logging.error("WPA_SEC: API-URL isn't set. Can't upload, no endpoint configured.")
            return

        self.ready = True
        logging.info("WPA_SEC: plugin loaded")

    def on_webhook(self, path, request):
        from flask import make_response, redirect
        response = make_response(redirect(self.options['api_url'], code=302))
        response.set_cookie('key', self.options['api_key'])
        return response

    def on_internet_available(self, agent):
        """
        Called when there's internet connectivity
        """
        if not self.ready or self.lock.locked():
            return

        with self.lock:
            config = agent.config()
            display = agent.view()
            reported = self.report.data_field_or('reported', default=list())
            handshake_dir = config['bettercap']['handshakes']
            try:
                handshake_filenames = os.listdir(handshake_dir)
            except FileNotFoundError:
                logging.info("WPA_SEC: Handshake directory doesn't exist.")
                return
            handshake_paths = [os.path.join(handshake_dir, filename) for filename in handshake_filenames if filename.endswith('.pcap')]
            handshake_paths = remove_whitelisted(handshake_paths, config['main']['whitelist'])
            handshake_new = set(handshake_paths) - set(reported) - set(self.skip)

            if handshake_new:
                logging.info("WPA_SEC: Internet connectivity detected. Uploading new handshakes to wpa-sec.stanev.org")
                for idx, handshake in enumerate(handshake_new):
                    display.on_uploading(f"wpa-sec.stanev.org ({idx + 1}/{len(handshake_new)})")
                    try:
                        if self._upload_to_wpasec(handshake):
                            reported.append(handshake)
                            self.report.update(data={'reported': reported})
                            logging.debug("WPA_SEC: Successfully uploaded %s", handshake)
                    except requests.exceptions.RequestException as req_e:
                        self.skip.append(handshake)
                        logging.debug("WPA_SEC: %s", req_e)
                        continue
                    except OSError as os_e:
                        logging.debug("WPA_SEC: %s", os_e)
                        continue
                display.on_normal()

            if 'download_results' in self.options and self.options['download_results']:
                cracked_file = os.path.join(handshake_dir, 'wpa-sec.cracked.potfile')
                if os.path.exists(cracked_file):
                    last_check = datetime.fromtimestamp(os.path.getmtime(cracked_file))
                    if last_check is not None and ((datetime.now() - last_check).seconds / (60 * 60)) < 1:
                        return
                try:
                    self._download_from_wpasec(os.path.join(handshake_dir, 'wpa-sec.cracked.potfile'))
                    logging.info("WPA_SEC: Downloaded cracked passwords.")
                except requests.exceptions.RequestException as req_e:
                    logging.debug("WPA_SEC: %s", req_e)
                except OSError as os_e:
                    logging.debug("WPA_SEC: %s", os_e)

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
            try:
                ui.remove_element('pass')
            except KeyError:
                pass

    def on_ui_update(self, ui):
        if 'show_pwd' in self.options and self.options['show_pwd'] and 'download_results' in self.options and self.options['download_results']:
            file_path = '/home/pi/handshakes/wpa-sec.cracked.potfile'
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