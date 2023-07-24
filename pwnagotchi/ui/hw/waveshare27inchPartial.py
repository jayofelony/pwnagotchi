import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl
from PIL import Image


class Waveshare27inchPartial(DisplayImpl):
    def __init__(self, config):
        super(Waveshare27inchPartial, self).__init__(config, 'waveshare27inchPartial')
        self._display = None
        self.counter = 0

    def layout(self):
        fonts.setup(10, 9, 10, 35, 25, 9)
        self._layout['width'] = 264
        self._layout['height'] = 176
        self._layout['face'] = (66, 27)
        self._layout['name'] = (5, 73)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (28, 0)
        self._layout['uptime'] = (199, 0)
        self._layout['line1'] = [0, 14, 264, 14]
        self._layout['line2'] = [0, 162, 264, 162]
        self._layout['friend_face'] = (0, 146)
        self._layout['friend_name'] = (40, 146)
        self._layout['shakes'] = (0, 163)
        self._layout['mode'] = (239, 163)
        self._layout['status'] = {
            'pos': (38, 93),
            'font': fonts.status_font(fonts.Medium),
            'max': 40
        }
        return self._layout



    def initialize(self):
        logging.info("initializing waveshare v1 2.7 inch display")
        from rpi_epd2in7.epd import EPD
        self._display = EPD(fast_refresh=True)
        self._display.init()


    def render(self, canvas):
        # have to rotate, because lib work with portrait mode only
        # also I have 180 degrees screen rotation inn config, not tested with other valuesjk:w
        rotated = canvas.rotate(90, expand=True)
        if self.counter == 0:
            self._display.smart_update(rotated)

        # print invert
        # print true image
        elif self.counter % 35 == 0:
            inverted_image = rotated.point(lambda x: 255-x)
            self._display.display_partial_frame(inverted_image, 0, 0, 264, 176, fast=True)
            self._display.display_partial_frame(rotated, 0, 0, 264, 176, fast=True)
        
        # partial update full screen
        elif self.counter % 7 == 0:
            # face + text under
            #self._display.display_partial_frame(rotated, 35, 35, 190, 115, fast=True)
            # full screen partial update
            self._display.display_partial_frame(rotated, 0, 0, 264, 176, fast=True)
        
        # partial update face 
        self._display.display_partial_frame(rotated, 110, 84, 92, 40, fast=True)

        if self.counter >= 100:
            self.counter = 0
        else:
            self.counter += 1


    def clear(self):
        pass

