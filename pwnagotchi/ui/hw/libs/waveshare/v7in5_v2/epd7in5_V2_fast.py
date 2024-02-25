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
EPD_WIDTH = 800
EPD_HEIGHT = 480

logger = logging.getLogger(__name__)


class EPD:
    def __init__(self):
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin = epdconfig.DC_PIN
        self.busy_pin = epdconfig.BUSY_PIN
        self.cs_pin = epdconfig.CS_PIN
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT

    Voltage_Frame_7IN5_V2 = [
        0x6, 0x3F, 0x3F, 0x11, 0x24, 0x7, 0x17,
    ]

    LUT_VCOM_7IN5_V2 = [
        0x0, 0xF, 0xF, 0x0, 0x0, 0x1,
        0x0, 0xF, 0x1, 0xF, 0x1, 0x2,
        0x0, 0xF, 0xF, 0x0, 0x0, 0x1,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
    ]

    LUT_WW_7IN5_V2 = [
        0x10, 0xF, 0xF, 0x0, 0x0, 0x1,
        0x84, 0xF, 0x1, 0xF, 0x1, 0x2,
        0x20, 0xF, 0xF, 0x0, 0x0, 0x1,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
    ]

    LUT_BW_7IN5_V2 = [
        0x10, 0xF, 0xF, 0x0, 0x0, 0x1,
        0x84, 0xF, 0x1, 0xF, 0x1, 0x2,
        0x20, 0xF, 0xF, 0x0, 0x0, 0x1,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
    ]

    LUT_WB_7IN5_V2 = [
        0x80, 0xF, 0xF, 0x0, 0x0, 0x1,
        0x84, 0xF, 0x1, 0xF, 0x1, 0x2,
        0x40, 0xF, 0xF, 0x0, 0x0, 0x1,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
    ]

    LUT_BB_7IN5_V2 = [
        0x80, 0xF, 0xF, 0x0, 0x0, 0x1,
        0x84, 0xF, 0x1, 0xF, 0x1, 0x2,
        0x40, 0xF, 0xF, 0x0, 0x0, 0x1,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
        0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
    ]

    # Hardware reset
    def reset(self):
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(20)
        epdconfig.digital_write(self.reset_pin, 0)
        epdconfig.delay_ms(2)
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(20)

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
        self.send_command(0x71)
        busy = epdconfig.digital_read(self.busy_pin)
        while (busy == 0):
            self.send_command(0x71)
            busy = epdconfig.digital_read(self.busy_pin)
        epdconfig.delay_ms(20)
        logger.debug("e-Paper busy release")

    def SetLut(self, lut_vcom, lut_ww, lut_bw, lut_wb, lut_bb):
        self.send_command(0x20)
        for count in range(0, 42):
            self.send_data(lut_vcom[count])

        self.send_command(0x21)
        for count in range(0, 42):
            self.send_data(lut_ww[count])

        self.send_command(0x22)
        for count in range(0, 42):
            self.send_data(lut_bw[count])

        self.send_command(0x23)
        for count in range(0, 42):
            self.send_data(lut_wb[count])

        self.send_command(0x24)
        for count in range(0, 42):
            self.send_data(lut_bb[count])

    def init(self):
        if (epdconfig.module_init() != 0):
            return -1
        # EPD hardware init start
        self.reset()

        # self.send_command(0x06)     # btst
        # self.send_data(0x17)
        # self.send_data(0x17)
        # self.send_data(0x28)        # If an exception is displayed, try using 0x38
        # self.send_data(0x17)

        # self.send_command(0x01)   #POWER SETTING
        # self.send_data(0x07)
        # self.send_data(0x07)      #VGH=20V,VGL=-20V
        # self.send_data(0x3f)		#VDH=15V
        # self.send_data(0x3f)		#VDL=-15V

        self.send_command(0x01)  # power setting
        self.send_data(0x17)  # 1-0=11: internal power
        self.send_data(self.Voltage_Frame_7IN5_V2[6])  # VGH&VGL
        self.send_data(self.Voltage_Frame_7IN5_V2[1])  # VSH
        self.send_data(self.Voltage_Frame_7IN5_V2[2])  # VSL
        self.send_data(self.Voltage_Frame_7IN5_V2[3])  # VSHR

        self.send_command(0x82)  # VCOM DC Setting
        self.send_data(self.Voltage_Frame_7IN5_V2[4])  # VCOM

        self.send_command(0x06)  # Booster Setting
        self.send_data(0x27)
        self.send_data(0x27)
        self.send_data(0x2F)
        self.send_data(0x17)

        self.send_command(0x30)  # OSC Setting
        self.send_data(self.Voltage_Frame_7IN5_V2[0])  # 3C=50Hz, 3A=100HZ

        self.send_command(0x04)  # POWER ON
        epdconfig.delay_ms(100)
        self.ReadBusy()

        self.send_command(0X00)  # PANNEL SETTING
        self.send_data(0x3F)  # KW-3f KWR-2F BWROTP-0f BWOTP-1f

        self.send_command(0x61)  # tres
        self.send_data(0x03)  # source 800
        self.send_data(0x20)
        self.send_data(0x01)  # gate 480
        self.send_data(0xE0)

        self.send_command(0X15)
        self.send_data(0x00)

        self.send_command(0X50)  # VCOM AND DATA INTERVAL SETTING
        self.send_data(0x10)
        self.send_data(0x07)

        self.send_command(0X60)  # TCON SETTING
        self.send_data(0x22)

        self.send_command(0x65)  # Resolution setting
        self.send_data(0x00)
        self.send_data(0x00)  # 800*480
        self.send_data(0x00)
        self.send_data(0x00)

        self.SetLut(self.LUT_VCOM_7IN5_V2, self.LUT_WW_7IN5_V2, self.LUT_BW_7IN5_V2, self.LUT_WB_7IN5_V2,
                    self.LUT_BB_7IN5_V2)
        # EPD hardware init end
        return 0

    def getbuffer(self, image):
        img = image
        imwidth, imheight = img.size
        if (imwidth == self.width and imheight == self.height):
            img = img.convert('1')
        elif (imwidth == self.height and imheight == self.width):
            # image has correct dimensions, but needs to be rotated
            img = img.rotate(90, expand=True).convert('1')
        else:
            logger.warning("Wrong image dimensions: must be " + str(self.width) + "x" + str(self.height))
            # return a blank buffer
            return [0x00] * (int(self.width / 8) * self.height)

        buf = bytearray(img.tobytes('raw'))
        # The bytes need to be inverted, because in the PIL world 0=black and 1=white, but
        # in the e-paper world 0=white and 1=black.
        for i in range(len(buf)):
            buf[i] ^= 0xFF
        return buf

    def display(self, image):
        self.send_command(0x13)
        self.send_data2(image)

        self.send_command(0x12)
        epdconfig.delay_ms(100)
        self.ReadBusy()

    def Clear(self):
        buf = [0x00] * (int(self.width / 8) * self.height)
        self.send_command(0x10)
        self.send_data2(buf)
        self.send_command(0x13)
        self.send_data2(buf)
        self.send_command(0x12)
        epdconfig.delay_ms(100)
        self.ReadBusy()

    def sleep(self):
        self.send_command(0x02)  # POWER_OFF
        self.ReadBusy()

        self.send_command(0x07)  # DEEP_SLEEP
        self.send_data(0XA5)

        epdconfig.delay_ms(2000)
        epdconfig.module_exit()
### END OF FILE ###