import logging
import json
import os
import re

import pwnagotchi.plugins as plugins
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts

def get_cache():
    return None

class Cache(plugins.Plugin):
    __author__ = "fmatray"
    __version__ = "1.0.0"
    __license__ = "GPL3"
    __description__ = "A simple plugin to cache AP informations"

    def __init__(self):
        self.options = dict()

    def on_config_changed(self, config):
        self.handshake_dir = config["bettercap"].get("handshakes")
        self.cache_dir = os.path.join(self.handshake_dir, "cache")
        if not (os.path.exists(self.cache_dir)):
            os.mkdir(self.cache_dir)

    def get_cache(self, file):
        cache_filename = os.path.basename(
            re.sub(r"\.(pcap|gps\.json|geo\.json)$", ".cache", file)
        )
        cache_filename = os.path.join(self.cache_dir, cache_filename)
        if not os.path.exists(cache_filename):
            return None
        try:
            with open(cache_filename, "r") as f:
                return json.load(f)
        except Exception as e:
            return None

    def cache_ap(self, ap):
        mac = ap["mac"].replace(":", "")
        hostname = re.sub(r"[^a-zA-Z0-9]", "", ap["hostname"])
        filename = os.path.join(self.cache_dir, f"{hostname}_{mac}.cache")
        with open(filename, "w") as f:
            json.dump(ap, f)

    def on_unfiltered_ap_list(self, agent, aps):
        for ap in filter(lambda ap: ap["hostname"] not in ["", "<hidden>"], aps):
            self.cache_ap(ap)

    def on_handshake(self, agent, filename, access_point, client_station):
        logging.info(f"[WIGLE] on_handshake")
        self.cache_ap(access_point)
