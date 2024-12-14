# Gets status of Pisugar2 - requires installing the PiSugar-Power-Manager
# curl http://cdn.pisugar.com/release/Pisugar-power-manager.sh | sudo bash
#
# based on https://github.com/evilsocket/pwnagotchi/blob/master/pwnagotchi/plugins/default/ups_lite.py
# https://www.tindie.com/products/pisugar/pisugar2-battery-for-raspberry-pi-zero/
import logging

from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.plugins as plugins
import pwnagotchi
import time
from pisugar import *

class PiSugar(plugins.Plugin):
    __author__ = "10230718+tisboyo@users.noreply.github.com"
    __version__ = "0.0.1"
    __license__ = "GPL3"
    __description__ = "A plugin that will add a voltage indicator for the PiSugar 2"

    def __init__(self):
        self.is_new_model = False
        self.options = dict()
        conn, event_conn = connect_tcp()
        self.ps = PiSugarServer(conn, event_conn)

    def on_loaded(self):
        # Load here so it doesn't attempt to load if the plugin is not enabled

        logging.info("[pisugar2] plugin loaded.")

        if self.ps.get_battery_led_amount() == 2:
            self.is_new_model = True
        else:
            self.is_new_model = False

        if self.options["sync_rtc_on_boot"]:
            self.ps.rtc_rtc2pi()

    def on_ui_setup(self, ui):
        ui.add_element(
            "bat",
            LabeledValue(
                color=BLACK,
                label="BAT",
                value="0%",
                position=(ui.width() / 2 + 15, 0),
                label_font=fonts.Bold,
                text_font=fonts.Medium,
            ),
        )
        # display charging status
        if self.is_new_model:
            ui.add_element(
                "chg",
                LabeledValue(
                    color=BLACK,
                    label="",
                    value="",
                    position=(ui.width() / 2 - 12, 0),
                    label_font=fonts.Bold,
                    text_font=fonts.Bold,
                ),
            )

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element("bat")
            ui.remove_element("chg")

    def on_ui_update(self, ui):
        capacity = int(self.ps.get_battery_level())
        logging.info("BATT GET VALUE IS : " + str(capacity))
        # new model use battery_power_plugged & battery_allow_charging to detect real charging status
        if self.is_new_model:
            if self.ps.get_battery_power_plugged().value and self.ps.get_battery_allow_charging().value:
                ui.set("chg", "CHG")
                ui.update(force=True, new_data={"status": "Power!! I can feel it!"})
            else:
                ui.set("chg", "")

        ui.set("bat", str(capacity) + "%")

        if capacity <= self.options["shutdown"]:
            logging.info(
                f"[pisugar2] Empty battery (<= {self.options['shutdown']}): shutting down"
            )
            ui.update(force=True, new_data={"status": "Battery exhausted, bye ..."})
            time.sleep(3)
            pwnagotchi.shutdown()