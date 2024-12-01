# board GPIO:
# A: GPIO5
# B: GPIO6
# X: GPIO16
# Y: GPIO20 / GPIO24 (refer to the pimoroni site or pinout.xyz)
# I2S pins for the DAC: GPIO 18 GPIO19 GPIO21
#
# HW datasheet: https://shop.pimoroni.com/products/pirate-audio-line-out?variant=31189750546515
# pinout xyz: https://pinout.xyz/pinout/pirate_audio_line_out

import logging

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl


class PirateAudio(DisplayImpl):
    def __init__(self, config):
        super(PirateAudio, self).__init__(config, 'pirateaudio')
        self._display = None

    def layout(self):
        fonts.setup(10, 9, 10, 35, 25, 9)
        self._layout['width'] = 240
        self._layout['height'] = 240
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
        logging.info("Initializing PirateAudio - display only")
        logging.info("Available pins for GPIO Buttons A/B/X/Y: 5, 6, 16, 20 or 24")
        logging.info("refer to the pimoroni site or pinout.xyz")
        logging.info("Backlight pin available on GPIO 13")        
        logging.info("I2S for the DAC available on pins: 18, 19 and 21")
        from pwnagotchi.ui.hw.libs.pimoroni.pirateaudio.ST7789 import ST7789
        self._display = ST7789(0,1,9,13)

    def render(self, canvas):
        self._display.display(canvas.rotate(90))

    def clear(self):
        self._display.clear()
