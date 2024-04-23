import logging

import time
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl
from inky.auto import auto
display = auto()

class Inky(DisplayImpl):

    def __init__(self, config):
        super(Inky, self).__init__(config, 'inky')
        self._display = None
        self._lastRefresh = 0

    def layout(self):

        fonts.setup(10, 8, 10, 28, 25, 9)
        if display.eeprom is not None: #Detect v2 and later Inky displays with eeproms
            logging.info(print("Inky eeprom detected, read", display.eeprom.get_variant(), "from eeprom"))
            self._layout['width'] = display.width
            self._layout['height'] = display.height
            self._layout['face'] = (0, int(display.height/6))
            self._layout['name'] = (5, int(display.height/6))
            self._layout['channel'] = (0, 0)
            self._layout['aps'] = (int(display.width/8), 0)
            self._layout['uptime'] = (display.width-int(display.width/3), 0)
            self._layout['line1'] = [0, int(display.height/10), display.width, int(display.height/10)]
            self._layout['line2'] = [0, display.height-int(display.height/10)-1, display.width, display.height-int(display.height/10)-1]
            self._layout['friend_face'] = (0, int(display.height/1.2))
            self._layout['friend_name'] = (int(display.width/6), int(display.height/1.2))
            self._layout['shakes'] = (0, display.height-int(display.height/10))
            self._layout['mode'] = (display.width-int(display.width/9), display.height-int(display.height/10))
            self._layout['status'] = {
                'pos': ((display.width-int(display.width/2)), (display.height/3)),
                'font': fonts.status_font(fonts.Small),
                'max': 20
            }
            return self._layout
        else: #legacy v1 Inky pHat displays
            self._layout['width'] = 212
            self._layout['height'] = 104
            self._layout['face'] = (0, 37)
            self._layout['name'] = (5, 18)
            self._layout['channel'] = (0, 0)
            self._layout['aps'] = (30, 0)
            self._layout['uptime'] = (147, 0)
            self._layout['line2'] = [0, 92, 212, 92]
            self._layout['friend_face'] = (0, 76)
            self._layout['friend_name'] = (40, 78)
            self._layout['shakes'] = (0, 93)
            self._layout['mode'] = (187, 93)
            self._layout['status'] = {
                'pos': (102, 18),
                'font': fonts.status_font(fonts.Small),
                'max': 20
            }
            return self._layout

    def initialize(self):
        logging.info("Initializing inky display")
        logging.info("If your inky doesn't display anything \ntry disabling 'dtoverlay=spi0-0cs' in your boot config")

        if display.eeprom is not None:
            self._display = auto()
            self._display.set_border(display.BLACK)
        elif self.config['color'] == 'fastAndFurious':
            logging.info("Initializing Inky in 2-color FAST MODE")
            logging.info("THIS MAY BE POTENTIALLY DANGEROUS. NO WARRANTY IS PROVIDED")
            logging.info("USE THIS DISPLAY IN THIS MODE AT YOUR OWN RISK")

            from pwnagotchi.ui.hw.libs.inkyphat.inkyphatfast import InkyPHATFast
            self._display = InkyPHATFast('black')
            self._display.set_border(InkyPHATFast.BLACK)
        else:
            from inky.phat import InkyPHAT
            self._display = InkyPHAT(self.config['color'])
            self._display.set_border(InkyPHAT.BLACK)

    def render(self, canvas):
        if self.config['color'] == 'black' or self.config['color'] == 'fastAndFurious' or display.colour == 'red':
            display_colors = 2
        else:
            display_colors = 3

        img_buffer = canvas.convert('RGB').convert('P', palette=1, colors=display_colors)
        if self.config['color'] == 'red' or display.colour == 'red':
            img_buffer.putpalette([
                255, 255, 255,  # index 0 is white
                0, 0, 0,  # index 1 is black
                255, 0, 0  # index 2 is red
            ])
        elif self.config['color'] == 'yellow' or display.colour == 'yellow':
            img_buffer.putpalette([
                255, 255, 255,  # index 0 is white
                0, 0, 0,  # index 1 is black
                255, 255, 0  # index 2 is yellow
            ])
        else:
            img_buffer.putpalette([
                255, 255, 255,  # index 0 is white
                0, 0, 0  # index 1 is black
            ])

        self._display.set_image(img_buffer)
        try:
            currentTime = time.time()

            if((self._lastRefresh == 0) or ((self._lastRefresh+10) <= currentTime)):
                self._display.show()
                self._lastRefresh = time.time()
        except:
            logging.exception("error while rendering on inky")

    def clear(self):
        self._display.Clear()
