# hw.py — board init for Zeki (SparkFun Thing Plus ESP32 WROOM USB-C, WRL-20168)
#
# Qwiic power is switched by GPIO0. It must be driven HIGH before I2C init,
# or the whole Qwiic chain is unpowered and the scan comes back empty.
#
# One shared bus: SparkFun's qwiic_i2c driver owns the machine.I2C on 21/22.
# Pass qwiic() to every SparkFun driver (i2c_driver=...), and i2c() to
# anything that wants a raw machine.I2C (ssd1306, scans).

import math
import time
from machine import Pin
import qwiic_i2c

QWIIC_PWR_PIN = 0
GLOW_PIN = 2
SDA_PIN = 21
SCL_PIN = 22
I2C_FREQ = 400_000

ADDR_TOF = 0x29
ADDR_BUZZER = 0x34
ADDR_FUEL = 0x36
ADDR_OLED = 0x3D
ADDR_TWIST = 0x3F

KNOWN = {
    ADDR_TOF: "VL53L1X distance",
    ADDR_BUZZER: "Qwiic Buzzer",
    ADDR_FUEL: "MAX17048 fuel gauge (onboard)",
    ADDR_OLED: "OLED 1.3in (SSD1306)",
    ADDR_TWIST: "Qwiic Twist",
}

_qwiic = None


def qwiic_power(on=True):
    Pin(QWIIC_PWR_PIN, Pin.OUT, value=1 if on else 0)


def qwiic():
    """Power the Qwiic chain and return the shared SparkFun I2C driver."""
    global _qwiic
    if _qwiic is None:
        qwiic_power(True)
        time.sleep_ms(100)
        _qwiic = qwiic_i2c.getI2CDriver(sda=SDA_PIN, scl=SCL_PIN, freq=I2C_FREQ)
    return _qwiic


def i2c():
    """The raw machine.I2C under the shared driver."""
    return qwiic().i2cbus


def scan():
    found = i2c().scan()
    print("I2C scan: {} device(s)".format(len(found)))
    for addr in found:
        print("  0x{:02X}  {}".format(addr, KNOWN.get(addr, "?")))
    return found


def oled():
    import ssd1306
    return ssd1306.SSD1306_I2C(128, 64, i2c(), addr=ADDR_OLED)


def tof():
    import qwiic_vl53l1x
    s = qwiic_vl53l1x.QwiicVL53L1X(ADDR_TOF, i2c_driver=qwiic())
    err = s.sensor_init()  # None/0 on success, nonzero error code on failure
    if err:
        raise OSError("VL53L1X init failed: {}".format(err))
    return s


def twist():
    import qwiic_twist
    t = qwiic_twist.QwiicTwist(ADDR_TWIST, i2c_driver=qwiic())
    if not t.begin():
        raise OSError("Qwiic Twist not found")
    return t


def buzzer():
    import qwiic_buzzer
    b = qwiic_buzzer.QwiicBuzzer(ADDR_BUZZER, i2c_driver=qwiic())
    if not b.begin():
        raise OSError("Qwiic Buzzer not found")
    return b


class Mood:
    """State color on the Twist LED + onboard WS2812 body glow.

    set(color, breathe) is cheap to call every loop: the Twist is only
    written when the color changes. Call tick(now) every loop for breathing.
    Either device may be None (missing hardware is not fatal).
    """

    def __init__(self, twist, cfg):
        from neopixel import NeoPixel
        self.twist = twist
        self.cfg = cfg
        self.px = NeoPixel(Pin(GLOW_PIN), 1)
        self.color = None
        self.breathe = False
        self._glow = None

    def set(self, color, breathe=False):
        self.breathe = breathe
        if color == self.color:
            return
        self.color = color
        if self.twist:
            k = self.cfg.TWIST_BRIGHTNESS
            self.twist.set_color(*(int(c * k) for c in color))

    def tick(self, now):
        if self.color is None:
            return
        c = self.cfg
        if self.breathe:
            phase = (now % c.GLOW_BREATH_MS) / c.GLOW_BREATH_MS
            k = c.GLOW_MIN + (c.GLOW_MAX - c.GLOW_MIN) * (0.5 - 0.5 * math.cos(2 * math.pi * phase))
        else:
            k = c.GLOW_MAX
        rgb = tuple(int(v * k) for v in self.color)
        if rgb != self._glow:
            self.px[0] = rgb
            try:
                self.px.write()
                self._glow = rgb
            except OSError:          # write needs a little IDF RAM; if short, retry next tick
                pass                 # (Day 4: ENOMEM here while a threaded poll held TLS buffers)


class Chime:
    """Non-blocking note player for the Qwiic Buzzer.

    play(((freq_hz, ms), ...)) queues notes; tick(now) every loop starts the
    next one. The buzzer times each note itself (duration register).
    """

    def __init__(self, buzzer, volume):
        self.b = buzzer
        self.volume = volume
        self.notes = []
        self.next_at = None

    def play(self, notes):
        self.notes = list(notes)
        self.next_at = time.ticks_ms()

    def tick(self, now):
        if self.next_at is None or time.ticks_diff(now, self.next_at) < 0:
            return
        if self.notes:
            freq, ms = self.notes.pop(0)
            self.b.configure(freq, ms, self.volume)
            self.b.on()
            self.next_at = time.ticks_add(now, ms + 20)
        else:
            self.b.off()
            self.next_at = None


class Knob:
    """Qwiic Twist as input events. poll() returns a list of
    ("turn", steps) / ("click",) / ("long",).

    Twist firmware facts (sparkfun/Qwiic_Twist, interrupts.ino):
    - PRESSED bit is TOGGLED on every pin change, so it is a live "held"
      flag. Never clear it, or it inverts (held reads as released).
    - "ms since last button event" only resets on release, so it can't time
      a hold. Holds are timed here instead.
    Turns come from the count register (no read-then-clear race). The click
    that follows a long press on release is swallowed.
    """

    _STATUS, _COUNT = 0x01, 0x05
    _MOVED, _PRESSED, _CLICKED = 0x01, 0x02, 0x04
    _STUCK_MS = 10_000      # "held" this long with no release = parity got out of sync

    def __init__(self, twist, long_ms):
        self.i2c = twist._i2c
        self.addr = twist.address
        self.long_ms = long_ms
        self.long_fired = False
        self.press_t = None
        self.count = self.i2c.readWord(self.addr, self._COUNT)
        self.i2c.writeByte(self.addr, self._STATUS, 0)

    def poll(self):
        now = time.ticks_ms()
        st = self.i2c.readByte(self.addr, self._STATUS)
        events = []
        clear = 0
        if st & self._MOVED:
            clear |= self._MOVED
            count = self.i2c.readWord(self.addr, self._COUNT)
            d = (count - self.count) & 0xFFFF
            if d > 32767:
                d -= 65536
            self.count = count
            if d:
                events.append(("turn", d))
        if st & self._CLICKED:              # a release happened
            clear |= self._CLICKED
            if not self.long_fired:
                events.append(("click",))
            self.long_fired = False
            self.press_t = None
        if st & self._PRESSED:              # held right now
            if self.press_t is None:
                self.press_t = now
            held = time.ticks_diff(now, self.press_t)
            if held >= self.long_ms and not self.long_fired:
                self.long_fired = True
                events.append(("long",))
            if held >= self._STUCK_MS:
                clear |= self._PRESSED      # resync a flipped toggle
                self.press_t = None
        else:
            self.press_t = None
        if clear:
            self.i2c.writeByte(self.addr, self._STATUS, st & ~clear)
        return events


if __name__ == "__main__":
    scan()
