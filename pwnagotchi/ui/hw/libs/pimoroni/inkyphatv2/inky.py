"""Inky e-Ink Display Driver."""
import time
import struct

from . import eeprom

try:
    import numpy
except ImportError:
    raise ImportError('This library requires the numpy module\nInstall with: sudo apt install python-numpy')

# Display colour codes
WHITE = 0
BLACK = 1
RED = YELLOW = 2

# GPIO pins required by BCM number
RESET_PIN = 27
BUSY_PIN = 17
DC_PIN = 22

# In addition the following pins are used for SPI
# CS_PIN = 8
# MOSI_PIN = 10
# SCLK_PIN = 11
# SCLK_PIN = 11

# SPI channel for device 0
CS0 = 0

_SPI_CHUNK_SIZE = 4096
_SPI_COMMAND = 0
_SPI_DATA = 1

_RESOLUTION = {
    (800, 480): (800, 480, 0),
    (600, 448): (600, 448, 0),
    (400, 300): (400, 300, 0),
    (212, 104): (104, 212, -90),
    (250, 122): (250, 122, -90),
}


class Inky:
    """Inky e-Ink Display Driver.

    Generally it is more convenient to use either the :class:`inky.InkyPHAT` or :class:`inky.InkyWHAT` classes.
    """

    WHITE = 0
    BLACK = 1
    RED = 2
    YELLOW = 2

    def __init__(self, resolution=(400, 300), colour='black', cs_channel=CS0, dc_pin=DC_PIN, reset_pin=RESET_PIN, busy_pin=BUSY_PIN, h_flip=False, v_flip=False,
                 spi_bus=None, i2c_bus=None, gpio=None):
        """Initialise an Inky Display.

        :param resolution: Display resolution (width, height) in pixels, default: (400, 300).
        :type resolution: tuple(int, int)
        :param str colour: One of 'red', 'black' or 'yellow', default: 'black'.
        :param int cs_channel: Chip-select channel for SPI communication, default: `0`.
        :param int dc_pin: Data/command pin for SPI communication, default: `22`.
        :param int reset_pin: Device reset pin, default: `27`.
        :param int busy_pin: Device busy/wait pin: `17`.
        :param bool h_flip: Enable horizontal display flip, default: `False`.
        :param bool v_flip: Enable vertical display flip, default: `False`.
        :param spi_bus: SPI device. If `None` then a default :class:`spidev.SpiDev` object is used. Default: `None`.
        :type spi_bus: :class:`spidev.SpiDev`
        :param i2c_bus: SMB object. If `None` then :class:`smbus2.SMBus(1)` is used.
        :type i2c_bus: :class:`smbus2.SMBus`
        :param gpio: GPIO module. If `None` then `RPi.GPIO` is imported. Default: `None`.
        :type gpio: :class:`RPi.GPIO`
        """
        self._spi_bus = spi_bus
        self._i2c_bus = i2c_bus

        if resolution not in _RESOLUTION.keys():
            raise ValueError('Resolution {}x{} not supported!'.format(*resolution))

        self.resolution = resolution
        self.width, self.height = resolution
        self.cols, self.rows, self.rotation = _RESOLUTION[resolution]

        if colour not in ('red', 'black', 'yellow'):
            raise ValueError('Colour {} is not supported!'.format(colour))

        self.colour = colour
        self.eeprom = eeprom.read_eeprom(i2c_bus=i2c_bus)
        self.lut = colour

        if self.eeprom is not None:
            if self.eeprom.width != self.width or self.eeprom.height != self.height:
                raise ValueError('Supplied width/height do not match Inky: {}x{}'.format(self.eeprom.width, self.eeprom.height))
            if self.eeprom.display_variant in (1, 6) and self.eeprom.get_color() == 'red':
                self.lut = 'red_ht'

        self.buf = numpy.zeros((self.height, self.width), dtype=numpy.uint8)
        self.border_colour = 0

        self.dc_pin = dc_pin
        self.reset_pin = reset_pin
        self.busy_pin = busy_pin
        self.cs_channel = cs_channel
        self.h_flip = h_flip
        self.v_flip = v_flip

        self._gpio = gpio
        self._gpio_setup = False

        """Inky Lookup Tables.

        These lookup tables comprise of two sets of values.

        The first set of values, formatted as binary, describe the voltages applied during the six update phases:

          Phase 0     Phase 1     Phase 2     Phase 3     Phase 4     Phase 5     Phase 6
          A B C D
        0b01001000, 0b10100000, 0b00010000, 0b00010000, 0b00010011, 0b00000000, 0b00000000,  LUT0 - Black
        0b01001000, 0b10100000, 0b10000000, 0b00000000, 0b00000011, 0b00000000, 0b00000000,  LUT1 - White
        0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000,  NOT USED BY HARDWARE
        0b01001000, 0b10100101, 0b00000000, 0b10111011, 0b00000000, 0b00000000, 0b00000000,  LUT3 - Yellow or Red
        0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000,  LUT4 - VCOM

        There are seven possible phases, arranged horizontally, and only the phases with duration/repeat information
        (see below) are used during the update cycle.

        Each phase has four steps: A, B, C and D. Each step is represented by two binary bits and these bits can
        have one of four possible values representing the voltages to be applied. The default values follow:

        0b00: VSS or Ground
        0b01: VSH1 or 15V
        0b10: VSL or -15V
        0b11: VSH2 or 5.4V

        During each phase the Black, White and Yellow (or Red) stages are applied in turn, creating a voltage
        differential across each display pixel. This is what moves the physical ink particles in their suspension.

        The second set of values, formatted as hex, describe the duration of each step in a phase, and the number
        of times that phase should be repeated:

          Duration                Repeat
          A     B     C     D
        0x10, 0x04, 0x04, 0x04, 0x04,  <-- Timings for Phase 0
        0x10, 0x04, 0x04, 0x04, 0x04,  <-- Timings for Phase 1
        0x04, 0x08, 0x08, 0x10, 0x10,      etc
        0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00,

        The duration and repeat parameters allow you to take a single sequence of A, B, C and D voltage values and
        transform them into a waveform that - effectively - wiggles the ink particles into the desired position.

        In all of our LUT definitions we use the first and second phases to flash/pulse and clear the display to
        mitigate image retention. The flashing effect is actually the ink particles being moved from the bottom to
        the top of the display repeatedly in an attempt to reset them back into a sensible resting position.

        """
        self._luts = {
            'black': [
                0b01001000, 0b10100000, 0b00010000, 0b00010000, 0b00010011, 0b00000000, 0b00000000,
                0b01001000, 0b10100000, 0b10000000, 0b00000000, 0b00000011, 0b00000000, 0b00000000,
                0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000,
                0b01001000, 0b10100101, 0b00000000, 0b10111011, 0b00000000, 0b00000000, 0b00000000,
                0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000,
                0x10, 0x04, 0x04, 0x04, 0x04,
                0x10, 0x04, 0x04, 0x04, 0x04,
                0x04, 0x08, 0x08, 0x10, 0x10,
                0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00,
            ],
            'red': [
                0b01001000, 0b10100000, 0b00010000, 0b00010000, 0b00010011, 0b00000000, 0b00000000,
                0b01001000, 0b10100000, 0b10000000, 0b00000000, 0b00000011, 0b00000000, 0b00000000,
                0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000,
                0b01001000, 0b10100101, 0b00000000, 0b10111011, 0b00000000, 0b00000000, 0b00000000,
                0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000,
                0x40, 0x0C, 0x20, 0x0C, 0x06,
                0x10, 0x08, 0x04, 0x04, 0x06,
                0x04, 0x08, 0x08, 0x10, 0x10,
                0x02, 0x02, 0x02, 0x40, 0x20,
                0x02, 0x02, 0x02, 0x02, 0x02,
                0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00
            ],
            'red_ht': [
                0b01001000, 0b10100000, 0b00010000, 0b00010000, 0b00010011, 0b00010000, 0b00010000,
                0b01001000, 0b10100000, 0b10000000, 0b00000000, 0b00000011, 0b10000000, 0b10000000,
                0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000,
                0b01001000, 0b10100101, 0b00000000, 0b10111011, 0b00000000, 0b01001000, 0b00000000,
                0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000,
                0x43, 0x0A, 0x1F, 0x0A, 0x04,
                0x10, 0x08, 0x04, 0x04, 0x06,
                0x04, 0x08, 0x08, 0x10, 0x0B,
                0x02, 0x04, 0x04, 0x40, 0x10,
                0x06, 0x06, 0x06, 0x02, 0x02,
                0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00
            ],
            'yellow': [
                0b11111010, 0b10010100, 0b10001100, 0b11000000, 0b11010000, 0b00000000, 0b00000000,
                0b11111010, 0b10010100, 0b00101100, 0b10000000, 0b11100000, 0b00000000, 0b00000000,
                0b11111010, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000, 0b00000000,
                0b11111010, 0b10010100, 0b11111000, 0b10000000, 0b01010000, 0b00000000, 0b11001100,
                0b10111111, 0b01011000, 0b11111100, 0b10000000, 0b11010000, 0b00000000, 0b00010001,
                0x40, 0x10, 0x40, 0x10, 0x08,
                0x08, 0x10, 0x04, 0x04, 0x10,
                0x08, 0x08, 0x03, 0x08, 0x20,
                0x08, 0x04, 0x00, 0x00, 0x10,
                0x10, 0x08, 0x08, 0x00, 0x20,
                0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00,
            ]
        }

    def setup(self):
        """Set up Inky GPIO and reset display."""
        if not self._gpio_setup:
            if self._gpio is None:
                try:
                    import RPi.GPIO as GPIO
                    self._gpio = GPIO
                except ImportError:
                    raise ImportError('This library requires the RPi.GPIO module\nInstall with: sudo apt install python-rpi.gpio')
            self._gpio.setmode(self._gpio.BCM)
            self._gpio.setwarnings(False)
            self._gpio.setup(self.dc_pin, self._gpio.OUT, initial=self._gpio.LOW, pull_up_down=self._gpio.PUD_OFF)
            self._gpio.setup(self.reset_pin, self._gpio.OUT, initial=self._gpio.HIGH, pull_up_down=self._gpio.PUD_OFF)
            self._gpio.setup(self.busy_pin, self._gpio.IN, pull_up_down=self._gpio.PUD_OFF)

            if self._spi_bus is None:
                import spidev
                self._spi_bus = spidev.SpiDev()

            self._spi_bus.open(0, self.cs_channel)
            self._spi_bus.max_speed_hz = 488000

            self._gpio_setup = True

        self._gpio.output(self.reset_pin, self._gpio.LOW)
        time.sleep(0.1)
        self._gpio.output(self.reset_pin, self._gpio.HIGH)
        time.sleep(0.1)

        self._send_command(0x12)  # Soft Reset
        self._busy_wait()

    def _busy_wait(self):
        """Wait for busy/wait pin."""
        while self._gpio.input(self.busy_pin) != self._gpio.LOW:
            time.sleep(0.01)

    def _update(self, buf_a, buf_b, busy_wait=True):
        """Update display.

        :param buf_a: Black/White pixels
        :param buf_b: Yellow/Red pixels

        """
        self.setup()

        packed_height = list(struct.pack('<H', self.rows))

        if isinstance(packed_height[0], str):
            packed_height = map(ord, packed_height)

        self._send_command(0x74, 0x54)  # Set Analog Block Control
        self._send_command(0x7e, 0x3b)  # Set Digital Block Control

        self._send_command(0x01, packed_height + [0x00])  # Gate setting

        self._send_command(0x03, 0x17)  # Gate Driving Voltage
        self._send_command(0x04, [0x41, 0xAC, 0x32])  # Source Driving Voltage

        self._send_command(0x3a, 0x07)  # Dummy line period
        self._send_command(0x3b, 0x04)  # Gate line width
        self._send_command(0x11, 0x03)  # Data entry mode setting 0x03 = X/Y increment

        self._send_command(0x2c, 0x3c)  # VCOM Register, 0x3c = -1.5v?

        self._send_command(0x3c, 0b00000000)
        if self.border_colour == self.BLACK:
            self._send_command(0x3c, 0b00000000)  # GS Transition Define A + VSS + LUT0
        elif self.border_colour == self.RED and self.colour == 'red':
            self._send_command(0x3c, 0b01110011)  # Fix Level Define A + VSH2 + LUT3
        elif self.border_colour == self.YELLOW and self.colour == 'yellow':
            self._send_command(0x3c, 0b00110011)  # GS Transition Define A + VSH2 + LUT3
        elif self.border_colour == self.WHITE:
            self._send_command(0x3c, 0b00110001)  # GS Transition Define A + VSH2 + LUT1

        if self.colour == 'yellow':
            self._send_command(0x04, [0x07, 0xAC, 0x32])  # Set voltage of VSH and VSL
        if self.colour == 'red' and self.resolution == (400, 300):
            self._send_command(0x04, [0x30, 0xAC, 0x22])

        self._send_command(0x32, self._luts[self.lut])  # Set LUTs

        self._send_command(0x44, [0x00, (self.cols // 8) - 1])  # Set RAM X Start/End
        self._send_command(0x45, [0x00, 0x00] + packed_height)  # Set RAM Y Start/End

        # 0x24 == RAM B/W, 0x26 == RAM Red/Yellow/etc
        for data in ((0x24, buf_a), (0x26, buf_b)):
            cmd, buf = data
            self._send_command(0x4e, 0x00)  # Set RAM X Pointer Start
            self._send_command(0x4f, [0x00, 0x00])  # Set RAM Y Pointer Start
            self._send_command(cmd, buf)

        self._send_command(0x22, 0xC7)  # Display Update Sequence
        self._send_command(0x20)  # Trigger Display Update
        time.sleep(0.05)

        if busy_wait:
            self._busy_wait()
            self._send_command(0x10, 0x01)  # Enter Deep Sleep

    def set_pixel(self, x, y, v):
        """Set a single pixel on the buffer.

        :param int x: x position on display.
        :param int y: y position on display.
        :param int v: Colour to set, valid values are `inky.BLACK`, `inky.WHITE`, `inky.RED` and `inky.YELLOW`.
        """
        if v in (WHITE, BLACK, RED):
            self.buf[y][x] = v

    def show(self, busy_wait=True):
        """Show buffer on display.

        :param bool busy_wait: If True, wait for display update to finish before returning, default: `True`.
        """
        region = self.buf

        if self.v_flip:
            region = numpy.fliplr(region)

        if self.h_flip:
            region = numpy.flipud(region)

        if self.rotation:
            region = numpy.rot90(region, self.rotation // 90)

        buf_a = numpy.packbits(numpy.where(region == BLACK, 0, 1)).tolist()
        buf_b = numpy.packbits(numpy.where(region == RED, 1, 0)).tolist()

        self._update(buf_a, buf_b, busy_wait=busy_wait)

    def set_border(self, colour):
        """Set the border colour.

        :param int colour: The border colour. Valid values are `inky.BLACK`, `inky.WHITE`, `inky.RED` and `inky.YELLOW`.
        """
        if colour in (WHITE, BLACK, RED):
            self.border_colour = colour

    def set_image(self, image):
        """Copy an image to the buffer.

        The dimensions of `image` should match the dimensions of the display being used.

        :param image: Image to copy.
        :type image: :class:`PIL.Image.Image` or :class:`numpy.ndarray` or list
        """
        if self.rotation % 180 == 0:
            self.buf = numpy.array(image, dtype=numpy.uint8).reshape((self.width, self.height))
        else:
            self.buf = numpy.array(image, dtype=numpy.uint8).reshape((self.height, self.width))

    def _spi_write(self, dc, values):
        """Write values over SPI.

        :param dc: whether to write as data or command
        :param values: list of values to write
        """
        self._gpio.output(self.dc_pin, dc)
        try:
            self._spi_bus.xfer3(values)
        except AttributeError:
            for x in range(((len(values) - 1) // _SPI_CHUNK_SIZE) + 1):
                offset = x * _SPI_CHUNK_SIZE
                self._spi_bus.xfer(values[offset:offset + _SPI_CHUNK_SIZE])

    def _send_command(self, command, data=None):
        """Send command over SPI.

        :param command: command byte
        :param data: optional list of values

        """
        self._spi_write(_SPI_COMMAND, [command])
        if data is not None:
            self._send_data(data)

    def _send_data(self, data):
        """Send data over SPI.

        :param data: list of values

        """
        if isinstance(data, int):
            data = [data]
        self._spi_write(_SPI_DATA, data)