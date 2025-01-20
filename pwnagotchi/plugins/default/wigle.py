import os
import logging
import json
import csv
import requests
import pwnagotchi

from io import StringIO
from datetime import datetime
from pwnagotchi.utils import WifiInfo, FieldNotFoundError, extract_from_pcap, StatusFile, remove_whitelisted
from threading import Lock
from pwnagotchi import plugins
from pwnagotchi._version import __version__ as __pwnagotchi_version__


def _extract_gps_data(path):
    """
    Extract data from gps-file

    return json-obj
    """

    try:
        if path.endswith('.geo.json'):
            with open(path, 'r') as json_file:
                tempJson = json.load(json_file)
                d = datetime.utcfromtimestamp(int(tempJson["ts"]))
                return {"Latitude": tempJson["location"]["lat"],
                        "Longitude": tempJson["location"]["lng"],
                        "Altitude": 10,
                        "Accuracy": tempJson["accuracy"],
                        "Updated": d.strftime('%Y-%m-%dT%H:%M:%S.%f')}
        else:
            with open(path, 'r') as json_file:
                return json.load(json_file)
    except OSError as os_err:
        raise os_err
    except json.JSONDecodeError as json_err:
        raise json_err


def _format_auth(data):
    out = ""
    for auth in data:
        out = f"{out}[{auth}]"
    return [f"{auth}" for auth in data]


def _transform_wigle_entry(gps_data, pcap_data, plugin_version):
    """
    Transform to wigle entry in file
    """
    dummy = StringIO()
    # write kismet header
    dummy.write(f"WigleWifi-1.6,appRelease={plugin_version},model=pwnagotchi,release={__pwnagotchi_version__},"
                f"device={pwnagotchi.name()},display=kismet,board=RaspberryPi,brand=pwnagotchi,star=Sol,body=3,subBody=0\n")
    dummy.write(
        "MAC,SSID,AuthMode,FirstSeen,Channel,RSSI,CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,Type\n")

    writer = csv.writer(dummy, delimiter=",", quoting=csv.QUOTE_NONE, escapechar="\\")
    writer.writerow([
        pcap_data[WifiInfo.BSSID],
        pcap_data[WifiInfo.ESSID],
        _format_auth(pcap_data[WifiInfo.ENCRYPTION]),
        datetime.strptime(gps_data['Updated'].rsplit('.')[0],
                          "%Y-%m-%dT%H:%M:%S").strftime('%Y-%m-%d %H:%M:%S'),
        pcap_data[WifiInfo.CHANNEL],
        pcap_data[WifiInfo.RSSI],
        gps_data['Latitude'],
        gps_data['Longitude'],
        gps_data['Altitude'],
        gps_data['Accuracy'],
        'WIFI'])
    return dummy.getvalue()


def _send_to_wigle(lines, api_key, donate=True, timeout=30):
    """
    Uploads the file to wigle-net
    """

    dummy = StringIO()

    for line in lines:
        dummy.write(f"{line}")

    dummy.seek(0)

    headers = {"Authorization": f"Basic {api_key}",
               "Accept": "application/json",
               "HTTP_USER_AGENT": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:15.0) Gecko/20100101 Firefox/15.0.1"}
    data = {"donate": "on" if donate else "false"}
    payload = {"file": (pwnagotchi.name() + ".csv", dummy, "multipart/form-data", {"Expires": "0"})}
    try:
        res = requests.post('https://api.wigle.net/api/v2/file/upload',
                            data=data,
                            headers=headers,
                            files=payload,
                            timeout=timeout)
        json_res = res.json()
        if not json_res['success']:
            raise requests.exceptions.RequestException(json_res['message'])
    except requests.exceptions.RequestException as re_e:
        raise re_e


