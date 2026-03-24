#!/home/pi/.pwn/bin/python3
"""Draw a boot indicator on the Waveshare V4 e-ink at startup.

Requires: Waveshare 2.13" V4 display (250x122).
On non-V4 displays the import will fail and the script exits silently.

Install: sudo cp epd-startup.py /usr/local/bin/ && sudo chmod +x /usr/local/bin/epd-startup.py
"""
import sys

sys.path.insert(0, '/home/pi/.pwn/lib/python3.13/site-packages')

try:
    from pwnagotchi.ui.hw.libs.waveshare.epaper.v2in13_V4.epd2in13_V4 import EPD
except ImportError:
    sys.exit(0)  # not a V4 display

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

    # Waking face  ( O_O )
    face_font = load_font(FONT_BOLD, 28)
    face = "( O_O )"
    face_bbox = draw.textbbox((0, 0), face, font=face_font)
    face_w = face_bbox[2] - face_bbox[0]
    face_h = face_bbox[3] - face_bbox[1]
    face_x = (WIDTH - face_w) // 2
    face_y = (HEIGHT - face_h) // 2 - 12

    draw.text((face_x, face_y), face, font=face_font, fill=0)

    sm_font = load_font(FONT_NAME, 10)
    boot_text = "booting ..."
    boot_bbox = draw.textbbox((0, 0), boot_text, font=sm_font)
    boot_w = boot_bbox[2] - boot_bbox[0]
    boot_x = (WIDTH - boot_w) // 2
    draw.text((boot_x, face_y + face_h + 16), boot_text, font=sm_font, fill=0)

    img = img.rotate(180)
    epd.display(epd.getbuffer(img))
    epd.sleep()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"epd-startup: {e}", file=sys.stderr)
