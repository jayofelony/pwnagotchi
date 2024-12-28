import logging
import subprocess
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK

class BTTether(plugins.Plugin):
    __author__ = 'Jayofelony'
    __version__ = '1.1'
    __license__ = 'GPL3'
    __description__ = 'A new BT-Tether plugin'

    def __init__(self):
        self.ready = False
        self.options = dict()
        self.status = '-'

    def on_loaded(self):
        logging.info("[BT-Tether] plugin loaded.")

    def on_config_changed(self, config):
        ip = config['main']['plugins']['bt-tether']['ip']
        phone_name = config['main']['plugins']['bt-tether']['phone-name'] + ' Network'
        if config['main']['plugins']['bt-tether']['phone'].lower() == 'android':
            address = f'{ip}'
            gateway = '192.168.44.1'
        elif config['main']['plugins']['bt-tether']['phone'].lower() == 'ios':
            address = f'{ip}'
            gateway = '172.20.10.1'
        try:
            subprocess.run(['nmcli', 'connection', 'modify', f'{phone_name}', 'ipv4.addresses', f'{address}', 'ipv4.gateway',f'{gateway}', 'ipv4.route-metric', '100'], check=True)
            subprocess.run(['nmcli', 'connection', 'reload'], check=True)
            subprocess.run(['systemctl', 'restart', 'NetworkManager'], check=True)
        except Exception as e:
            logging.error(f"[BT-Tether] Failed to connect to device: {e}")
        self.ready = True

    def on_ready(self, agent):
        try:
            mac = self.options['mac']
            subprocess.run(['nmcli', 'device', 'connect', f'{mac}'], check=True)
        except Exception as e:
            logging.error(f"[BT-Tether] Failed to connect to device: {e}")
        self.ready = True

    def on_ui_setup(self, ui):
        with ui._lock:
            ui.add_element('bluetooth', LabeledValue(color=BLACK, label='BT', value='-',
                                                     position=(ui.width() / 2 - 10, 0),
                                                     label_font=fonts.Bold, text_font=fonts.Medium))

    def on_ui_update(self, ui):
        if (subprocess.run(['bluetoothctl', 'info'], capture_output=True, text=True)).stdout.find('Connected: yes') != -1:
            self.status = 'C'
        else:
            self.status = '-'
            try:
                mac = self.options['mac']
                subprocess.run(['nmcli', 'device', 'connect', f'{mac}'], check=True)
            except Exception as e:
                logging.error(f"[BT-Tether] Failed to connect to device: {e}")
        ui.set('bluetooth', self.status)

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element('bluetooth')
        try:
            mac = self.options['mac']
            subprocess.run(['nmcli', 'device', 'disconnect', f'{mac}'], check=True)
            logging.info(f"[BT-Tether] Disconnected from device with MAC: {mac}")
        except Exception as e:
            logging.error(f"[BT-Tether] Failed to disconnect from device: {e}")