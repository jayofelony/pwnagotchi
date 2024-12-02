# Created for the Pwnagotchi project by RasTacsko
# HW libraries are based on the adafruit python SSD1306 repo:
# https://github.com/adafruit/Adafruit_Python_SSD1306
# SMBus parts coming from BLavery's lib_oled96 repo:
# https://github.com/BLavery/lib_oled96
# I2C address, width and height import from config.toml made by NurseJackass

import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl

#
# Default is 128x64 display on i2c address 0x3C
#
# Configure i2c address and dimensions in config.toml:
#
# ui.display.type = "i2coled"
# ui.display.i2c_addr = 0x3C
# ui.display.width = 128
# ui.display.height = 64
#

class I2COled(DisplayImpl):
    def __init__(self, config):
        self._config = config['ui']['display']
        super(I2COled, self).__init__(config, 'i2coled')

    def layout(self):
        fonts.setup(8, 8, 8, 10, 10, 8)
        self._layout['width'] = self._config['width'] if 'width' in self._config else 128
        self._layout['height'] = self._config['height'] if 'height' in self._config else 64
        self._layout['face'] = (0, 30)
        self._layout['name'] = (0, 10)
        self._layout['channel'] = (72, 10)
        self._layout['aps'] = (0, 0)
        self._layout['uptime'] = (87, 0)
        self._layout['line1'] = [0, 9, 128, 9]
        self._layout['line2'] = [0, 54, 128, 54]
        self._layout['friend_face'] = (0, 41)
        self._layout['friend_name'] = (40, 43)
        self._layout['shakes'] = (0, 55)
        self._layout['mode'] = (107, 10)
        self._layout['status'] = {
            'pos': (37, 19),
            'font': fonts.status_font(fonts.Small),
            'max': 18
        }
        return self._layout

    def initialize(self):
        i2caddr = self._config['i2c_addr'] if 'i2c_addr' in self._config else 0x3C
        width = self._config['width'] if 'width' in self._config else 128
        height = self._config['height'] if 'height' in self._config else 64
        logging.info("Initializing SSD1306 based %dx%d I2C Oled Display on address 0x%X" % (width, height, i2caddr))
        logging.info("Available config options: ui.display.width, ui.display.height and ui.display.i2caddr")

        from pwnagotchi.ui.hw.libs.i2coled.oled import OLED
        self._display = OLED(address=i2caddr, width=width, height=height)
        self._display.Init()
        self._display.Clear()

    def render(self, canvas):
        self._display.display(canvas)

    def clear(self):
        self._display.Clear()
