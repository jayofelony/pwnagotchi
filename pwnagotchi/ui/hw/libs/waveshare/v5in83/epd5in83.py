# *****************************************************************************
# * | File        :	  epd5in83.py
# * | Author      :   Waveshare team
# * | Function    :   Electronic paper driver
# * | Info        :
# *----------------
# * | This version:   V4.0
# * | Date        :   2019-06-20
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
EPD_WIDTH = 600
EPD_HEIGHT = 448

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

    def ReadBusy(self):
        logger.debug("e-Paper busy")
        while (epdconfig.digital_read(self.busy_pin) == 0):  # 0: idle, 1: busy
            epdconfig.delay_ms(100)
        logger.debug("e-Paper busy release")

    def init(self):
        if (epdconfig.module_init() != 0):
            return -1
        # EPD hardware init start
        self.reset()

        self.send_command(0x01)  # POWER_SETTING
        self.send_data(0x37)
        self.send_data(0x00)

        self.send_command(0x00)  # PANEL_SETTING
        self.send_data(0xCF)
        self.send_data(0x08)

        self.send_command(0x06)  # BOOSTER_SOFT_START
        self.send_data(0xc7)
        self.send_data(0xcc)
        self.send_data(0x28)

        self.send_command(0x04)  # POWER_ON
        self.ReadBusy()

        self.send_command(0x30)  # PLL_CONTROL
        self.send_data(0x3c)

        self.send_command(0x41)  # TEMPERATURE_CALIBRATION
        self.send_data(0x00)

        self.send_command(0x50)  # VCOM_AND_DATA_INTERVAL_SETTING
        self.send_data(0x77)

        self.send_command(0x60)  # TCON_SETTING
        self.send_data(0x22)

        self.send_command(0x61)  # TCON_RESOLUTION
        self.send_data(0x02)  # source 600
        self.send_data(0x58)
        self.send_data(0x01)  # gate 448
        self.send_data(0xC0)

        self.send_command(0x82)  # VCM_DC_SETTING
        self.send_data(0x1E)  # decide by LUT file

        self.send_command(0xe5)  # FLASH MODE
        self.send_data(0x03)

        # EPD hardware init end
        return 0

    def getbuffer(self, image):
        buf = [0x00] * int(self.width * self.height / 4)
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()
        logger.debug('imwidth = %d  imheight =  %d ', imwidth, imheight)
        if (imwidth == self.width and imheight == self.height):
            for y in range(imheight):
                for x in range(imwidth):
                    # Set the bits for the column of pixels at the current position.
                    if pixels[x, y] < 64:  # black
                        buf[int((x + y * self.width) / 4)] &= ~(0xC0 >> (x % 4 * 2))
                    elif pixels[x, y] < 192:  # convert gray to red
                        buf[int((x + y * self.width) / 4)] &= ~(0xC0 >> (x % 4 * 2))
                        buf[int((x + y * self.width) / 4)] |= 0x40 >> (x % 4 * 2)
                    else:  # white
                        buf[int((x + y * self.width) / 4)] |= 0xC0 >> (x % 4 * 2)
        elif (imwidth == self.height and imheight == self.width):
            for y in range(imheight):
                for x in range(imwidth):
                    newx = y
                    newy = self.height - x - 1
                    if pixels[x, y] < 64:  # black
                        buf[int((newx + newy * self.width) / 4)] &= ~(0xC0 >> (y % 4 * 2))
                    elif pixels[x, y] < 192:  # convert gray to red
                        buf[int((newx + newy * self.width) / 4)] &= ~(0xC0 >> (y % 4 * 2))
                        buf[int((newx + newy * self.width) / 4)] |= 0x40 >> (y % 4 * 2)
                    else:  # white
                        buf[int((newx + newy * self.width) / 4)] |= 0xC0 >> (y % 4 * 2)
        return buf

    def display(self, image):
        self.send_command(0x10)
        for i in range(0, int(self.width / 4 * self.height)):
            temp1 = image[i]
            j = 0
            while (j < 4):
                if ((temp1 & 0xC0) == 0xC0):
                    temp2 = 0x03
                elif ((temp1 & 0xC0) == 0x00):
                    temp2 = 0x00
                else:
                    temp2 = 0x04
                temp2 = (temp2 << 4) & 0xFF
                temp1 = (temp1 << 2) & 0xFF
                j += 1
                if ((temp1 & 0xC0) == 0xC0):
                    temp2 |= 0x03
                elif ((temp1 & 0xC0) == 0x00):
                    temp2 |= 0x00
                else:
                    temp2 |= 0x04
                temp1 = (temp1 << 2) & 0xFF
                self.send_data(temp2)
                j += 1

        self.send_command(0x12)
        epdconfig.delay_ms(100)
        self.ReadBusy()

    def Clear(self):
        self.send_command(0x10)
        for i in range(0, int(self.width / 4 * self.height)):
            for j in range(0, 4):
                self.send_data(0x33)
        self.send_command(0x12)
        self.ReadBusy()

    def sleep(self):
        self.send_command(0x02)  # POWER_OFF
        self.ReadBusy()
        self.send_command(0x07)  # DEEP_SLEEP
        self.send_data(0XA5)

        epdconfig.delay_ms(2000)
        epdconfig.module_exit()

### END OF FILE ###
