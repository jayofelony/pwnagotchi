# *****************************************************************************
# * | File        :   epd3in52.py
# * | Author      :   Waveshare team
# * | Function    :   Electronic paper driver
# * | Info        :
# *----------------
# * | This version:   V1.0
# * | Date        :   2022-07-20
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
from multiprocessing.reduction import recv_handle
from .. import epdconfig

# Display resolution
EPD_WIDTH = 240
EPD_HEIGHT = 360

logger = logging.getLogger(__name__)


class EPD:
    def __init__(self):
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin = epdconfig.DC_PIN
        self.busy_pin = epdconfig.BUSY_PIN
        self.cs_pin = epdconfig.CS_PIN
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT
        self.Flag = 0
        self.WHITE = 0xFF
        self.BLACK = 0x00
        self.Source_Line = 0xAA
        self.Gate_Line = 0x55
        self.UP_BLACK_DOWN_WHITE = 0xF0
        self.LEFT_BLACK_RIGHT_WHITE = 0x0F
        self.Frame = 0x01
        self.Crosstalk = 0x02
        self.Chessboard = 0x03
        self.Image = 0x04

    # GC 0.9S
    lut_R20_GC = [
        0x01, 0x0f, 0x0f, 0x0f, 0x01, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_R21_GC = [
        0x01, 0x4f, 0x8f, 0x0f, 0x01, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_R22_GC = [
        0x01, 0x0f, 0x8f, 0x0f, 0x01, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_R23_GC = [
        0x01, 0x4f, 0x8f, 0x4f, 0x01, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_R24_GC = [
        0x01, 0x0f, 0x8f, 0x4f, 0x01, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]

    # DU 0.3s
    lut_R20_DU = [
        0x01, 0x0f, 0x01, 0x00, 0x00, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_R21_DU = [
        0x01, 0x0f, 0x01, 0x00, 0x00, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_R22_DU = [
        0x01, 0x8f, 0x01, 0x00, 0x00, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_R23_DU = [
        0x01, 0x4f, 0x01, 0x00, 0x00, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_R24_DU = [
        0x01, 0x0f, 0x01, 0x00, 0x00, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]

    lut_vcom = [
        0x01, 0x19, 0x19, 0x19, 0x19, 0x01, 0x01,
        0x01, 0x19, 0x19, 0x19, 0x01, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_ww = [
        0x01, 0x59, 0x99, 0x59, 0x99, 0x01, 0x01,
        0x01, 0x59, 0x99, 0x19, 0x01, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_bw = [
        0x01, 0x59, 0x99, 0x59, 0x99, 0x01, 0x01,
        0x01, 0x59, 0x99, 0x19, 0x01, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_wb = [
        0x01, 0x19, 0x99, 0x59, 0x99, 0x01, 0x01,
        0x01, 0x59, 0x99, 0x59, 0x01, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    lut_bb = [
        0x01, 0x19, 0x99, 0x59, 0x99, 0x01, 0x01,
        0x01, 0x59, 0x99, 0x59, 0x01, 0x01, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
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

    # send a lot of data
    def send_data2(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte2(data)
        epdconfig.digital_write(self.cs_pin, 1)

    def ReadBusy(self):
        logger.debug("e-Paper busy")
        while (epdconfig.digital_read(self.busy_pin) == 0):  # 0: busy, 1: idle
            epdconfig.delay_ms(5)
        logger.debug("e-Paper busy release")

    def lut(self):
        self.send_command(0x20)  # vcom
        self.send_data2(self.lut_vcom[:42])

        self.send_command(0x21)  # ww --
        self.send_data2(self.lut_ww[:42])

        self.send_command(0x22)  # bw r
        self.send_data2(self.lut_bw[:42])

        self.send_command(0x23)  # wb w
        self.send_data2(self.lut_bb[:42])

        self.send_command(0x24)  # bb b
        self.send_data2(self.lut_wb[:42])

    def refresh(self):
        self.send_command(0x17)
        self.send_data(0xA5)
        self.ReadBusy()
        epdconfig.delay_ms(200)

    # LUT download
    def lut_GC(self):
        self.send_command(0x20);  # vcom
        self.send_data2(self.lut_R20_GC[:56])

        self.send_command(0x21);  # red not use
        self.send_data2(self.lut_R21_GC[:42])

        self.send_command(0x24);  # bb b
        self.send_data2(self.lut_R24_GC[:42])

        if (self.Flag == 0):
            self.send_command(0x22);  # bw r
            self.send_data2(self.lut_R22_GC[:56])

            self.send_command(0x23);  # wb w
            self.send_data2(self.lut_R23_GC[:42])
            self.Flag = 1

        else:
            self.send_command(0x22);  # bw r
            self.send_data2(self.lut_R23_GC[:56])

            self.send_command(0x23);  # wb w
            self.send_data2(self.lut_R22_GC[:42])
            self.Flag = 0

    # LUT download
    def lut_DU(self):
        self.send_command(0x20);  # vcom
        self.send_data2(self.lut_R20_DU[:56])

        self.send_command(0x21);  # red not use
        self.send_data2(self.lut_R21_DU[:42])

        self.send_command(0x24);  # bb b
        self.send_data2(self.lut_R24_DU[:42])

        if (self.Flag == 0):
            self.send_command(0x22);  # bw r
            self.send_data2(self.lut_R22_DU[:56])

            self.send_command(0x23);  # wb w
            self.send_data2(self.lut_R23_DU[:42])

            self.Flag = 1

        else:
            self.send_command(0x22);  # bw r
            self.send_data2(self.lut_R23_DU[:56])

            self.send_command(0x23);  # wb w
            self.send_data2(self.lut_R22_DU[:42])

            self.Flag = 0

    def init(self):
        if (epdconfig.module_init() != 0):
            return -1
        # EPD hardware init start
        self.Flag = 0
        self.reset()

        self.send_command(0x00)  # panel setting   PSR
        self.send_data(0xFF)  # RES1 RES0 REG KW/R     UD    SHL   SHD_N  RST_N
        self.send_data(0x01)  # x x x VCMZ TS_AUTO TIGE NORG VC_LUTZ

        self.send_command(0x01)  # POWER SETTING   PWR
        self.send_data(0x03)  # x x x x x x VDS_EN VDG_EN
        self.send_data(0x10)  # x x x VCOM_SLWE VGH[3:0]   VGH=20V, VGL=-20V
        self.send_data(0x3F)  # x x VSH[5:0]    VSH = 15V
        self.send_data(0x3F)  # x x VSL[5:0]    VSL=-15V
        self.send_data(0x03)  # OPTEN VDHR[6:0]  VHDR=6.4V
        # T_VDS_OFF[1:0] 00=1 frame; 01=2 frame; 10=3 frame; 11=4 frame
        self.send_command(0x06)  # booster soft start   BTST
        self.send_data(0x37)  # BT_PHA[7:0]
        self.send_data(0x3D)  # BT_PHB[7:0]
        self.send_data(0x3D)  # x x BT_PHC[5:0]

        self.send_command(0x60)  # TCON setting            TCON
        self.send_data(0x22)  # S2G[3:0] G2S[3:0]   non-overlap = 12

        self.send_command(0x82)  # VCOM_DC setting        VDCS
        self.send_data(0x07)  # x  VDCS[6:0]    VCOM_DC value= -1.9v    00~3f,0x12=-1.9v

        self.send_command(0x30)
        self.send_data(0x09)

        self.send_command(0xe3)  # power saving            PWS
        self.send_data(0x88)  # VCOM_W[3:0] SD_W[3:0]

        self.send_command(0x61)  # resoultion setting
        self.send_data(0xf0)  # HRES[7:3] 0 0 0
        self.send_data(0x01)  # x x x x x x x VRES[8]
        self.send_data(0x68)  # VRES[7:0]

        self.send_command(0x50);
        self.send_data(0xB7);
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

    def display(self, image):
        if (image == None):
            return
        self.send_command(0x13);  # Transfer new data
        self.send_data2(image)

    def display_NUM(self, NUM):
        # pcnt = 0

        self.send_command(0x13);  # Transfer new data
        for column in range(0, self.height):
            for row in range(0, self.width // 8):
                if NUM == self.WHITE:
                    self.send_data(0xFF)

                elif NUM == self.BLACK:
                    self.send_data(0x00)

                elif NUM == self.Source_Line:
                    self.send_data(0xAA)

                elif NUM == self.Gate_Line:
                    if (column % 2):
                        self.send_data(0xff)  # An odd number of Gate line
                    else:
                        self.send_data(0x00)  # The even line Gate

                elif NUM == self.Chessboard:
                    if (row >= (self.width / 8 / 2) and column >= (self.height / 2)):
                        self.send_data(0xff)
                    elif (row < (self.width / 8 / 2) and column < (self.height / 2)):
                        self.send_data(0xff)
                    else:
                        self.send_data(0x00)

                elif NUM == self.LEFT_BLACK_RIGHT_WHITE:
                    if (row >= (self.width / 8 / 2)):
                        self.send_data(0xff)
                    else:
                        self.send_data(0x00)

                elif NUM == self.UP_BLACK_DOWN_WHITE:
                    if (column >= (self.height / 2)):
                        self.send_data(0xFF)
                    else:
                        self.send_data(0x00)

                elif NUM == self.Frame:
                    if (column == 0 or column == (self.height - 1)):
                        self.send_data(0x00)
                    elif (row == 0):
                        self.send_data(0x7F)
                    elif (row == (self.width / 8 - 1)):
                        self.send_data(0xFE);
                    else:
                        self.send_data(0xFF);

                elif NUM == self.Crosstalk:
                    if ((row >= (self.width / 8 / 3) and row <= (self.width / 8 / 3 * 2) and column <= (
                            self.height / 3)) or (
                            row >= (self.width / 8 / 3) and row <= (self.width / 8 / 3 * 2) and column >= (
                            self.height / 3 * 2))):
                        self.send_data(0x00)
                    else:
                        self.send_data(0xFF)

                elif NUM == self.Image:
                    epdconfig.delay_ms(1)
                    # self.send_data(gImage_1[pcnt++])

    def Clear(self):
        self.send_command(0x13);  # Transfer new data
        self.send_data2([0xFF] * int(self.width * self.height / 8))
        self.lut_GC()
        self.refresh()

    def sleep(self):
        self.send_command(0X07)  # DEEP_SLEEP_MODE
        self.send_data(0xA5)

        epdconfig.delay_ms(2000)
        epdconfig.module_exit()
### END OF FILE ###
