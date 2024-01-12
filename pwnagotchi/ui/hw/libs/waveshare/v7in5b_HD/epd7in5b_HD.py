# *****************************************************************************
# * | File        :	  epd7in5bc_HD.py
# * | Author      :   Waveshare team
# * | Function    :   Electronic paper driver
# * | Info        :
# *----------------
# * | This version:   V1.0
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
EPD_WIDTH = 880
EPD_HEIGHT = 528

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
        epdconfig.delay_ms(4)
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
        busy = epdconfig.digital_read(self.busy_pin)
        while (busy == 1):
            busy = epdconfig.digital_read(self.busy_pin)
        epdconfig.delay_ms(200)

    def init(self):
        if (epdconfig.module_init() != 0):
            return -1

        self.reset()

        self.send_command(0x12);  # SWRESET
        self.ReadBusy();  # waiting for the electronic paper IC to release the idle signal

        self.send_command(0x46);  # Auto Write RAM
        self.send_data(0xF7);
        self.ReadBusy();  # waiting for the electronic paper IC to release the idle signal

        self.send_command(0x47);  # Auto Write RAM
        self.send_data(0xF7);
        self.ReadBusy();  # waiting for the electronic paper IC to release the idle signal

        self.send_command(0x0C);  # Soft start setting
        self.send_data(0xAE);
        self.send_data(0xC7);
        self.send_data(0xC3);
        self.send_data(0xC0);
        self.send_data(0x40);

        self.send_command(0x01);  # Set MUX as 527
        self.send_data(0xAF);
        self.send_data(0x02);
        self.send_data(0x01);

        self.send_command(0x11);  # Data entry mode
        self.send_data(0x01);

        self.send_command(0x44);
        self.send_data(0x00);  # RAM x address start at 0
        self.send_data(0x00);
        self.send_data(0x6F);  # RAM x address end at 36Fh -> 879
        self.send_data(0x03);
        self.send_command(0x45);
        self.send_data(0xAF);  # RAM y address start at 20Fh;
        self.send_data(0x02);
        self.send_data(0x00);  # RAM y address end at 00h;
        self.send_data(0x00);

        self.send_command(0x3C);  # VBD
        self.send_data(0x01);  # LUT1, for white

        self.send_command(0x18);
        self.send_data(0X80);
        self.send_command(0x22);
        self.send_data(0XB1);  # Load Temperature and waveform setting.
        self.send_command(0x20);
        self.ReadBusy();  # waiting for the electronic paper IC to release the idle signal

        self.send_command(0x4E);
        self.send_data(0x00);
        self.send_data(0x00);
        self.send_command(0x4F);
        self.send_data(0xAF);
        self.send_data(0x02);

        return 0

    def getbuffer(self, image):
        # logger.debug("bufsiz = ",int(self.width/8) * self.height)
        buf = [0xFF] * (int(self.width / 8) * self.height)
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()
        logger.debug('imwidth = %d  imheight =  %d ', imwidth, imheight)
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

    def display(self, imageblack, imagered):
        self.send_command(0x4F);
        self.send_data(0xAf);

        self.send_command(0x24)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(imageblack[i]);

        self.send_command(0x26)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(~imagered[i]);

        self.send_command(0x22);
        self.send_data(0xC7);  # Load LUT from MCU(0x32)
        self.send_command(0x20);
        epdconfig.delay_ms(200);  # !!!The delay here is necessary, 200uS at least!!!
        self.ReadBusy();

    def Clear(self):
        self.send_command(0x4F);
        self.send_data(0xAf);

        self.send_command(0x24)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(0xff);

        self.send_command(0x26)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(0x00);

        self.send_command(0x22);
        self.send_data(0xC7);  # Load LUT from MCU(0x32)
        self.send_command(0x20);
        epdconfig.delay_ms(200);  # !!!The delay here is necessary, 200uS at least!!!
        self.ReadBusy();

    def sleep(self):
        self.send_command(0x10);  # deep sleep
        self.send_data(0x01);

        epdconfig.delay_ms(2000)
        epdconfig.module_exit()
### END OF FILE ###
