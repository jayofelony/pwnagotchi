from . import SSD1306

# Display resolution, change if the screen resolution is changed!
EPD_WIDTH = 128
EPD_HEIGHT = 64

# Available screen resolutions:
# disp = SSD1306.SSD1306_128_32(128, 32, address=0x3C)
# disp = SSD1306.SSD1306_96_16(96, 16, address=0x3C)
# If you change for different resolution, you have to modify the layout in pwnagotchi/ui/hw/i2coled.py

class OLED(object):

    def __init__(self, address=0x3C, width=EPD_WIDTH, height=EPD_HEIGHT):
        self.width = width
        self.height = height

        # choose subclass based on dimensions
        if height == 32:
            self.disp = SSD1306.SSD1306_128_32(width, height, address)
        elif height == 16:
            self.disp = SSD1306.SSD1306_96_16(width, height, address)
        else:
            self.disp = SSD1306.SSD1306_128_64(width, height, address)

    def Init(self):
        self.disp.begin()

    def Clear(self):
        self.disp.clear()

    def display(self, image):
        self.disp.getbuffer(image)
        self.disp.ShowImage()