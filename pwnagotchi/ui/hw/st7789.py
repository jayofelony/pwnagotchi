import logging
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl

class st7789_display(DisplayImpl):
    def __init__(self, config, name='st7789'):
        super(st7789_display, self).__init__(config, 'st7789')
        self._display = None
        logging.warn("Loaded st7789 display")
        self.defaults = {'spi_port':0,
                         'cs': 0,
                         'dc': 25,
                         'bl': 22,
                         'rst': None,
                         'rotation':180,
                         'width':320,
                         'height':240,
                         'invert': True,
                         'spi_hz':60*1000*1000,
                         'offset_left':0,
                         'offset_top':0,
                         'backlight_pwm_steps':0}

    def layout(self):
        fonts.setup(12, 10, 12, 70, 25, 9)
        w = self.config.get('width', 320)
        h = self.config.get('height', 240)
        self._layout['width'] = w
        self._layout['height'] = h
        self._layout['face'] = (35, 50)
        self._layout['name'] = (5, 20)
        self._layout['channel'] = (0, 0)
        self._layout['aps'] = (40, 0)
        self._layout['uptime'] = (w-80, 0)
        self._layout['line1'] = [0, 14, w, 14]
        self._layout['line2'] = [0, h-20, w, h-20]
        self._layout['friend_face'] = (0, 130)
        self._layout['friend_name'] = (40, 135)
        self._layout['shakes'] = (0, h-20)
        self._layout['mode'] = (w-40, h-20)
        self._layout['status'] = {
            'pos': (80, 160),
            'font': fonts.status_font(fonts.Medium),
            'max': 20
        }
        return self._layout

    def initialize(self):
      try:
        from pwnagotchi.ui.hw.libs.ST7789 import ST7789
        cfg = self.config.get("st7789", {})
        logging.warn("Initializing ST7789 based display: %s %s" % (type(self).__name__, cfg))

        # pull everything from config with reasonable defaults (adafruit minipitft)
        spi_port = cfg.get("spi_port", self.defaults['spi_port'])
        cs = cfg.get("cs", self.defaults['cs'])
        dc = cfg.get("dc", self.defaults['dc'])
        bl = cfg.get("backlight", self.defaults['bl'])
        rst = cfg.get("rst", self.defaults['rst'])
        w = self.config.get("width", self.defaults['width'])
        h = self.config.get("height", self.defaults['height'])
        rotation = cfg.get("rotation", self.defaults['rotation'])
        invert = cfg.get("invert", self.defaults['invert'])
        spi_hz = cfg.get("spi_hz", self.defaults['spi_hz'])
        of_l = cfg.get("offset_left", self.defaults['offset_left'])
        of_t = cfg.get("offset_top", self.defaults['offset_top'])
        bl_pwm = cfg.get("backlight_pwm_steps", self.defaults['backlight_pwm_steps'])
        
        logging.warn("Setting up with %s, %s, %s, %s" % ((spi_port, cs, dc, bl), w, h, spi_hz))
        self._display = ST7789(spi_port, cs, dc, bl, rst=rst,
                               width=w, height=h, rotation=rotation, invert=invert,
                               spi_speed_hz=spi_hz,
                               offset_left=of_l, offset_top=of_t,
                               backlight_pwm=bl_pwm)
      except Exception as e:
          logging.exception(e)

    def render(self, canvas):
        self._display.display(canvas)

    def clear(self):
        self._display.clear()

    def set_backlight(self, value):
        if self._display:
            self._display.set_backlight(value)

    def get_backlight(self):
        if self._display:
            return self._display.get_backlight(value)
