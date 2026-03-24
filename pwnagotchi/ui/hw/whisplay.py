import logging
import os
import importlib.util
import numpy as np

import pwnagotchi.ui.fonts as fonts
from pwnagotchi.ui.hw.base import DisplayImpl

class Whisplay(DisplayImpl):
    def __init__(self, config):
        super(Whisplay, self).__init__(config, 'whisplay')
        self._display = None

    def layout(self):
        fonts.setup(10, 9, 10, 35, 25, 9)
        # Update layout to match 280x240 display
        self._layout['width'] = 240
        self._layout['height'] = 280
        self._layout['face'] = (0, 35)
        self._layout['name'] = (20, 0)
        self._layout['channel'] = (5, 15)
        self._layout['aps'] = (33, 15)
        self._layout['uptime'] = (195, 15)
        # extend line positions to the new width
        self._layout['line1'] = [0, 30, 280, 30]
        self._layout['line2'] = [0, 220, 280, 220]
        self._layout['friend_face'] = (0, 92)
        self._layout['friend_name'] = (40, 94)
        self._layout['shakes'] = (17, 223)
        self._layout['mode'] = (235, 223)
        self._layout['status'] = {
            'pos': (140, 35),
            'font': fonts.status_font(fonts.Medium),
            'max': 20
        }


        return self._layout

    def initialize(self):
        logging.info("Initializing Whisplay with PiSugar WhisPlayBoard driver")
        # Pins (physical BOARD numbering) for this wiring/setup:
        logging.info("5V pins: physical 2 and 4")
        logging.info("GND: any GND pin")
        logging.info("I2C SDA (SDA) = physical pin 3")
        logging.info("I2C SCL (SCL) = physical pin 5")
        logging.info("LCD control / Backlight = physical pin 15")
        logging.info("SPI SCLK = physical pin 23, MOSI = physical pin 19, CS (CE0) = physical pin 24")
        logging.info("SPI D/C = physical pin 13, SPI RST = physical pin 7")
        logging.info("I2S pins (physical): WS=35, DIN=38, DOUT=40")
        # Instantiate the WhisPlayBoard driver
        from pwnagotchi.ui.hw.libs.whisplay.whisplaydriver import WhisPlayBoard
        self._display = WhisPlayBoard()
        self._display.set_rgb(0, 0, 0)
        self._display.set_backlight(50)

    def render(self, canvas):
        """Render canvas to display by converting to RGB565 and sending via draw_image."""
        screen_width = self._display.LCD_WIDTH
        screen_height = self._display.LCD_HEIGHT

        # Convert canvas to PIL Image if it's a numpy array
        if isinstance(canvas, np.ndarray):
            img = Image.fromarray(canvas.astype('uint8'))
        else:
            img = canvas.convert('RGB')

        # Get original dimensions and calculate aspect ratios
        original_width, original_height = img.size
        aspect_ratio = original_width / original_height
        screen_aspect_ratio = screen_width / screen_height

        # Scale and crop to maintain aspect ratio while filling screen
        if aspect_ratio > screen_aspect_ratio:
            # Original image is wider, scale based on screen height
            new_height = screen_height
            new_width = int(new_height * aspect_ratio)
            resized_img = img.resize((new_width, new_height))
            # Calculate horizontal offset to center the image
            offset_x = (new_width - screen_width) // 2
            # Crop the image to fit screen width
            cropped_img = resized_img.crop(
                (offset_x, 0, offset_x + screen_width, screen_height))
        else:
            # Original image is taller or has the same aspect ratio, scale based on screen width
            new_width = screen_width
            new_height = int(new_width / aspect_ratio)
            resized_img = img.resize((new_width, new_height))
            # Calculate vertical offset to center the image
            offset_y = (new_height - screen_height) // 2
            # Crop the image to fit screen height
            cropped_img = resized_img.crop(
                (0, offset_y, screen_width, offset_y + screen_height))

        # Convert to RGB565 pixel data with 40-pixel top padding
        pixel_data = []

        # Add the actual image data (reduced height due to padding)
        for y in range(screen_height):
            for x in range(screen_width):
                r, g, b = cropped_img.getpixel((x, y))
                # Convert RGB to RGB565 (5-6-5 bits)
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                pixel_data.extend([(rgb565 >> 8) & 0xFF, rgb565 & 0xFF])

        # Draw the image on the display (back to 0, 0 without offset)
        self._display.draw_image(0, 0, screen_width, screen_height, pixel_data)

    def clear(self):
        """Clear the display (fill with black)."""
        self._display.fill_screen(0)