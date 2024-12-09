import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class DummyDisplay(DisplayImpl):
    def __init__(self, config):
        super(DummyDisplay, self).__init__(config, 'DummyDisplay')

    def layout(self):
        width = 480 if 'width' not in self.config else self.config['width']
        height = 720 if 'height' not in self.config else self.config['height']
        fonts.setup(int(height/30), int(height/40), int(height/30), int(height/6), int(height/30), int(height/35))
        self._layout['width'] = width
        self._layout['height'] = height
        self._layout['face'] = (0, int(width/12))
        self._layout['name'] = (5, int(width/25))
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (int(width/8), 0)
        self._layout['uptime'] = (width-int(width/12), 0)
        self._layout['line1'] = [0, int(height/32), width, int(height/32)]
        self._layout['line2'] = [0, height-int(height/25)-1, width, height-int(height/25)-1]
        self._layout['friend_face'] = (0, int(height/10))
        self._layout['friend_name'] = (int(width/12), int(height/10))
        self._layout['shakes'] = (0, height-int(height/25))
        self._layout['mode'] = (width-int(width/8), height - int (height/25))
        lw, lh = fonts.Small.getbbox("W")
        self._layout['status'] = {
            'pos': (int(width/48), int(height/3)),
            'font': fonts.status_font(fonts.Small),
            'max': int(width / lw)
        }
        return self._layout

    def initialize(self):
        return

    def render(self, canvas):
        return

    def clear(self):
        return
