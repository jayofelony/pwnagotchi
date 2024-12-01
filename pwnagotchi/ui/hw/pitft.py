# board GPIO:
# Key1 (for2,8"): GPIO17
# Key2 (for2,8"): GPIO22
# Key3 (for2,8"): GPIO23
# Key4 (for2,8"): GPIO27
#
# Key1 (for2,4"): GPIO16
# Key2 (for2,4"): GPIO13
# Key3 (for2,4"): GPIO12
# Key4 (for2,4"): GPIO6
# Key5 (for2,4"): GPIO5
#
# Touch chipset: STMPE610
# HW datasheet 2,8": https://learn.adafruit.com/adafruit-pitft-28-inch-resistive-touchscreen-display-raspberry-pi/overview
# HW datasheet 2,4": https://learn.adafruit.com/adafruit-2-4-pitft-hat-with-resistive-touchscreen-mini-kit/overview

import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class Pitft(DisplayImpl):
    def __init__(self, config):
        super(Pitft, self).__init__(config, 'pitft')
        self._display = None

    def layout(self):
        fonts.setup(12, 10, 12, 70, 25, 9)
        self._layout['width'] = 320
        self._layout['height'] = 240
        self._layout['face'] = (0, 36)
        self._layout['name'] = (150, 36)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (40, 0)
        self._layout['uptime'] = (240, 0)
        self._layout['line1'] = [0, 14, 320, 14]
        self._layout['line2'] = [0, 220, 320, 220]
        self._layout['friend_face'] = (0, 130)
        self._layout['friend_name'] = (40, 135)
        self._layout['shakes'] = (0, 220)
        self._layout['mode'] = (280, 220)
        self._layout['status'] = {
            'pos': (150, 48),
            'font': fonts.status_font(fonts.Medium),
            'max': 20
        }

        return self._layout

    def initialize(self):
        logging.info("Initializing adafruit pitft 320x240 screen")
        logging.info("Available pins for GPIO Buttons on the 3,2inch: 17, 22, 23, 27")
        logging.info("Available pins for GPIO Buttons on the 2,8inch: 26, 13, 12, 6, 5")
        logging.info("Backlight pin available on GPIO 18")
        from pwnagotchi.ui.hw.libs.adafruit.pitft.ILI9341 import ILI9341
        self._display = ILI9341(0, 0, 25, 18)

    def render(self, canvas):
        self._display.display(canvas)

    def clear(self):
        self._display.clear()
