# Qwiic Twist: print rotation count and button presses; set LED to orange
import time
import hw

t = hw.twist()
t.set_color(255, 80, 0)  # orange
t.set_count(0)
t.clear_interrupts()
print("Twist fw 0x{:04X}: LED orange. Turn and click for 30 s...".format(t.get_version()))

clicks = 0
last = None
t0 = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), t0) < 30_000:
    count = t.get_count()
    if count > 32767:  # driver returns uint16; turning below 0 wraps to 65535
        count -= 65536
    if t.was_clicked():
        clicks += 1
        print("click #{}".format(clicks))
    if count != last:
        print("count = {}".format(count))
        last = count
    time.sleep_ms(50)
print("Twist: final count={}, clicks={}".format(last, clicks))
