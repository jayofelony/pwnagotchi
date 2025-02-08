import os
import logging
import json
import csv
import requests
import pwnagotchi
import re
from threading import Lock
from io import StringIO
from datetime import datetime, UTC

from flask import make_response, redirect
from pwnagotchi.utils import (
    WifiInfo,
    FieldNotFoundError,
    extract_from_pcap,
    StatusFile,
    remove_whitelisted,
)
from pwnagotchi import plugins
from pwnagotchi._version import __version__ as __pwnagotchi_version__
from scapy.all import Scapy_Exception


def _extract_gps_data(path):
    """
    Extract data from gps-file

    return json-obj
    """
    try:
        if path.endswith(".geo.json"):
            with open(path, "r") as json_file:
                tempJson = json.load(json_file)
                d = datetime.fromtimestamp(int(tempJson["ts"]), tz=UTC)
                return {
                    "Latitude": tempJson["location"]["lat"],
                    "Longitude": tempJson["location"]["lng"],
                    "Altitude": 10,
                    "Accuracy": tempJson["accuracy"],
                    "Updated": d.strftime("%Y-%m-%dT%H:%M:%S.%f"),
                }
        with open(path, "r") as json_file:
            return json.load(json_file)
    except (OSError, json.JSONDecodeError) as exp:
        raise exp

def _transform_wigle_entry(gps_data, pcap_data):
    """
    Transform to wigle entry in file
    """
    logging.info(f"transform to wigle")
    dummy = StringIO()
    writer = csv.writer(dummy, delimiter=",", quoting=csv.QUOTE_NONE, escapechar="\\")
    writer.writerow(
        [
            pcap_data[WifiInfo.BSSID],
            pcap_data[WifiInfo.ESSID],
            list(pcap_data[WifiInfo.ENCRYPTION]),
            datetime.strptime(
                gps_data["Updated"].rsplit(".")[0], "%Y-%m-%dT%H:%M:%S"
            ).strftime("%Y-%m-%d %H:%M:%S"),
            pcap_data[WifiInfo.CHANNEL],
            pcap_data[WifiInfo.RSSI],
            gps_data["Latitude"],
            gps_data["Longitude"],
            gps_data["Altitude"],
            gps_data["Accuracy"],
            "WIFI",
        ]
    )
    return dummy.getvalue()


def _generate_csv(lines, plugin_version):
    """
    Generates the csv file
    """
    dummy = StringIO()
    # write kismet header
    dummy.write(
        f"WigleWifi-1.6,appRelease={plugin_version},model=pwnagotchi,release={__pwnagotchi_version__},"
        f"device={pwnagotchi.name()},display=kismet,board=RaspberryPi,brand=pwnagotchi,star=Sol,body=3,subBody=0\n"
    )
    # write header
    dummy.write(
        "MAC,SSID,AuthMode,FirstSeen,Channel,RSSI,CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,Type\n"
    )
    # write WIFIs
    for line in lines:
        dummy.write(f"{line}")
    dummy.seek(0)
    return dummy

def to_file(filename, content):
    try:
        with open(f"/tmp/{filename}", mode="w") as f:
            f.write(content)
    except Exception as exp:
        logging.debug(f"WIGLE: {exp}")
        pass

def _send_to_wigle(lines, api_name, api_key, plugin_version, donate=False, timeout=30):
    """
    Uploads the file to wigle-net
    """
    dummy = _generate_csv(lines, plugin_version)

    date = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{pwnagotchi.name()}_{date}.csv"
    payload = {
        "file": (
            filename,
            dummy,
            "text/csv",
        )
    }
    to_file(filename, dummy.getvalue())
    try:
        res = requests.post(
            "https://api.wigle.net/api/v2/file/upload",
            headers={"Accept": "application/json"},
            auth=(api_name, api_key),
            data={"donate": "on" if donate else "false"},
            files=payload,
            timeout=timeout,
        )
        json_res = res.json()
        logging.info(f"Request result: {json_res}")
        if not json_res["success"]:
            raise requests.exceptions.RequestException(json_res["message"])
    except requests.exceptions.RequestException as re_e:
        raise re_e


