# *****************************************************************************
# * | File        :	  epd5in79b.py
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
        self.send_data(0xF7)  # 24s  #  0xD7  16s  Probability refresh bad, probability damage ink screen
        self.send_command(0x20)  # DISPLAY REFRESH
        epdconfig.delay_ms(100)  # The delay here is necessary, 200uS at least!!!
        self.ReadBusy()  # waiting for the electronic paper IC to release the idle signal

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

        self.send_command(0xCe)
        self.send_data(0x31)
        self.send_command(0xCf)
        self.send_data(0x0f)
        self.send_data(0x01)
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

    def display(self, imageblack, imagered):
        buf = [0x00] * int(self.width * self.height / 8)
        for i in range(0, int(self.width * self.height / 8)):
            buf[i] = ~imagered[i]

        Width = int(self.width / 16) + 1
        Width1 = int(self.width / 8)
        Height = self.height

        self.send_command(0x24)
        for i in range(Height):
            self.send_data2(imageblack[i * Width1: i * Width1 + Width])
        self.send_command(0X26)
        for i in range(self.height):
            self.send_data2(buf[i * Width1: i * Width1 + Width])

        self.send_command(0xA4)
        for i in range(self.height):
            self.send_data2(imageblack[i * Width1 + Width - 1: i * Width1 + Width * 2 - 1])
        self.send_command(0xA6)
        for i in range(self.height):
            self.send_data2(buf[i * Width1 + Width - 1: i * Width1 + Width * 2 - 1])

        self.TurnOnDisplay()

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
