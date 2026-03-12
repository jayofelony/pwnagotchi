from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.plugins as plugins
import logging
import time


class InternetConnectionPlugin(plugins.Plugin):
    __author__ = '@jayofelony'
    __version__ = '1.3.0'
    __license__ = 'GPL3'
    __description__ = 'A plugin that displays the Internet connection status on the pwnagotchi display.'
    __help__ = """
    A plugin that displays the Internet connection status on the pwnagotchi display.
    """

    def __init__(self):
        self.options = dict()
        self._last_seen = 0
        self._timeout = 120

    def on_loaded(self):
        self._timeout = self.options.get('timeout', 120)
        logging.info("[Internet-Connection] plugin loaded.")

    def on_config_changed(self, config):
        self.config = config

    def on_ui_setup(self, ui):
        try:
            pos = self.options['position']
            if isinstance(pos, str):
                pos = tuple(int(x.strip()) for x in pos.split(','))
        except Exception:
            pos = (ui.width() // 2 + 25, 0)
        with ui._lock:
            ui.add_element('connection_status', LabeledValue(color=BLACK, label='WWW', value='-',
                                                             position=pos,
                                                             label_font=fonts.Bold, text_font=fonts.Medium))

    def on_internet_available(self, agent):
        self._last_seen = time.time()
        display = agent.view()
        display.set('connection_status', 'C')
        logging.debug('[Internet-Connection] connected to the World Wide Web!')

    def on_ui_update(self, ui):
        if self._last_seen and time.time() - self._last_seen > self._timeout:
            ui.set('connection_status', '-')
            self._last_seen = 0

    def on_unload(self, ui):
        with ui._lock:
            logging.info("[Internet-Connection] plugin unloaded")
            ui.remove_element('connection_status')
