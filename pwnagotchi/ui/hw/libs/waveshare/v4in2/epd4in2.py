# *****************************************************************************
# * | File        :   epd4in2.py
# * | Author      :   Waveshare team
# * | Function    :   Electronic paper driver
# * | Info        :
# *----------------
# * | This version:   V4.2
# * | Date        :   2022-10-29
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
from PIL import Image
import RPi.GPIO as GPIO

# Display resolution
EPD_WIDTH  = 400
EPD_HEIGHT = 300

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
        self.DATA = [0x00] * 15000

    lut_vcom0 = [
        0x00, 0x08, 0x08, 0x00, 0x00, 0x02,
        0x00, 0x0F, 0x0F, 0x00, 0x00, 0x01,
        0x00, 0x08, 0x08, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00,
    ]
    lut_ww = [
        0x50, 0x08, 0x08, 0x00, 0x00, 0x02,
        0x90, 0x0F, 0x0F, 0x00, 0x00, 0x01,
        0xA0, 0x08, 0x08, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    lut_bw = [
        0x50, 0x08, 0x08, 0x00, 0x00, 0x02,
        0x90, 0x0F, 0x0F, 0x00, 0x00, 0x01,
        0xA0, 0x08, 0x08, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    lut_wb = [
        0xA0, 0x08, 0x08, 0x00, 0x00, 0x02,
        0x90, 0x0F, 0x0F, 0x00, 0x00, 0x01,
        0x50, 0x08, 0x08, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    lut_bb = [
        0x20, 0x08, 0x08, 0x00, 0x00, 0x02,
        0x90, 0x0F, 0x0F, 0x00, 0x00, 0x01,
        0x10, 0x08, 0x08, 0x00, 0x00, 0x02,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    # ******************************partial screen update LUT*********************************/
    EPD_4IN2_Partial_lut_vcom1 = [
        0x00, 0x01, 0x20, 0x01, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    EPD_4IN2_Partial_lut_ww1 = [
        0x00, 0x01, 0x20, 0x01, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    EPD_4IN2_Partial_lut_bw1 = [
        0x20, 0x01, 0x20, 0x01, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    EPD_4IN2_Partial_lut_wb1 = [
        0x10, 0x01, 0x20, 0x01, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    EPD_4IN2_Partial_lut_bb1 = [
        0x00, 0x01, 0x20, 0x01, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    # ******************************gray*********************************/
    # 0~3 gray
    EPD_4IN2_4Gray_lut_vcom = [
        0x00, 0x0A, 0x00, 0x00, 0x00, 0x01,
        0x60, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x00, 0x14, 0x00, 0x00, 0x00, 0x01,
        0x00, 0x13, 0x0A, 0x01, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    # R21
    EPD_4IN2_4Gray_lut_ww = [
        0x40, 0x0A, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x10, 0x14, 0x0A, 0x00, 0x00, 0x01,
        0xA0, 0x13, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    # R22H r
    EPD_4IN2_4Gray_lut_bw = [
        0x40, 0x0A, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x00, 0x14, 0x0A, 0x00, 0x00, 0x01,
        0x99, 0x0C, 0x01, 0x03, 0x04, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    # R23H w
    EPD_4IN2_4Gray_lut_wb = [
        0x40, 0x0A, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x00, 0x14, 0x0A, 0x00, 0x00, 0x01,
        0x99, 0x0B, 0x04, 0x04, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]
    # R24H b
    EPD_4IN2_4Gray_lut_bb = [
        0x80, 0x0A, 0x00, 0x00, 0x00, 0x01,
        0x90, 0x14, 0x14, 0x00, 0x00, 0x01,
        0x20, 0x14, 0x0A, 0x00, 0x00, 0x01,
        0x50, 0x13, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    # Hardware reset
    def reset(self):
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(10)
        epdconfig.digital_write(self.reset_pin, 0)
        epdconfig.delay_ms(10)
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(10)
        epdconfig.digital_write(self.reset_pin, 0)
        epdconfig.delay_ms(10)
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(10)
        epdconfig.digital_write(self.reset_pin, 0)
        epdconfig.delay_ms(10)
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(10)

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
        self.send_command(0x71)
        while epdconfig.digital_read(self.busy_pin) == 0:  # 0: idle, 1: busy
            self.send_command(0x71)
            epdconfig.delay_ms(100)

    def set_lut(self):
        self.send_command(0x20)  # vcom
        self.send_data2(self.lut_vcom0)

        self.send_command(0x21)  # ww --
        self.send_data2(self.lut_ww)

        self.send_command(0x22)  # bw r
        self.send_data2(self.lut_bw)

        self.send_command(0x23)  # wb w
        self.send_data2(self.lut_bb)

        self.send_command(0x24)  # bb b
        self.send_data2(self.lut_wb)

    def Partial_SetLut(self):
        self.send_command(0x20)
        self.send_data2(self.EPD_4IN2_Partial_lut_vcom1)

        self.send_command(0x21)
        self.send_data2(self.EPD_4IN2_Partial_lut_ww1)

        self.send_command(0x22)
        self.send_data2(self.EPD_4IN2_Partial_lut_bw1)

        self.send_command(0x23)
        self.send_data2(self.EPD_4IN2_Partial_lut_wb1)

        self.send_command(0x24)
        self.send_data2(self.EPD_4IN2_Partial_lut_bb1)

    def Gray_SetLut(self):
        self.send_command(0x20)  # vcom
        self.send_data2(self.EPD_4IN2_4Gray_lut_vcom)

        self.send_command(0x21)  # red not use
        self.send_data2(self.EPD_4IN2_4Gray_lut_ww)

        self.send_command(0x22)  # bw r
        self.send_data2(self.EPD_4IN2_4Gray_lut_bw)

        self.send_command(0x23)  # wb w
        self.send_data2(self.EPD_4IN2_4Gray_lut_wb)

        self.send_command(0x24)  # bb b
        self.send_data2(self.EPD_4IN2_4Gray_lut_bb)

        self.send_command(0x25)  # vcom
        self.send_data2(self.EPD_4IN2_4Gray_lut_ww)

    def init(self):
        if epdconfig.module_init() != 0:
            return -1
        # EPD hardware init start
        self.reset()

        self.send_command(0x01)  # POWER SETTING
        self.send_data(0x03)  # VDS_EN, VDG_EN
        self.send_data(0x00)  # VCOM_HV, VGHL_LV[1], VGHL_LV[0]
        self.send_data(0x2b)  # VDH
        self.send_data(0x2b)  # VDL

        self.send_command(0x06)  # boost soft start
        self.send_data(0x17)
        self.send_data(0x17)
        self.send_data(0x17)

        self.send_command(0x04)  # POWER_ON
        self.ReadBusy()

        self.send_command(0x00)  # panel setting
        self.send_data(0xbf)  # KW-BF   KWR-AF  BWROTP 0f

        self.send_command(0x30)  # PLL setting
        self.send_data(0x3c)  # 3A 100HZ   29 150Hz 39 200HZ  31 171HZ

        self.send_command(0x61)  # resolution setting
        self.send_data(0x01)
        self.send_data(0x90)  # 128
        self.send_data(0x01)
        self.send_data(0x2c)

        self.send_command(0x82)  # vcom_DC setting
        self.send_data(0x12)

        self.send_command(0X50)  # VCOM AND DATA INTERVAL SETTING
        self.send_data(
            0x97)  # 97white border 77black border  VBDF 17|D7 VBDW 97 VBDB 57  VBDF F7 VBDW 77 VBDB 37  VBDR B7

        self.set_lut()
        # EPD hardware init end
        return 0

    def init_Partial(self):
        if epdconfig.module_init() != 0:
            return -1
        # EPD hardware init start
        self.reset()

        self.send_command(0x01)  # POWER SETTING
        self.send_data(0x03)  # VDS_EN, VDG_EN
        self.send_data(0x00)  # VCOM_HV, VGHL_LV[1], VGHL_LV[0]
        self.send_data(0x2b)  # VDH
        self.send_data(0x2b)  # VDL

        self.send_command(0x06)  # boost soft start
        self.send_data(0x17)
        self.send_data(0x17)
        self.send_data(0x17)

        self.send_command(0x04)  # POWER_ON
        self.ReadBusy()

        self.send_command(0x00)  # panel setting
        self.send_data(0xbf)  # KW-BF   KWR-AF  BWROTP 0f

        self.send_command(0x30)  # PLL setting
        self.send_data(0x3c)  # 3A 100HZ   29 150Hz 39 200HZ  31 171HZ

        self.send_command(0x61)  # resolution setting
        self.send_data(0x01)
        self.send_data(0x90)  # 128
        self.send_data(0x01)
        self.send_data(0x2c)

        self.send_command(0x82)  # vcom_DC setting
        self.send_data(0x12)

        self.send_command(0X50)  # VCOM AND DATA INTERVAL SETTING
        self.send_data(
            0x07)  # 97white border 77black border  VBDF 17|D7 VBDW 97 VBDB 57  VBDF F7 VBDW 77 VBDB 37  VBDR B7

        self.Partial_SetLut()
        # EPD hardware init end
        return 0

    def Init_4Gray(self):
        if epdconfig.module_init() != 0:
            return -1
        # EPD hardware init start
        self.reset()

        self.send_command(0x01)  # POWER SETTING
        self.send_data(0x03)
        self.send_data(0x00)  # VGH=20V,VGL=-20V
        self.send_data(0x2b)  # VDH=15V
        self.send_data(0x2b)  # VDL=-15V
        self.send_data(0x13)

        self.send_command(0x06)  # booster soft start
        self.send_data(0x17)  # A
        self.send_data(0x17)  # B
        self.send_data(0x17)  # C

        self.send_command(0x04)
        self.ReadBusy()

        self.send_command(0x00)  # panel setting
        self.send_data(0x3f)  # KW-3f   KWR-2F BWROTP 0f BWOTP 1f

        self.send_command(0x30)  # PLL setting
        self.send_data(0x3c)  # 100hz

        self.send_command(0x61)  # resolution setting
        self.send_data(0x01)  # 400
        self.send_data(0x90)
        self.send_data(0x01)  # 300
        self.send_data(0x2c)

        self.send_command(0x82)  # vcom_DC setting
        self.send_data(0x12)

        self.send_command(0X50)  # VCOM AND DATA INTERVAL SETTING
        self.send_data(0x97)

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
        if imwidth == self.width and imheight == self.height:
            logger.debug("Vertical")
            for y in range(imheight):
                for x in range(imwidth):
                    # Set the bits for the column of pixels at the current position.
                    if pixels[x, y] == 0xC0:
                        pixels[x, y] = 0x80
                    elif pixels[x, y] == 0x80:
                        pixels[x, y] = 0x40
                    i = i + 1
                    if i % 4 == 0:
                        buf[int((x + (y * self.width)) / 4)] = (
                                    (pixels[x - 3, y] & 0xc0) | (pixels[x - 2, y] & 0xc0) >> 2 | (
                                        pixels[x - 1, y] & 0xc0) >> 4 | (pixels[x, y] & 0xc0) >> 6)

        elif imwidth == self.height and imheight == self.width:
            logger.debug("Horizontal")
            for x in range(imwidth):
                for y in range(imheight):
                    newx = y
                    newy = x
                    if pixels[x, y] == 0xC0:
                        pixels[x, y] = 0x80
                    elif pixels[x, y] == 0x80:
                        pixels[x, y] = 0x40
                    i = i + 1
                    if i % 4 == 0:
                        buf[int((newx + (newy * self.width)) / 4)] = (
                                    (pixels[x, y - 3] & 0xc0) | (pixels[x, y - 2] & 0xc0) >> 2 | (
                                        pixels[x, y - 1] & 0xc0) >> 4 | (pixels[x, y] & 0xc0) >> 6)

        return buf

    def display(self, image):
        if self.width % 8 == 0:
            linewidth = int(self.width / 8)
        else:
            linewidth = int(self.width / 8) + 1

        self.send_command(0x92)
        self.set_lut()
        self.send_command(0x10)
        self.send_data2([0xFF] * int(self.width * linewidth))

        self.send_command(0x13)
        self.send_data2(image)

        self.send_command(0x12)
        self.ReadBusy()

    def EPD_4IN2_PartialDisplay(self, X_start, Y_start, X_end, Y_end, Image):
        # EPD_WIDTH       = 400
        # EPD_HEIGHT      = 300

        if EPD_WIDTH % 8 != 0:
            Width = int(EPD_WIDTH / 8) + 1
        else:
            Width = int(EPD_WIDTH / 8)
        Height = EPD_HEIGHT

        if X_start % 8 != 0:
            X_start = int(X_start / 8) + 1
        else:
            X_start = int(X_start / 8)
        if X_end % 8 != 0:
            X_end = int(X_end / 8) + 1
        else:
            X_end = int(X_end / 8)

        buf = [0x00] * (Y_end - Y_start) * (X_end - X_start)

        self.send_command(0x91)  # This command makes the display enter partial mode
        self.send_command(0x90)  # resolution setting
        self.send_data(int(X_start * 8 / 256))
        self.send_data(int(X_start * 8 % 256))  # x-start

        self.send_data(int(X_end * 8 / 256))
        self.send_data(int(X_end * 8 % 256) - 1)  # x-end

        self.send_data(int(Y_start / 256))
        self.send_data(int(Y_start % 256))  # y-start

        self.send_data(int(Y_end / 256))
        self.send_data(int(Y_end % 256) - 1)  # y-end
        self.send_data(0x28)

        self.send_command(0x10)  # writes Old data to SRAM for programming
        for j in range(0, Y_end - Y_start):
            for i in range(0, X_end - X_start):
                buf[j * (X_end - X_start) + i] = self.DATA[(Y_start + j) * Width + X_start + i]
        self.send_data2(buf)

        self.send_command(0x13)  # writes New data to SRAM.
        for j in range(0, Y_end - Y_start):
            for i in range(0, X_end - X_start):
                buf[j * (X_end - X_start) + i] = ~Image[(Y_start + j) * Width + X_start + i]
                self.DATA[(Y_start + j) * Width + X_start + i] = ~Image[(Y_start + j) * Width + X_start / 8 + i]
        self.send_data2(buf)

        self.send_command(0x12)  # DISPLAY REFRESH
        epdconfig.delay_ms(200)  # The delay here is necessary, 200uS at least!!!
        self.ReadBusy()

    def display_4Gray(self, image):
        self.send_command(0x92)
        self.set_lut()
        self.send_command(0x10)

        if self.width % 8 == 0:
            linewidth = int(self.width / 8)
        else:
            linewidth = int(self.width / 8) + 1

        buf = [0x00] * self.height * linewidth

        for i in range(0, int(EPD_WIDTH * EPD_HEIGHT / 8)):  # EPD_WIDTH * EPD_HEIGHT / 4
            temp3 = 0
            for j in range(0, 2):
                temp1 = image[i * 2 + j]
                for k in range(0, 2):
                    temp2 = temp1 & 0xC0
                    if temp2 == 0xC0:
                        temp3 |= 0x01  # white
                    elif temp2 == 0x00:
                        temp3 |= 0x00  # black
                    elif temp2 == 0x80:
                        temp3 |= 0x01  # gray1
                    else:  # 0x40
                        temp3 |= 0x00  # gray2
                    temp3 <<= 1

                    temp1 <<= 2
                    temp2 = temp1 & 0xC0
                    if temp2 == 0xC0:  # white
                        temp3 |= 0x01
                    elif temp2 == 0x00:  # black
                        temp3 |= 0x00
                    elif temp2 == 0x80:
                        temp3 |= 0x01  # gray1
                    else:  # 0x40
                        temp3 |= 0x00  # gray2
                    if j != 1 or k != 1:
                        temp3 <<= 1
                    temp1 <<= 2
            buf[i] = temp3
        self.send_data2(buf)

        self.send_command(0x13)

        for i in range(0, int(EPD_WIDTH * EPD_HEIGHT / 8)):  # 5808*4  46464
            temp3 = 0
            for j in range(0, 2):
                temp1 = image[i * 2 + j]
                for k in range(0, 2):
                    temp2 = temp1 & 0xC0
                    if temp2 == 0xC0:
                        temp3 |= 0x01  # white
                    elif temp2 == 0x00:
                        temp3 |= 0x00  # black
                    elif temp2 == 0x80:
                        temp3 |= 0x00  # gray1
                    else:  # 0x40
                        temp3 |= 0x01  # gray2
                    temp3 <<= 1

                    temp1 <<= 2
                    temp2 = temp1 & 0xC0
                    if temp2 == 0xC0:  # white
                        temp3 |= 0x01
                    elif temp2 == 0x00:  # black
                        temp3 |= 0x00
                    elif temp2 == 0x80:
                        temp3 |= 0x00  # gray1
                    else:  # 0x40
                        temp3 |= 0x01  # gray2
                    if j != 1 or k != 1:
                        temp3 <<= 1
                    temp1 <<= 2
            buf[i] = temp3
        self.send_data2(buf)

        self.Gray_SetLut()
        self.send_command(0x12)
        epdconfig.delay_ms(200)
        self.ReadBusy()
        # pass

    def Clear(self):
        if self.width % 8 == 0:
            linewidth = int(self.width / 8)
        else:
            linewidth = int(self.width / 8) + 1

        self.send_command(0x10)
        self.send_data2([0xff] * int(self.height * linewidth))

        self.send_command(0x13)
        self.send_data2([0xff] * int(self.height * linewidth))

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