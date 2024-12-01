# board GPIO:
# A:        GPIO23
# B:        GPIO24
#
# HW datasheet: https://learn.adafruit.com/adafruit-1-3-color-tft-bonnet-for-raspberry-pi/overview

import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class MiniPitft(DisplayImpl):
    def __init__(self, config):
        super(MiniPitft, self).__init__(config, 'minipitft')

    def layout(self):
        fonts.setup(10, 9, 10, 35, 25, 9)
        self._layout['width'] = 240
        self._layout['height'] = 240
        self._layout['face'] = (0, 40)
        self._layout['name'] = (5, 20)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (28, 0)
        self._layout['uptime'] = (175, 0)
        self._layout['line1'] = [0, 14, 240, 14]
        self._layout['line2'] = [0, 108, 240, 108]
        self._layout['friend_face'] = (0, 92)
        self._layout['friend_name'] = (40, 94)
        self._layout['shakes'] = (0, 109)
        self._layout['mode'] = (215, 109)
        self._layout['status'] = {
            'pos': (125, 20),
            'font': fonts.status_font(fonts.Medium),
            'max': 20
        }

        return self._layout

    def initialize(self):
        logging.info("Initializing Adafruit Mini Pi Tft 240x240")
        logging.info("Available pins for GPIO Buttons: 23, 24")
        logging.info("Backlight pin available on GPIO 22")        
        logging.info("I2C bus available on stemma QT header")
        from pwnagotchi.ui.hw.libs.adafruit.minipitft.ST7789 import ST7789
        self._display = ST7789(0,0,25,22)

    def render(self, canvas):
        self._display.display(canvas)

    def clear(self):
        self._display.clear()