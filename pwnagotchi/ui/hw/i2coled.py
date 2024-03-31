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

class I2COled(DisplayImpl):
    def __init__(self, config):
        super(I2COled, self).__init__(config, 'i2coled')

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
        logging.info("initializing I2C Oled Display on address 0x3C")
        from pwnagotchi.ui.hw.libs.waveshare.oled.oledlcd.epd import EPD
        self._display = EPD()
        self._display.Init()
        self._display.Clear()

    def render(self, canvas):
        self._display.display(canvas)

    def clear(self):
        self._display.clear()