#!/usr/bin/python
# -*- coding:utf-8 -*-
# *****************************************************************************
# * | File        :	  epd4in01f.py
# * | Author      :   Waveshare team
# * | Function    :   Electronic paper driver
# * | Info        :
# *----------------
# * | This version:   V1.1
# * | Date        :   2022-08-10
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
EPD_HEIGHT = 400

logger = logging.getLogger(__name__)


class EPD:
    def __init__(self):
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin = epdconfig.DC_PIN
        self.busy_pin = epdconfig.BUSY_PIN
        self.cs_pin = epdconfig.CS_PIN
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT
        self.BLACK = 0x000000  # 0000  BGR
        self.WHITE = 0xffffff  # 0001
        self.GREEN = 0x00ff00  # 0010
        self.BLUE = 0xff0000  # 0011
        self.RED = 0x0000ff  # 0100
        self.YELLOW = 0x00ffff  # 0101
        self.ORANGE = 0x0080ff  # 0110

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

    def ReadBusyHigh(self):
        logger.debug("e-Paper busy")
        while (epdconfig.digital_read(self.busy_pin) == 0):  # 0: idle, 1: busy
            epdconfig.delay_ms(10)
        logger.debug("e-Paper busy release")

    def ReadBusyLow(self):
        logger.debug("e-Paper busy")
        while (epdconfig.digital_read(self.busy_pin) == 1):  # 0: idle, 1: busy
            epdconfig.delay_ms(10)
        logger.debug("e-Paper busy release")

    def init(self):
        if (epdconfig.module_init() != 0):
            return -1
        # EPD hardware init start
        self.reset()

        self.ReadBusyHigh()
        self.send_command(0x00)
        self.send_data(0x2f)
        self.send_data(0x00)
        self.send_command(0x01)
        self.send_data(0x37)
        self.send_data(0x00)
        self.send_data(0x05)
        self.send_data(0x05)
        self.send_command(0x03)
        self.send_data(0x00)
        self.send_command(0x06)
        self.send_data(0xC7)
        self.send_data(0xC7)
        self.send_data(0x1D)
        self.send_command(0x41)
        self.send_data(0x00)
        self.send_command(0x50)
        self.send_data(0x37)
        self.send_command(0x60)
        self.send_data(0x22)
        self.send_command(0x61)
        self.send_data(0x02)
        self.send_data(0x80)
        self.send_data(0x01)
        self.send_data(0x90)
        self.send_command(0xE3)
        self.send_data(0xAA)

        # EPD hardware init end
        return 0

    def getbuffer(self, image):
        buf = [0x00] * int(self.width * self.height / 2)
        image_monocolor = image.convert('RGB')  # Picture mode conversion
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()
        logger.debug('imwidth = %d  imheight =  %d ', imwidth, imheight)
        if (imwidth == self.width and imheight == self.height):
            for y in range(imheight):
                for x in range(imwidth):
                    # Set the bits for the column of pixels at the current position.
                    Add = int((x + y * self.width) / 2)
                    Color = 0;
                    if (pixels[x, y][0] == 0 and pixels[x, y][1] == 0 and pixels[x, y][2] == 0):
                        Color = 0
                    elif (pixels[x, y][0] == 255 and pixels[x, y][1] == 255 and pixels[x, y][2] == 255):
                        Color = 1
                    elif (pixels[x, y][0] == 0 and pixels[x, y][1] == 255 and pixels[x, y][2] == 0):
                        Color = 2
                    elif (pixels[x, y][0] == 0 and pixels[x, y][1] == 0 and pixels[x, y][2] == 255):
                        Color = 3
                    elif (pixels[x, y][0] == 255 and pixels[x, y][1] == 0 and pixels[x, y][2] == 0):
                        Color = 4
                    elif (pixels[x, y][0] == 255 and pixels[x, y][1] == 255 and pixels[x, y][2] == 0):
                        Color = 5
                    elif (pixels[x, y][0] == 255 and pixels[x, y][1] == 128 and pixels[x, y][2] == 0):
                        Color = 6

                    data_t = buf[Add] & (~(0xF0 >> ((x % 2) * 4)))
                    buf[Add] = data_t | ((Color << 4) >> ((x % 2) * 4));

        elif (imwidth == self.height and imheight == self.width):
            for y in range(imheight):
                for x in range(imwidth):
                    newx = y
                    newy = self.height - x - 1
                    Add = int((newx + newy * self.width) / 2)
                    Color = 0;
                    if (pixels[x, y][0] == 0 and pixels[x, y][1] == 0 and pixels[x, y][2] == 0):
                        Color = 0
                    elif (pixels[x, y][0] == 255 and pixels[x, y][1] == 255 and pixels[x, y][2] == 255):
                        Color = 1
                    elif (pixels[x, y][0] == 0 and pixels[x, y][1] == 255 and pixels[x, y][2] == 0):
                        Color = 2
                    elif (pixels[x, y][0] == 0 and pixels[x, y][1] == 0 and pixels[x, y][2] == 255):
                        Color = 3
                    elif (pixels[x, y][0] == 255 and pixels[x, y][1] == 0 and pixels[x, y][2] == 0):
                        Color = 4
                    elif (pixels[x, y][0] == 255 and pixels[x, y][1] == 255 and pixels[x, y][2] == 0):
                        Color = 5
                    elif (pixels[x, y][0] == 255 and pixels[x, y][1] == 128 and pixels[x, y][2] == 0):
                        Color = 6

                    data_t = buf[Add] & (~(0xF0 >> ((newx % 2) * 4)))
                    buf[Add] = data_t | ((Color << 4) >> ((newx % 2) * 4));
        return buf

    def display(self, image):
        self.send_command(0x61)  # Set Resolution setting
        self.send_data(0x02)
        self.send_data(0x80)
        self.send_data(0x01)
        self.send_data(0x90)
        self.send_command(0x10)
        self.send_data2(image)
        self.send_command(0x04)  # 0x04
        self.ReadBusyHigh()
        self.send_command(0x12)  # 0x12
        self.ReadBusyHigh()
        self.send_command(0x02)  # 0x02
        self.ReadBusyLow()
        # epdconfig.delay_ms(500)

    def Clear(self):
        self.send_command(0x61)  # Set Resolution setting
        self.send_data(0x02)
        self.send_data(0x80)
        self.send_data(0x01)
        self.send_data(0x90)
        self.send_command(0x10)
        self.send_data2([0x11] * int(EPD_HEIGHT) * int(EPD_WIDTH / 2))
        # BLACK   0x00    /// 0000
        # WHITE   0x11    /// 0001
        # GREEN   0x22    /// 0010
        # BLUE    0x33    /// 0011
        # RED     0x44    /// 0100
        # YELLOW  0x55    /// 0101
        # ORANGE  0x66    /// 0110
        # CLEAN   0x77    /// 0111   unavailable  Afterimage
        self.send_command(0x04)  # 0x04
        self.ReadBusyHigh()
        self.send_command(0x12)  # 0x12
        self.ReadBusyHigh()
        self.send_command(0x02)  # 0x02
        self.ReadBusyLow()
        # epdconfig.delay_ms(500)

    def sleep(self):
        # epdconfig.delay_ms(500)
        self.send_command(0x07)  # DEEP_SLEEP
        self.send_data(0XA5)

        epdconfig.delay_ms(2000)
        epdconfig.module_exit()
