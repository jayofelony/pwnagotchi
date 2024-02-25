# Based on UPS Lite v1.1 from https://github.com/xenDE
# Made specifically to address the problems caused by the hardware changes in 1.3.  Oh yeah I also removed the auto-shutdown feature because it's kind of broken.
#
# To setup, see page six of this manual to see how to enable i2c:
# https://github.com/linshuqin329/UPS-Lite/blob/master/UPS-Lite_V1.3_CW2015/Instructions%20for%20UPS-Lite%20V1.3.pdf
#
# Follow page seven, install the dependencies (python-smbus) and copy this script over for later use:
# https://github.com/linshuqin329/UPS-Lite/blob/master/UPS-Lite_V1.3_CW2015/UPS_Lite_V1.3_CW2015.py
#
# Now, install this plugin by copying this to the 'available-plugins' folder in your pwnagotchi, install and enable the plugin with the commands:
# sudo pwnagotchi plugins install upslite_plugin_1_3
# sudo pwnagotchi plugins enable upslite_plugin_1_3
#
# Now restart raspberry pi. Once back up ensure upslite_plugin_1_3 plugin is turned on in the WebUI. If there is still '0%' on your battery meter
# run the script we saved earlier and ensure that the pwnagotchi is plugged in both at the battery and the raspberry pi. The script should start trying to
# read the battery, and should be successful once there's a USB cable running power to the battery supply.

import logging
import struct

import RPi.GPIO as GPIO

import pwnagotchi
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK

CW2015_ADDRESS = 0X62
CW2015_REG_VCELL = 0X02
CW2015_REG_SOC = 0X04
CW2015_REG_MODE = 0X0A


# TODO: add enable switch in config.yml an cleanup all to the best place
class UPS:
    def __init__(self):
        # only import when the module is loaded and enabled
        import smbus
        # 0 = /dev/i2c-0 (port I2C0), 1 = /dev/i2c-1 (port I2C1)
        self._bus = smbus.SMBus(1)

    def voltage(self):
        try:
            read = self._bus.read_word_data(CW2015_ADDRESS, CW2015_REG_VCELL)
            swapped = struct.unpack("<H", struct.pack(">H", read))[0]
            return swapped * 1.25 / 1000 / 16
        except:
            return 0.0

    def capacity(self):
        try:
            address = 0x36
            read = self._bus.read_word_data(CW2015_ADDRESS, CW2015_REG_SOC)
            swapped = struct.unpack("<H", struct.pack(">H", read))[0]
            return swapped / 256
        except:
            return 0.0

    def charging(self):
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(4, GPIO.IN)
            return '+' if GPIO.input(4) == GPIO.HIGH else '-'
        except:
            return '-'


class UPSLite(plugins.Plugin):
    __author__ = 'marbasec'
    __version__ = '1.3.0'
    __license__ = 'GPL3'
    __description__ = 'A plugin that will add a voltage indicator for the UPS Lite v1.3'

    def __init__(self):
        self.ups = None

    def on_loaded(self):
        self.ups = UPS()

    def on_ui_setup(self, ui):
        ui.add_element('ups', LabeledValue(color=BLACK, label='UPS', value='0%', position=(ui.width() / 2 + 15, 0),
                                           label_font=fonts.Bold, text_font=fonts.Medium))

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element('ups')

    def on_ui_update(self, ui):
        capacity = self.ups.capacity()
        charging = self.ups.charging()
        ui.set('ups', "%2i%s" % (capacity, charging))
