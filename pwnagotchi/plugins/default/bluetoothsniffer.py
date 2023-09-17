import logging
import os
import subprocess
import json
import time

import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
from datetime import datetime


class BluetoothSniffer(plugins.Plugin):
    __author__ = 'diytechtinker'
    __version__ = '0.1.3'
    __license__ = 'GPL3'
    __description__ = 'A plugin that sniffs Bluetooth devices and saves their MAC addresses, name and counts to a JSON file'

    def __init__(self):
        # Defining the instance variables
        self.options = {
            'timer': 45,
            'devices_file': '/root/handshakes/bluetooth_devices.json',
            'count_interval': 86400,
            'bt_x_coord': 160,
            'bt_y_coord': 66
        }
        self.data = {}
        self.last_scan_time = 0

    def on_loaded(self):
        logging.info("[BtS] bluetoothsniffer plugin loaded.")
        logging.info("[BtS] Bluetooth devices file location: %s", self.options['devices_file'])
        # Creating the device file path if it does not exist
        if not os.path.exists(os.path.dirname(self.options['devices_file'])):
            os.makedirs(os.path.dirname(self.options['devices_file']))

        # Creating the device file if it does not exist
        if not os.path.exists(self.options['devices_file']):
            with open(self.options['devices_file'], 'w') as f:
                json.dump({}, f)

        # Loading the data from the device file
        with open(self.options['devices_file'], 'r') as f:
            self.data = json.load(f)

    def on_ui_setup(self, ui):
        with ui._lock:
            ui.add_element('BtS', LabeledValue(color=BLACK,
                                               label='BT SNFD',
                                               value=" ",
                                               position=(int(self.options["bt_x_coord"]),
                                                         int(self.options["bt_y_coord"])),
                                               label_font=fonts.Small,
                                               text_font=fonts.Small))

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element('BtS')

    def on_ui_update(self, ui):
        current_time = time.time()
        # Checking the time elapsed since last scan
        if current_time - self.last_scan_time >= self.options['timer']:
            self.last_scan_time = current_time
            # logging.info("[BtS] Bluetooth sniffed: %s", str(self.bt_sniff_info()))
            ui.set('BtS', str(self.bt_sniff_info()))
            self.scan(ui)

    # Method for scanning the nearby bluetooth devices
    def scan(self, display):
        logging.info("[BtS] Scanning for bluetooths...")
        current_time = time.time()
        changed = False

        # Running the system command hcitool to scan nearby bluetooth devices
        cmd_inq = "hcitool inq --flush"
        try:
            inq_output = subprocess.check_output(cmd_inq.split())
        except subprocess.CalledProcessError as e:
            logging.error("[BtS] Error running command: %s", e)

        for line in inq_output.splitlines()[1:]:
            fields = line.split()
            mac_address = fields[0].decode()
            for i in range(len(fields)):
                if fields[i].decode() == "class:" and i+1 < len(fields):
                    device_class = fields[i+1].decode()
            logging.info("[BtS] Found bluetooth %s", mac_address)

            # Update the count, first_seen, and last_seen time of the device
            if mac_address in self.data and len(self.data) > 0:
                if 'Unknown' == self.data[mac_address]['name']:
                    name = self.get_device_name(mac_address)
                    self.data[mac_address]['name'] = name
                    self.data[mac_address]['new_info'] = 2
                    logging.info("[BtS] Updated bluetooth name: %s", name)
                    changed = True

                if 'Unknown' == self.data[mac_address]['manufacturer']:
                    manufacturer = self.get_device_manufacturer(mac_address)
                    self.data[mac_address]['manufacturer'] = manufacturer
                    self.data[mac_address]['new_info'] = 2
                    logging.info("[BtS] Updated bluetooth manufacturer: %s", manufacturer)
                    changed = True

                if device_class != self.data[mac_address]['class']:
                    self.data[mac_address]['class'] = device_class
                    self.data[mac_address]['new_info'] = 2
                    logging.info("[BtS] Updated bluetooth class: %s", device_class)
                    changed = True

                last_seen_time = int(datetime.strptime(self.data[mac_address]['last_seen'], '%H:%M:%S %d-%m-%Y').timestamp())
                if current_time - last_seen_time >= self.options['count_interval']:
                    self.data[mac_address]['count'] += 1
                    self.data[mac_address]['last_seen'] = time.strftime('%H:%M:%S %d-%m-%Y', time.localtime(current_time))
                    self.data[mac_address]['new_info'] = 2
                    logging.info("[BtS] Updated bluetooth count.")
                    changed = True
            else:
                name = self.get_device_name(mac_address)
                manufacturer = self.get_device_manufacturer(mac_address)
                self.data[mac_address] = {'name': name, 'count': 1, 'class': device_class, 'manufacturer': manufacturer, 'first_seen': time.strftime('%H:%M:%S %d-%m-%Y', time.localtime(current_time)), 'last_seen': time.strftime('%H:%M:%S %d-%m-%Y', time.localtime(current_time)), 'new_info': True}
                logging.info("[BtS] Added new bluetooth device %s with MAC: %s", name, mac_address)
                changed = True

        # Save the updated devices to the JSON file
        if changed:
            with open(self.options['devices_file'], 'w') as f:
                logging.info("[BtS] Saving bluetooths %s into json.", name)
                json.dump(self.data, f)
            display.set('status', 'Bluetooth sniffed and stored!')
            display.update(force=True)

    # Method to get the device name
    def get_device_name(self, mac_address):
        logging.info("[BtS] Trying to get name for %s", mac_address)
        name = 'Unknown'
        hcitool_process = subprocess.Popen(["hcitool", "name", mac_address], stdout=subprocess.PIPE)
        output, error = hcitool_process.communicate()
        if output.decode().strip() != '':
            name = output.decode().strip()
        logging.info("[BtS] Got name %s for %s", name, mac_address)
        return name

    # Method to get the device manufacturer
    def get_device_manufacturer(self, mac_address):
        manufacturer = 'Unknown'
        cmd_info = f"hcitool info {mac_address} | grep 'Manufacturer:' | cut -d ' ' -f 2-"
        try:
            logging.info("[BtS] Trying to get manufacturer for %s", mac_address)
            start_time = time.time()
            process = subprocess.Popen(cmd_info, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            while process.poll() is None:
                time.sleep(0.1)
                if time.time() - start_time > 7:
                    logging.info("[BtS] Timeout while trying to get manufacturer for %s", mac_address)
                    process.kill()
                    return manufacturer
            output, error = process.communicate(timeout=1)
            if output.decode().strip() != '':
                manufacturer = output.decode().strip()
            logging.info("[BtS] Got manufacturer %s for %s", manufacturer, mac_address)
        except Exception as e:
            logging.info("[BtS] Error while trying to get manufacturer for %s: %s", mac_address, str(e))
        return manufacturer

    def bt_sniff_info(self):
        num_devices = len(self.data)
        if num_devices > 0:
            num_unknown = sum(1 for device in self.data.values() if device['name'] == 'Unknown' or device['manufacturer'] == 'Unknown')
            num_known = num_devices - num_unknown
            return_text = "%s|%s" % (num_devices, num_known)
        else:
            return_text = "0|0"
        return return_text