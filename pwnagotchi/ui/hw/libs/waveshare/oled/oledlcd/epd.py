from . import SSD1306

# Display resolution
EPD_WIDTH = 128
EPD_HEIGHT = 64

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