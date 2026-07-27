import logging
import json
import os
import re
import pathlib
from datetime import datetime, UTC
from threading import Lock


class CacheManager:
    """Core cache manager for AP information"""

    def __init__(self, config):
        self.lock = Lock()
        self.ready = False
        self.last_clean = None
        self.cache_dir = None

        try:
            handshake_dir = config["bettercap"].get("handshakes")
            self.cache_dir = os.path.join(handshake_dir, "cache")
            os.makedirs(self.cache_dir, exist_ok=True)
            self.last_clean = datetime.now(tz=UTC)
            self.ready = True
            logging.info("[CACHE] Cache manager initialized at %s", self.cache_dir)
        except Exception as e:
            logging.error(f"[CACHE] Failed to initialize cache: {e}")

    def write_ap_cache(self, access_point):
        """Write AP information to cache"""
        if not self.ready:
            return

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

    def read_ap_cache(self, cache_dir, file):
        """Read AP cache from disk"""
        cache_filename = os.path.basename(re.sub(r"\.(pcap|gps\.json|geo\.json)$", ".cache", file))
        cache_filename = os.path.join(cache_dir, cache_filename)
        if not os.path.exists(cache_filename):
            return None
        try:
            with open(cache_filename, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.debug(f"[CACHE] Exception reading cache: {e}")
            return None

    def clean_ap_cache(self):
        """Clean AP cache files older than 5 minutes"""
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
                logging.debug(f"[CACHE] Cleaning {len(cache_to_delete)} files")

            for cache_file in cache_to_delete:
                try:
                    cache_file.unlink()
                except FileNotFoundError:
                    pass

    def on_wifi_update(self, aps):
        """Cache APs from WiFi update events"""
        if self.ready:
            for ap in filter(lambda ap: ap.get("hostname") not in ["", "<hidden>"], aps):
                self.write_ap_cache(ap)

    def on_unfiltered_ap_list(self, aps):
        """Cache APs from unfiltered AP list events"""
        if self.ready:
            for ap in filter(lambda ap: ap.get("hostname") not in ["", "<hidden>"], aps):
                self.write_ap_cache(ap)

    def on_association(self, access_point):
        """Cache AP on association event"""
        if self.ready:
            self.write_ap_cache(access_point)

    def on_deauthentication(self, access_point, client_station):
        """Cache AP on deauthentication event"""
        if self.ready:
            self.write_ap_cache(access_point)

    def on_handshake(self, filename, access_point, client_station):
        """Cache AP on handshake event"""
        if self.ready:
            self.write_ap_cache(access_point)

    def periodic_cleanup(self):
        """Check if cleanup is needed (call periodically)"""
        if not self.ready or not self.last_clean:
            return

        current_time = datetime.now(tz=UTC)
        if (current_time - self.last_clean).total_seconds() > 60:
            self.clean_ap_cache()
            self.last_clean = current_time
