#!/home/pi/.pwn/bin/python3
"""Draw a sleeping face on the Waveshare V4 e-ink before shutdown.

Requires: Waveshare 2.13" V4 display (250x122).
On non-V4 displays the import will fail and the script exits silently.

Install: sudo cp epd-shutdown.py /usr/local/bin/ && sudo chmod +x /usr/local/bin/epd-shutdown.py
"""
import sys

sys.path.insert(0, '/home/pi/.pwn/lib/python3.13/site-packages')

try:
    from pwnagotchi.ui.hw.libs.waveshare.epaper.v2in13_V4.epd2in13_V4 import EPD
except ImportError:
    sys.exit(0)  # not a V4 display — nothing to do

from PIL import Image, ImageDraw, ImageFont

WIDTH = 250
HEIGHT = 122

FONT_NAME = 'DejaVuSansMono'
FONT_BOLD = 'DejaVuSansMono-Bold'


def load_font(name, size):
    try:
        return ImageFont.truetype(name, size)
    except (IOError, OSError):
        return ImageFont.load_default()


def main():
    epd = EPD()
    epd.init()

    img = Image.new('1', (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    # Sleeping face  ( -_- ) Zzz
    face_font = load_font(FONT_BOLD, 28)
    face = "( -_- )"
    face_bbox = draw.textbbox((0, 0), face, font=face_font)
    face_w = face_bbox[2] - face_bbox[0]
    face_h = face_bbox[3] - face_bbox[1]
    face_x = (WIDTH - face_w) // 2 - 15
    face_y = (HEIGHT - face_h) // 2 - 12

    draw.text((face_x, face_y), face, font=face_font, fill=0)

    z1_font = load_font(FONT_BOLD, 16)
    z2_font = load_font(FONT_BOLD, 12)
    z3_font = load_font(FONT_BOLD, 9)
    zx = face_x + face_w + 4
    draw.text((zx, face_y - 2), "Z", font=z1_font, fill=0)
    draw.text((zx + 12, face_y + 12), "z", font=z2_font, fill=0)
    draw.text((zx + 20, face_y + 22), "z", font=z3_font, fill=0)

    sm_font = load_font(FONT_NAME, 10)
    off_text = "powered off"
    off_bbox = draw.textbbox((0, 0), off_text, font=sm_font)
    off_w = off_bbox[2] - off_bbox[0]
    off_x = (WIDTH - off_w) // 2
    draw.text((off_x, face_y + face_h + 16), off_text, font=sm_font, fill=0)

    # Full refresh persists after power cut
    img = img.rotate(180)
    epd.display(epd.getbuffer(img))
    epd.sleep()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"epd-shutdown: {e}", file=sys.stderr)
