# ui.py — screens: status bar (top 10 px) + word-wrapped message body.
#
# 128x64 SSD1306, built-in 8x8 font: 16 chars per row, 6 body rows.
# Text goes through lines.fold() first (ASCII fallback for Turkish letters).

import lines

W = 128
H = 64
BAR_H = 10          # status bar: rows 0-8 content, row 9 separator line
CHARS = W // 8      # 16
ROW_H = 9           # 8 px glyph + 1 px leading
MAX_ROWS = (H - BAR_H) // ROW_H   # 6
BLINK_MS = 500


def wrap(text, width=CHARS):
    """Word-wrap to rows of <= width chars. "\\n" forces a break."""
    rows = []
    for seg in lines.fold(text).split("\n"):
        cur = ""
        for word in seg.split():
            while len(word) > width:          # hard-split words longer than a row
                if cur:
                    rows.append(cur)
                    cur = ""
                rows.append(word[:width])
                word = word[width:]
            if not cur:
                cur = word
            elif len(cur) + 1 + len(word) <= width:
                cur += " " + word
            else:
                rows.append(cur)
                cur = word
        rows.append(cur)
    return rows


def wifi_bars(rssi):
    if rssi >= -60:
        return 4
    if rssi >= -70:
        return 3
    if rssi >= -80:
        return 2
    return 1


class Screen:
    """Redraws only when something visible changed. oled may be None."""

    def __init__(self, oled):
        self.d = oled
        self.rows = []
        self.hi = None            # index of the highlighted (inverted) row
        self.net = "connecting"   # "up" | "connecting" | "offline"
        self.bars = 0
        self.badge = 0
        self.dirty = True
        self._blink = None

    def say(self, text):
        self.show(wrap(text))

    def show(self, rows, hi=None):
        """Set body rows directly; row `hi` is drawn inverted."""
        if len(rows) > MAX_ROWS:
            print("ui: clipped to {} rows: {!r}".format(MAX_ROWS, rows))
            rows = rows[:MAX_ROWS]
        if rows != self.rows or hi != self.hi:
            self.rows = rows
            self.hi = hi
            self.dirty = True

    def status(self, net, bars=0, badge=0):
        if (net, bars, badge) != (self.net, self.bars, self.badge):
            self.net, self.bars, self.badge = net, bars, badge
            self.dirty = True

    def render(self, now):
        blink = (now // BLINK_MS) % 2 == 0
        if self.net != "up" and blink != self._blink:
            self.dirty = True                 # animate the offline / connecting icon
        self._blink = blink
        if not self.dirty or self.d is None:
            return
        d = self.d
        d.fill(0)
        self._draw_bar(d, now, blink)
        top = BAR_H + 1 + (MAX_ROWS - len(self.rows)) * ROW_H // 2
        for i, row in enumerate(self.rows):
            y = top + i * ROW_H
            if i == self.hi:
                d.fill_rect(0, y - 1, W, ROW_H, 1)
            d.text(row, (W - len(row) * 8) // 2, y, 0 if i == self.hi else 1)
        d.show()
        self.dirty = False

    def _draw_bar(self, d, now, blink):
        # Wi-Fi: 4 bars, heights 2/4/6/8, bottom at y=8.
        if self.net == "up":
            lit = self.bars
        elif self.net == "connecting":
            lit = (now // BLINK_MS) % 5    # sweep 0..4 bars
        else:
            lit = 0
        for i in range(4):
            h = 2 + 2 * i
            x = i * 3
            if i < lit:
                d.fill_rect(x, 9 - h, 2, h, 1)
            else:
                d.pixel(x, 8, 1)                        # unlit bar = dot on baseline
        if self.net == "offline" and blink:
            d.line(13, 2, 18, 7, 1)                     # blinking X
            d.line(13, 7, 18, 2, 1)
        # Badge for unseen submissions, right-aligned, inverted.
        if self.badge:
            label = "{} new".format(self.badge)
            w = len(label) * 8 + 2
            d.fill_rect(W - w, 0, w, 9, 1)
            d.text(label, W - w + 1, 1, 0)
        d.hline(0, BAR_H - 1, W, 1)
