# Created for the Pwnagotchi project by RasTacsko
# HW libraries are based on the pimoroni gfx-hat repo:
# https://github.com/pimoroni/gfx-hat/tree/master
# 
# Contrast and Backlight color are imported from config.toml
# 
# ui.display.contrast = 40
# ui.display.blcolor = "olive"
# 
# Contrast should be between 30-50, default is 40
# Backlight are predefined in the lcd.py
# Available backlight colors:
# white, grey, maroon, red, purple, fuchsia, green, 
# lime, olive, yellow, navy, blue, teal, aqua

import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl

class GfxHat(DisplayImpl):
    def __init__(self, config):
        self._config = config['ui']['display']
        super(GfxHat, self).__init__(config, 'gfxhat')

    def layout(self):
        fonts.setup(8, 8, 8, 10, 10, 8)
        self._layout['width'] = 128
        self._layout['height'] = 64
        self._layout['face'] = (0, 30)
        self._layout['name'] = (0, 10)
        self._layout['channel'] = (72, 10)
        self._layout['aps'] = (0, 0)
        self._layout['uptime'] = (87, 0)
        self._layout['line1'] = [0, 9, 128, 9]
        self._layout['line2'] = [0, 54, 128, 54]
        self._layout['friend_face'] = (0, 41)
        self._layout['friend_name'] = (40, 43)
        self._layout['shakes'] = (0, 55)
        self._layout['mode'] = (107, 10)
        self._layout['status'] = {
            'pos': (37, 19),
            'font': fonts.status_font(fonts.Small),
            'max': 18
        }
        return self._layout

    def initialize(self):
        contrast = self._config['contrast'] if 'contrast' in self._config else 40
        blcolor = self._config['blcolor'] if 'blcolor' in self._config else 'OLIVE'
        logging.info("Initializing Pimoroni GfxHat - Contrast: %d Backlight color: %s" % (contrast, blcolor))
        logging.info("Available config options: ui.display.contrast and ui.display.color")
        logging.info("Contrast should be between 30-50, default is 40")
        logging.info("Backlight are predefined in the lcd.py")
        logging.info("Available backlight colors:")
        logging.info("white, grey, maroon, red, purple, fuchsia, green,")
        logging.info("lime, olive, yellow, navy, blue, teal, aqua")
        logging.info("Touch control work in progress (6 touch buttons with short and long press and LED feedback)")
        from pwnagotchi.ui.hw.libs.pimoroni.gfxhat.lcd import LCD
        self._display = LCD(contrast=contrast)
        self._display.Init(color_name=blcolor)
        self._display.Clear()


    def render(self, canvas):
        self._display.Display(canvas)

    def clear(self):
        self._display.Clear()
