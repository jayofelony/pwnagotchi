import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl
from PIL import Image


class Waveshare2in13bV3(DisplayImpl):
    def __init__(self, config):
        super(Waveshare2in13bV3, self).__init__(config, 'waveshare2in13b_v3')

    def layout(self):
        fonts.setup(10, 8, 10, 25, 25, 9)
        self._layout['width'] = 212
        self._layout['height'] = 104
        self._layout['face'] = (0, 26)
        self._layout['name'] = (5, 15)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (28, 0)
        self._layout['uptime'] = (147, 0)
        self._layout['line1'] = [0, 12, 212, 12]
        self._layout['line2'] = [0, 92, 212, 92]
        self._layout['friend_face'] = (0, 76)
        self._layout['friend_name'] = (40, 78)
        self._layout['shakes'] = (0, 93)
        self._layout['mode'] = (187, 93)
        self._layout['status'] = {
            'pos': (91, 15),
            'font': fonts.status_font(fonts.Medium),
            'max': 20
        }
        return self._layout

    def initialize(self):
        logging.info("initializing waveshare 2.13inb v2in13_V3 display")
        from pwnagotchi.ui.hw.libs.waveshare.epaper.v2in13b_v3.epd2in13b_V3 import EPD
        self._display = EPD()
        self._display.init()
        self._display.Clear()

    def render(self, canvasBlack=None, canvasRed=None):
        # Match V4 behavior: if only one canvas is passed, show it on black channel
        buffer = self._display.getbuffer
        # Create blank image matching the display dimensions
        image = Image.new('1', (self._layout['height'], self._layout['width']), 255)
        imageBlack = image if canvasBlack is None else canvasBlack
        imageRed = image if canvasRed is None else canvasRed
        self._display.display(buffer(imageBlack), buffer(imageRed))

    def clear(self):
        self._display.Clear()
