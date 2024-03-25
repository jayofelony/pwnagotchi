import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class Waveshare154V2(DisplayImpl):
    def __init__(self, config):
        super(Waveshare154V2, self).__init__(config, 'waveshare1in54_v2')

    def layout(self):
        fonts.setup(10, 9, 10, 35, 25, 9)
        self._layout['width'] = 200
        self._layout['height'] = 200
        self._layout['face'] = (0, 40)
        self._layout['name'] = (5, 20)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (28, 0)
        self._layout['uptime'] = (135, 0)
        self._layout['line1'] = [0, 14, 200, 14]
        self._layout['line2'] = [0, 186, 200, 186]
        self._layout['friend_face'] = (0, 92)
        self._layout['friend_name'] = (40, 94)
        self._layout['shakes'] = (0, 187)
        self._layout['mode'] = (170, 187)
        self._layout['status'] = {
            'pos': (5, 90),
            'font': fonts.status_font(fonts.Medium),
            'max': 20
        }
        return self._layout

    def initialize(self):
        logging.info("initializing waveshare1in54_v2 display")
        from pwnagotchi.ui.hw.libs.waveshare.epaper.v1in54_v2.epd1in54_V2 import EPD
        try:
            # Double initialization is a workaround for the display not working after a reboot, or mirrored/flipped screen
            self._display = EPD()
            self._display.init(0)
            self.clear()
            self._display.init(1)
            self.clear()
        except Exception as e:
            logging.error(f"failed to initialize waveshare1in54_v2 display: {e}")

    def render(self, canvas):
        try:
            buf = self._display.getbuffer(canvas)
            self._display.displayPart(buf)
        except Exception as e:
            logging.error(f"failed to render to waveshare1in54_v2 display: {e}")

    def clear(self):
        try:
            self._display.Clear(0xFF)
        except Exception as e:
            logging.error(f"failed to clear waveshare1in54_v2 display: {e}")
