import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class GamePi20(DisplayImpl):
    def __init__(self, config):
        super(GamePi20, self).__init__(config, 'gamepi20')

    def layout(self):
        fonts.setup(12, 10, 12, 70, 25, 9)
        self._layout['width'] = 320
        self._layout['height'] = 240
        self._layout['face'] = (35, 50)
        self._layout['name'] = (5, 20)
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
            'pos': (80, 160),
            'font': fonts.status_font(fonts.Medium),
            'max': 20
        }

        return self._layout

    def initialize(self):
        logging.info("initializing gamepi20 display")
        from pwnagotchi.ui.hw.libs.pimoroni.displayhatmini.ST7789 import ST7789
        self._display = ST7789(0, 0, 25, 24, 27, 320, 240, 0, True, 60 * 1000 * 1000, 0, 0)

    def render(self, canvas):
        self._display.display(canvas)

    def clear(self):
        self._display.clear()
