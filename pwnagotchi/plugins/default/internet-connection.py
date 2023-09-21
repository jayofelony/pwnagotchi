import logging
import pwnagotchi.ui.components as components
import pwnagotchi.ui.view as view
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.plugins as plugins
import socket
import os


class InternetConnectionPlugin(plugins.Plugin):
    __author__ = 'adi1708, edited by jayofelony'
    __version__ = '1.2'
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
        'enabled': True,
    }

    def on_loaded(self):
        logging.info("[Internet-Connection] plugin loaded.")

    def on_ui_setup(self, ui):
        if ui.is_waveshare35lcd():
            v_pos = (180, 61)
            with ui._lock:
                ui.add_element('connection_ip', components.LabeledValue(color=view.BLACK, label='eth0:', value='',
                                                                        position=v_pos, label_font=fonts.Bold,
                                                                        text_font=fonts.Small))
        with ui._lock:
            # add a LabeledValue element to the UI with the given label and value
            # the position and font can also be specified
            ui.add_element('connection_status', components.LabeledValue(color=view.BLACK, label='WWW', value='-',
                                                                        position=(ui.width() / 2 - 35, 0),
                                                                        label_font=fonts.Bold, text_font=fonts.Medium))

    def on_ui_update(self, ui):
        if ui.is_wavehare35lcd():
            ip = os.popen('ifconfig eth0 | grep inet | awk \'{print $2}\'').read()
            ui.set('connection_ip', ip)
        # check if there is an active Internet connection
        try:
            # Connect to the host - tells us if the host is actually reachable
            socket.create_connection(("1.1.1.1", 80), 2).close()
            ui.set('connection_status', 'C')
        except TimeoutError as err:
            # if the command failed, it means there is no active Internet connection
            # we could log the error, but no need really
            # logging.error('[Internet-Connection] Socket creation failed: %s' % err)
            ui.set('connection_status', 'D')

    def on_unload(self, ui):
        with ui._lock:
            logging.info("[Internet-Connection] plugin unloaded")
            ui.remove_element('connection_status')
            if ui.is_waveshare35lcd():
                ui.remove_element('connection_ip')
