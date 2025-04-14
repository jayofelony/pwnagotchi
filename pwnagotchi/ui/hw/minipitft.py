# board GPIO:
# A:        GPIO23
# B:        GPIO24
#
# HW datasheet: https://learn.adafruit.com/adafruit-1-3-color-tft-bonnet-for-raspberry-pi/overview

import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.st7789 import st7789_display

class MiniPitft(st7789_display):
    def __init__(self, config):
        super(MiniPitft, self).__init__(config, 'minipitft')
        self.defaults['dc'] = 25
        self.defaults['bl'] = 22
        self.defaults['width'] = 240
        self.defaults['height'] = 240

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

