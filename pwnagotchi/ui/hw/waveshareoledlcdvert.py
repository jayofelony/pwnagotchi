# workinprogress based on the displayhatmini driver
# LCD support OK
# OLED support ongoing
# board GPIO:
# Key1: GPIO4 / pin7
# Key2: GPIO17 / pin11
# Key3: GPIO23 / pin16
# Key4: GPIO24 / pin18
# OLED SDA: GPIO2 / pin3 
# OLED SCL: GPIO3 / pin5
# OLED info: 
# driver: SSD1315 (I2C)
# resolution: 128x64
# I2C address: 0x3C 0x3D
# HW datasheet: https://www.waveshare.com/wiki/OLED/LCD_HAT_(A)

import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class Waveshareoledlcdvert(DisplayImpl):
    def __init__(self, config):
        super(Waveshareoledlcdvert, self).__init__(config, 'waveshareoledlcdvert')

    def layout(self):
        fonts.setup(10, 9, 10, 35, 25, 9)
        self._layout['width'] = 240
        self._layout['height'] = 320
        self._layout['face'] = (0, 40)
        self._layout['name'] = (5, 20)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (28, 0)
        self._layout['uptime'] = (175, 0)
        self._layout['line1'] = [0, 14, 240, 14]
        self._layout['line2'] = [0, 108, 240, 108]
        self._layout['friend_face'] = (0, 92)
        self._layout['friend_name'] = (40, 94)
        self._layout['shakes'] = (0, 109)
        self._layout['mode'] = (215, 109)
        self._layout['status'] = {
            'pos': (125, 20),
            'font': fonts.status_font(fonts.Medium),
            'max': 20
        }

        return self._layout

    def initialize(self):
        logging.info("initializing Waveshare OLED/LCD hat vertical mode")
        logging.info("Available pins for GPIO Buttons K1/K2/K3/K4: 4, 17, 23, 24")
        from pwnagotchi.ui.hw.libs.waveshare.oled.oledlcd.ST7789vert import ST7789
        self._display = ST7789(0,0,22,18)

    def render(self, canvas):
        self._display.display(canvas)

    def clear(self):
        self._display.clear()