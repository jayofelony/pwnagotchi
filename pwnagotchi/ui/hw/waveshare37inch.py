import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class Waveshare37inch(DisplayImpl):
    def __init__(self, config):
        super(Waveshare37inch, self).__init__(config, 'waveshare37inch')
        self._display = None

    def layout(self):
        fonts.setup(20, 19, 20, 45, 35, 19)
        self._layout['width'] = 480
        self._layout['height'] = 280
        self._layout['face'] = (0, 75)
        self._layout['name'] = (5, 35)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (65, 0)
        self._layout['uptime'] = (355, 0)
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
        logging.info("initializing waveshare v1 3.7 inch display")
        from pwnagotchi.ui.hw.libs.waveshare.v37inch.epd3in7 import EPD
        self._display = EPD()
        self._display.init(0)
        self._display.Clear(0xFF, 0)
        self._display.init(1)  # 1Gray mode

    def render(self, canvas):
        buf = self._display.getbuffer(canvas)
        self._display.display_1Gray(buf)

    def clear(self):
        self._display.Clear(0xFF, 1)