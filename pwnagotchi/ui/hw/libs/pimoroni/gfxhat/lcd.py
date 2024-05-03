"""Library for the GFX HAT ST7567 SPI LCD."""
from .st7567 import ST7567

st7567 = ST7567()

dimensions = st7567.dimensions


def clear():
    """Clear GFX HAT's display buffer."""
    st7567.clear()


def set_pixel(x, y, value):
    """Set a single pixel in GTX HAT's display buffer.

    :param x: X position (from 0 to 127)
    :param y: Y position (from 0 to 63)
    :param value: pixel state 1 = On, 0 = Off

    """
    st7567.set_pixel(x, y, value)


def show():
    """Update GFX HAT with the current buffer contents."""
    st7567.show()


def contrast(value):
    """Change GFX HAT LCD contrast."""
    st7567.contrast(value)


def rotation(r=0):
    """Set the display rotation.

    :param r: Specify the rotation in degrees: 0, or 180

    """
    if r == 0:
        st7567.rotated = False

    elif r == 180:
        st7567.rotated = True

    else:
        raise ValueError('Rotation must be 0 or 180 degrees')


def get_rotation():
    """Get the display rotation value.

    Returns an integer, either 0, or 180

    """
    return 180 if st7567.rotated else 0
