import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class Waveshare29bV4(DisplayImpl):
    def __init__(self, config):
        super(Waveshare29bV4, self).__init__(config, 'waveshare2in9b_v4')
        self._display = None

    def layout(self):
        fonts.setup(10, 9, 10, 35, 25, 9)
        self._layout['width'] = 296
        self._layout['height'] = 128
        self._layout['face'] = (0, 40)
        self._layout['name'] = (5, 25)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (28, 0)
        self._layout['uptime'] = (230, 0)
        self._layout['line1'] = [0, 14, 296, 14]
        self._layout['line2'] = [0, 112, 296, 112]
        self._layout['friend_face'] = (0, 96)
        self._layout['friend_name'] = (40, 96)
        self._layout['shakes'] = (0, 114)
        self._layout['mode'] = (268, 114)
        self._layout['status'] = {
            'pos': (130, 25),
            'font': fonts.status_font(fonts.Medium),
            'max': 28
        }
        return self._layout

    def initialize(self):
        logging.info("initializing waveshare V4 2.9 inch display")
        from pwnagotchi.ui.hw.libs.waveshare.v2in9b_v4.epd2in9b_V4 import EPD
        self._display = EPD()
        self._display.init()
        self._display.Clear(0xFF)
        self._display.init()

    def render(self, canvas):
        buf = self._display.getbuffer(canvas)
        self._display.display(buf)

    def clear(self):
        self._display.Clear(0xFF)
