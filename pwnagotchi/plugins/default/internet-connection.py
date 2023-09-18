import logging
import pwnagotchi.ui.components as components
import pwnagotchi.ui.view as view
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.plugins as plugins
import pwnagotchi
import subprocess
import socket


class InternetConnectionPlugin(plugins.Plugin):
    __author__ = 'adi1708, edited by jayofelony'
    __version__ = '1.1'
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
            ui.add_element('connection_status', components.LabeledValue(color=view.BLACK, label='WWW', value='-',
                                                                        position=(ui.width() / 2 - 10, 0), label_font=fonts.Bold,
                                                                        text_font=fonts.Medium))

    def on_ui_update(self, ui):
        # check if there is an active Internet connection
        try:
            # See if we can resolve the host name - tells us if there is
            # A DNS listening
            host = socket.gethostbyname("1.1.1.1")
            # Connect to the host - tells us if the host is actually reachable
            s = socket.create_connection((host, 80), 2)
            s.close()
            ui.set('connection_status', 'C')
        except:
            # if the command failed, it means there is no active Internet connection
            ui.set('connection_status', 'D')

    def on_unload(self, ui):
        with ui._lock:
            logging.info("[Internet-Connection] plugin unloaded")
            ui.remove_element('connection_status')
