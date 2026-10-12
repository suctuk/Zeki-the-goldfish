# Live VL53L1X + cup-logic view on the OLED (60 s). Use it to check the
# sensor and, later, to tune config.py's cup thresholds once it's mounted.
#   row 1: raw reading and range status (0 = valid, 2/4 = nothing in range,
#          3 = too close, 1/7 = unreliable)
#   row 2: median the cup logic uses
#   row 3: cup mode and settled baseline
#   row 4: last event
import time
import config as C
import cup
import hw
import ui

STATUS = {0: "ok", 2: "far", 4: "far", 3: "close", 1: "sigma", 7: "wrap", 6: "ok"}

screen = ui.Screen(hw.oled())
screen.status("up", 4)
c = cup.Cup(hw.tof())
last_ev = "-"
n_reads = 0
prev_raw = None
t0 = time.ticks_ms()
shown = 0
while time.ticks_diff(time.ticks_ms(), t0) < 60_000:
    now = time.ticks_ms()
    ev = c.tick(now)
    if c.last_raw is not prev_raw:
        prev_raw = c.last_raw
        n_reads += 1
    if ev:
        last_ev = "{} @{}s".format(ev.upper(), time.ticks_diff(now, t0) // 1000)
        print(last_ev, "settled", c.settled)
    if time.ticks_diff(now, shown) >= 150:
        shown = now
        mm, st = c.last_raw or (0, -1)
        screen.show([
            "raw {:4d} {}".format(mm, STATUS.get(st, "st" + str(st))),
            "med {}".format(c.last_mm if c.last_mm is not None else "-"),
            "{} {}".format(c.mode[:6], c.settled if c.settled is not None else "-"),
            last_ev,
            "{}s left".format(60 - time.ticks_diff(now, t0) // 1000),
        ], hi=3 if ev or last_ev != "-" else None)
        screen.render(now)
    time.sleep_ms(10)
secs = time.ticks_diff(time.ticks_ms(), t0) / 1000
print("readings: {} in {:.0f} s ({:.1f}/s)".format(n_reads, secs, n_reads / secs))
