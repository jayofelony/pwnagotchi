# board GPIO:
# Key1: 
# Key2: 
# Key3: 
# Key4: 
#
# Touch chipset: 
# HW info: https://argon40.com/products/pod-display-2-8inch
# HW datasheet:

import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class ArgonPod(DisplayImpl):
    def __init__(self, config):
        super(ArgonPod, self).__init__(config, 'argonpod')
        self._display = None

    def layout(self):
        fonts.setup(12, 10, 12, 70, 25, 9)
        self._layout['width'] = 320
        self._layout['height'] = 240
        self._layout['face'] = (0, 36)
        self._layout['name'] = (150, 36)
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
            'pos': (150, 48),
            'font': fonts.status_font(fonts.Medium),
            'max': 20
        }

        return self._layout

    def initialize(self):
        logging.info("Initializing Argon Pod display")
        from pwnagotchi.ui.hw.libs.argon.argonpod.ILI9341 import ILI9341
        self._display = ILI9341(0, 0, 22, 18)

    def render(self, canvas):
        self._display.display(canvas)

    def clear(self):
        self._display.clear()
