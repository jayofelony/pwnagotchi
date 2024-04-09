from . import SSD1306

# Display resolution, change if the screen resolution is changed!
EPD_WIDTH = 128
EPD_HEIGHT = 64

# Available screen resolutions:
# disp = SSD1306.SSD1306_128_32(128, 32, address=0x3C)
# disp = SSD1306.SSD1306_96_16(96, 16, address=0x3C)
# If you change for different resolution, you have to modify the layout in pwnagotchi/ui/hw/i2coled.py
disp = SSD1306.SSD1306_128_64(128, 64, address=0x3C)

class EPD(object):

    def __init__(self):
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT

    def Init(self):
        disp.begin()

    def Clear(self):
        disp.clear()

    def display(self, image):
        disp.getbuffer(image)
        disp.ShowImage()