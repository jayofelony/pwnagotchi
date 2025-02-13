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
from dataclasses import dataclass

from flask import make_response, redirect
from pwnagotchi.utils import (
    WifiInfo,
    FieldNotFoundError,
    extract_from_pcap,
    StatusFile,
    remove_whitelisted,
)
from pwnagotchi import plugins
from pwnagotchi.plugins.default.cache import read_ap_cache
from pwnagotchi._version import __version__ as __pwnagotchi_version__

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import Text
from pwnagotchi.ui.view import BLACK

from scapy.all import Scapy_Exception


@dataclass
class WigleStatistics:
    ready: bool = False
    username: str = None
    rank: int = None
    monthrank: int = None
    discoveredwiFi: int = None
    last: str = None
    groupID: str = None
    groupname: str = None
    grouprank: int = None

    def update_user(self, json_res):
        self.ready = True
        self.username = json_res["user"]
        self.rank = json_res["rank"]
        self.monthrank = json_res["monthRank"]
        self.discoveredwiFi = json_res["statistics"]["discoveredWiFi"]
        last = json_res["statistics"]["last"]
        self.last = f"{last[6:8]}/{last[4:6]}/{last[0:4]}"

    def update_user_group(self, json_res):
        self.groupID = json_res["groupId"]
        self.groupname = json_res["groupName"]

    def update_group(self, json_res):
        rank = 1
        for group in json_res["groups"]:
            if group["groupId"] == self.groupID:
                self.grouprank = rank
            rank += 1


class Wigle(plugins.Plugin):
    __author__ = "Dadav and updated by Jayofelony and fmatray"
    __version__ = "4.1.0"
    __license__ = "GPL3"
    __description__ = "This plugin automatically uploads collected WiFi to wigle.net"
    LABEL_SPACING = 0

    def __init__(self):
        self.ready = False
        self.report = None
        self.skip = list()
        self.lock = Lock()
        self.options = dict()
        self.statistics = WigleStatistics()
        self.last_stat = datetime.now(tz=UTC)
        self.ui_counter = 0

    def on_loaded(self):
        logging.info("[WIGLE] plugin loaded.")

    def on_config_changed(self, config):
        self.api_key = self.options.get("api_key", None)
        if not self.api_key:
            logging.info("[WIGLE] api_key must be set.")
            return
        self.donate = self.options.get("donate", False)
        self.handshake_dir = config["bettercap"].get("handshakes")
        report_filename = os.path.join(self.handshake_dir, ".wigle_uploads")
        self.report = StatusFile(report_filename, data_format="json")
        self.cache_dir = os.path.join(self.handshake_dir, "cache")
        self.cvs_dir = self.options.get("cvs_dir", None)
        self.whitelist = config["main"].get("whitelist", [])
        self.timeout = self.options.get("timeout", 30)
        self.position = self.options.get("position", (10, 10))
        self.ready = True
        logging.info("[WIGLE] Ready for wardriving!!!")
        self.get_statistics(force=True)

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

    def get_pcap_data(self, pcap_filename):
        try:
            if cache := read_ap_cache(self.cache_dir, self.pcap_filename):
                logging.info(f"[WIGLE] Using cache for {pcap_filename}")
                return {
                    WifiInfo.BSSID: cache["mac"],
                    WifiInfo.ESSID: cache["hostname"],
                    WifiInfo.ENCRYPTION: cache["encryption"],
                    WifiInfo.CHANNEL: cache["channel"],
                    WifiInfo.FREQUENCY: cache["frequency"],
                    WifiInfo.RSSI: cache["rssi"],
                }
        except (AttributeError, KeyError):
            pass
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
        writer = csv.writer(content, delimiter=",", quoting=csv.QUOTE_NONE, escapechar="\\")
        for gps_data, pcap_data in data:  # write WIFIs
            try:
                timestamp = datetime.strptime(
                    gps_data["Updated"].rsplit(".")[0], "%Y-%m-%dT%H:%M:%S"
                ).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                timestamp = datetime.strptime(
                    gps_data["Updated"].rsplit(".")[0], "%Y-%m-%d %H:%M:%S"
                ).strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow(
                [
                    pcap_data[WifiInfo.BSSID],
                    pcap_data[WifiInfo.ESSID],
                    f"[{']['.join(pcap_data[WifiInfo.ENCRYPTION])}]",
                    timestamp,
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
                headers={
                    "Authorization": f"Basic {self.api_key}",
                    "Accept": "application/json",
                },
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

    def request_statistics(self, url):
        try:
            return requests.get(
                url,
                headers={
                    "Authorization": f"Basic {self.api_key}",
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            ).json()
        except (requests.exceptions.RequestException, OSError) as exp:
            return None

    def get_user_statistics(self):
        json_res = self.request_statistics(
            "https://api.wigle.net/api/v2/stats/user",
        )
        if json_res and json_res["success"]:
            self.statistics.update_user(json_res)

    def get_usergroup_statistics(self):
        if not self.statistics.username or self.statistics.groupID:
            return
        url = f"https://api.wigle.net/api/v2/group/groupForUser/{self.statistics.username}"
        if json_res := self.request_statistics(url):
            self.statistics.update_user_group(json_res)

    def get_group_statistics(self):
        if not self.statistics.groupID:
            return
        json_res = self.request_statistics("https://api.wigle.net/api/v2/stats/group")
        if json_res and json_res["success"]:
            self.statistics.update_group(json_res)

    def get_statistics(self, force=False):
        if force or (datetime.now(tz=UTC) - self.last_stat).total_seconds() > 30:
            self.last_stat = datetime.now(tz=UTC)
            self.get_user_statistics()
            self.get_usergroup_statistics()
            self.get_group_statistics()

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
            try:
                ui.remove_element("wigle")
            except KeyError:
                pass

    def on_ui_update(self, ui):
        with ui._lock:
            if not (self.ready and self.statistics.ready):
                ui.set("wigle", "We Will Wait Wigle")
                return
            msg = "-"
            self.ui_counter = (self.ui_counter + 1) % 6
            if self.ui_counter == 0:
                msg = f"User:{self.statistics.username}"
            if self.ui_counter == 1:
                msg = f"Rank:{self.statistics.rank} Month:{self.statistics.monthrank}"
            elif self.ui_counter == 2:
                msg = f"{self.statistics.discoveredwiFi} discovered WiFis"
            elif self.ui_counter == 3:
                msg = f"Last upl.:{self.statistics.last}"
            elif self.ui_counter == 4:
                msg = f"Grp:{self.statistics.groupname}"
            elif self.ui_counter == 5:
                msg = f"Grp rank:{self.statistics.grouprank}"
            ui.set("wigle", msg)
