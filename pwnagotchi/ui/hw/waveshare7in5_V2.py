import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class Waveshare7in5V2(DisplayImpl):
    def __init__(self, config):
        super(Waveshare7in5V2, self).__init__(config, 'waveshare7in5_v2')

    def layout(self):
        fonts.setup(10, 8, 10, 18, 25, 9)
        self._layout['width'] = 800
        self._layout['height'] = 480
        self._layout['face'] = (0, 43)
        self._layout['name'] = (0, 14)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (0, 71)
        self._layout['uptime'] = (0, 25)
        self._layout['line1'] = [0, 12, 800, 12]
        self._layout['line2'] = [0, 116, 800, 116]
        self._layout['friend_face'] = (12, 88)
        self._layout['friend_name'] = (1, 103)
        self._layout['shakes'] = (26, 117)
        self._layout['mode'] = (0, 117)
        self._layout['status'] = {
            'pos': (65, 26),
            'font': fonts.status_font(fonts.Small),
            'max': 12
        }
        return self._layout

    def initialize(self):
        if self.config['color'] == 'fast':
            logging.info("initializing waveshare 7.5 V2 inch lcd display")
            from pwnagotchi.ui.hw.libs.waveshare.epaper.v7in5_v2.epd7in5_V2_fast import EPD
            self._display = EPD()
            self._display.init()
            self._display.Clear()
        elif self.config['color'] == 'old':
            logging.info("initializing waveshare 7.5 V2 inch lcd display")
            from pwnagotchi.ui.hw.libs.waveshare.epaper.v7in5_v2.epd7in5_V2_old import EPD
            self._display = EPD()
            self._display.init()
            self._display.Clear()
        else:
            logging.info("initializing waveshare 7.5 V2 inch lcd display")
            from pwnagotchi.ui.hw.libs.waveshare.epaper.v7in5_v2.epd7in5_V2 import EPD
            self._display = EPD()
            self._display.init()
            self._display.Clear()

    def render(self, canvas):
        buf = self._display.getbuffer(canvas)
        self._display.display(buf)

    def clear(self):
        self._display.Clear()
