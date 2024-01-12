# *****************************************************************************
# * | File        :	  epd2in9b_V4.py
# * | Author      :   Waveshare team
# * | Function    :   Electronic paper driver
# * | Info        :
# *----------------
# * |	This version:   V1.0
# * | Date        :   2023-12-18
# # | Info        :   python demo
# -----------------------------------------------------------------------------
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documnetation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to  whom the Software is
# furished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS OR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#


import logging
from .. import epdconfig

# Display resolution
EPD_WIDTH = 128
EPD_HEIGHT = 296

logger = logging.getLogger(__name__)


class EPD:
    def __init__(self):
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin = epdconfig.DC_PIN
        self.busy_pin = epdconfig.BUSY_PIN
        self.cs_pin = epdconfig.CS_PIN
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT

    # Hardware reset
    def reset(self):
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(200)
        epdconfig.digital_write(self.reset_pin, 0)
        epdconfig.delay_ms(2)
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(200)

    def send_command(self, command):
        epdconfig.digital_write(self.dc_pin, 0)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte([command])
        epdconfig.digital_write(self.cs_pin, 1)

    def send_data(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte([data])
        epdconfig.digital_write(self.cs_pin, 1)

    # send a lot of data
    def send_data2(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte2(data)
        epdconfig.digital_write(self.cs_pin, 1)

    def ReadBusy(self):
        logger.debug("e-Paper busy")
        self.send_command(0X71)
        while (epdconfig.digital_read(self.busy_pin) == 1):  # 0: idle, 1: busy
            epdconfig.delay_ms(200)
        logger.debug("e-Paper busy release")

    def TurnOnDisplay(self):
        self.send_command(0x22)  # Display Update Control
        self.send_data(0xF7)
        self.send_command(0x20)  # Activate Display Update Sequence
        self.ReadBusy()

    def TurnOnDisplay_Base(self):
        self.send_command(0x22)  # Display Update Control
        self.send_data(0xF4)
        self.send_command(0x20)  # Activate Display Update Sequence
        self.ReadBusy()

    def TurnOnDisplay_Fast(self):
        self.send_command(0x22)  # Display Update Control
        self.send_data(0xC7)
        self.send_command(0x20)  # Activate Display Update Sequence
        self.ReadBusy()

    def TurnOnDisplay_Partial(self):
        self.send_command(0x22)  # Display Update Control
        self.send_data(0x1C)
        self.send_command(0x20)  # Activate Display Update Sequence
        self.ReadBusy()

    def init(self):
        if (epdconfig.module_init() != 0):
            return -1

        # EPD hardware init start
        self.reset()

        self.ReadBusy()
        self.send_command(0x12)  # SWRESET
        self.ReadBusy()

        self.send_command(0x01)  # Driver output control
        self.send_data((self.height - 1) % 256)
        self.send_data((self.height - 1) // 256)
        self.send_data(0x00)

        self.send_command(0x11)  # data entry mode
        self.send_data(0x03)

        self.send_command(0x44)  # set Ram-X address start/end position
        self.send_data(0x00)
        self.send_data(self.width // 8 - 1)

        self.send_command(0x45)  # set Ram-Y address start/end position
        self.send_data(0x00)
        self.send_data(0x00)
        self.send_data((self.height - 1) % 256)
        self.send_data((self.height - 1) // 256)

        self.send_command(0x3C)  # BorderWavefrom
        self.send_data(0x05)

        self.send_command(0x21)  # Display update control
        self.send_data(0x00)
        self.send_data(0x80)

        self.send_command(0x18)  # Read built-in temperature sensor
        self.send_data(0x80)

        self.send_command(0x4E)  # set RAM x address count to 0
        self.send_data(0x00)
        self.send_command(0x4F)  # set RAM y address count to 0X199
        self.send_data(0x00)
        self.send_data(0x00)
        self.ReadBusy()

        return 0

    def init_Fast(self):
        if (epdconfig.module_init() != 0):
            return -1

        # EPD hardware init start
        self.reset()

        self.ReadBusy()
        self.send_command(0x12)  # SWRESET
        self.ReadBusy()

        self.send_command(0x18)  # Read built-in temperature sensor
        self.send_data(0x80)

        self.send_command(0x22)  # Load temperature value
        self.send_data(0xB1)
        self.send_command(0x20)
        self.ReadBusy()

        self.send_command(0x1A)  # Write to temperature register
        self.send_data(0x5a)  # 90
        self.send_data(0x00)

        self.send_command(0x22)  # Load temperature value
        self.send_data(0x91)
        self.send_command(0x20)
        self.ReadBusy()

        self.send_command(0x01)  # Driver output control
        self.send_data((self.height - 1) % 256)
        self.send_data((self.height - 1) / 256)
        self.send_data(0x00)

        self.send_command(0x11)  # data entry mode
        self.send_data(0x03)

        self.send_command(0x44)  # set Ram-X address start/end position
        self.send_data(0x00)
        self.send_data(self.width // 8 - 1)

        self.send_command(0x45)  # set Ram-Y address start/end position
        self.send_data(0x00)
        self.send_data(0x00)
        self.send_data((self.height - 1) % 256)
        self.send_data((self.height - 1) // 256)

        self.send_command(0x4E)  # set RAM x address count to 0
        self.send_data(0x00)
        self.send_command(0x4F)  # set RAM y address count to 0X199
        self.send_data(0x00)
        self.send_data(0x00)
        self.ReadBusy()

        return 0

    def getbuffer(self, image):
        # logger.debug("bufsiz = ",int(self.width/8) * self.height)
        buf = [0xFF] * (int(self.width / 8) * self.height)
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()
        # logger.debug("imwidth = %d, imheight = %d",imwidth,imheight)
        if (imwidth == self.width and imheight == self.height):
            logger.debug("Vertical")
            for y in range(imheight):
                for x in range(imwidth):
                    # Set the bits for the column of pixels at the current position.
                    if pixels[x, y] == 0:
                        buf[int((x + y * self.width) / 8)] &= ~(0x80 >> (x % 8))
        elif (imwidth == self.height and imheight == self.width):
            logger.debug("Horizontal")
            for y in range(imheight):
                for x in range(imwidth):
                    newx = y
                    newy = self.height - x - 1
                    if pixels[x, y] == 0:
                        buf[int((newx + newy * self.width) / 8)] &= ~(0x80 >> (y % 8))
        return buf

    def display(self, blackimage, ryimage):  # ryimage: red or yellow image
        if (self.width % 8 == 0):
            Width = self.width // 8
        else:
            Width = self.width // 8 + 1
        Height = self.height
        if (blackimage != None):
            self.send_command(0x24)
            self.send_data2(blackimage)
        if (ryimage != None):
            for j in range(Height):
                for i in range(Width):
                    ryimage[i + j * Width] = ~ryimage[i + j * Width]
            self.send_command(0x26)
            self.send_data2(ryimage)

        self.TurnOnDisplay()

    def display_Fast(self, blackimage, ryimage):  # ryimage: red or yellow image
        if (self.width % 8 == 0):
            Width = self.width // 8
        else:
            Width = self.width // 8 + 1
        Height = self.height
        if (blackimage != None):
            self.send_command(0x24)
            self.send_data2(blackimage)
        if (ryimage != None):
            for j in range(Height):
                for i in range(Width):
                    ryimage[i + j * Width] = ~ryimage[i + j * Width]
            self.send_command(0x26)
            self.send_data2(ryimage)

        self.TurnOnDisplay_Fast()

    def Clear(self):
        self.send_command(0x24)
        self.send_data2([0xff] * int(self.width * self.height // 8))
        self.send_command(0x26)
        self.send_data2([0x00] * int(self.width * self.height // 8))

        self.TurnOnDisplay()

    def Clear_Fast(self):
        self.send_command(0x24)
        self.send_data2([0xff] * int(self.width * self.height // 8))
        self.send_command(0x26)
        self.send_data2([0x00] * int(self.width * self.height // 8))

        self.TurnOnDisplay_Fast()

    def display_Base(self, blackimage, ryimage):
        if (self.width % 8 == 0):
            Width = self.width // 8
        else:
            Width = self.width // 8 + 1
        Height = self.height
        if (blackimage != None):
            self.send_command(0x24)
            self.send_data2(blackimage)
        if (ryimage != None):
            for j in range(Height):
                for i in range(Width):
                    ryimage[i + j * Width] = ~ryimage[i + j * Width]
            self.send_command(0x26)
            self.send_data2(ryimage)

        self.TurnOnDisplay_Base()

        if (blackimage != None):
            for j in range(Height):
                for i in range(Width):
                    blackimage[i + j * Width] = ~blackimage[i + j * Width]
            self.send_command(0x26)
            self.send_data2(blackimage)
        else:
            self.send_command(0x26)
            self.send_data2(blackimage)

    def display_Base_color(self, color):
        if (self.width % 8 == 0):
            Width = self.width // 8
        else:
            Width = self.width // 8 + 1
        Height = self.height
        self.send_command(0x24)  # Write Black and White image to RAM
        for j in range(Height):
            for i in range(Width):
                self.send_data(color)

        self.send_command(0x26)  # Write Black and White image to RAM
        for j in range(Height):
            for i in range(Width):
                self.send_data(~color)

        self.TurnOnDisplay_Base()
        self.send_command(0x26)  # Write Black and White image to RAM
        for j in range(Height):
            for i in range(Width):
                self.send_data(color)

    def display_Partial(self, Image, Xstart, Ystart, Xend, Yend):
        if ((Xstart % 8 + Xend % 8 == 8 & Xstart % 8 > Xend % 8) | Xstart % 8 + Xend % 8 == 0 | (
                Xend - Xstart) % 8 == 0):
            Xstart = Xstart // 8
            Xend = Xend // 8
        else:
            Xstart = Xstart // 8
            if Xend % 8 == 0:
                Xend = Xend // 8
            else:
                Xend = Xend // 8 + 1

        if (self.width % 8 == 0):
            Width = self.width // 8
        else:
            Width = self.width // 8 + 1
        Height = self.height

        Xend -= 1
        Yend -= 1

        self.send_command(0x44)  # set RAM x address start/end, in page 35
        self.send_data(Xstart & 0xff)  # RAM x address start at 00h
        self.send_data(Xend & 0xff)  # RAM x address end at 0fh(15+1)*8->128
        self.send_command(0x45)  # set RAM y address start/end, in page 35
        self.send_data(Ystart & 0xff)  # RAM y address start at 0127h
        self.send_data((Ystart >> 8) & 0x01)  # RAM y address start at 0127h
        self.send_data(Yend & 0xff)  # RAM y address end at 00h
        self.send_data((Yend >> 8) & 0x01)

        self.send_command(0x4E)  # set RAM x address count to 0
        self.send_data(Xstart & 0xff)
        self.send_command(0x4F)  # set RAM y address count to 0X127
        self.send_data(Ystart & 0xff)
        self.send_data((Ystart >> 8) & 0x01)

        self.send_command(0x24)  # Write Black and White image to RAM
        for j in range(Height):
            for i in range(Width):
                if ((j > Ystart - 1) & (j < (Yend + 1)) & (i > Xstart - 1) & (i < (Xend + 1))):
                    self.send_data(Image[i + j * Width])
        self.TurnOnDisplay_Partial()

    def sleep(self):
        self.send_command(0x10)  # deep sleep
        self.send_data(0x01)

        epdconfig.delay_ms(2000)
        epdconfig.module_exit()
### END OF FILE ###
