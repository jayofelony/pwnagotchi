# *****************************************************************************
# * | File        :	  epd2in7b.py
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
EPD_WIDTH = 176
EPD_HEIGHT = 264

logger = logging.getLogger(__name__)


class EPD:
    def __init__(self):
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin = epdconfig.DC_PIN
        self.busy_pin = epdconfig.BUSY_PIN
        self.cs_pin = epdconfig.CS_PIN
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT

    lut_vcom_dc = [
        0x00, 0x00,
        0x00, 0x1A, 0x1A, 0x00, 0x00, 0x01,
        0x00, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x00, 0x0E, 0x01, 0x0E, 0x01, 0x10,
        0x00, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x00, 0x04, 0x10, 0x00, 0x00, 0x05,
        0x00, 0x03, 0x0E, 0x00, 0x00, 0x0A,
        0x00, 0x23, 0x00, 0x00, 0x00, 0x01
    ]

    lut_ww = [
        0x90, 0x1A, 0x1A, 0x00, 0x00, 0x01,
        0x40, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x84, 0x0E, 0x01, 0x0E, 0x01, 0x10,
        0x80, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x00, 0x04, 0x10, 0x00, 0x00, 0x05,
        0x00, 0x03, 0x0E, 0x00, 0x00, 0x0A,
        0x00, 0x23, 0x00, 0x00, 0x00, 0x01
    ]

    # R22H    r
    lut_bw = [
        0xA0, 0x1A, 0x1A, 0x00, 0x00, 0x01,
        0x00, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x84, 0x0E, 0x01, 0x0E, 0x01, 0x10,
        0x90, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0xB0, 0x04, 0x10, 0x00, 0x00, 0x05,
        0xB0, 0x03, 0x0E, 0x00, 0x00, 0x0A,
        0xC0, 0x23, 0x00, 0x00, 0x00, 0x01
    ]

    # R23H    w
    lut_bb = [
        0x90, 0x1A, 0x1A, 0x00, 0x00, 0x01,
        0x40, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x84, 0x0E, 0x01, 0x0E, 0x01, 0x10,
        0x80, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x00, 0x04, 0x10, 0x00, 0x00, 0x05,
        0x00, 0x03, 0x0E, 0x00, 0x00, 0x0A,
        0x00, 0x23, 0x00, 0x00, 0x00, 0x01
    ]
    # R24H    b
    lut_wb = [
        0x90, 0x1A, 0x1A, 0x00, 0x00, 0x01,
        0x20, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x84, 0x0E, 0x01, 0x0E, 0x01, 0x10,
        0x10, 0x0A, 0x0A, 0x00, 0x00, 0x08,
        0x00, 0x04, 0x10, 0x00, 0x00, 0x05,
        0x00, 0x03, 0x0E, 0x00, 0x00, 0x0A,
        0x00, 0x23, 0x00, 0x00, 0x00, 0x01
    ]

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

    def set_lut(self):
        self.send_command(0x20)  # vcom
        for count in range(0, 44):
            self.send_data(self.lut_vcom_dc[count])
        self.send_command(0x21)  # ww --
        for count in range(0, 42):
            self.send_data(self.lut_ww[count])
        self.send_command(0x22)  # bw r
        for count in range(0, 42):
            self.send_data(self.lut_bw[count])
        self.send_command(0x23)  # wb w
        for count in range(0, 42):
            self.send_data(self.lut_bb[count])
        self.send_command(0x24)  # bb b
        for count in range(0, 42):
            self.send_data(self.lut_wb[count])

    def init(self):
        if (epdconfig.module_init() != 0):
            return -1

        self.reset()

        self.send_command(0x04)  # POWER_ON
        self.ReadBusy()

        self.send_command(0x00)  # PANEL_SETTING
        self.send_data(0xaf)  # KW-BF   KWR-AF    BWROTP 0f

        self.send_command(0x30)  # PLL_CONTROL
        self.send_data(0x3a)  # 3A 100HZ   29 150Hz 39 200HZ    31 171HZ

        self.send_command(0x01)  # POWER_SETTING
        self.send_data(0x03)  # VDS_EN, VDG_EN
        self.send_data(0x00)  # VCOM_HV, VGHL_LV[1], VGHL_LV[0]
        self.send_data(0x2b)  # VDH
        self.send_data(0x2b)  # VDL
        self.send_data(0x09)  # VDHR

        self.send_command(0x06)  # BOOSTER_SOFT_START
        self.send_data(0x07)
        self.send_data(0x07)
        self.send_data(0x17)

        # Power optimization
        self.send_command(0xF8)
        self.send_data(0x60)
        self.send_data(0xA5)

        # Power optimization
        self.send_command(0xF8)
        self.send_data(0x89)
        self.send_data(0xA5)

        # Power optimization
        self.send_command(0xF8)
        self.send_data(0x90)
        self.send_data(0x00)

        # Power optimization
        self.send_command(0xF8)
        self.send_data(0x93)
        self.send_data(0x2A)

        # Power optimization
        self.send_command(0xF8)
        self.send_data(0x73)
        self.send_data(0x41)

        self.send_command(0x82)  # VCM_DC_SETTING_REGISTER
        self.send_data(0x12)
        self.send_command(0x50)  # VCOM_AND_DATA_INTERVAL_SETTING
        self.send_data(0x87)  # define by OTP

        self.set_lut()

        self.send_command(0x16)  # PARTIAL_DISPLAY_REFRESH
        self.send_data(0x00)

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
        self.send_command(0x10)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(~imageblack[i])
        self.send_command(0x11)

        self.send_command(0x13)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(~imagered[i])
        self.send_command(0x11)

        self.send_command(0x12)
        self.ReadBusy()

    def Clear(self, color=0x00):
        self.send_command(0x10)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(color)
        self.send_command(0x11)

        self.send_command(0x13)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(color)
        self.send_command(0x11)

        self.send_command(0x12)
        self.ReadBusy()

    def sleep(self):
        self.send_command(0X50)
        self.send_data(0xf7)
        self.send_command(0X02)
        self.send_command(0X07)
        self.send_data(0xA5)

        epdconfig.delay_ms(2000)
        epdconfig.module_exit()
### END OF FILE ###
