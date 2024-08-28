import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class Waveshare3in7(DisplayImpl):
    def __init__(self, config):
        super(Waveshare3in7, self).__init__(config, 'waveshare3in7')

    def layout(self):
        fonts.setup(20, 19, 20, 45, 35, 19)
        self._layout['width'] = 480
        self._layout['height'] = 280
        self._layout['face'] = (0,34)
        self._layout['name'] = (35,105)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (75,0)
        self._layout['uptime'] = (377,0)
        self._layout['line1'] = [0, 25, 480, 25]
        self._layout['line2'] = [0, 255, 480, 255]
        self._layout['friend_face'] = (0, 146)
        self._layout['friend_name'] = (40, 146)
        self._layout['shakes'] = (0, 258)
        self._layout['mode'] = (430, 258)
        self._layout['status'] = {
        'pos': (225, 35),
        'font': fonts.status_font(fonts.Medium),
        'max': 21
        }
        return self._layout

    def initialize(self):
        logging.info("initializing waveshare 3.7 inch lcd display")
        from pwnagotchi.ui.hw.libs.waveshare.epaper.v3in7.epd3in7 import EPD
        self._display = EPD()
        self._display.init(0)
        self._display.Clear(0)
        self._display.init(1)  # 1Gray mode

    def render(self, canvas):
        buf = self._display.getbuffer(canvas)
        self._display.display_1Gray(buf)

    def clear(self):
        self._display.Clear(0)
