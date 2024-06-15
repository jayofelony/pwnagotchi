# Based on UPS Lite v1.1 from https://github.com/xenDE

import logging
import time

from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.plugins as plugins
import pwnagotchi


class UPS:
    def __init__(self):
        # only import when the module is loaded and enabled
        import smbus
        # 0 = /dev/i2c-0 (port I2C0), 1 = /dev/i2c-1 (port I2C1)
        self._bus = smbus.SMBus(1)

    def voltage(self):
        try:
            low = self._bus.read_byte_data(0x57, 0x23)
            high = self._bus.read_byte_data(0x57, 0x22)
            v = (((high << 8) + low) / 1000)
            return v
        except:
            return 0.0

    def capacity(self):
        battery_level = 0
        # battery_v = self.voltage()
        try:
            battery_level = self._bus.read_byte_data(0x57, 0x2a)
            return battery_level
        except:
            return battery_level

    def status(self):
        stat02 = self._bus.read_byte_data(0x57, 0x02)
        stat03 = self._bus.read_byte_data(0x57, 0x03)
        stat04 = self._bus.read_byte_data(0x57, 0x04)
        return stat02, stat03, stat04


class PiSugar3(plugins.Plugin):
    __author__ = 'taiyonemo@protonmail.com'
    __editor__ = 'jayofelony'
    __version__ = '1.0.1'
    __license__ = 'GPL3'
    __description__ = 'A plugin that will add a percentage indicator for the PiSugar 3'

    def __init__(self):
        self.ups = None
        self.lasttemp = 69
        self.drot = 0  # display rotation
        self.nextDChg = 0  # last time display changed, rotate on updates after 5 seconds
        self.options = dict()

    def on_loaded(self):
        self.ups = UPS()
        logging.info("[PiSugar3] plugin loaded.")

    def on_ui_setup(self, ui):
        try:
            ui.add_element('bat', LabeledValue(color=BLACK, label='BAT', value='0%', position=(ui.width() / 2 + 10, 0),
                                               label_font=fonts.Bold, text_font=fonts.Medium))
        except Exception as err:
            logging.warning("[PiSugar3] setup err: %s" % repr(err))

    def on_unload(self, ui):
        try:
            with ui._lock:
                ui.remove_element('bat')
        except Exception as err:
            logging.warning("[PiSugar3] unload err: %s" % repr(err))

    def on_ui_update(self, ui):
        capacity = self.ups.capacity()
        voltage = self.ups.voltage()
        stats = self.ups.status()
        temp = stats[2] - 40
        if temp != self.lasttemp:
            logging.debug("[PiSugar3] (chg %X, info %X, temp %d)" % (stats[0], stats[1], temp))
            self.lasttemp = temp

        if stats[0] & 0x80:  # charging, or has power connected
            ui._state._state['bat'].label = "CHG"
        else:
            ui._state._state['bat'].label = "BAT"

        if time.time() > self.nextDChg:
            self.drot = (self.drot + 1) % 3
            self.nextDChg = time.time() + 5

        if self.drot == 0:  # show battery voltage
            ui.set('bat', "%2.2fv" % voltage)
        elif self.drot == 1:
            ui.set('bat', "%2i%%" % capacity)
        else:
            ui.set('bat', "%2i\xb0" % temp)

        if capacity <= self.options['shutdown']:
            logging.info('[PiSugar3] Empty battery (<= %s%%): shutting down' % self.options['shutdown'])
            ui.update(force=True, new_data={'status': 'Battery exhausted, bye ...'})
            pwnagotchi.shutdown()
