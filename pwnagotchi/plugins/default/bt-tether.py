import logging
import subprocess
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK

class BTTether(plugins.Plugin):
    __author__ = 'Jayofelony'
    __version__ = '1.2'
    __license__ = 'GPL3'
    __description__ = 'A new BT-Tether plugin'

    def __init__(self):
        self.ready = False
        self.options = dict()
        self.status = '-'

    def on_loaded(self):
        logging.info("[BT-Tether] plugin loaded.")

    def on_config_changed(self, config):
        if any(self.options[key] == '' for key in ['phone', 'phone-name', 'ip', 'mac']):
            self.ready = False
        ip = self.options['ip']
        mac = self.options['mac']
        phone_name = self.options['phone-name'] + ' Network'
        if self.options['phone'].lower() == 'android':
            address = f'{ip}'
            gateway = '192.168.44.1'
        elif self.options['phone'].lower() == 'ios':
            address = f'{ip}'
            gateway = '172.20.10.1'
        else:
            logging.error("[BT-Tether] Phone type not supported.")
            return
        try:
            subprocess.run([
                'nmcli', 'connection', 'modify', f'{phone_name}',
                'connection.type', 'bluetooth',
                'bluetooth.type', 'panu',
                'bluetooth.bdaddr', f'{mac}',
                'ipv4.method', 'manual',
                'ipv4.dns', '8.8.8.8;1.1.1.1;'
                'ipv4.addresses', f'{address}',
                'ipv4.gateway', f'{gateway}',
                'ipv4.route-metric', '100'
            ], check=True)
            subprocess.run(['nmcli', 'connection', 'reload'], check=True)
            subprocess.run(['nmcli', 'connection', 'up', f'{phone_name}'], check=True)
        except Exception as e:
            logging.debug(f"[BT-Tether] Failed to connect to device: {e}")
            logging.error(f"[BT-Tether] Failed to connect to device: have you enabled bluetooth tethering on your phone?")
        self.ready = True

    def on_ready(self, agent):
        if any(self.options[key] == '' for key in ['phone', 'phone-name', 'ip', 'mac']):
            self.ready = False
        self.ready = True

    def on_ui_setup(self, ui):
        with ui._lock:
            ui.add_element('bluetooth', LabeledValue(color=BLACK, label='BT', value='-',
                                                     position=(ui.width() / 2 - 10, 0),
                                                     label_font=fonts.Bold, text_font=fonts.Medium))

    def on_ui_update(self, ui):
        if self.ready:
            phone_name = self.options['phone-name'] + ' Network'
            if (subprocess.run(['bluetoothctl', 'info'], capture_output=True, text=True)).stdout.find('Connected: yes') != -1:
                self.status = 'C'
            else:
                self.status = '-'
                try:
                    subprocess.run(['nmcli', 'connection', 'up', f'{phone_name}'], check=True)
                except Exception as e:
                    logging.debug(f"[BT-Tether] Failed to connect to device: {e}")
                    logging.error(f"[BT-Tether] Failed to connect to device: have you enabled bluetooth tethering on your phone?")
            ui.set('bluetooth', self.status)
        return

    def on_unload(self, ui):
        phone_name = self.options['phone-name'] + ' Network'
        with ui._lock:
            ui.remove_element('bluetooth')
        try:
            if (subprocess.run(['bluetoothctl', 'info'], capture_output=True, text=True)).stdout.find('Connected: yes') != -1:
                subprocess.run(['nmcli', 'connection', 'down', f'{phone_name}'], check=True)
                logging.info(f"[BT-Tether] Disconnected from device with name: {phone_name}")
            else:
                logging.info(f"[BT-Tether] Device with name {phone_name} is not connected, not disconnecting")
        except Exception as e:
            logging.error(f"[BT-Tether] Failed to disconnect from device: {e}")