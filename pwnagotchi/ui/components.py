import logging
from PIL import Image, ImageOps
from textwrap import TextWrapper


class Widget(object):
    def __init__(self, xy, color=0, bgcolor="white"):
        self.xy = xy
        self.color = color
        self.bgcolor = bgcolor

    def draw(self, canvas, drawer):
        raise Exception("not implemented")

    def setColor(self, color):
        self.color = color

    def setBackground(self, color):
        self.bgcolor = color

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
    def __init__(self, value="", position=(0, 0), font=None, color=0, bgcolor="white", wrap=False, max_length=0, png=False, scale=1, colorize=True):
        super().__init__(position, color, bgcolor)
        self.value = value
        self.font = font
        self.wrap = wrap
        self.max_length = max_length
        self.wrapper = TextWrapper(width=self.max_length, replace_whitespace=False) if wrap else None
        self.png = png
        self.scale = scale
        self.colorize = colorize

        self.image = None
        self.offsets = (0,0)
        self.last_file = None

    def draw(self, canvas, drawer):
        if self.value is not None:
            if not self.png:
                if self.wrap:
                    text = '\n'.join(self.wrapper.wrap(self.value))
                else:
                    text = self.value
                drawer.text(self.xy, text, font=self.font, fill=self.color)
            else:
                ox, oy = self.offsets
                try:
                    if self.value != self.last_file:
                        image = Image.open(self.value)
                        image = image.convert('RGBA')
                        pixels = image.load()
                        for y in range(image.size[1]):
                            for x in range(image.size[0]):
                                if pixels[x,y][3] < 255:    # check alpha
                                    pixels[x,y] = (255, 255, 255, 255)
                        self.raw_image = image.copy()
                    else:
                        logging.debug("Not reloading same image")
                        image = self.raw_image.copy()

                    if self.colorize:
                        logging.debug("Colorizing %s from (%s, %s)" % (self.value, self.color, self.bgcolor))
                        image = ImageOps.colorize(image.convert('L'), black = self.color, white = self.bgcolor)
                    if len(self.xy) > 2:
                        iw,ih = image.size
                        bw,bh = (self.xy[2]-self.xy[0], self.xy[3]-self.xy[1])
                        sc = min(float(bw/iw), float(bh/ih))
                        nw = int(iw * sc)
                        nh = int(ih * sc)
                        ox = int((bw-nw)/2)
                        oy = int((bh-nh)/2)
                        image = image.resize((nw,nh), Image.NEAREST)
                        self.offsets = [ox,oy]
                        logging.debug("Offsets %s" % (self.offsets))
                    elif self.scale != 1.0:
                        new_w = int(image.size[0]*self.scale)
                        new_h = int(image.size[1]*self.scale)
                        image = image.resize((new_w, new_h), Image.NEAREST)
                    self.image = image.convert(canvas.mode)
                    self.last_file = self.value
                except Exception as e:
                    logging.exception("%s: %s" % (self.value, e))
                if self.image:
                    canvas.paste(self.image, (self.xy[0]+self.offsets[0], self.xy[1]+self.offsets[1]))

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
