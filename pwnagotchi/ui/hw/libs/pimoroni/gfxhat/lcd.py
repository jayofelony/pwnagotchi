from . import st7567
from . import backlight
CONTRAST = 40

# Define RGB colors
WHITE = (255, 255, 255)
GREY = (255, 255, 255)
MAROON = (128, 0, 0)
RED = (255, 0, 0)
PURPLE = (128, 0, 128)
FUCHSIA = (255, 0, 255)
GREEN = (0, 128, 0)
LIME = (0, 255, 0)
OLIVE = (128, 128, 0)
YELLOW = (255, 255, 0)
NAVY = (0, 0, 128)
BLUE = (0, 0, 255)
TEAL = (0, 128, 128)
AQUA = (0, 255, 255)

# Map color names to RGB values
color_map = {
    'WHITE': WHITE,
    'GREY' : GREY,
    'MAROON': MAROON,
    'RED': RED,
    'PURPLE': PURPLE,
    'FUCHSIA': FUCHSIA,
    'GREEN' : GREEN,
    'LIME' : LIME,
    'OLIVE' : OLIVE,
    'YELLOW' : YELLOW,
    'NAVY' : NAVY,
    'BLUE' : BLUE,
    'TEAL' : TEAL,
    'AQUA' : AQUA
}

class LCD(object):

    def __init__(self, contrast=CONTRAST, blcolor=('OLIVE')):
        self.disp = st7567.ST7567()
        self.disp.contrast(contrast)

    def Init(self, color_name):
        self.disp.setup()
        blcolor = color_map.get(color_name.upper(), OLIVE)  # Default to olive if color not found
        backlight.set_all(*blcolor)
        backlight.show()

    def Clear(self):
        self.disp.clear()

    def Display(self, image):
        self.disp.show(image)