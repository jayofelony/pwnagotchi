import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class Waveshare3in52(DisplayImpl):
    def __init__(self, config):
        super(Waveshare3in52, self).__init__(config, 'waveshare3in52')

    def layout(self):
        fonts.setup(16, 14, 16, 100, 31, 15)
        self._layout['width'] = 360
        self._layout['height'] = 240
        self._layout['face'] = (0, 40)
        self._layout['name'] = (0, 0)
        self._layout['channel'] = (300, 0)
        self._layout['aps'] = (0, 220)
        self._layout['uptime'] = (120, 0)
        self._layout['line1'] = [0, 24, 360, 24]
        self._layout['line2'] = [0, 220, 360, 220]
        self._layout['friend_face'] = (0, 195)
        self._layout['friend_name'] = (0, 185)
        self._layout['shakes'] = (100, 220)
        self._layout['mode'] = (0,200)
        self._layout['status'] = {
            'pos': (3, 170),
            'font': fonts.status_font(fonts.Small),
            'max': 100
        }
        return self._layout

    def initialize(self):
        logging.info("initializing waveshare 3.52 inch  display")
        from pwnagotchi.ui.hw.libs.waveshare.v3in52.epd3in52 import EPD
        self._display = EPD()
        self._display.init()
        self._display.Clear()

    def render(self, canvas):
        buf = self._display.getbuffer(canvas)
        self._display.display(buf)
        self._display.refresh()


    def clear(self):
        self._display.Clear()
