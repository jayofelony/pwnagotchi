import logging
import pwnagotchi.ui.components as components
import pwnagotchi.ui.view as view
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.plugins as plugins
import pwnagotchi
import subprocess


class InternetConnectionPlugin(plugins.Plugin):
    __author__ = 'adi1708, edited by jayofelony'
    __version__ = '1.0.1'
    __license__ = 'GPL3'
    __description__ = 'A plugin that displays the Internet connection status on the pwnagotchi display.'
    __name__ = 'InternetConnectionPlugin'
    __help__ = """
    A plugin that displays the Internet connection status on the pwnagotchi display.
    """
    __dependencies__ = {
        'pip': ['scapy']
    }
    __defaults__ = {
        'enabled': False,
    }

    def on_loaded(self):
        logging.info("[Internet-Connection] plugin loaded.")

    def on_ui_setup(self, ui):
        with ui._lock:
            # add a LabeledValue element to the UI with the given label and value
            # the position and font can also be specified
            ui.add_element('connection_status', components.LabeledValue(color=view.BLACK, label='', value='',
                                                                        position=(0, 30), label_font=fonts.Small,
                                                                        text_font=fonts.Small))

    def on_ui_update(self, ui):
        # check if there is an active Internet connection
        try:
            # use the 'ping' command to check if we can reach a well-known website
            output = subprocess.check_output(['ping', '-c', '1', 'google.com'])
            # if the command was successful, it means there is an active Internet connection
            ui.set('connection_status', 'connected')
        except subprocess.CalledProcessError:
            # if the command failed, it means there is no active Internet connection
            ui.set('connection_status', 'disconnected')

    def on_unload(self, ui):
        with ui._lock:
            logging.info("[Internet-Connection] plugin unloaded")
            ui.remove_element('connection_status')
