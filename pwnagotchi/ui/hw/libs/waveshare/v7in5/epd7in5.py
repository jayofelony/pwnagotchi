# *****************************************************************************
# * | File        :	  epd7in5.py
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
EPD_WIDTH = 640
EPD_HEIGHT = 384

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
        epdconfig.delay_ms(5)
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

    def send_data2(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte2(data)
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
        self.send_data2([0x37, 0x00])

        self.send_command(0x00)  # PANEL_SETTING
        self.send_data2([0xCF, 0x08])

        self.send_command(0x06)  # BOOSTER_SOFT_START
        self.send_data2([0xc7, 0xcc, 0x28])

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
        self.send_data(EPD_WIDTH >> 8)  # source 640
        self.send_data(EPD_WIDTH & 0xff)
        self.send_data(EPD_HEIGHT >> 8)  # gate 384
        self.send_data(EPD_HEIGHT & 0xff)

        self.send_command(0x82)  # VCM_DC_SETTING
        self.send_data(0x1E)  # decide by LUT file

        self.send_command(0xe5)  # FLASH MODE
        self.send_data(0x03)

        # EPD hardware init end
        return 0

    def getbuffer(self, image):
        img = image
        imwidth, imheight = img.size
        halfwidth = int(self.width / 2)
        buf = [0x33] * halfwidth * self.height

        if (imwidth == self.width and imheight == self.height):
            img = img.convert('1')
        elif (imwidth == self.height and imheight == self.width):
            img = img.rotate(90, expand=True).convert('1')
            imwidth, imheight = img.size
        else:
            logger.warning("Wrong image dimensions: must be " + str(self.width) + "x" + str(self.height))
            # return a blank buffer
            return buf

        pixels = img.load()

        for y in range(imheight):
            offset = y * halfwidth
            for x in range(1, imwidth, 2):
                i = offset + x // 2
                if (pixels[x - 1, y] > 191):
                    if (pixels[x, y] > 191):
                        buf[i] = 0x33
                    else:
                        buf[i] = 0x30
                else:
                    if (pixels[x, y] > 191):
                        buf[i] = 0x03
                    else:
                        buf[i] = 0x00
        return buf

    def display(self, image):
        self.send_command(0x10)
        self.send_data2(image)
        self.send_command(0x12)
        epdconfig.delay_ms(100)
        self.ReadBusy()

    def Clear(self):
        buf = [0x33] * int(self.width * self.height / 2)
        self.send_command(0x10)
        self.send_data2(buf)
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