class Wigle(plugins.Plugin):
    __author__ = "Dadav and updated by Jayofelony"
    __version__ = "4.0.0"
    __license__ = "GPL3"
    __description__ = "This plugin automatically uploads collected WiFi to wigle.net"

    def __init__(self):
        self.ready = False
        self.report = StatusFile("/root/.wigle_uploads", data_format="json")
        self.skip = list()
        self.lock = Lock()
        self.options = dict()
        self.api_name = None
        self.api_key = None
        self.donate = False
        self.handshake_dir = None
        self.whitelist = None

    def on_config_changed(self, config):
        self.api_name = self.options.get("api_name", None)
        self.api_key = self.options.get("api_key", None)
        if not (self.api_name and self.api_key):
            logging.debug(
                "WIGLE: api_name and/or api_key isn't set. Can't upload to wigle.net"
            )
            return
        self.donate = self.options.get("donate", False)
        self.handshake_dir = config["bettercap"].get("handshakes", None)
        self.whitelist = config["main"].get("whitelist", None)
        self.ready = True
        logging.info("WIGLE: ready")

    def on_webhook(self, path, request):
        response = make_response(redirect("https://www.wigle.net/", code=302))
        return response

    def get_new_gps_files(self, reported):
        all_files = os.listdir(self.handshake_dir)
        all_gps_files = [
            os.path.join(self.handshake_dir, filename)
            for filename in all_files
            if filename.endswith(".gps.json") or filename.endswith(".geo.json")
        ]

        all_gps_files = remove_whitelisted(all_gps_files, self.whitelist)
        return set(all_gps_files) - set(reported) - set(self.skip)

    @staticmethod
    def get_pcap_filename(gps_file):
        pcap_filename = re.sub(r"\.(geo|gps)\.json$", ".pcap", gps_file)
        if not os.path.exists(pcap_filename):
            logging.debug("WIGLE: Can't find pcap for %s", gps_file)
            return None
        return pcap_filename

    @staticmethod
    def get_gps_data(gps_file):
        try:
            gps_data = _extract_gps_data(gps_file)
        except (OSError, json.JSONDecodeError) as exp:
            logging.debug(f"WIGLE: {exp}")
            return None
        if gps_data["Latitude"] == 0 and gps_data["Longitude"] == 0:
            logging.debug(
                f"WIGLE: Not enough gps-information for {gps_file}. Trying again next time."
            )
            return None
        return gps_data

    @staticmethod
    def get_pcap_data(pcap_filename):
        try:
            logging.info(f"Extracting PCAP for {pcap_filename}")
            pcap_data = extract_from_pcap(
                pcap_filename,
                [
                    WifiInfo.BSSID,
                    WifiInfo.ESSID,
                    WifiInfo.ENCRYPTION,
                    WifiInfo.CHANNEL,
                    WifiInfo.RSSI,
                ],
            )
            logging.info(f"PCAP DATA for {pcap_data}")
            logging.info(f"Extracting PCAP for {pcap_filename} DONE: {pcap_data}")
        except FieldNotFoundError:
            logging.debug(
                f"WIGLE: Could not extract all information. Skip {pcap_filename}"
            )
            return None
        except Scapy_Exception as sc_e:
            logging.debug(f"WIGLE: {sc_e}")
            return None
        return pcap_data

    def upload(self, reported, csv_entries, no_err_entries):
        try:
            logging.info("Uploading to Wigle")
            _send_to_wigle(
                csv_entries, self.api_name, self.api_key, self.__version__, donate=self.donate
            )
            reported += no_err_entries
            self.report.update(data={"reported": reported})
            logging.info("WIGLE: Successfully uploaded %d files", len(no_err_entries))
        except requests.exceptions.RequestException as re_e:
            self.skip += no_err_entries
            logging.debug("WIGLE: Got an exception while uploading %s", re_e)
        except OSError as os_e:
            self.skip += no_err_entries
            logging.debug("WIGLE: Got the following error: %s", os_e)

    def on_internet_available(self, agent):
        """
        Called when there's internet connectivity
        """
        if not self.ready:
            return
        with self.lock:
            reported = self.report.data_field_or("reported", default=list())
            if new_gps_files := self.get_new_gps_files(reported):
                logging.info(
                    "WIGLE: Internet connectivity detected. Uploading new handshakes to wigle.net"
                )
                csv_entries = list()
                no_err_entries = list()
                for gps_file in new_gps_files:
                    logging.info(f"WIGLE: handeling {gps_file}")
                    if not (pcap_filename := self.get_pcap_filename(gps_file)):
                        self.skip.append(gps_file)
                        continue
                    if not (gps_data := self.get_gps_data(gps_file)):
                        self.skip.append(gps_file)
                        continue
                    if not (pcap_data := self.get_pcap_data(pcap_filename)):
                        self.skip.append(gps_file)
                        continue
                    new_entry = _transform_wigle_entry(gps_data, pcap_data)
                    csv_entries.append(new_entry)
                    no_err_entries.append(gps_file)
                if csv_entries:
                    display = agent.view()
                    display.on_uploading("wigle.net")
                    self.upload(reported, csv_entries, no_err_entries)
                    display.on_normal()
