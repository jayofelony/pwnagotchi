# This is a customized version of the builtin Pwnagotchi Memtemp plugin which
# includes the changes from https://github.com/evilsocket/pwnagotchi/pull/918
# but tweaked further to better fit my specific requirements.
#
# Author: https://github.com/xenDE
# Contributors: spees <speeskonijn@gmail.com>, crahan@n00.be

#Edits by discord@rai68 - allows all 4 status - tested only on wave 2.13 v3

import logging
import pwnagotchi
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue, Text
from pwnagotchi.ui.view import BLACK


class MemTempPlus(plugins.Plugin):
    __author__ = 'https://github.com/xenDE'
    __version__ = '1.0.2-1'
    __license__ = 'GPL3'
    __description__ = 'A plugin that will display memory/cpu usage and temperature'

    ALLOWED_FIELDS = {
        'mem': 'mem_usage',
        'cpu': 'cpu_load',
        'temp': 'cpu_temp',
        'freq': 'cpu_freq',
    }
    DEFAULT_FIELDS = ['mem', 'cpu', 'temp','freq'] #enables 4 by default
    LINE_SPACING = 12
    LABEL_SPACING = 0
    FIELD_WIDTH = 4

    def on_loaded(self):
        logging.info('memtemp plugin loaded.')

    def mem_usage(self):
        return f'{int(pwnagotchi.mem_usage() * 100)}%'

    def cpu_load(self):
        return f'{int(pwnagotchi.cpu_load() * 100)}%'

    def cpu_temp(self):
        if self.options['scale'].lower() == 'fahrenheit':
            temp = (pwnagotchi.temperature() * 9 / 5) + 32
            symbol = 'F'
        elif self.options['scale'].lower() == 'kelvin':
            temp = pwnagotchi.temperature() + 273.15
            symbol = 'K'
        else:
            # default to celsius
            temp = pwnagotchi.temperature()
            symbol = 'C'
        return f'{temp}{symbol}'

    def cpu_freq(self):
        with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq', 'rt') as fp:
            return f'{round(float(fp.readline()) / 1000000, 1)}G'

    def pad_text(self, data):
        return ' ' * (self.FIELD_WIDTH - len(data)) + data

    def on_ui_setup(self, ui):
        try:
            # Configure field list
            self.fields = self.options['fields'].split(',')
            self.fields = [x.strip() for x in self.fields if x.strip() in self.ALLOWED_FIELDS.keys()]
            self.fields = self.fields[:4]  # CHANGED to limit to the first 4 fields
        except Exception:
            # Set default value
            self.fields = self.DEFAULT_FIELDS

        try:
            # Configure line_spacing
            line_spacing = int(self.options['linespacing'])
        except Exception:
            # Set default value
            line_spacing = self.LINE_SPACING

        try:
            # Configure position
            pos = self.options['position'].split(',')
            pos = [int(x.strip()) for x in pos]
            v_pos = (pos[0], pos[1])
            h_pos = v_pos
        except Exception:
            # Set position based on screen type
            if ui.is_waveshare_v2():
                v_pos = (197, 70)
                h_pos = (178, 80)
            else:
                v_pos = (175, 50)
                h_pos = (155, 60)

        if self.options['orientation'] == 'vertical':
            # Dynamically create the required LabeledValue objects
            for idx, field in enumerate(self.fields):
                v_pos_x = v_pos[0]
                v_pos_y = v_pos[1] + ((len(self.fields) - 3) * -1 * line_spacing)
                ui.add_element(
                    f'memtemp_{field}',
                    LabeledValue(
                        color=BLACK,
                        label=f'{self.pad_text(field)}:',
                        value='-',
                        position=(v_pos_x, v_pos_y + (idx * line_spacing)),
                        label_font=fonts.Small,
                        text_font=fonts.Small,
                        label_spacing=self.LABEL_SPACING,
                    )
                )
        else:
            # default to horizontal
            h_pos_x = h_pos[0] + ((len(self.fields) - 3) * -1 * 25)
            h_pos_y = h_pos[1]
            ui.add_element(
                'memtemp_header',
                Text(
                    color=BLACK,
                    value=' '.join([self.pad_text(x) for x in self.fields]),
                    position=(h_pos_x, h_pos_y),
                    font=fonts.Small,
                )
            )
            ui.add_element(
                'memtemp_data',
                Text(
                    color=BLACK,
                    value=' '.join([self.pad_text('-') for x in self.fields]),
                    position=(h_pos_x, h_pos_y + line_spacing),
                    font=fonts.Small,
                )
            )

    def on_unload(self, ui):
        with ui._lock:
            if self.options['orientation'] == 'vertical':
                for idx, field in enumerate(self.fields):
                    ui.remove_element(f'memtemp_{field}')
            else:
                # default to horizontal
                ui.remove_element('memtemp_header')
                ui.remove_element('memtemp_data')

    def on_ui_update(self, ui):
        if self.options['orientation'] == 'vertical':
            for idx, field in enumerate(self.fields):
                ui.set(f'memtemp_{field}', getattr(self, self.ALLOWED_FIELDS[field])())
        else:
            # default to horizontal
            data = ' '.join([self.pad_text(getattr(self, self.ALLOWED_FIELDS[x])()) for x in self.fields])
            ui.set('memtemp_data', data)
