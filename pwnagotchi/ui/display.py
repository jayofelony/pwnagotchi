import os
import logging
import threading

import pwnagotchi.plugins as plugins
import pwnagotchi.ui.hw as hw
from pwnagotchi.ui.view import View


class Display(View):
    def __init__(self, config, state={}):
        super(Display, self).__init__(config, hw.display_for(config), state)
        config = config['ui']['display']

        self._enabled = config['enabled']
        self._rotation = config['rotation']

        self.init_display()

        self._canvas_next_event = threading.Event()
        self._canvas_next = None
        self._render_thread_instance = threading.Thread(
            target=self._render_thread,
            daemon=True
        )
        self._render_thread_instance.start()

    def is_lcdhat(self):
        return self._implementation.name == 'lcdhat'

    def is_waveshare144lcd(self):
        return self._implementation.name == 'waveshare144lcd'

    def is_oledhat(self):
        return self._implementation.name == 'oledhat'

    def is_waveshare1in02(self):
        return self._implementation.name == 'waveshare1in02'

    def is_waveshare1in54(self):
        return self._implementation.name == 'waveshare1in54'

    def is_waveshare1in54V2(self):
        return self._implementation.name == 'waveshare1in54_v2'

    def is_waveshare1in54b(self):
        return self._implementation.name == 'waveshare1in54b'

    def is_waveshare1in54bV22(self):
        return self._implementation.name == 'waveshare1in54b_v2'

    def is_waveshare1in54c(self):
        return self._implementation.name == 'waveshare1in54c'

    def is_waveshare1in64g(self):
        return self._implementation.name == 'waveshare1in64g'

    def is_waveshare2in7(self):
        return self._implementation.name == 'waveshare2in7'

    def is_waveshare2in7V2(self):
        return self._implementation.name == 'waveshare2in7_v2'

    def is_waveshare2in9(self):
        return self._implementation.name == 'waveshare2in9'

    def is_waveshare2in9V2(self):
        return self._implementation.name == 'waveshare2in9_v2'

    def is_waveshare2in9bV3(self):
        return self._implementation.name == 'waveshare2in9b_v3'

    def is_waveshare2in9bV4(self):
        return self._implementation.name == 'waveshare2in9b_v4'

    def is_waveshare2in9bc(self):
        return self._implementation.name == 'waveshare2in9bc'

    def is_waveshare2in9d(self):
        return self._implementation.name == 'waveshare2in9d'

    def is_waveshare_v1(self):
        return self._implementation.name == 'waveshare_1'

    def is_waveshare_v2(self):
        return self._implementation.name == 'waveshare_2'

    def is_waveshare_v3(self):
        return self._implementation.name == 'waveshare_3'

    def is_waveshare_v4(self):
        return self._implementation.name == 'waveshare_4'

    def is_waveshare2in13b_v3(self):
        return self._implementation.name == 'waveshare2in13b_v3'

    def is_waveshare2in13b_v4(self):
        return self._implementation.name == 'waveshare2in13b_v4'

    def is_waveshare2in13bc(self):
        return self._implementation.name == 'waveshare2in13bc'

    def is_waveshare2in13d(self):
        return self._implementation.name == 'waveshare2in13d'

    def is_waveshare2in23g(self):
        return self._implementation.name == 'waveshare2in23g'

    def is_waveshare2in36g(self):
        return self._implementation.name == 'waveshare2in36g'

    def is_waveshare2in66(self):
        return self._implementation.name == 'waveshare2in66'

    def is_waveshare2in66g(self):
        return self._implementation.name == 'waveshare2in66g'

    def is_waveshare3in0g(self):
        return self._implementation.name == 'waveshare3in0g'

    def is_waveshare3in7(self):
        return self._implementation.name == 'waveshare3in7'

    def is_waveshare3in52(self):
        return self._implementation.name == 'waveshare3in52'

    def is_waveshare4in01f(self):
        return self._implementation.name == 'waveshare4in01f'

    def is_waveshare4in2(self):
        return self._implementation.name == 'waveshare4in2'

    def is_waveshare4in2V2(self):
        return self._implementation.name == 'waveshare4in2_v2'

    def is_waveshare4in2bV2(self):
        return self._implementation.name == 'waveshare4in2b_v2'

    def is_waveshare4in2bc(self):
        return self._implementation.name == 'waveshare4in2bc'

    def is_waveshare4in26(self):
        return self._implementation.name == 'waveshare4in26'

    def is_waveshare4in37g(self):
        return self._implementation.name == 'waveshare4in37g'

    def is_waveshare5in65f(self):
        return self._implementation.name == 'waveshare5in65f'

    def is_waveshare5in83(self):
        return self._implementation.name == 'waveshare5in83'

    def is_waveshare5in83V2(self):
        return self._implementation.name == 'waveshare5in83_v2'

    def is_waveshare5in83bV2(self):
        return self._implementation.name == 'waveshare5in83b_v2'

    def is_waveshare5in83bc(self):
        return self._implementation.name == 'waveshare5in83bc'

    def is_waveshare7in3f(self):
        return self._implementation.name == 'waveshare7in3f'

    def is_waveshare7in3g(self):
        return self._implementation.name == 'waveshare7in3g'

    def is_waveshare7in5(self):
        return self._implementation.name == 'waveshare7in5'

    def is_waveshare7in5HD(self):
        return self._implementation.name == 'waveshare7in5_HD'

    def is_waveshare7in5V2(self):
        return self._implementation.name == 'waveshare7in5_v2'

    def is_waveshare7in5bHD(self):
        return self._implementation.name == 'waveshare7in5b_HD'

    def is_waveshare7in5bV2(self):
        return self._implementation.name == 'waveshare7in5b_v2'

    def is_waveshare7in5bc(self):
        return self._implementation.name == 'waveshare7in5bc'

    def is_waveshare13in3k(self):
        return self._implementation.name == 'waveshare13in3k'

    def is_inky(self):
        return self._implementation.name == 'inky'

    def is_papirus(self):
        return self._implementation.name == 'papirus'

    def is_dfrobot_v1(self):
        return self._implementation.name == 'dfrobot_v1'

    def is_dfrobot_v2(self):
        return self._implementation.name == 'dfrobot_v2'

    def is_spotpear24inch(self):
        return self._implementation.name == 'spotpear24inch'

    def is_displayhatmini(self):
        return self._implementation.name == 'displayhatmini'

    def is_waveshare35lcd(self):
        return self._implementation.name == 'waveshare35lcd'

    def is_waveshare_any(self):
        return self.is_waveshare_v1() or self.is_waveshare_v2()

    def init_display(self):
        if self._enabled:
            self._implementation.initialize()
            plugins.on('display_setup', self._implementation)
        else:
            logging.warning("display module is disabled")
        self.on_render(self._on_view_rendered)

    def clear(self):
        self._implementation.clear()

    def image(self):
        img = None
        if self._canvas is not None:
            img = self._canvas if self._rotation == 0 else self._canvas.rotate(-self._rotation)
        return img

    def _render_thread(self):
        """Used for non-blocking screen updating."""

        while True:
            self._canvas_next_event.wait()
            self._canvas_next_event.clear()
            self._implementation.render(self._canvas_next)

    def _on_view_rendered(self, img):
        try:
            if self._config['ui']['web']['on_frame'] != '':
                os.system(self._config['ui']['web']['on_frame'])
        except Exception as e:
            logging.error("%s" % e)

        if self._enabled:
            self._canvas = (img if self._rotation == 0 else img.rotate(self._rotation))
            if self._implementation is not None:
                self._canvas_next = self._canvas
                self._canvas_next_event.set()
