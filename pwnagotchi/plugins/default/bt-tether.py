import logging
import subprocess
import re

import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK

MAC_PTTRN = "^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
IP_PTTRN = "^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$"

class BTTether(plugins.Plugin):
    __author__ = "Jayofelony, modified my fmatray"
    __version__ = "1.3"
    __license__ = "GPL3"
    __description__ = "A new BT-Tether plugin"

    def __init__(self):
        self.ready = False
        self.options = dict()
        self.phone_name = None
        self.mac = None

    @staticmethod
    def nmcli(args, pattern=None):
        try:
            result = subprocess.run(["nmcli"] + args, 
                                    check=True, capture_output=True, text=True)
            if pattern:
                return result.stdout.find(pattern)
            return result
        except Exception as exp:
            logging.error(f"[BT-Tether] Error with nmcli: {exp}")
            raise exp

    def on_loaded(self):
        logging.info("[BT-Tether] plugin loaded.")

    def on_config_changed(self, config):
        if "phone-name" not in self.options:
            logging.error("[BT-Tether] Phone name not provided")
            return
        if not ("mac" in self.options and re.match(MAC_PTTRN, self.options["mac"])):
            logging.error("[BT-Tether] Error with mac adresse")
            return            

        if not ("phone" in self.options and self.options["phone"].lower() in ["android", "ios"]):
            logging.error("[BT-Tether] Phone type not supported")
            return
        if self.options["phone"].lower() == "android":
            address = self.options.get("ip", "192.168.44.2")
            gateway = "192.168.44.1"
        elif self.options["phone"].lower() == "ios":
            address = self.options.get("ip", "172.20.10.2")
            gateway = "172.20.10.1"
        if not re.match(IP_PTTRN, address):
            logging.error(f"[BT-Tether] IP error: {address}")
            return

        self.phone_name = self.options["phone-name"] + " Network"
        self.mac = self.options["mac"]
        dns = self.options.get("dns", "8.8.8.8 1.1.1.1").replace(",", " ").replace(";", " ")

        try:
            # Configure connection. Metric is set to 200 to prefer connection over USB
            self.nmcli(["connection", "modify", f"{self.phone_name}",
                        "connection.type", "bluetooth",
                        "bluetooth.type", "panu",
                        "bluetooth.bdaddr", f"{self.mac}",
                        "connection.autoconnect", "yes",
                        "connection.autoconnect-retries", "0",
                        "ipv4.method", "manual",
                        "ipv4.dns", f"{dns}",
                        "ipv4.addresses", f"{address}/24",
                        "ipv4.gateway", f"{gateway}",
                        "ipv4.route-metric", "200" ])
            self.nmcli(["connection", "reload"])
            self.ready = True
            logging.info(f"[BT-Tether] Connection {self.phone_name} configured")
        except Exception as e:
            logging.error(f"[BT-Tether] Error while configuring: {e}")
            return
        try:
            self.nmcli(["connection", "up", f"{self.phone_name}"])
        except Exception as e:
            logging.error(f"[BT-Tether] Failed to connect to device: {e}")
            logging.error(
                f"[BT-Tether] Failed to connect to device: have you enabled bluetooth tethering on your phone?"
            )

    def on_ui_setup(self, ui):
        with ui._lock:
            ui.add_element('bluetooth', LabeledValue(color=BLACK, label='BT', value='-',
                                                     position=(ui.width() / 2 - 10, 0),
                                                     label_font=fonts.Bold, text_font=fonts.Medium))
    def on_ui_update(self, ui):
        if not self.ready:
            return
        with ui._lock:
            status = ""
            try:
                # Checking connection
                if self.nmcli(["-w", "0", "-g", "GENERAL.STATE", "connection", "show", self.phone_name], 
                                "activated") != -1:
                    ui.set("bluetooth", "U")
                    return
                else:
                    ui.set("bluetooth", "D")
                    status = "BT Conn. down"
                    
                # Checking device
                if self.nmcli(["-w", "0", "-g", "GENERAL.STATE", "device", "show", self.mac], 
                            "(connected)") != -1:
                    ui.set("bluetooth", "C")
                    status += "\nBT dev conn."
                else:
                    ui.set("bluetooth", "-")
                    status += "\nBT dev disconn."
                ui.set("status", status)
            except Exception as e:
                logging.error(f"[BT-Tether] Error on update: {e}")

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element("bluetooth")
        try:
            self.nmcli(["connection", "down", f"{self.phone_name}"])
        except Exception as e:
            logging.error(f"[BT-Tether] Failed to disconnect from device: {e}")