class Wigle(plugins.Plugin):
    __author__ = "Dadav and updated by Jayofelony"
    __version__ = "3.1.0"
    __license__ = "GPL3"
    __description__ = "This plugin automatically uploads collected WiFi to wigle.net"

    def __init__(self):
        self.ready = False
        self.report = StatusFile('/root/.wigle_uploads', data_format='json')
        self.skip = list()
        self.lock = Lock()
        self.options = dict()

    def on_loaded(self):
        if 'api_key' not in self.options or ('api_key' in self.options and self.options['api_key'] is None):
            logging.debug("WIGLE: api_key isn't set. Can't upload to wigle.net")
            return

        if 'donate' not in self.options:
            self.options['donate'] = False

        self.ready = True
        logging.info("WIGLE: ready")
    
    def on_webhook(self, path, request):
        from flask import make_response, redirect
        response = make_response(redirect("https://www.wigle.net/", code=302))
        return response

    def on_internet_available(self, agent):
        """
        Called when there's internet connectivity
        """
        if not self.ready or self.lock.locked():
            return

        from scapy.all import Scapy_Exception

        config = agent.config()
        display = agent.view()
        reported = self.report.data_field_or('reported', default=list())
        handshake_dir = config['bettercap']['handshakes']
        all_files = os.listdir(handshake_dir)
        all_gps_files = [os.path.join(handshake_dir, filename)
                         for filename in all_files
                         if filename.endswith('.gps.json') or filename.endswith('.geo.json')]

        all_gps_files = remove_whitelisted(all_gps_files, config['main']['whitelist'])
        new_gps_files = set(all_gps_files) - set(reported) - set(self.skip)
        if new_gps_files:
            logging.info("WIGLE: Internet connectivity detected. Uploading new handshakes to wigle.net")
            csv_entries = list()
            no_err_entries = list()
            for gps_file in new_gps_files:
                if gps_file.endswith('.gps.json'):
                    pcap_filename = gps_file.replace('.gps.json', '.pcap')
                if gps_file.endswith('.geo.json'):
                    pcap_filename = gps_file.replace('.geo.json', '.pcap')
                if not os.path.exists(pcap_filename):
                    logging.debug("WIGLE: Can't find pcap for %s", gps_file)
                    self.skip.append(gps_file)
                    continue
                try:
                    gps_data = _extract_gps_data(gps_file)
                except OSError as os_err:
                    logging.debug("WIGLE: %s", os_err)
                    self.skip.append(gps_file)
                    continue
                except json.JSONDecodeError as json_err:
                    logging.debug("WIGLE: %s", json_err)
                    self.skip.append(gps_file)
                    continue
                if gps_data['Latitude'] == 0 and gps_data['Longitude'] == 0:
                    logging.debug("WIGLE: Not enough gps-information for %s. Trying again next time.", gps_file)
                    self.skip.append(gps_file)
                    continue
                try:
                    pcap_data = extract_from_pcap(pcap_filename, [WifiInfo.BSSID,
                                                                  WifiInfo.ESSID,
                                                                  WifiInfo.ENCRYPTION,
                                                                  WifiInfo.CHANNEL,
                                                                  WifiInfo.RSSI])
                except FieldNotFoundError:
                    logging.debug("WIGLE: Could not extract all information. Skip %s", gps_file)
                    self.skip.append(gps_file)
                    continue
                except Scapy_Exception as sc_e:
                    logging.debug("WIGLE: %s", sc_e)
                    self.skip.append(gps_file)
                    continue
                new_entry = _transform_wigle_entry(gps_data, pcap_data, self.__version__)
                csv_entries.append(new_entry)
                no_err_entries.append(gps_file)
            if csv_entries:
                display.on_uploading('wigle.net')

                try:
                    _send_to_wigle(csv_entries, self.options['api_key'], donate=self.options['donate'])
                    reported += no_err_entries
                    self.report.update(data={'reported': reported})
                    logging.info("WIGLE: Successfully uploaded %d files", len(no_err_entries))
                except requests.exceptions.RequestException as re_e:
                    self.skip += no_err_entries
                    logging.debug("WIGLE: Got an exception while uploading %s", re_e)
                except OSError as os_e:
                    self.skip += no_err_entries
                    logging.debug("WIGLE: Got the following error: %s", os_e)

                display.on_normal()
