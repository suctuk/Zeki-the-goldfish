# cup.py — "detect the interaction, not the object" (see spec: cup detection).
#
#   BASELINE -> readings stable for SETTLE_MS                 -> SETTLED
#   SETTLED  -> median < settled - HAND_MM (hand in the cup)   -> ACTIVE
#   ACTIVE   -> stable within +/-NOISE_MM for SETTLE_MS -> compare:
#                 new < settled - DELTA_MM -> "added"
#                 new > settled + DELTA_MM -> "removed"
#                 otherwise                -> "fiddled"
#               settled = new (rebaseline every time)
#   ACTIVE   -> never settles within ACTIVE_TIMEOUT_MS -> BASELINE (no event)
#   SETTLED  -> stable at a different level with no hand seen -> silent rebaseline
#
# Range status (ST codes): 0/6 valid; 2 (signal fail) and 4 (out of bounds)
# mean nothing in range -> TOF_FAR_MM; 3 (below min range) -> 0 mm; anything
# else is dropped. Baselines closer than MIN_SETTLE_MM are refused, so a hand
# resting on the lens can't become "settled" (Day 3 bug: settled at 0-16 mm,
# then far readings were all dropped and the cup never recovered).
# Call tick(now) every loop; it returns "added" / "removed" / "fiddled" / None.

import time
import config as C

BASELINE, SETTLED, ACTIVE = "baseline", "settled", "active"


class Cup:
    def __init__(self, sensor):
        self.s = sensor
        sensor.set_distance_mode(1)   # short: <=1.3 m, better ambient immunity
        sensor.set_timing_budget_in_ms(C.TOF_TIMING_BUDGET_MS)
        sensor.set_inter_measurement_in_ms(C.TOF_INTER_MEAS_MS)
        sensor.start_ranging()
        self.buf = []
        self.mode = BASELINE
        self.settled = None
        self.ref = None       # stability tracker: first value, since-when,
        self.ref_t = 0        # and the running sum/count of the stable window
        self.win_sum = 0
        self.win_n = 0
        self.active_t = 0
        self.last_mm = None   # latest median, for debugging / UI
        self.last_raw = None  # (mm, status) of the latest reading

    def _read(self):
        """Median of the last MEDIAN_N valid readings, or None if no new data."""
        s = self.s
        if not s.check_for_data_ready():
            return None
        mm = s.get_distance()
        status = s.get_range_status()
        s.clear_interrupt()
        self.last_raw = (mm, status)
        if C.CUP_DEBUG:
            print("cup raw {:4d} mm st={} mode={} settled={}".format(mm, status, self.mode, self.settled))
        if status in (2, 4):
            mm = C.TOF_FAR_MM
        elif status == 3:
            mm = 0
        elif status not in (0, 6):
            return None
        self.buf.append(mm)
        if len(self.buf) > C.MEDIAN_N:
            self.buf.pop(0)
        if len(self.buf) < C.MEDIAN_N:
            return None
        return sorted(self.buf)[C.MEDIAN_N // 2]

    def _stable(self, mm, now):
        """True once mm has stayed within +/-NOISE_MM of one value for SETTLE_MS.
        self.level() is then the mean of that window (more precise than the
        first reading, since the band is wider than DELTA_MM)."""
        if self.ref is None or abs(mm - self.ref) > C.NOISE_MM:
            self.ref = mm
            self.ref_t = now
            self.win_sum = mm
            self.win_n = 1
            return False
        self.win_sum += mm
        self.win_n += 1
        return time.ticks_diff(now, self.ref_t) >= C.SETTLE_MS

    def level(self):
        return self.win_sum // self.win_n

    def tick(self, now):
        mm = self._read()
        if mm is None:
            return None
        self.last_mm = mm

        if self.mode == BASELINE:
            if self._stable(mm, now) and self.level() >= C.MIN_SETTLE_MM:
                self._settle(self.level(), "baseline")
            return None

        if self.mode == SETTLED:
            if mm < self.settled - C.HAND_MM:
                self.mode = ACTIVE
                self.active_t = now
                self.ref = None
                if C.CUP_DEBUG:
                    print("cup: hand in ({} mm vs settled {})".format(mm, self.settled))
            elif abs(mm - self.settled) > C.DELTA_MM:
                if self._stable(mm, now) and self.level() >= C.MIN_SETTLE_MM:   # moved, no hand
                    self._settle(self.level(), "drift")
            else:
                self.ref = None
            return None

        # ACTIVE
        if self._stable(mm, now) and self.level() >= C.MIN_SETTLE_MM:
            old = self.settled
            new = self.level()
            self._settle(new, "after interaction")
            if new < old - C.DELTA_MM:
                return "added"
            if new > old + C.DELTA_MM:
                return "removed"
            return "fiddled"
        if time.ticks_diff(now, self.active_t) > C.ACTIVE_TIMEOUT_MS:
            print("cup: interaction never settled, relearning baseline")
            self.mode = BASELINE
            self.ref = None
        return None

    def _settle(self, mm, why):
        if C.CUP_DEBUG or why != "after interaction":
            print("cup: settled {} -> {} mm ({})".format(self.settled, mm, why))
        self.settled = mm
        self.mode = SETTLED
        self.ref = None
