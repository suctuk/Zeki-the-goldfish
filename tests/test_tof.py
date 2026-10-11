# VL53L1X: print distance every 200 ms for 10 s
import time
import hw

s = hw.tof()
s.set_distance_mode(1)  # 1 = short (up to ~1.3 m, better in ambient light)
s.start_ranging()
t0 = time.ticks_ms()
n = 0
while time.ticks_diff(time.ticks_ms(), t0) < 10_000:
    while not s.check_for_data_ready():
        time.sleep_ms(2)
    mm = s.get_distance()
    status = s.get_range_status()
    s.clear_interrupt()
    n += 1
    print("{:5d} ms  {:4d} mm  status={}".format(time.ticks_diff(time.ticks_ms(), t0), mm, status))
    time.sleep_ms(200)
s.stop_ranging()
print("VL53L1X: {} readings".format(n))
