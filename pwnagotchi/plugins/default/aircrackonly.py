import pwnagotchi.plugins as plugins

import logging
import subprocess
import string
import os

'''
Aircrack-ng needed, to install:
> apt-get install aircrack-ng
'''


class AircrackOnly(plugins.Plugin):
    __author__ = 'pwnagotchi [at] rossmarks [dot] uk'
    __version__ = '1.0.1'
    __license__ = 'GPL3'
    __description__ = 'confirm pcap contains handshake/PMKID or delete it'

    def __init__(self):
        self.text_to_set = ""
        self.options = dict()

    def on_ready(self):
        return

    def on_loaded(self):
        logging.info("aircrackonly plugin loaded")

        if 'face' not in self.options:
            self.options['face'] = '(>.<)'

        check = subprocess.run(
            '/usr/bin/dpkg -l aircrack-ng | grep aircrack-ng | awk \'{print $2, $3}\'', shell=True,
            stdout=subprocess.PIPE)
        check = check.stdout.decode('utf-8').strip()
        if check != "aircrack-ng <none>":
            logging.info("aircrackonly: Found " + check)
        else:
            logging.warning("aircrack-ng is not installed!")

    def on_handshake(self, agent, filename, access_point, client_station):
        display = agent.view()
        to_delete = 0
        handshake_found = 0

        result = subprocess.run(('/usr/bin/aircrack-ng ' + filename + ' | grep "1 handshake" | awk \'{print $2}\''),
                                shell=True, stdout=subprocess.PIPE)
        result = result.stdout.decode('utf-8').translate({ord(c): None for c in string.whitespace})
        if result:
            handshake_found = 1
            logging.info("[AircrackOnly] contains handshake")

        if handshake_found == 0:
            result = subprocess.run(('/usr/bin/aircrack-ng ' + filename + ' | grep "PMKID" | awk \'{print $2}\''),
                                    shell=True, stdout=subprocess.PIPE)
            result = result.stdout.decode('utf-8').translate({ord(c): None for c in string.whitespace})
            if result:
                logging.info("[AircrackOnly] contains PMKID")
            else:
                to_delete = 1

        if to_delete == 1:
            os.remove(filename)
            self.text_to_set = "Removed an uncrackable pcap"
            logging.warning("Removed uncrackable pcap " + filename)
            display.update(force=True)

    def on_ui_update(self, ui):
        if self.text_to_set:
            ui.set('face', self.options['face'])
            ui.set('status', self.text_to_set)
            self.text_to_set = ""
