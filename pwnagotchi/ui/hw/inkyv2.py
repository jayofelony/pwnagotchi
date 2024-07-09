import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class InkyV2(DisplayImpl):
    def __init__(self, config):
        super(InkyV2, self).__init__(config, 'inkyv2')

    def layout(self):
        fonts.setup(10, 8, 10, 28, 25, 9)
        self._layout['width'] = 212
        self._layout['height'] = 104
        self._layout['face'] = (0, 37)
        self._layout['name'] = (5, 18)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (30, 0)
        self._layout['uptime'] = (147, 0)
        self._layout['line1'] = [0, 12, 212, 12]
        self._layout['line2'] = [0, 92, 212, 92]
        self._layout['friend_face'] = (0, 76)
        self._layout['friend_name'] = (40, 78)
        self._layout['shakes'] = (0, 93)
        self._layout['mode'] = (187, 93)
        self._layout['status'] = {
            'pos': (102, 18),
            'font': fonts.status_font(fonts.Small),
            'max': 20
        }
        return self._layout

    def initialize(self):
        logging.info("initializing inky v2 display")

        from pwnagotchi.ui.hw.libs.pimoroni.inkyphatv2.inkyv2 import InkyPHAT
        self._display = InkyPHAT()
        self._display.set_border(InkyPHAT.BLACK)

    def render(self, canvas):
        display_colors = 2

        img_buffer = canvas.convert('RGB').convert('P', palette=1, colors=display_colors)
        img_buffer.putpalette([
            255, 255, 255,  # index 0 is white
            0, 0, 0  # index 1 is black
        ])

        self._display.set_image(img_buffer)
        try:
            self._display.show()
        except:
            logging.exception("error while rendering on inky v2")

    def clear(self):
        self._display.Clear()
