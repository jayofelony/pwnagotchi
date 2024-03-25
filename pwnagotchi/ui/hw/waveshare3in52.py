import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class Waveshare3in52(DisplayImpl):
    def __init__(self, config):
        super(Waveshare3in52, self).__init__(config, 'waveshare3in52')

    def layout(self):
        fonts.setup(16, 14, 16, 50, 31, 15)
        self._layout['width'] = 360
        self._layout['height'] = 240
        self._layout['face'] = (0, 85)
        self._layout['name'] = (10, 30)
        self._layout['channel'] = (1, 4)
        self._layout['aps'] = (45, 4)
        self._layout['uptime'] = (250, 4)
        self._layout['line1'] = [0, 24, 360, 24]
        self._layout['line2'] = [0, 220, 360, 220]
        self._layout['friend_face'] = (0, 180)
        self._layout['friend_name'] = (0, 170)
        self._layout['shakes'] = (1, 223)
        self._layout['mode'] = (320, 222)
        self._layout['status'] = {
            'pos': (185, 50),
            'font': fonts.status_font(fonts.Small),
            'max': 100
        }
        return self._layout

    def initialize(self):
        logging.info("initializing waveshare 3.52 inch  display")
        from pwnagotchi.ui.hw.libs.waveshare.epaper.v3in52.epd3in52 import EPD
        self._display = EPD()
        self._display.init()
        self._display.Clear()

    def render(self, canvas):
        buf = self._display.getbuffer(canvas)
        self._display.display(buf)
        self._display.refresh()

    def clear(self):
        self._display.Clear()
