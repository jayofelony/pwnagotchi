import os
import json
import logging

import pwnagotchi
import pwnagotchi.plugins as plugins
import pwnagotchi.ui.faces as faces
import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK


class Age(plugins.Plugin):
    __author__ = 'HannaDiamond'
    __version__ = '1.0.1'
    __license__ = 'MIT'
    __description__ = 'A plugin that will add age and strength stats based on epochs and trained epochs'

    def __init__(self):
        self.epochs = 0
        self.train_epochs = 0

    def on_loaded(self):
        data_path = '/root/brain.json'
        self.load_data(data_path)


    def on_ui_setup(self, ui):
        ui.add_element('Age', LabeledValue(color=BLACK, label='♥ Age', value=0,
                                           position=(int(self.options["age_x_coord"]),
                                                     int(self.options["age_y_coord"])),
                                           label_font=fonts.Bold, text_font=fonts.Medium))
        ui.add_element('Strength', LabeledValue(color=BLACK, label='Str', value=0,
                                                position=(int(self.options["str_x_coord"]),
                                                          int(self.options["str_y_coord"])),
                                                label_font=fonts.Bold, text_font=fonts.Medium))

    def on_unload(self, ui):
        with ui._lock:
            ui.remove_element('Age')
            ui.remove_element('Strength')

    def on_ui_update(self, ui):
        ui.set('Age', str(self.abrev_number(self.epochs)))
        ui.set('Strength', str(self.abrev_number(self.train_epochs)))


    def on_ai_training_step(self, agent, _locals, _globals):
        self.train_epochs += 1
        if self.train_epochs % 100 == 0:
            self.strength_checkpoint(agent)

    def on_epoch(self, agent, epoch, epoch_data):
        self.epochs += 1
        if self.epochs % 100 == 0:
            self.age_checkpoint(agent)

    def abrev_number(self, num):
        if num < 100000:
            return str(num)
        else:
            magnitude = 0
            while abs(num) >= 1000:
                magnitude += 1
                num /= 1000.0
                abbr = ['', 'K', 'M', 'B', 'T', 'P'][magnitude]
            return '{}{}'.format('{:.2f}'.format(num).rstrip('0').rstrip('.'), abbr)

    def age_checkpoint(self, agent):
        view = agent.view()
        view.set('face', faces.HAPPY)
        view.set('status', "Wow, I've lived for " + str(self.abrev_number(self.epochs)) + " epochs!")
        view.update(force=True)

    def strength_checkpoint(self, agent):
        view = agent.view()
        view.set('face', faces.MOTIVATED)
        view.set('status', "Look at my strength go up! \n"
                           "I've trained for " + str(self.abrev_number(self.train_epochs)) + " epochs")
        view.update(force=True)

    def load_data(self, data_path):
        if os.path.exists(data_path):
            with open(data_path) as f:
                data = json.load(f)
                self.epochs = data['epochs_lived']
                self.train_epochs = data['epochs_trained']

