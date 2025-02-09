import os
import logging
import json
import csv
import requests
import pwnagotchi
import re
from glob import glob
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

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import Text
from pwnagotchi.ui.view import BLACK

from scapy.all import Scapy_Exception


class Wigle(plugins.Plugin):
    __author__ = "Dadav and updated by Jayofelony and fmatray"
    __version__ = "4.0.0"
    __license__ = "GPL3"
    __description__ = "This plugin automatically uploads collected WiFi to wigle.net"
    LABEL_SPACING = 0

    def __init__(self):
        self.ready = False
        self.report = StatusFile("/root/.wigle_uploads", data_format="json")
        self.skip = list()
        self.lock = Lock()
        self.options = dict()
        self.statistics = dict(
            ready=False,
            username=None,
            rank=None,
            monthrank=None,
            discoveredwiFi=None,
            last=None,
        )
        self.last_stat = datetime.now(tz=UTC)
        self.ui_counter = 0

    def on_config_changed(self, config):
        api_name = self.options.get("api_name", None)
        api_key = self.options.get("api_key", None)
        if not (api_name and api_key):
            logging.info("[WIGLE] api_name and api_key must be set.")
            return
        self.auth = (api_name, api_key)
        self.donate = self.options.get("donate", False)
        self.handshake_dir = config["bettercap"].get("handshakes")
        self.cvs_dir = self.options.get("cvs_dir", None)
        self.whitelist = config["main"].get("whitelist", [])
        self.timeout = self.options.get("timeout", 30)
        self.position = self.options.get("position", (10, 10))
        self.ready = True
        logging.info("[WIGLE] Ready for wardriving!!!")

    def on_webhook(self, path, request):
        return make_response(redirect("https://www.wigle.net/", code=302))

    def get_new_gps_files(self, reported):
        all_gps_files = glob(os.path.join(self.handshake_dir, "*.gps.json"))
        all_gps_files += glob(os.path.join(self.handshake_dir, "*.geo.json"))
        all_gps_files = remove_whitelisted(all_gps_files, self.whitelist)
        return set(all_gps_files) - set(reported) - set(self.skip)

    @staticmethod
    def get_pcap_filename(gps_file):
        pcap_filename = re.sub(r"\.(geo|gps)\.json$", ".pcap", gps_file)
        if not os.path.exists(pcap_filename):
            logging.debug("[WIGLE] Can't find pcap for %s", gps_file)
            return None
        return pcap_filename

    @staticmethod
    def extract_gps_data(path):
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

    def get_gps_data(self, gps_file):
        try:
            gps_data = self.extract_gps_data(gps_file)
        except (OSError, json.JSONDecodeError) as exp:
            logging.debug(f"[WIGLE] Error while extracting GPS data: {exp}")
            return None
        if gps_data["Latitude"] == 0 and gps_data["Longitude"] == 0:
            logging.debug(f"[WIGLE] Not enough gps data for {gps_file}. Next time.")
            return None
        return gps_data

    @staticmethod
    def get_pcap_data(pcap_filename):
        try:
            pcap_data = extract_from_pcap(
                pcap_filename,
                [
                    WifiInfo.BSSID,
                    WifiInfo.ESSID,
                    WifiInfo.ENCRYPTION,
                    WifiInfo.CHANNEL,
                    WifiInfo.FREQUENCY,
                    WifiInfo.RSSI,
                ],
            )
            logging.debug(f"[WIGLE] PCAP data for {pcap_filename}: {pcap_data}")
        except FieldNotFoundError:
            logging.debug(f"[WIGLE] Cannot extract all data: {pcap_filename} (skipped)")
            return None
        except Scapy_Exception as sc_e:
            logging.debug(f"[WIGLE] {sc_e}")
            return None
        return pcap_data

    def generate_csv(self, data):
        date = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{pwnagotchi.name()}_{date}.csv"

        content = StringIO()
        # write kismet header + header
        content.write(
            f"WigleWifi-1.6,appRelease={self.__version__},model=pwnagotchi,release={__pwnagotchi_version__},"
            f"device={pwnagotchi.name()},display=kismet,board=RaspberryPi,brand=pwnagotchi,star=Sol,body=3,subBody=0\n"
            f"MAC,SSID,AuthMode,FirstSeen,Channel,Frequency,RSSI,CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,RCOIs,MfgrId,Type\n"
        )
        writer = csv.writer(
            content, delimiter=",", quoting=csv.QUOTE_NONE, escapechar="\\"
        )
        for gps_data, pcap_data in data:  # write WIFIs
            writer.writerow(
                [
                    pcap_data[WifiInfo.BSSID],
                    pcap_data[WifiInfo.ESSID],
                    f"[{']['.join(pcap_data[WifiInfo.ENCRYPTION])}]",
                    datetime.strptime(
                        gps_data["Updated"].rsplit(".")[0], "%Y-%m-%dT%H:%M:%S"
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    pcap_data[WifiInfo.CHANNEL],
                    pcap_data[WifiInfo.FREQUENCY],
                    pcap_data[WifiInfo.RSSI],
                    gps_data["Latitude"],
                    gps_data["Longitude"],
                    gps_data["Altitude"],
                    gps_data["Accuracy"],
                    "",  # RCOIs to populate
                    "",  # MfgrId always empty
                    "WIFI",
                ]
            )
        content.seek(0)
        return filename, content

    def save_to_file(self, cvs_filename, cvs_content):
        if not self.cvs_dir:
            return
        filename = os.path.join(self.cvs_dir, cvs_filename)
        logging.info(f"[WIGLE] Saving to file {filename}")
        try:
            with open(filename, mode="w") as f:
                f.write(cvs_content.getvalue())
        except Exception as exp:
            logging.error(f"[WIGLE] Error while writing CSV file(skipping): {exp}")

    def post_wigle(self, reported, cvs_filename, cvs_content, no_err_entries):
        try:
            json_res = requests.post(
                "https://api.wigle.net/api/v2/file/upload",
                headers={"Accept": "application/json"},
                auth=self.auth,
                data={"donate": "on" if self.donate else "false"},
                files=dict(file=(cvs_filename, cvs_content, "text/csv")),
                timeout=self.timeout,
            ).json()
            if not json_res["success"]:
                raise requests.exceptions.RequestException(json_res["message"])
            reported += no_err_entries
            self.report.update(data={"reported": reported})
            logging.info(f"[WIGLE] Successfully uploaded {len(no_err_entries)} wifis")
        except (requests.exceptions.RequestException, OSError) as exp:
            self.skip += no_err_entries
            logging.debug(f"[WIGLE] Exception while uploading: {exp}")

    def upload_new_handshakes(self, reported, new_gps_files, agent):
        logging.info("[WIGLE] Uploading new handshakes to wigle.net")
        csv_entries, no_err_entries = list(), list()
        for gps_file in new_gps_files:
            logging.info(f"[WIGLE] Processing {os.path.basename(gps_file)}")
            if (
                (pcap_filename := self.get_pcap_filename(gps_file))
                and (gps_data := self.get_gps_data(gps_file))
                and (pcap_data := self.get_pcap_data(pcap_filename))
            ):
                csv_entries.append((gps_data, pcap_data))
                no_err_entries.append(gps_file)
            else:
                self.skip.append(gps_file)
        logging.info(f"[WIGLE] Wifi to upload: {len(csv_entries)}")
        if csv_entries:
            cvs_filename, cvs_content = self.generate_csv(csv_entries)
            self.save_to_file(cvs_filename, cvs_content)
            display = agent.view()
            display.on_uploading("wigle.net")
            self.post_wigle(reported, cvs_filename, cvs_content, no_err_entries)
            display.on_normal()

    def get_statistics(self):
        if (datetime.now(tz=UTC) - self.last_stat).total_seconds() < 30:
            return
        self.last_stat = datetime.now(tz=UTC)
        try:
            self.statistics["ready"] = False
            json_res = requests.get(
                "https://api.wigle.net/api/v2/stats/user",
                headers={"Accept": "application/json"},
                auth=self.auth,
                timeout=self.timeout,
            ).json()
            if not json_res["success"]:
                return
            self.statistics["ready"] = True
            self.statistics["username"] = json_res["user"]
            self.statistics["rank"] = json_res["rank"]
            self.statistics["monthrank"] = json_res["monthRank"]
            self.statistics["discoveredwiFi"] = json_res["statistics"]["discoveredWiFi"]
            last = json_res["statistics"]["last"]
            self.statistics["last"] = f"{last[6:8]}/{last[4:6]}/{last[0:4]}"
        except (requests.exceptions.RequestException, OSError) as exp:
            pass

    def on_internet_available(self, agent):
        if not self.ready:
            return
        with self.lock:
            reported = self.report.data_field_or("reported", default=list())
            if new_gps_files := self.get_new_gps_files(reported):
                self.upload_new_handshakes(reported, new_gps_files, agent)
            else:
                self.get_statistics()

    def on_ui_setup(self, ui):
        with ui._lock:
            ui.add_element(
                "wigle",
                Text(value="-", position=self.position, font=fonts.Small, color=BLACK),
            )

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element("wigle")

    def on_ui_update(self, ui):
        if not self.ready:
            return
        with ui._lock:
            if not self.statistics["ready"]:
                ui.set("wigle", "We Will Wait Wigle")
                return
            msg = "-"
            self.ui_counter = (self.ui_counter + 1) % 4
            if self.ui_counter == 0:
                msg = f"User:{self.statistics['username']}"
            if self.ui_counter == 1:
                msg = f"Rank:{self.statistics['rank']} Monthly:{self.statistics['monthrank']}"
            elif self.ui_counter == 2:
                msg = f"{self.statistics['discoveredwiFi']} discovered WiFis"
            elif self.ui_counter == 3:
                msg = f"Last report:{self.statistics['last']}"
            ui.set("wigle", msg)
