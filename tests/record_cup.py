# Guided cup recording for tuning: the OLED shows what to do in each phase
# (with a countdown) and every raw VL53L1X reading is printed as
#   <ms> <mm> <range_status> <phase>
# Save the output and replay it through cup.py on the PC (tools: sim_cup).
# Needs WATCHDOG_S = 0 in config.py (it runs ~110 s from the REPL).
import time
import config as C
import hw
import ui

PHASES = (
    (12, "EMPTY", "hands away"),
    (16, "REACH x3", "touch, no change"),
    (12, "DROP 1 ITEM", "then hand away"),
    (12, "DROP ANOTHER", "then hand away"),
    (12, "TAKE 1 OUT", "then hand away"),
    (16, "PEN SLEEVE x3", "reach for a pen"),
    (12, "EMPTY", "hands away"),
)

screen = ui.Screen(hw.oled())
screen.status("up", 4)
s = hw.tof()
s.set_distance_mode(1)
s.set_timing_budget_in_ms(C.TOF_TIMING_BUDGET_MS)
s.set_inter_measurement_in_ms(C.TOF_INTER_MEAS_MS)
s.start_ranging()
print("# phases:", [p[1] for p in PHASES])
t0 = time.ticks_ms()
ends = []
total = 0
for secs, _, _ in PHASES:
    total += secs * 1000
    ends.append(total)
shown = None
while True:
    t = time.ticks_diff(time.ticks_ms(), t0)
    phase = next((i for i, e in enumerate(ends) if t < e), None)
    if phase is None:
        break
    left = (ends[phase] - t) // 1000
    if (phase, left) != shown:
        shown = (phase, left)
        _, title, hint = PHASES[phase]
        screen.show([title, hint, "", "{}s".format(left + 1), "step {}/{}".format(phase + 1, len(PHASES))], hi=0)
        screen.render(time.ticks_ms())
    if s.check_for_data_ready():
        mm = s.get_distance()
        st = s.get_range_status()
        s.clear_interrupt()
        print(t, mm, st, phase)
    time.sleep_ms(5)
s.stop_ranging()
screen.show(["done", "thanks!"])
screen.render(time.ticks_ms())
print("# done")
