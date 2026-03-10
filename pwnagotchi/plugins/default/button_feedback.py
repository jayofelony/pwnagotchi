import os
import time
import logging
import pwnagotchi.plugins as plugins


class ButtonFeedback(plugins.Plugin):
    __author__ = 'CoderFX'
    __version__ = '1.0.0'
    __license__ = 'GPL3'
    __description__ = 'Shows a temporary status message on the display when an external script writes to a message file. Works with PiSugar buttons, GPIO buttons, or any shell trigger.'

    def __init__(self):
        self.options = dict()
        self._showing = False
        self._msg = None
        self._msg_shown_at = 0

    def on_loaded(self):
        self._message_file = self.options.get('message_file', '/tmp/.pwnagotchi-button-msg')
        self._display_seconds = self.options.get('display_seconds', 5)
        logging.info('[button_feedback] plugin loaded (file=%s, duration=%ds)',
                     self._message_file, self._display_seconds)

    def on_ui_update(self, ui):
        try:
            if os.path.exists(self._message_file):
                if not self._showing:
                    with open(self._message_file, 'r') as f:
                        self._msg = f.read().strip()
                    if self._msg:
                        self._showing = True
                        self._msg_shown_at = time.time()

                if self._showing:
                    if time.time() - self._msg_shown_at < self._display_seconds:
                        ui.set('status', self._msg)
                    else:
                        try:
                            os.remove(self._message_file)
                        except OSError:
                            pass
                        self._showing = False
                        self._msg = None
            else:
                if self._showing:
                    self._showing = False
                    self._msg = None
        except Exception as e:
            logging.debug('[button_feedback] %s', e)
