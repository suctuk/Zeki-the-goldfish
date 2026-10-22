"""Printable QR cards for the "Give Zeki an idea!" Google Form.

    %USERPROFILE%\\.venvs\\zeki\\Scripts\\python.exe tools/make_qr.py

Writes (300 dpi):
  demo/zeki-form-qr.png           plain card (~4 x 5 in)
  demo/zeki-form-qr-goldfish.png  the QR in a goldfish's belly (~5.3 x 5 in)

Scannability rules kept in both: dark modules on white, a full white quiet
zone around the code, nothing drawn over it.
"""

import math
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeJeWwwxhGkTh1oBItt9br56bcX9HU0WJiW5o3zyFGX3Qdh_w/viewform"
DEMO = Path(__file__).resolve().parent.parent / "demo"
ORANGE = (255, 122, 26)
ORANGE_DARK = (214, 86, 0)
ORANGE_LIGHT = (255, 170, 90)
INK = (30, 30, 30)


def font(size, bold=False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), ("arialbd.ttf" if bold else "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def qr_image(side):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=24, border=2)
    qr.add_data(FORM_URL)
    qr.make(fit=True)
    img = qr.make_image(fill_color=INK, back_color="white").convert("RGB")
    return img.resize((side, side), Image.NEAREST), qr.modules_count


def centered(draw, W, text, y, f, fill):
    w = draw.textlength(text, font=f)
    draw.text(((W - w) / 2, y), text, font=f, fill=fill)


def plain_card():
    W, H = 1200, 1500
    card = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(card)
    draw.rectangle([0, 0, W, 190], fill=ORANGE)
    centered(draw, W, "Give Zeki an idea!", 45, font(96, bold=True), "white")
    code, n = qr_image(920)
    card.paste(code, ((W - 920) // 2, 250))
    centered(draw, W, "Scan, share a project idea,", 1210, font(56), INK)
    centered(draw, W, "and watch Zeki show it off.", 1280, font(56), INK)
    centered(draw, W, "(He's a goldfish. He'll forget. Probably.)", 1385, font(40), ORANGE)
    out = DEMO / "zeki-form-qr.png"
    card.save(out, dpi=(300, 300))
    return out, n


def goldfish_card():
    W, H = 1600, 1700
    S = 4                                   # draw at 4x, downsample for smooth edges
    big = Image.new("RGB", (W * S, H * S), "white")
    d = ImageDraw.Draw(big)

    def sc(*pts):
        return [v * S for v in pts]

    cx, cy = 700, 900                       # body centre
    a, b = 600, 500                         # body semi-axes
    win = 700                               # white window for the QR (incl. its quiet zone)

    # Tail: two lobes behind the body, with a notch.
    tail = [(cx + a - 60, cy), (1560, cy - 330), (1500, cy), (1560, cy + 330)]
    d.polygon(sc(*[v for p in tail for v in p]), fill=ORANGE, outline=ORANGE_DARK, width=10 * S)
    x0 = cx + a - 60                        # tail stripes, kept inside the tail
    for k in (-1, 1):
        for t in (0.45, 0.65, 0.8):
            x1, y1 = x0 + (1560 - x0) * t, cy + k * 330 * t * 0.75
            d.line(sc(x0 + 60, cy + k * 12, x1, y1), fill=ORANGE_LIGHT, width=8 * S)

    # Dorsal and belly fins.
    dorsal = [(cx - 260, cy - b + 40), (cx - 40, cy - b - 170), (cx + 260, cy - b - 120), (cx + 330, cy - b + 90)]
    d.polygon(sc(*[v for p in dorsal for v in p]), fill=ORANGE, outline=ORANGE_DARK, width=10 * S)
    belly = [(cx - 120, cy + b - 30), (cx + 20, cy + b + 120), (cx + 200, cy + b + 100), (cx + 230, cy + b - 60)]
    d.polygon(sc(*[v for p in belly for v in p]), fill=ORANGE, outline=ORANGE_DARK, width=10 * S)

    # Body.
    d.ellipse(sc(cx - a, cy - b, cx + a, cy + b), fill=ORANGE, outline=ORANGE_DARK, width=12 * S)
    # Scales: soft arcs on the back half of the body, outside the QR window.
    for row in range(-2, 3):
        for col in range(3):
            x = cx + win // 2 + 110 + col * 50
            y = cy + row * 95
            if ((x - cx) / a) ** 2 + ((y - cy) / b) ** 2 < 0.8:
                d.arc(sc(x - 34, y - 34, x + 34, y + 34), 270, 90, fill=ORANGE_LIGHT, width=7 * S)

    # Eye + smile on the head, left of the window.
    ex, ey = cx - a + 150, cy - 150
    d.ellipse(sc(ex - 62, ey - 62, ex + 62, ey + 62), fill="white", outline=ORANGE_DARK, width=8 * S)
    d.ellipse(sc(ex - 24, ey - 30, ex + 40, ey + 34), fill=INK)
    d.ellipse(sc(ex + 2, ey - 18, ex + 20, ey), fill="white")
    d.arc(sc(cx - a + 30, cy - 10, cx - a + 150, cy + 90), 20, 120, fill=ORANGE_DARK, width=9 * S)
    # Gill line.
    d.arc(sc(cx - a + 120, cy - 260, cx - a + 300, cy + 260), 300, 60, fill=ORANGE_DARK, width=8 * S)

    # Bubbles from the mouth.
    for r, (bx, by) in ((26, (55, cy - 190)), (40, (95, cy - 330)), (18, (40, cy - 450))):
        d.ellipse(sc(bx - r, by - r, bx + r, by + r), outline=ORANGE_DARK, width=7 * S)

    # The QR window in the belly: white rounded square, code with its own border.
    wx0, wy0 = cx - win // 2 + 60, cy - win // 2
    d.rounded_rectangle(sc(wx0, wy0, wx0 + win, wy0 + win), radius=40 * S, fill="white",
                        outline=ORANGE_DARK, width=8 * S)
    card = big.resize((W, H), Image.LANCZOS)
    code, n = qr_image(win - 40)
    card.paste(code, (wx0 + 20, wy0 + 20))

    draw = ImageDraw.Draw(card)
    centered(draw, W, "Give Zeki an idea!", 40, font(100, bold=True), ORANGE_DARK)
    centered(draw, W, "Scan, share a project idea, and watch him show it off.", 1605, font(46), INK)
    out = DEMO / "zeki-form-qr-goldfish.png"
    card.save(out, dpi=(300, 300))
    # Check the window really sits inside the body (all four corners).
    for x, y in ((wx0, wy0), (wx0 + win, wy0), (wx0, wy0 + win), (wx0 + win, wy0 + win)):
        assert ((x - cx) / a) ** 2 + ((y - cy) / b) ** 2 <= 1.25, "QR window sticks out of the fish"
    return out, n


if __name__ == "__main__":
    DEMO.mkdir(exist_ok=True)
    for make in (plain_card, goldfish_card):
        path, n = make()
        print("wrote", path, "({0}x{0} modules)".format(n))
