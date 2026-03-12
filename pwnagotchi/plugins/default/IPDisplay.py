############################
# setup is simple
# main.plugins.IPDisplay.skip_devices = [
#     'eth0',
#     'usb0',
#     'bnep0',
#     'wlan0',
#     'ect...'
# ]
# main.plugins.IPDisplay.position = "0, 82"
# main.plugins.IPDisplay.delay_time = 2 # how many seconds to delay cycling devices

from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.plugins as plugins
import logging
import time
import subprocess

class IPDisplay(plugins.Plugin):
    __author__ = 'NeonLightning(thank to NurseJackass and jayofelony)'
    __version__ = '1.0.1'
    __license__ = 'GPL3'
    __description__ = 'Display IP addresses on the Pwnagotchi UI'

    def __init__(self):
        self.options = dict()
        self.device_skip_list = ['lo']
        self.device_index = 0
        self.ready = False
        self.last_update_time = 0
        self.skip_time = 0

    def on_loaded(self):
        self.skip_time = self.options.get('delay_time', 2)
        skip = self.options.get('skip_devices')
        if skip:
            self.device_skip_list = skip
        logging.info("[IPDisplay] plugin loaded")
        
    def on_ready(self, agent):
        self._agent = agent
        logging.info("IP Display Plugin ready.")
        self.ready = True

    def on_ui_setup(self, ui):
        try:
            pos = self.options['position']
            if isinstance(pos, str):
                pos = tuple(int(x.strip()) for x in pos.split(','))
            pos1 = pos
        except Exception:
            pos1 = (0, 82)
        ui.add_element('ip1', LabeledValue(color=BLACK, label="", value='Initializing...',
                                           position=pos1, label_font=fonts.Small, text_font=fonts.Small))

    def get_iface_addrs(self):
        command = f"ip -4 -o addr | awk '/inet / {{print $2 \":\" $4}}' | cut -d '/' -f 1"
        ifaces = []
        for line in subprocess.getoutput(command).split('\n'):
            pts = line.strip().split(":")
            if pts[0].lower() not in self.device_skip_list:
                ifaces.append(line.strip())
        return ifaces
    
    def on_ui_update(self, ui):
        try:
            if time.time() - self.last_update_time < self.skip_time:
                return
            self.last_update_time = time.time()
            self.device_index += 1
            ifaces = self.get_iface_addrs()
            if not ifaces:
                ui.set('ip1', '')
                return
            if self.device_index >= len(ifaces):
                self.device_index = 0
            current_device = ifaces[self.device_index]
            if current_device.startswith("bnep0:"):
                try:
                    connected_devices = subprocess.check_output(['hcitool', 'con'], timeout=5)
                    if b'ACL' not in connected_devices:
                        self.device_index += 1
                        if self.device_index >= len(ifaces):
                            self.device_index = 0
                        if not ifaces:
                            return
                        current_device = ifaces[self.device_index]
                except Exception:
                    pass
            ui.set('ip1', f'{current_device}')
        except Exception as e:
            logging.exception(repr(e))   
                
    def on_unload(self, ui):
        self.ready = False
        ui.remove_element('ip1')
        logging.info("IP Display Plugin unloaded.")
