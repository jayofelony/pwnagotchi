from PIL import Image, ImageOps
from textwrap import TextWrapper


class Widget(object):
    def __init__(self, xy, color=0):
        self.xy = xy
        self.color = color

    def draw(self, canvas, drawer):
        raise Exception("not implemented")

# canvas.paste: https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.paste
# takes mask variable, to identify color system. (not used for pwnagotchi yet)
# Pwn should use "1" since its mainly black or white displays.
class Bitmap(Widget):
    def __init__(self, path, xy, color=0):
        super().__init__(xy, color)
        self.image = Image.open(path)

    def draw(self, canvas, drawer):
        if self.color == 0xFF:
            self.image = ImageOps.invert(self.image)
        canvas.paste(self.image, self.xy)


class Line(Widget):
    def __init__(self, xy, color=0, width=1):
        super().__init__(xy, color)
        self.width = width

    def draw(self, canvas, drawer):
        drawer.line(self.xy, fill=self.color, width=self.width)


class Rect(Widget):
    def draw(self, canvas, drawer):
        drawer.rectangle(self.xy, outline=self.color)


class FilledRect(Widget):
    def draw(self, canvas, drawer):
        drawer.rectangle(self.xy, fill=self.color)


class Text(Widget):
    def __init__(self, value="", position=(0, 0), font=None, color=0, wrap=False, max_length=0, png=False, scale=1):
        super().__init__(position, color)
        self.value = value
        self.font = font
        self.wrap = wrap
        self.max_length = max_length
        self.wrapper = TextWrapper(width=self.max_length, replace_whitespace=False) if wrap else None
        self.png = png
        self.scale = scale

    def draw(self, canvas, drawer):
        if self.value is not None:
            if not self.png:
                if self.wrap:
                    text = '\n'.join(self.wrapper.wrap(self.value))
                else:
                    text = self.value
                drawer.text(self.xy, text, font=self.font, fill=self.color)
            else:
                self.image = Image.open(self.value)
                self.image = self.image.convert('RGBA')
                self.pixels = self.image.load()
                for y in range(self.image.size[1]):
                    for x in range(self.image.size[0]):
                        if self.pixels[x, y][3] < 255:
                            self.pixels[x, y] = (255, 255, 255, 255)
                if self.color == 255:
                    self._image = ImageOps.colorize(self.image.convert('L'), black="white", white="black")
                else:
                    self._image = self.image
                if self.scale != 1:
                    width, height = self._image.size
                    new_width = int(width * self.scale)
                    new_height = int(height * self.scale)
                    scaled_image = Image.new('RGBA', (new_width, new_height))
                    original_pixels = self._image.load()
                    scaled_pixels = scaled_image.load()
                    for y in range(new_height):
                        for x in range(new_width):
                            original_x = x // self.scale
                            original_y = y // self.scale
                            scaled_pixels[x, y] = original_pixels[original_x, original_y]
                    self.image = scaled_image
                else:
                    self.image = self._image
                self.image = self.image.convert('1')
                canvas.paste(self.image, self.xy)

class LabeledValue(Widget):
    def __init__(self, label, value="", position=(0, 0), label_font=None, text_font=None, color=0, label_spacing=5):
        super().__init__(position, color)
        self.label = label
        self.value = value
        self.label_font = label_font
        self.text_font = text_font
        self.label_spacing = label_spacing

    def draw(self, canvas, drawer):
        if self.label is None:
            drawer.text(self.xy, self.value, font=self.label_font, fill=self.color)
        else:
            pos = self.xy
            drawer.text(pos, self.label, font=self.label_font, fill=self.color)
            drawer.text((pos[0] + self.label_spacing + 5 * len(self.label), pos[1]), self.value, font=self.text_font, fill=self.color)
