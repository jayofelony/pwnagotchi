# Witty Pi 4 L3V7
#
import logging
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK

class UPS:
    I2C_MC_ADDRESS = 0x08
    I2C_VOLTAGE_IN_I = 1
    I2C_VOLTAGE_IN_D = 2
    I2C_CURRENT_OUT_I = 5
    I2C_CURRENT_OUT_D = 6
    I2C_POWER_MODE = 7

    def __init__(self):
        # only import when the module is loaded and enabled
        import smbus
        # 0 = /dev/i2c-0 (port I2C0), 1 = /dev/i2c-1 (port I2C1)
        self._bus = smbus.SMBus(1)

    def voltage(self):
        try:
            i = self._bus.read_byte_data(self.I2C_MC_ADDRESS, self.I2C_VOLTAGE_IN_I)
            d = self._bus.read_byte_data(self.I2C_MC_ADDRESS, self.I2C_VOLTAGE_IN_D)
            return (i + d / 100)
        except Exception as e:
            logging.info(f"register={i} failed (exception={e})")
            return 0.0

    def current(self):
        try:
            i = self._bus.read_byte_data(self.I2C_MC_ADDRESS, self.I2C_CURRENT_OUT_I)
            d = self._bus.read_byte_data(self.I2C_MC_ADDRESS, self.I2C_CURRENT_OUT_D)
            return (i + d / 100)
        except Exception as e:
            logging.info(f"register={i} failed (exception={e})")
            return 0.0

    def capacity(self):
        voltage = max(3.1, min(self.voltage(), 4.2)) # Clamp voltage
        return round((voltage - 3.1) / (4.2 - 3.1) * 100)

    def charging(self):
        try:
            dc = self._bus.read_byte_data(self.I2C_MC_ADDRESS, self.I2C_POWER_MODE)
            return '+' if dc == 0 else '-'
        except:
            return '-'

class WittyPi(plugins.Plugin):
    __author__ = 'https://github.com/krishenriksen'
    __version__ = '1.0.0'
    __license__ = 'GPL3'
    __description__ = 'A plugin that will display battery info from Witty Pi 4 L3V7'

    def __init__(self):
        self.ups = None

    def on_loaded(self):
        self.ups = UPS()
        logging.info("wittypi plugin loaded.")

    def on_ui_setup(self, ui):
        ui.add_element('ups', LabeledValue(color=BLACK, label='UPS', value='0%', position=(ui.width() / 2 + 15, 0), label_font=fonts.Bold, text_font=fonts.Medium))

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element('ups')

    def on_ui_update(self, ui):
        capacity = self.ups.capacity()
        charging = self.ups.charging()
        ui.set('ups', "%2i%s" % (capacity, charging))
