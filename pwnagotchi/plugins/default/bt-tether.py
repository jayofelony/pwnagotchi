import logging
import subprocess
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK

class BTTether(plugins.Plugin):
    __author__ = 'Jayofelony'
    __version__ = '1.0'
    __license__ = 'GPL3'
    __description__ = 'A new BT-Tether plugin'

    def __init__(self):
        self.ready = False
        self.options = dict()
        self.status = '-'

    def on_loaded(self):
        logging.info("[BT-Tether] plugin loaded.")

    def on_ready(self, agent):
        ip = self.options['ip']
        if self.options['phone'] == 'android':
            address = f'{ip}/24,192.168.44.1'
            route = '192.168.44.0/24,192.168.44.1'
        elif self.options['phone'] == 'ios':
            address = f'{ip}/24,172.20.10.1'
            route = '172.20.10.0/24,172.20.10.1'
        file = f'''
        [connection]
        id=bluetooth
        type=bluetooth
        autoconnect=yes
        [bluetooth]
        bdaddr={self.options['mac']}
        type=panu
        [ipv4]
        address1={address}
        route1={route}
        dns=8.8.8.8;1.1.1.1;
        method=manual
        [ipv6]
        addr-gen-mode=default
        method=disabled
        [proxy]
        '''
        try:
            file = '\n'.join(line.strip() for line in file.strip().splitlines() if line.strip())
            with open('/etc/NetworkManager/system-connections/bluetooth.nmconnection', 'w+') as bt_file:
                bt_file.write(file)
            subprocess.run(['chmod', '600', '/etc/NetworkManager/system-connections/bluetooth.nmconnection'], check=True)
            try:
                mac = self.options['mac']
                subprocess.run(['nmcli', 'device', 'connect', f'{mac}'], check=True)
            except Exception as e:
                logging.error(f"[BT-Tether] Failed to connect to device: {e}")
        except Exception as e:
            logging.error(f"[BT-Tether] Failed to save Bluetooth connection file: {e}")
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