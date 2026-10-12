# Twist as input events: turn, click, long press (hold >= 0.8 s).
# Shows "GO" and each event on the OLED so you know it's listening.
import time
import config as C
import hw
import ui

screen = ui.Screen(hw.oled())
screen.status("up", 4)
k = hw.Knob(hw.twist(), C.LONG_PRESS_MS)
log = ["GO! turn, click,", "hold (30 s)"]
screen.show(log)
screen.render(time.ticks_ms())
print("Knob ready (30 s)")
t0 = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), t0) < 30_000:
    for ev in k.poll():
        ms = time.ticks_diff(time.ticks_ms(), t0)
        print("{:6d} ms  {}".format(ms, ev))
        log = (log + ["{:5.1f}s {}".format(ms / 1000, " ".join(str(x) for x in ev))])[-6:]
        screen.show(log, hi=len(log) - 1)
    screen.render(time.ticks_ms())
    time.sleep_ms(C.TWIST_POLL_MS)
screen.show(["done"])
screen.render(time.ticks_ms())
print("done")
