"""
`Inky pHAT`_ class and methods.

A getting started `tutorial`_ for the Inky pHAT is available on the pimoroni website.

The `pinout`_ for the Inky pHAT is documented on pinout.xyz

.. _`Inky pHAT`: https://shop.pimoroni.com/products/inky-phat
.. _`tutorial`: https://learn.pimoroni.com/tutorial/sandyj/getting-started-with-inky-phat
.. _`pinout`: https://pinout.xyz/pinout/inky_phat
"""
from libs.pimoroni.inkyphatv2 import inky, inky_ssd1608


class InkyPHAT_SSD1608(inky_ssd1608.Inky):
    """Inky pHAT V2 (250x122 pixel) e-Ink Display Driver."""

    WIDTH = 250
    HEIGHT = 122

    WHITE = 0
    BLACK = 1
    RED = 2
    YELLOW = 2

    def __init__(self, colour):
        """Initialise an Inky pHAT Display.

        :param colour: one of red, black or yellow, default: black

        """
        inky_ssd1608.Inky.__init__(
            self,
            resolution=(self.WIDTH, self.HEIGHT),
            colour=colour,
            h_flip=False,
            v_flip=False)


class InkyPHAT(inky.Inky):
    """Inky pHAT e-Ink Display Driver.

    :Example: ::

        >>> from inky import InkyPHAT
        >>> display = InkyPHAT('red')
        >>> display.set_border(display.BLACK)
        >>> for x in range(display.WIDTH):
        >>>     for y in range(display.HEIGHT):
        >>>         display.set_pixel(x, y, display.RED)
        >>> display.show()
    """

    WIDTH = 212
    HEIGHT = 104

    WHITE = 0
    BLACK = 1
    RED = 2
    YELLOW = 2

    def __init__(self, colour='black'):
        """Initialise an Inky pHAT Display.

        :param str colour: one of 'red', 'black' or 'yellow', default: 'black'.
        """
        inky.Inky.__init__(
            self,
            resolution=(self.WIDTH, self.HEIGHT),
            colour=colour,
            h_flip=False,
            v_flip=False)