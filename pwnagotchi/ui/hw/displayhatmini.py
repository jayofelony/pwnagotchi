import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class DisplayHatMini(DisplayImpl):
    def __init__(self, config):
        super(DisplayHatMini, self).__init__(config, 'displayhatmini')
        self._display = None

    def layout(self):
        fonts.setup(12, 10, 12, 55, 25, 9)
        self._layout['width'] = 320
        self._layout['height'] = 240
        self._layout['face'] = (14, 28)
        self._layout['name'] = (28, 20)
        self._layout['channel'] = (278, 96)
        self._layout['aps'] = (224, 96)
        self._layout['uptime'] = (134, 3)
        self._layout['friend_face'] = (0, 130)
        self._layout['friend_name'] = (40, 135)
        self._layout['shakes'] = (34, 193)
        self._layout['mode'] = (22, 3)
        self._layout['status'] = {
            'pos': (26, 124),
            'font': fonts.status_font(fonts.Medium),
            'max': 20
        }

        return self._layout

    def initialize(self):
        logging.info("initializing Display Hat Mini")
        from pwnagotchi.ui.hw.libs.pimoroni.displayhatmini.ST7789 import ST7789
        self._display = ST7789(0,1,9,13)

    def render(self, canvas):
        self._display.display(canvas)

    def clear(self):
        self._display.clear()