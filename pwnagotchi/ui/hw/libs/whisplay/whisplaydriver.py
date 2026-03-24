import RPi.GPIO as GPIO
import spidev
import time


class WhisPlayBoard:
    # LCD 参数
    LCD_WIDTH = 240
    LCD_HEIGHT = 280
    CornerHeight = 20  # 圆角高度占的像素
    DC_PIN = 13
    RST_PIN = 7
    LED_PIN = 15

    # RGB LED 引脚
    RED_PIN = 22
    GREEN_PIN = 18
    BLUE_PIN = 16

    # 按键引脚
    BUTTON_PIN = 11

    def __init__(self):
        self._gpio_initialized = False

        try:
            GPIO.setmode(GPIO.BOARD)
            self._gpio_initialized = True
        except RuntimeError as e:
            # GPIO mode already set, continue
            print(f"GPIO.setmode warning: {e}")
            self._gpio_initialized = True
        except Exception as e:
            print(f"GPIO initialization failed: {e}. Display will run in limited mode.")
            self._gpio_initialized = False

        GPIO.setwarnings(False)

        # 初始化 LCD 引脚
        if self._gpio_initialized:
            try:
                GPIO.setup([self.DC_PIN, self.RST_PIN, self.LED_PIN], GPIO.OUT)
            except Exception as e:
                # Pins might already be set up or GPIO access denied
                print(f"Warning: LCD GPIO setup failed: {e}")
                self._gpio_initialized = False

        if self._gpio_initialized:
            try:
                GPIO.output(self.LED_PIN, GPIO.LOW)  # 使能背光
            except Exception as e:
                print(f"Warning: Could not set LED output: {e}")

        # 初始化 RGB LED 引脚
        if self._gpio_initialized:
            try:
                GPIO.setup([self.RED_PIN, self.GREEN_PIN, self.BLUE_PIN], GPIO.OUT)
                self.red_pwm = GPIO.PWM(self.RED_PIN, 100)
                self.green_pwm = GPIO.PWM(self.GREEN_PIN, 100)
                self.blue_pwm = GPIO.PWM(self.BLUE_PIN, 100)
                self._current_r = 0
                self._current_g = 0
                self._current_b = 0
                self.red_pwm.start(0)
                self.green_pwm.start(0)
                self.blue_pwm.start(0)
            except Exception as e:
                print(f"Warning: RGB LED setup failed: {e}")
                self.red_pwm = None
                self.green_pwm = None
                self.blue_pwm = None
        else:
            self.red_pwm = None
            self.green_pwm = None
            self.blue_pwm = None

        self.backlight_pwm = None

        # 初始化按键
        if self._gpio_initialized:
            try:
                GPIO.setup(self.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                self.button_press_callback = None
                self.button_release_callback = None
                GPIO.add_event_detect(
                    self.BUTTON_PIN, GPIO.BOTH, callback=self._button_event, bouncetime=50
                )
            except Exception as e:
                print(f"Warning: Button setup failed: {e}")
                self.button_press_callback = None
                self.button_release_callback = None
        else:
            self.button_press_callback = None
            self.button_release_callback = None

        # 初始化 SPI
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 100_000_000
        self.spi.mode = 0b00

        self.previous_frame = None
        # 检测硬件版本并设置背光模式
        self._detect_hardware_version()
        self._detect_wm8960()

        # Initialize offset attributes for compatibility
        self._offset_left = 0
        self._offset_top = 0

        # Only initialize display if GPIO was successfully set up
        if self._gpio_initialized:
            try:
                self.set_backlight(0)
                self._reset_lcd()
                self._init_display()
                self.fill_screen(0)
            except Exception as e:
                print(f"Warning: Display initialization failed: {e}")
        else:
            print("Warning: GPIO not available, skipping display initialization. SPI will be attempted directly.")

    def _detect_hardware_version(self):
        """
        检测树莓派硬件版本，并根据版本设置背光模式
        """
        try:
            with open("/proc/cpuinfo", "r") as f:
                lines = f.readlines()
                model_name = None
                for line in lines:
                    if line.startswith("Model"):
                        model_name = line.strip().split(":")[1].strip()
                        break
                if model_name:
                    if "Zero" in model_name and "2" not in model_name:
                        # 如果是 Zero 或 Zero W
                        self.backlight_mode = False  # 使用简单开关模式
                    else:
                        # 其他型号（如 Zero 2 W, 3B, 4B 等）
                        self.backlight_mode = True  # 使用 PWM 模式
                    print(
                        f"Detected hardware: {model_name}, Backlight mode: {'PWM' if self.backlight_mode else 'Simple Switch'}")
                else:
                    print("Model name not found in /proc/cpuinfo")
                    self.backlight_mode = True  # 默认使用 PWM 模式
        except Exception as e:
            print(f"Error detecting hardware version: {e}")
            self.backlight_mode = True  # 默认使用 PWM 模式

    def _detect_wm8960(self):
        """
        检测是否存在名字包含 wm8960 的声卡
        """
        try:
            with open("/proc/asound/cards", "r") as f:
                lines = f.readlines()
                for line in lines:
                    if "wm8960" in line.lower():
                        print("wm8960 sound card detected.")
                        return True
        except Exception as e:
            print(f"Error detecting wm8960 sound card: {e}")
            return False

        print("wm8960 sound card driver is installed. Please refer to the following page for installation instructions.")
        print("https://docs.pisugar.com/")
        return False

    # ========== 背光控制 ==========
    def set_backlight(self, brightness):
        if not self._gpio_initialized:
            return

        if self.backlight_mode:  # 如果是 PWM 模式
            if self.backlight_pwm is None:
                try:
                    self.backlight_pwm = GPIO.PWM(self.LED_PIN, 1000)
                    self.backlight_pwm.start(100)
                except Exception as e:
                    print(f"Warning: Could not create backlight PWM: {e}")
                    return
            if 0 <= brightness <= 100:
                try:
                    duty_cycle = 100 - brightness
                    self.backlight_pwm.ChangeDutyCycle(duty_cycle)
                except Exception as e:
                    print(f"Warning: Could not set backlight: {e}")
        else:  # 如果是简单开关模式
            try:
                if brightness == 0:
                    GPIO.output(self.LED_PIN, GPIO.HIGH)  # 关闭背光
                else:
                    GPIO.output(self.LED_PIN, GPIO.LOW)  # 打开背光
            except Exception as e:
                print(f"Warning: Could not control backlight: {e}")

    def set_backlight_mode(self, mode):
        """
        设置背光模式
        :param mode: True 使用 PWM 调节亮度，False 使用简单开关控制
        """
        if mode == self.backlight_mode:
            return  # 模式未改变，无需操作

        if mode:  # 切换到 PWM 模式
            self.backlight_pwm = GPIO.PWM(self.LED_PIN, 1000)
            self.backlight_pwm.start(100)
        else:  # 切换到简单开关模式
            if self.backlight_pwm is not None:
                self.backlight_pwm.stop()
                self.backlight_pwm = None
            GPIO.output(self.LED_PIN, GPIO.HIGH)  # 确保背光打开
        self.backlight_mode = mode

    def _reset_lcd(self):
        if not self._gpio_initialized:
            print("Warning: Cannot reset LCD - GPIO not initialized")
            return
        try:
            GPIO.output(self.RST_PIN, GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(self.RST_PIN, GPIO.LOW)
            time.sleep(0.1)
            GPIO.output(self.RST_PIN, GPIO.HIGH)
            time.sleep(0.12)
        except Exception as e:
            print(f"Warning: LCD reset failed: {e}")

    def _init_display(self):
        self._send_command(0x11)
        time.sleep(0.12)
        USE_HORIZONTAL = 1
        direction = {0: 0x00, 1: 0xC0, 2: 0x70,
                     3: 0xA0}.get(USE_HORIZONTAL, 0x00)
        self._send_command(0x36, direction)
        self._send_command(0x3A, 0x05)
        self._send_command(0xB2, 0x0C, 0x0C, 0x00, 0x33, 0x33)
        self._send_command(0xB7, 0x35)
        self._send_command(0xBB, 0x32)
        self._send_command(0xC2, 0x01)
        self._send_command(0xC3, 0x15)
        self._send_command(0xC4, 0x20)
        self._send_command(0xC6, 0x0F)
        self._send_command(0xD0, 0xA4, 0xA1)
        self._send_command(
            0xE0,
            0xD0,
            0x08,
            0x0E,
            0x09,
            0x09,
            0x05,
            0x31,
            0x33,
            0x48,
            0x17,
            0x14,
            0x15,
            0x31,
            0x34,
        )
        self._send_command(
            0xE1,
            0xD0,
            0x08,
            0x0E,
            0x09,
            0x09,
            0x15,
            0x31,
            0x33,
            0x48,
            0x17,
            0x14,
            0x15,
            0x31,
            0x34,
        )
        self._send_command(0x21)
        self._send_command(0x29)

    def _send_command(self, cmd, *args):
        GPIO.output(self.DC_PIN, GPIO.LOW)
        self.spi.xfer2([cmd])
        if args:
            GPIO.output(self.DC_PIN, GPIO.HIGH)
            self._send_data(list(args))

    def _send_data(self, data):
        GPIO.output(self.DC_PIN, GPIO.HIGH)

        try:

            self.spi.writebytes2(data)
        except AttributeError:
            max_chunk = 4096
            for i in range(0, len(data), max_chunk):
                self.spi.writebytes(data[i : i + max_chunk])

    def set_window(self, x0, y0, x1, y1, use_horizontal=0):
        if use_horizontal in (0, 1):
            self._send_command(0x2A, x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)
            self._send_command(
                0x2B, (y0 + 20) >> 8, (y0 + 20) & 0xFF, (y1 +
                                                         20) >> 8, (y1 + 20) & 0xFF
            )
        elif use_horizontal in (2, 3):
            self._send_command(
                0x2A, (x0 + 20) >> 8, (x0 + 20) & 0xFF, (x1 +
                                                         20) >> 8, (x1 + 20) & 0xFF
            )
            self._send_command(0x2B, y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)
        self._send_command(0x2C)

    def draw_pixel(self, x, y, color):
        if x >= self.LCD_WIDTH or y >= self.LCD_HEIGHT:
            return
        self.set_window(x, y, x, y)
        self._send_data([(color >> 8) & 0xFF, color & 0xFF])

    def draw_line(self, x0, y0, x1, y1, color):
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        while True:
            self.draw_pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def fill_screen(self, color):
        self.set_window(0, 0, self.LCD_WIDTH - 1, self.LCD_HEIGHT - 1)
        buffer = []
        high = (color >> 8) & 0xFF
        low = color & 0xFF
        for _ in range(self.LCD_WIDTH * self.LCD_HEIGHT):
            buffer.extend([high, low])
        self._send_data(buffer)

    def draw_image(self, x, y, width, height, pixel_data):
        if (x + width > self.LCD_WIDTH) or (y + height > self.LCD_HEIGHT):
            raise ValueError("图像尺寸超出屏幕范围")
        self.set_window(x, y, x + width - 1, y + height - 1)
        self._send_data(pixel_data)

    # ========== RGB 与按键 ==========
    def set_rgb(self, r, g, b):
        if self.red_pwm is None or self.green_pwm is None or self.blue_pwm is None:
            return
        try:
            self.red_pwm.ChangeDutyCycle(100 - (r / 255 * 100))
            self.green_pwm.ChangeDutyCycle(100 - (g / 255 * 100))
            self.blue_pwm.ChangeDutyCycle(100 - (b / 255 * 100))
            self._current_r = r
            self._current_g = g
            self._current_b = b
        except Exception as e:
            print(f"Warning: Could not set RGB: {e}")

    def set_rgb_fade(self, r_target, g_target, b_target, duration_ms=100):
        steps = 20  # 可以调整步数来控制渐变的平滑度
        delay_ms = duration_ms / steps

        r_step = (r_target - self._current_r) / steps
        g_step = (g_target - self._current_g) / steps
        b_step = (b_target - self._current_b) / steps

        for _ in range(steps + 1):
            r_interim = int(self._current_r + _ * r_step)
            g_interim = int(self._current_g + _ * g_step)
            b_interim = int(self._current_b + _ * b_step)
            self.set_rgb(
                max(0, min(255, r_interim)),
                max(0, min(255, g_interim)),
                max(0, min(255, b_interim)),
            )
            time.sleep(delay_ms / 1000.0)

    def button_pressed(self):
        return GPIO.input(self.BUTTON_PIN) == 1

    def on_button_press(self, callback):
        self.button_press_callback = callback

    def on_button_release(self, callback):
        self.button_release_callback = callback

    def _button_release_event(self, channel):
        if self.button_release_callback:
            self.button_release_callback()

    def _button_press_event(self, channel):
        if self.button_press_callback:
            self.button_press_callback()

    def _button_event(self, channel):
        # 按下是5V，松开是0V
        if not self._gpio_initialized:
            return
        try:
            if GPIO.input(channel):
                # Falling edge (按钮按下)
                self._button_press_event(channel)
            else:
                # Rising edge (按钮释放)
                self._button_release_event(channel)
        except Exception as e:
            print(f"Warning: Button event error: {e}")

    # ========== 清理 ==========
    def cleanup(self):
        # 清理代码中添加对 backlight_pwm 的处理
        if self.backlight_pwm is not None:
            self.backlight_pwm.stop()
        self.spi.close()
        self.red_pwm.stop()
        self.green_pwm.stop()
        self.blue_pwm.stop()
        GPIO.cleanup()