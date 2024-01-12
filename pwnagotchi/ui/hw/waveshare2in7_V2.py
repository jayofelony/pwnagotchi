import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class Waveshare27inchV2(DisplayImpl):
    def __init__(self, config):
        super(Waveshare27inchV2, self).__init__(config, 'waveshare2in7_v2')
        self._display = None

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
        logging.info("initializing waveshare V2 2.7 inch display")
        from pwnagotchi.ui.hw.libs.waveshare.v2in7_v2.epd2in7_V2 import EPD
        self._display = EPD()
        self._display.init()
        # this must have changed by waveshare
        # remove the 0xFF(Clear(0xFF)) other wise it errors. can't pass oxff and self
        self._display.Clear()

    def render(self, canvas):
        buf = self._display.getbuffer(canvas)
        self._display.display_Partial(buf,0,0,176,264)

    def clear(self):
        # This line also removes the 0xFF
        self._display.Clear()
