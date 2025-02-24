import logging
import json
import os
import re
import pathlib
import pwnagotchi.plugins as plugins
from datetime import datetime, UTC
from threading import Lock


def read_ap_cache(cache_dir, file):
    cache_filename = os.path.basename(re.sub(r"\.(pcap|gps\.json|geo\.json)$", ".cache", file))
    cache_filename = os.path.join(cache_dir, cache_filename)
    if not os.path.exists(cache_filename):
        logging.info("Cache not exist")
        return None
    try:
        with open(cache_filename, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.info(f"Exception {e}")
        return None


class Cache(plugins.Plugin):
    __author__ = "fmatray"
    __version__ = "1.0.0"
    __license__ = "GPL3"
    __description__ = "A simple plugin to cache AP informations"

    def __init__(self):
        self.options = dict()
        self.ready = False
        self.lock = Lock()

    def on_loaded(self):
        logging.info("[CACHE] plugin loaded.")

    def on_config_changed(self, config):
        try:
            handshake_dir = config["bettercap"].get("handshakes")
            self.cache_dir = os.path.join(handshake_dir, "cache")
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            logging.info(f"[CACHE] Cannot access to the cache directory")
            return
        self.last_clean = datetime.now(tz=UTC)
        self.ready = True
        logging.info(f"[CACHE] Cache plugin configured")
        self.clean_ap_cache()

    def on_unload(self, ui):
        self.clean_ap_cache()

    def clean_ap_cache(self):
        if not self.ready:
            return
        with self.lock:
            ctime = datetime.now(tz=UTC)
            cache_to_delete = list()
            for cache_file in pathlib.Path(self.cache_dir).glob("*.apcache"):
                try:
                    mtime = datetime.fromtimestamp(cache_file.lstat().st_mtime, tz=UTC)
                    if (ctime - mtime).total_seconds() > 60 * 5:
                        cache_to_delete.append(cache_file)
                except FileNotFoundError:
                    pass
            if cache_to_delete:
                logging.info(f"[CACHE] Cleaning {len(cache_to_delete)} files")
            for cache_file in cache_to_delete:
                try:
                    cache_file.unlink()
                except FileNotFoundError as e:
                    pass

    def write_ap_cache(self, access_point):
        with self.lock:
            try:
                mac = access_point["mac"].replace(":", "")
                hostname = re.sub(r"[^a-zA-Z0-9]", "", access_point["hostname"])
            except KeyError:
                return
            cache_file = os.path.join(self.cache_dir, f"{hostname}_{mac}.apcache")
            try:
                with open(cache_file, "w") as f:
                    json.dump(access_point, f)
            except Exception as e:
                logging.error(f"[CACHE] Cannot write {cache_file}: {e}")
                pass

    def on_wifi_update(self, agent, access_points):
        if self.ready:
            for ap in filter(lambda ap: ap["hostname"] not in ["", "<hidden>"], access_points):
                self.write_ap_cache(ap)

    def on_unfiltered_ap_list(self, agent, aps):
        if self.ready:
            for ap in filter(lambda ap: ap["hostname"] not in ["", "<hidden>"], aps):
                self.write_ap_cache(ap)

    def on_association(self, agent, access_point):
        if self.ready:
            self.write_ap_cache(access_point)

    def on_deauthentication(self, agent, access_point, client_station):
        if self.ready:
            self.write_ap_cache(access_point)

    def on_handshake(self, agent, filename, access_point, client_station):
        if self.ready:
            self.write_ap_cache(access_point)

    def on_ui_update(self, ui):
        if not self.ready:
            return
        current_time = datetime.now(tz=UTC)
        if (current_time - self.last_clean).total_seconds() > 60:
            self.clean_ap_cache()
            self.last_clean = current_time
