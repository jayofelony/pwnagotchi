import time
from pwnagotchi.ui.hw.libs.waveshare.lcd import lcdconfig

LCD_X = 2
LCD_Y = 1
LCD_X_MAXPIXEL = 128  # LCD width maximum memory
LCD_Y_MAXPIXEL = 160  # LCD height maximum memory

# scanning method
L2R_U2D = 1
L2R_D2U = 2
R2L_U2D = 3
R2L_D2U = 4
U2D_L2R = 5
U2D_R2L = 6
D2U_L2R = 7
D2U_R2L = 8
SCAN_DIR_DFT = U2D_R2L

LCD_WIDTH = 160
LCD_HEIGHT = 128


class LCD_1inch8(lcdconfig.RaspberryPi):
    LCD_Dis_Column = LCD_WIDTH
    LCD_Dis_Page = LCD_HEIGHT
    LCD_Scan_Dir = SCAN_DIR_DFT
    LCD_X_Adjust = LCD_X
    LCD_Y_Adjust = LCD_Y
    width = LCD_WIDTH
    height = LCD_HEIGHT

    def command(self, cmd):
        self.digital_write(self.DC_PIN, False)
        self.spi_writebyte([cmd])

    def data(self, val):
        self.digital_write(self.DC_PIN, True)
        self.spi_writebyte([val])

    def reset(self):
        """Reset the display"""
        self.digital_write(self.RST_PIN, True)
        time.sleep(0.01)
        self.digital_write(self.RST_PIN, False)
        time.sleep(0.01)
        self.digital_write(self.RST_PIN, True)
        time.sleep(0.01)

    def SetGramScanWay(self, Scan_dir):
        # Get the screen scan direction
        self.LCD_Scan_Dir = Scan_dir

        # Get GRAM and LCD width and height
        if (Scan_dir == L2R_U2D) or (Scan_dir == L2R_D2U) or (Scan_dir == R2L_U2D) or (Scan_dir == R2L_D2U):
            self.LCD_Dis_Column = LCD_HEIGHT
            self.LCD_Dis_Page = LCD_WIDTH
            self.LCD_X_Adjust = LCD_X
            self.LCD_Y_Adjust = LCD_Y
            if Scan_dir == L2R_U2D:
                MemoryAccessReg_Data = 0X00 | 0x00
            elif Scan_dir == L2R_D2U:
                MemoryAccessReg_Data = 0X00 | 0x80
            elif Scan_dir == R2L_U2D:
                MemoryAccessReg_Data = 0x40 | 0x00
            else:  # R2L_D2U:
                MemoryAccessReg_Data = 0x40 | 0x80
        else:
            self.LCD_Dis_Column = LCD_WIDTH
            self.LCD_Dis_Page = LCD_HEIGHT
            self.LCD_X_Adjust = LCD_Y
            self.LCD_Y_Adjust = LCD_X
            if Scan_dir == U2D_L2R:
                MemoryAccessReg_Data = 0X00 | 0x00 | 0x20
            elif Scan_dir == U2D_R2L:
                MemoryAccessReg_Data = 0X00 | 0x40 | 0x20
            elif Scan_dir == D2U_L2R:
                MemoryAccessReg_Data = 0x80 | 0x00 | 0x20
            else:  # R2L_D2U
                MemoryAccessReg_Data = 0x40 | 0x80 | 0x20

        # Set the read / write scan direction of the frame memory
        self.command(0x36)  # MX, MY, RGB mode
        self.data(MemoryAccessReg_Data & 0xf7)  # RGB color filter panel

    def Init_reg(self):
        """Initialize dispaly"""
        self.command(0xB1)
        self.data(0x01)
        self.data(0x2C)
        self.data(0x2D)

        self.command(0xB2)
        self.data(0x01)
        self.data(0x2C)
        self.data(0x2D)

        self.command(0xB3)
        self.data(0x01)
        self.data(0x2C)
        self.data(0x2D)
        self.data(0x01)
        self.data(0x2C)
        self.data(0x2D)

        # Column inversion
        self.command(0xB4)
        self.data(0x07)

        # ST7735R Power Sequence
        self.command(0xC0)
        self.data(0xA2)
        self.data(0x02)
        self.data(0x84)
        self.command(0xC1)
        self.data(0xC5)

        self.command(0xC2)
        self.data(0x0A)
        self.data(0x00)

        self.command(0xC3)
        self.data(0x8A)
        self.data(0x2A)
        self.command(0xC4)
        self.data(0x8A)
        self.data(0xEE)

        self.command(0xC5)  # VCOM
        self.data(0x0E)

        # ST7735R Gamma Sequence
        self.command(0xe0)
        self.data(0x0f)
        self.data(0x1a)
        self.data(0x0f)
        self.data(0x18)
        self.data(0x2f)
        self.data(0x28)
        self.data(0x20)
        self.data(0x22)
        self.data(0x1f)
        self.data(0x1b)
        self.data(0x23)
        self.data(0x37)
        self.data(0x00)
        self.data(0x07)
        self.data(0x02)
        self.data(0x10)

        self.command(0xe1)
        self.data(0x0f)
        self.data(0x1b)
        self.data(0x0f)
        self.data(0x17)
        self.data(0x33)
        self.data(0x2c)
        self.data(0x29)
        self.data(0x2e)
        self.data(0x30)
        self.data(0x30)
        self.data(0x39)
        self.data(0x3f)
        self.data(0x00)
        self.data(0x07)
        self.data(0x03)
        self.data(0x10)

        # Enable test command
        self.command(0xF0)
        self.data(0x01)

        # Disable ram power save mode
        self.command(0xF6)
        self.data(0x00)

        # 65k mode
        self.command(0x3A)
        self.data(0x05)

    def Init(self, Lcd_ScanDir=U2D_R2L):
        self.module_init()
        self.reset()

        # Set the initialization register
        self.Init_reg()

        # Set the display scan and color transfer modes
        self.SetGramScanWay(Lcd_ScanDir)
        self.delay_ms(200)

        # sleep out
        self.command(0x11)
        self.delay_ms(120)

        # Turn on the LCD display
        self.command(0x29)

        self.clear()

    def SetWindows(self, Xstart, Ystart, Xend, Yend):
        # set the X coordinates
        self.command(0x2A)
        self.data(0x00)  # Set the horizontal starting point to the high octet
        self.data((Xstart & 0xff) + self.LCD_X_Adjust)  # Set the horizontal starting point to the low octet
        self.data(0x00)  # Set the horizontal end to the high octet
        self.data(((Xend - 1) & 0xff) + self.LCD_X_Adjust)  # Set the horizontal end to the low octet

        # set the Y coordinates
        self.command(0x2B)
        self.data(0x00)
        self.data((Ystart & 0xff) + self.LCD_Y_Adjust)
        self.data(0x00)
        self.data(((Yend - 1) & 0xff) + self.LCD_Y_Adjust)

        self.command(0x2C)

    def clear(self, color=0XFFFF):
        _buffer = [color] * (self.LCD_Dis_Column * self.LCD_Dis_Page * 2)
        if (self.LCD_Scan_Dir == L2R_U2D) or (self.LCD_Scan_Dir == L2R_D2U) or (self.LCD_Scan_Dir == R2L_U2D) or (
                self.LCD_Scan_Dir == R2L_D2U):
            # self.LCD_SetArealColor(0,0, LCD_X_MAXPIXEL , LCD_Y_MAXPIXEL  , Color = color)#white
            self.SetWindows(0, 0, LCD_X_MAXPIXEL, LCD_Y_MAXPIXEL)
            self.digital_write(self.DC_PIN, True)
            for i in range(0, len(_buffer), 4096):
                self.spi_writebyte(_buffer[i:i + 4096])

        else:
            # self.LCD_SetArealColor(0,0, LCD_Y_MAXPIXEL , LCD_X_MAXPIXEL  , Color = color)#white
            self.SetWindows(0, 0, LCD_Y_MAXPIXEL, LCD_X_MAXPIXEL)
            self.digital_write(self.DC_PIN, True)
            for i in range(0, len(_buffer), 4096):
                self.spi_writebyte(_buffer[i:i + 4096])

    def ShowImage(self, Image):
        if (Image == None):
            return

        imwidth, imheight = Image.size
        if imwidth != self.width or imheight != self.height:
            raise ValueError('Image must be same dimensions as display \
                ({0}x{1}).'.format(self.width, self.height))
        img = self.np.asarray(Image)
        pix = self.np.zeros((self.height, self.width, 2), dtype=self.np.uint8)
        pix[..., [0]] = self.np.add(self.np.bitwise_and(img[..., [0]], 0xF8), self.np.right_shift(img[..., [1]], 5))
        pix[..., [1]] = self.np.add(self.np.bitwise_and(self.np.left_shift(img[..., [1]], 3), 0xE0),
                                    self.np.right_shift(img[..., [2]], 3))
        pix = pix.flatten().tolist()
        self.SetWindows(0, 0, self.width, self.height)
        self.digital_write(self.DC_PIN, True)
        for i in range(0, len(pix), 4096):
            self.spi_writebyte(pix[i:i + 4096])
        '''
        self.SetWindows ( Xstart, Ystart, self.LCD_Dis_Column , self.LCD_Dis_Page  )
        self.digital_write(self.DC_PIN,self.GPIO.HIGH)
        # Pixels = Image.load()
        img = np.asarray(Image)
        pix = np.zeros((Image.height,Image.width, 2), dtype = np.uint8)
        pix[...,[0]] = np.add(np.bitwise_and(img[...,[0]],0xF8),np.right_shift(img[...,[1]],5))
        pix[...,[1]] = np.add(np.bitwise_and(np.left_shift(img[...,[1]],3),0xE0), np.right_shift(img[...,[2]],3))
        pix = pix.flatten().tolist()
        self.digital_write(self.DC_PIN,self.GPIO.HIGH)
        for i in range(0,len(pix),4096):
            self.spi_writebyte(pix[i:i+4096])
        '''
