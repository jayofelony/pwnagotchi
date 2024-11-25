"""Library for the GFX HAT Cap1166 touch controller."""
from . import cap1xxx

_cap1166 = None
is_setup = False

I2C_ADDR = 0x2c

UP = 0
DOWN = 1
BACK = 2
MINUS = LEFT = 3
SELECT = ENTER = 4
PLUS = RIGHT = 5

LED_MAPPING = [5, 4, 3, 2, 1, 0]

NAME_MAPPING = ['up', 'down', 'back', 'minus', 'select', 'plus']


def setup():
    """Set up the touch input on GFX HAT."""
    global _cap1166, is_setup

    if is_setup:
        return

    _cap1166 = cap1xxx.Cap1166(i2c_addr=I2C_ADDR)

    for x in range(6):
        _cap1166.set_led_linking(x, 0)

    # Force recalibration
    _cap1166._write_byte(0x26, 0b00111111)
    _cap1166._write_byte(0x1F, 0b01000000)

    is_setup = True


def get_name(index):
    """Get the name of a touch pad from its channel index.

    :param index: Index of touch pad from 0 to 5

    """
    return NAME_MAPPING[index]


def set_led(index, state):
    """Set LED state.

    :param index: LED index
    :param state: LED state (1 = on, 0 = off)

    """
    setup()

    _cap1166.set_led_state(LED_MAPPING[index], state)


def high_sensitivity():
    """Switch to high sensitivity mode.

    This predetermined high sensitivity mode is for using
    touch through 3mm perspex or similar materials.

    """
    setup()

    _cap1166._write_byte(0x00, 0b11000000)
    _cap1166._write_byte(0x1f, 0b00000000)


def enable_repeat(enable):
    """Enable touch hold repeat.

    If enable is true, repeat will be enabled. This will
    trigger new touch events at the set repeat_rate when
    a touch input is held.

    :param enable: enable/disable repeat: True/False

    """
    setup()

    if enable:
        _cap1166.enable_repeat(0b11111111)
    else:
        _cap1166.enable_repeat(0b00000000)


def set_repeat_rate(rate):
    """Set hold repeat rate.

    Repeat rate values are clamped to the nearest 35ms,
    values from 35 to 560 are valid.

    :param rate: time in ms from 35 to 560

    """
    setup()

    _cap1166.set_repeat_rate(rate)


def on(buttons, handler=None):
    """Handle a press of one or more buttons.

    Decorator. Use with @captouch.on(UP)

    :param buttons: List, or single instance of cap touch button constant
    :param bounce: Maintained for compatibility with Dot3k joystick, unused

    """
    setup()

    buttons = buttons if isinstance(buttons, list) else [buttons]

    def register(handler):
        for button in buttons:
            _cap1166.on(channel=button, event='press', handler=handler)
            _cap1166.on(channel=button, event='release', handler=handler)
            _cap1166.on(channel=button, event='held', handler=handler)

    if handler is not None:
        register(handler)
        return

    return register
