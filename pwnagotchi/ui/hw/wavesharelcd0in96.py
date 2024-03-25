import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class Wavesharelcd0in96(DisplayImpl):
    def __init__(self, config):
        super(Wavesharelcd0in96, self).__init__(config, 'wavesharelcd0in96')

    def layout(self):
        fonts.setup(10, 8, 10, 18, 25, 9)
        self._layout['width'] = 160
        self._layout['height'] = 80
        self._layout['face'] = (0, 43)
        self._layout['name'] = (0, 14)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (0, 71)
        self._layout['uptime'] = (0, 25)
        self._layout['line1'] = [0, 12, 80, 12]
        self._layout['line2'] = [0, 116, 80, 116]
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
        logging.info("initializing waveshare 0.96 inch lcd display")
        from pwnagotchi.ui.hw.libs.waveshare.lcd.lcdhat0in96.LCD_0inch96 import LCD_0inch96
        self._display = LCD_0inch96()
        self._display.Init()
        self._display.clear()
        self._display.bl_DutyCycle(50)

    def render(self, canvas):
        self._display.ShowImage(canvas)

    def clear(self):
        self._display.clear()
