# *****************************************************************************
# * | File        :	  epd1in54.py
# * | Author      :   Waveshare team
# * | Function    :   Electronic paper driver
# * | Info        :
# *----------------
# * | This version:   V1.0
# * | Date        :   2019-06-20
# # | Info        :   python demo
# -----------------------------------------------------------------------------
# ******************************************************************************/
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
EPD_WIDTH = 80
EPD_HEIGHT = 128

logger = logging.getLogger(__name__)


class EPD:
    def __init__(self):
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin = epdconfig.DC_PIN
        self.busy_pin = epdconfig.BUSY_PIN
        self.cs_pin = epdconfig.CS_PIN
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT

    # full screen update LUT

    lut_w1 = [
        0x60, 0x5A, 0x5A, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_b1 = [
        0x90, 0x5A, 0x5A, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    # partial screen update LUT
    lut_w = [
        0x60, 0x01, 0x01, 0x00, 0x00, 0x01,
        0x80, 0x1f, 0x00, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    lut_b = [
        0x90, 0x01, 0x01, 0x00, 0x00, 0x01,
        0x40, 0x1f, 0x00, 0x00, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ]

    # Hardware reset
    def reset(self):
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(200)
        epdconfig.digital_write(self.reset_pin, 0)  # module reset
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
        self.send_command(0x71)
        busy = epdconfig.digital_read(self.busy_pin)
        busy = not (busy & 0x01)
        while (busy):
            self.send_command(0x71)
            busy = epdconfig.digital_read(self.busy_pin)
            busy = not (busy & 0x01)
        epdconfig.delay_ms(800)
        logger.debug("e-Paper busy release")

    def TurnOnDisplay(self):
        self.send_command(0x12)
        epdconfig.delay_ms(10)
        self.ReadBusy()

    def SetFulltReg(self):
        self.send_command(0x23)
        for count in range(0, 42):
            self.send_data(self.lut_w1[count])

        self.send_command(0x24)
        for count in range(0, 42):
            self.send_data(self.lut_b1[count])

    def SetPartReg(self):
        self.send_command(0x23)
        for count in range(0, 42):
            self.send_data(self.lut_w[count])

        self.send_command(0x24)
        for count in range(0, 42):
            self.send_data(self.lut_b[count])

    def Init(self):
        if (epdconfig.module_init() != 0):
            return -1
        # EPD hardware init start
        self.reset()

        self.send_command(0xD2)
        self.send_data(0x3F)

        self.send_command(0x00)
        self.send_data(0x6F)  # from outside

        self.send_command(0x01)  # power setting
        self.send_data(0x03)
        self.send_data(0x00)
        self.send_data(0x2b)
        self.send_data(0x2b)

        self.send_command(0x06)  # Configuring the charge pump
        self.send_data(0x3f)

        self.send_command(0x2A)  # Setting XON and the options of LUT
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(0x30)  # Set the clock frequency
        self.send_data(0x17)  # 50Hz

        self.send_command(0x50)  # Set VCOM and data output interval
        self.send_data(0x57)

        self.send_command(0x60)  # Set The non-overlapping period of Gate and Source.
        self.send_data(0x22)

        self.send_command(0x61)  # resolution setting
        self.send_data(0x50)  # source 128
        self.send_data(0x80)

        self.send_command(0x82)  # sets VCOM_DC value
        self.send_data(0x12)  # -1v

        self.send_command(0xe3)  # Set POWER SAVING
        self.send_data(0x33)
        self.SetFulltReg()
        self.send_command(0x04)  # power on
        self.ReadBusy()
        # EPD hardware init end
        return 0

    def Partial_Init(self):
        self.reset()

        self.send_command(0xD2)
        self.send_data(0x3F)

        self.send_command(0x00)
        self.send_data(0x6F)  # from outside

        self.send_command(0x01)  # power setting
        self.send_data(0x03)
        self.send_data(0x00)
        self.send_data(0x2b)
        self.send_data(0x2b)

        self.send_command(0x06)  # Configuring the charge pump
        self.send_data(0x3f)

        self.send_command(0x2A)  # Setting XON and the options of LUT
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(0x30)  # Set the clock frequency
        self.send_data(0x17)

        self.send_command(0x50)  # Set VCOM and data output interval
        self.send_data(0xf2)

        self.send_command(0x60)  # Set The non-overlapping period of Gate and Source.
        self.send_data(0x22)

        self.send_command(0x82)  # Set VCOM_DC value
        self.send_data(0x12)  # -1v

        self.send_command(0xe3)  # Set POWER SAVING
        self.send_data(0x33)

        self.SetPartReg()

        self.send_command(0x04)  # Set POWER SAVING
        self.ReadBusy()
        # EPD hardware init end
        return 0

    def getbuffer(self, image):
        buf = [0xFF] * (int(self.width / 8) * self.height)
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()
        if (imwidth == self.width and imheight == self.height):
            logger.debug("Horizontal")
            for y in range(imheight):
                for x in range(imwidth):
                    # Set the bits for the column of pixels at the current position.
                    if pixels[x, y] == 0:
                        buf[int((x + y * self.width) / 8)] &= ~(0x80 >> (x % 8))
        elif (imwidth == self.height and imheight == self.width):
            logger.debug("Vertical")
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
        # Width = (self.width % 8 == 0)? (self.width / 8 ): (self.width / 8 + 1)
        if (self.width % 8 == 0):
            Width = self.width / 8
        else:
            Width = self.width / 8 + 1

        self.send_command(0x10)
        for j in range(0, self.height):
            for i in range(0, int(Width)):
                self.send_data(0xff)

        self.send_command(0x13)
        for j in range(0, self.height):
            for i in range(0, int(Width)):
                self.send_data(image[i + j * int(Width)])
        self.TurnOnDisplay()

    def Clear(self):
        # Width = (self.width % 8 == 0)? (self.width / 8 ): (self.width / 8 + 1)
        if (self.width % 8 == 0):
            Width = self.width / 8
        else:
            Width = self.width / 8 + 1

        Height = self.height

        self.send_command(0x10)
        for j in range(0, Height):
            for i in range(0, int(Width)):
                self.send_data(0x00)

        self.send_command(0x13)
        for j in range(0, Height):
            for i in range(0, int(Width)):
                self.send_data(0xff)
        self.TurnOnDisplay()

    def DisplayPartial(self, old_Image, Image):

        # Set partial Windows */
        self.send_command(0x91)  # This command makes the display enter partial mode
        self.send_command(0x90)  # resolution setting
        self.send_data(0)  # x-start
        self.send_data(79)  # x-end

        self.send_data(0)
        self.send_data(127)  # y-end
        self.send_data(0x00)

        # Width = (self.width % 8 == 0)? (self.width / 8 ): (self.width / 8 + 1)
        if (self.width % 8 == 0):
            Width = self.width / 8
        else:
            Width = self.width / 8 + 1

        Height = self.height
        # send data
        self.send_command(0x10)
        for j in range(0, Height):
            for i in range(0, int(Width)):
                self.send_data(old_Image[i + j * int(Width)])

        self.send_command(0x13)
        for j in range(0, Height):
            for i in range(0, int(Width)):
                self.send_data(Image[i + j * int(Width)])

        # Set partial refresh
        self.TurnOnDisplay()

    def Sleep(self):
        self.send_command(0x50)
        self.send_data(0xf7)
        self.send_command(0x02)
        self.ReadBusy()
        self.send_command(0x07)
        self.send_data(0xA5)
        epdconfig.delay_ms(200)

        epdconfig.delay_ms(2000)
        epdconfig.module_exit()

### END OF FILE ###
