import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class WaveshareV1(DisplayImpl):
    def __init__(self, config):
        super(WaveshareV1, self).__init__(config, 'waveshare_1')

    def layout(self):
        fonts.setup(10, 8, 10, 35, 25, 9)
        self._layout['width'] = 250
        self._layout['height'] = 122
        self._layout['face'] = (0, 40)
        self._layout['name'] = (5, 20)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (28, 0)
        self._layout['uptime'] = (185, 0)
        self._layout['line1'] = [0, 14, 250, 14]
        self._layout['line2'] = [0, 108, 250, 108]
        self._layout['friend_face'] = (0, 92)
        self._layout['friend_name'] = (40, 94)
        self._layout['shakes'] = (0, 109)
        self._layout['mode'] = (225, 109)
        self._layout['status'] = {
            'pos': (125, 20),
            'font': fonts.status_font(fonts.Medium),
            'max': 20
        }
        return self._layout

    def initialize(self):
        logging.info("initializing waveshare v2in13_V1 display in monochromatic mode")
        from pwnagotchi.ui.hw.libs.waveshare.epaper.v2in13_V1.epd2in13 import EPD
        self._display = EPD()
        self._display.init(self._display.lut_full_update)
        self._display.Clear(0xFF)
        self._display.init(self._display.lut_partial_update)

    def render(self, canvas):
        buf = self._display.getbuffer(canvas)
        self._display.display(buf)

    def clear(self):
        self._display.Clear(0xff)
