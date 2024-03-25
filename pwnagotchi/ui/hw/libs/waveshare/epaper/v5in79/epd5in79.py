# *****************************************************************************
# * | File        :	  epd5in79.py
# * | Author      :   Waveshare team
# * | Function    :   Electronic paper driver
# * | Info        :
# *----------------
# * | This version:   V1.0
# * | Date        :   2024-03-05
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
from pwnagotchi.ui.hw.libs.waveshare.epaper import epdconfig

# Display resolution
EPD_WIDTH = 792
EPD_HEIGHT = 272

GRAY1 = 0xff  # white
GRAY2 = 0xC0
GRAY3 = 0x80  # gray
GRAY4 = 0x00  # Blackest

logger = logging.getLogger(__name__)


class EPD:
    def __init__(self):
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin = epdconfig.DC_PIN
        self.busy_pin = epdconfig.BUSY_PIN
        self.cs_pin = epdconfig.CS_PIN
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT
        self.GRAY1 = GRAY1  # white
        self.GRAY2 = GRAY2
        self.GRAY3 = GRAY3  # gray
        self.GRAY4 = GRAY4  # Blackest

        self.LUT_DATA_4Gray = [
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

            0x01, 0x4A, 0x00, 0x00, 0x00, 0x01, 0x00,
            0x01, 0x82, 0x42, 0x00, 0x00, 0x10, 0x00,
            0x01, 0x8A, 0x00, 0x00, 0x00, 0x01, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

            0x01, 0x41, 0x00, 0x00, 0x00, 0x01, 0x00,
            0x01, 0x82, 0x42, 0x00, 0x00, 0x10, 0x00,
            0x01, 0x81, 0x00, 0x00, 0x00, 0x01, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

            0x01, 0x81, 0x00, 0x00, 0x00, 0x01, 0x00,
            0x01, 0x82, 0x42, 0x00, 0x00, 0x10, 0x00,
            0x01, 0x41, 0x00, 0x00, 0x00, 0x01, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

            0x01, 0x8A, 0x00, 0x00, 0x00, 0x01, 0x00,
            0x01, 0x82, 0x42, 0x00, 0x00, 0x10, 0x00,
            0x01, 0x4A, 0x00, 0x00, 0x00, 0x01, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

            0x02, 0x00, 0x00,
            0x22, 0x17, 0x41, 0xA8, 0x32, 0x40, ]

    # Hardware reset
    def reset(self):
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(200)
        epdconfig.digital_write(self.reset_pin, 0)
        epdconfig.delay_ms(1)
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
        while (epdconfig.digital_read(self.busy_pin) == 1):  # 0: idle, 1: busy
            epdconfig.delay_ms(200)
        logger.debug("e-Paper busy release")

    def TurnOnDisplay(self):
        self.send_command(0x22)
        self.send_data(0xF7)
        self.send_command(0x20)  # DISPLAY REFRESH
        epdconfig.delay_ms(100)  # The delay here is necessary, 200uS at least!!!
        self.ReadBusy()  # waiting for the electronic paper IC to release the idle signal

    def TurnOnDisplay_Fast(self):
        self.send_command(0x22)
        self.send_data(0xC7)
        self.send_command(0x20)  # DISPLAY REFRESH
        epdconfig.delay_ms(100)  # The delay here is necessary, 200uS at least!!!
        self.ReadBusy()  # waiting for the electronic paper IC to release the idle signal

    def TurnOnDisplay_Partial(self):
        self.send_command(0x22)
        self.send_data(0xFF)
        self.send_command(0x20)  # DISPLAY REFRESH
        epdconfig.delay_ms(100)  # The delay here is necessary, 200uS at least!!!
        self.ReadBusy()  # waiting for the electronic paper IC to release the idle signal

    def TurnOnDisplay_4GRAY(self):
        self.send_command(0x22)
        self.send_data(0xCF)
        self.send_command(0x20)  # DISPLAY REFRESH
        epdconfig.delay_ms(100)  # The delay here is necessary, 200uS at least!!!
        self.ReadBusy()  # waiting for the electronic paper IC to release the idle signal

    def EPD_5in79_Lut(self):
        self.send_command(0x32)
        self.send_data2(self.LUT_DATA_4Gray[:227])
        self.send_command(0x3f)
        self.send_data(self.LUT_DATA_4Gray[227])

        self.send_command(0x03)
        self.send_data(self.LUT_DATA_4Gray[228])

        self.send_command(0x04)
        self.send_data(self.LUT_DATA_4Gray[229])
        self.send_data(self.LUT_DATA_4Gray[230])
        self.send_data(self.LUT_DATA_4Gray[231])

        self.send_command(0x2C)
        self.send_data(self.LUT_DATA_4Gray[232])

    def init(self):
        if (epdconfig.module_init() != 0):
            return -1

        self.reset()
        self.ReadBusy()  # waiting for the electronic paper IC to release the idle signal
        self.send_command(0x12)  # POWER ON
        self.ReadBusy()  # waiting for the electronic paper IC to release the idle signal

        self.send_command(0x11)
        self.send_data(0x01)

        self.send_command(0x44)  # Set Ram X- address Start / End position
        self.send_data(0x00)  # XStart, POR = 00h
        self.send_data(0x31)  # 400/8-1
        self.send_command(0x45)  # Set Ram Y- address  Start / End position
        self.send_data(0x0f)
        self.send_data(0x01)  # 300-1
        self.send_data(0x00)  # YEnd L
        self.send_data(0x00)  # YEnd H

        self.send_command(0x4e)
        self.send_data(0x00)
        self.send_command(0x4f)
        self.send_data(0x0f)
        self.send_data(0x01)

        self.ReadBusy()

        self.send_command(0x91)
        self.send_data(0x00)

        self.send_command(0xC4)  # Set Ram X- address Start / End position
        self.send_data(0x31)  # XStart, POR = 00h
        self.send_data(0x00)  # 400/8-1
        self.send_command(0xC5)  # Set Ram Y- address  Start / End position
        self.send_data(0x0f)
        self.send_data(0x01)  # 300-1
        self.send_data(0x00)  # YEnd L
        self.send_data(0x00)  # YEnd H

        self.send_command(0xCE)
        self.send_data(0x31)
        self.send_command(0xCF)
        self.send_data(0x0f)
        self.send_data(0x01)

        self.ReadBusy()

        return 0

    def init_Fast(self):
        if (epdconfig.module_init() != 0):
            return -1

        self.reset()
        self.ReadBusy()
        self.send_command(0x12)
        self.ReadBusy()

        self.send_command(0x18)
        self.send_data(0x80)

        self.send_command(0x22)
        self.send_data(0xB1)
        self.send_command(0x20)
        self.ReadBusy()

        self.send_command(0x1A)
        self.send_data(0x64)
        self.send_data(0x00)

        self.send_command(0x22)
        self.send_data(0x91)
        self.send_command(0x20)
        self.ReadBusy()

        self.send_command(0x11)
        self.send_data(0x01)

        self.send_command(0x44)
        self.send_data(0x00)
        self.send_data(0x31)
        self.send_command(0x45)
        self.send_data(0x0f)
        self.send_data(0x01)
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(0x4e)
        self.send_data(0x00)
        self.send_command(0x4f)
        self.send_data(0x0f)
        self.send_data(0x01)

        self.ReadBusy()

        self.send_command(0x91)
        self.send_data(0x00)

        self.send_command(0xC4)
        self.send_data(0x31)
        self.send_data(0x00)
        self.send_command(0xC5)
        self.send_data(0x0f)
        self.send_data(0x01)
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(0xCe)
        self.send_data(0x31)
        self.send_command(0xCf)
        self.send_data(0x0f)
        self.send_data(0x01)

        self.ReadBusy()

        return 0

    def init_Partial(self):
        if (epdconfig.module_init() != 0):
            return -1

        self.reset()
        self.ReadBusy()
        self.send_command(0x12)
        self.ReadBusy()

        self.send_command(0x3C)
        self.send_data(0x80)

        return 0

    def init_4Gray(self):
        if (epdconfig.module_init() != 0):
            return -1

        self.reset()
        self.ReadBusy()
        self.send_command(0x12)
        self.ReadBusy()

        self.send_command(0x0C)
        self.send_data(0x8B)
        self.send_data(0x9C)
        self.send_data(0xA6)
        self.send_data(0x0F)

        self.send_command(0x3C)
        self.send_data(0x81)

        self.ReadBusy()

        self.send_command(0x11)
        self.send_data(0x01)

        self.send_command(0x44)
        self.send_data(0x00)
        self.send_data(0x31)
        self.send_command(0x45)
        self.send_data(0x0f)
        self.send_data(0x01)
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(0x4e)
        self.send_data(0x00)
        self.send_command(0x4f)
        self.send_data(0x0f)
        self.send_data(0x01)

        self.ReadBusy()

        self.send_command(0x91)
        self.send_data(0x00)

        self.send_command(0xC4)
        self.send_data(0x31)
        self.send_data(0x00)
        self.send_command(0xC5)
        self.send_data(0x0f)
        self.send_data(0x01)
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(0xCe)
        self.send_data(0x31)
        self.send_command(0xCf)
        self.send_data(0x0f)
        self.send_data(0x01)

        self.EPD_5in79_Lut()
        return 0

    def getbuffer(self, image):
        # logger.debug("bufsiz = ",int(self.width/8) * self.height)
        buf = [0xFF] * (int(self.width / 8) * self.height)
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()
        # logger.debug("imwidth = %d, imheight = %d",imwidth,imheight)
        if imwidth == self.width and imheight == self.height:
            logger.debug("Horizontal")
            for y in range(imheight):
                for x in range(imwidth):
                    # Set the bits for the column of pixels at the current position.
                    if pixels[x, y] == 0:
                        buf[int((x + y * self.width) / 8)] &= ~(0x80 >> (x % 8))
        elif imwidth == self.height and imheight == self.width:
            logger.debug("Vertical")
            for y in range(imheight):
                for x in range(imwidth):
                    newx = y
                    newy = self.height - x - 1
                    if pixels[x, y] == 0:
                        buf[int((newx + newy * self.width) / 8)] &= ~(0x80 >> (y % 8))
        return buf

    def getbuffer_4Gray(self, image):
        # logger.debug("bufsiz = ",int(self.width/8) * self.height)
        buf = [0xFF] * (int(self.width / 4) * self.height)
        image_monocolor = image.convert('L')
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()
        i = 0
        # logger.debug("imwidth = %d, imheight = %d",imwidth,imheight)
        if (imwidth == self.width and imheight == self.height):
            logger.debug("Vertical")
            for y in range(imheight):
                for x in range(imwidth):
                    # Set the bits for the column of pixels at the current position.
                    if (pixels[x, y] == 0xC0):
                        pixels[x, y] = 0x80
                    elif (pixels[x, y] == 0x80):
                        pixels[x, y] = 0x40
                    i = i + 1
                    if (i % 4 == 0):
                        buf[int((x + (y * self.width)) / 4)] = (
                                    (pixels[x - 3, y] & 0xc0) | (pixels[x - 2, y] & 0xc0) >> 2 | (
                                        pixels[x - 1, y] & 0xc0) >> 4 | (pixels[x, y] & 0xc0) >> 6)

        elif (imwidth == self.height and imheight == self.width):
            logger.debug("Horizontal")
            for x in range(imwidth):
                for y in range(imheight):
                    newx = y
                    newy = self.height - x - 1
                    if (pixels[x, y] == 0xC0):
                        pixels[x, y] = 0x80
                    elif (pixels[x, y] == 0x80):
                        pixels[x, y] = 0x40
                    i = i + 1
                    if (i % 4 == 0):
                        buf[int((newx + (newy * self.width)) / 4)] = (
                                    (pixels[x, y - 3] & 0xc0) | (pixels[x, y - 2] & 0xc0) >> 2 | (
                                        pixels[x, y - 1] & 0xc0) >> 4 | (pixels[x, y] & 0xc0) >> 6)
        return buf

    def display(self, imageblack):
        Width = int(self.width / 16) + 1
        Width1 = int(self.width / 8)

        self.send_command(0x24)
        for i in range(self.height):
            self.send_data2(imageblack[i * Width1: i * Width1 + Width])
        self.send_command(0X26)
        self.send_data2([0x00] * 13600)

        self.send_command(0xA4)
        for i in range(self.height):
            self.send_data2(imageblack[i * Width1 + Width - 1: i * Width1 + Width * 2 - 1])
        self.send_command(0xA6)
        self.send_data2([0x00] * 13600)

        self.TurnOnDisplay()

    def display_Base(self, imageblack):
        Width = int(self.width / 16) + 1
        Width1 = int(self.width / 8)

        self.send_command(0x24)
        for i in range(self.height):
            self.send_data2(imageblack[i * Width1: i * Width1 + Width])
        self.send_command(0X26)
        self.send_data2([0x00] * 13600)

        self.send_command(0xA4)
        for i in range(self.height):
            self.send_data2(imageblack[i * Width1 + Width - 1: i * Width1 + Width * 2 - 1])
        self.send_command(0xA6)
        self.send_data2([0x00] * 13600)

        self.TurnOnDisplay()

        self.send_command(0x26)
        for i in range(self.height):
            self.send_data2(imageblack[i * Width1: i * Width1 + Width])

        self.send_command(0xA6)
        for i in range(self.height):
            self.send_data2(imageblack[i * Width1 + Width - 1: i * Width1 + Width * 2 - 1])

    def display_Base_color(self, color):
        Width = int(self.width / 16) + 1
        Width1 = int(self.width / 8)

        self.send_command(0x24)
        self.send_data2([color] * 13600)
        self.send_command(0X26)
        self.send_data2([0x00] * 13600)

        self.send_command(0xA4)
        self.send_data2([color] * 13600)
        self.send_command(0xA6)
        self.send_data2([0x00] * 13600)

        self.TurnOnDisplay()

        self.send_command(0x26)
        self.send_data2([color] * 13600)

        self.send_command(0xA6)
        self.send_data2([color] * 13600)

    def display_Fast(self, imageblack):
        Width = int(self.width / 16) + 1
        Width1 = int(self.width / 8)

        self.send_command(0x24)
        for i in range(self.height):
            self.send_data2(imageblack[i * Width1: i * Width1 + Width])
        self.send_command(0X26)
        self.send_data2([0x00] * 13600)

        self.send_command(0xA4)
        for i in range(self.height):
            self.send_data2(imageblack[i * Width1 + Width - 1: i * Width1 + Width * 2 - 1])
        self.send_command(0xA6)
        self.send_data2([0x00] * 13600)

        self.TurnOnDisplay_Fast()

    def display_Partial(self, Image):
        Width = int(self.width / 16) + 1
        Width1 = int(self.width / 8)
        Height = self.height
        self.send_command(0x44)
        self.send_data(0x00)
        self.send_data(0x31)
        self.send_command(0x45)
        self.send_data(0x0f)
        self.send_data(0x01)  # 300-1
        self.send_data(0x00)  # YEnd L
        self.send_data(0x00)  # YEnd H

        self.send_command(0x4e)
        self.send_data(0x00)
        self.send_command(0x4f)
        self.send_data(0x0f)
        self.send_data(0x01)

        self.send_command(0x24)
        for i in range(Height):
            self.send_data2(Image[i * Width1: i * Width1 + Width])

        self.send_command(0xC4)  # Set Ram X- address Start / End position
        self.send_data(0x31)  # XStart, POR = 00h
        self.send_data(0x00)  # 400/8-1
        self.send_command(0xC5)  # Set Ram Y- address  Start / End position
        self.send_data(0x0f)
        self.send_data(0x01)  # 300-1
        self.send_data(0x00)  # YEnd L
        self.send_data(0x00)  # YEnd H

        self.send_command(0xCe)
        self.send_data(0x31)
        self.send_command(0xCf)
        self.send_data(0x0f)
        self.send_data(0x01)

        self.send_command(0xA4)
        for i in range(Height):
            self.send_data2(Image[i * Width1 + Width - 1: i * Width1 + Width * 2 - 1])

        self.TurnOnDisplay_Partial()

    def display_4Gray(self, image):
        Width = int(self.width / 16) + 1
        Width1 = int(self.width / 8)

        self.send_command(0x24)
        for j in range(self.height):
            for i in range(Width):
                temp3 = 0
                for o in range(0, 2):
                    temp1 = image[(j * Width1 + i) * 2 + o]
                    for k in range(0, 4):
                        temp2 = temp1 & 0xC0
                        if (temp2 == 0xC0):
                            temp3 |= 0x01
                        elif (temp2 == 0x00):
                            temp3 |= 0x00
                        elif (temp2 == 0x80):
                            temp3 |= 0x00
                        else:  # 0x40
                            temp3 |= 0x01
                        if (o != 1 or k != 3):
                            temp3 <<= 1
                        temp1 <<= 2
                self.send_data(temp3)

        self.send_command(0x26)
        for j in range(self.height):
            for i in range(Width):
                temp3 = 0
                for o in range(0, 2):
                    temp1 = image[(j * Width1 + i) * 2 + o]
                    for k in range(0, 4):
                        temp2 = temp1 & 0xC0
                        if (temp2 == 0xC0):
                            temp3 |= 0x01
                        elif (temp2 == 0x00):
                            temp3 |= 0x00
                        elif (temp2 == 0x80):
                            temp3 |= 0x01
                        else:  # 0x40
                            temp3 |= 0x00
                        if (o != 1 or k != 3):
                            temp3 <<= 1
                        temp1 <<= 2
                self.send_data(temp3)

        self.send_command(0xA4)
        for j in range(self.height):
            for i in range(Width):
                temp3 = 0
                for o in range(0, 2):
                    temp1 = image[(j * Width1 + i + Width - 1) * 2 + o]
                    for k in range(0, 4):
                        temp2 = temp1 & 0xC0
                        if (temp2 == 0xC0):
                            temp3 |= 0x01
                        elif (temp2 == 0x00):
                            temp3 |= 0x00
                        elif (temp2 == 0x80):
                            temp3 |= 0x00
                        else:  # 0x40
                            temp3 |= 0x01
                        if (o != 1 or k != 3):
                            temp3 <<= 1
                        temp1 <<= 2
                self.send_data(temp3)

        self.send_command(0xA6)
        for j in range(self.height):
            for i in range(Width):
                temp3 = 0
                for o in range(0, 2):
                    temp1 = image[(j * Width1 + i + Width - 1) * 2 + o]
                    for k in range(0, 4):
                        temp2 = temp1 & 0xC0
                        if (temp2 == 0xC0):
                            temp3 |= 0x01
                        elif (temp2 == 0x00):
                            temp3 |= 0x00
                        elif (temp2 == 0x80):
                            temp3 |= 0x01
                        else:  # 0x40
                            temp3 |= 0x00
                        if (o != 1 or k != 3):
                            temp3 <<= 1
                        temp1 <<= 2
                self.send_data(temp3)

        self.TurnOnDisplay_4GRAY()

    def Clear(self):
        self.send_command(0x24)
        self.send_data2([0xFF] * 13600)
        self.send_command(0X26)
        self.send_data2([0x00] * 13600)

        self.send_command(0xA4)
        self.send_data2([0xFF] * 13600)
        self.send_command(0xA6)
        self.send_data2([0x00] * 13600)

        self.TurnOnDisplay()

    def sleep(self):
        self.send_command(0X10)  # deep sleep
        self.send_data(0x03)

        epdconfig.delay_ms(2000)
        epdconfig.module_exit()
### END OF FILE ###
