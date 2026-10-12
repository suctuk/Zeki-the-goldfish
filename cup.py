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
# Only range status 0 readings count. Call tick(now) every loop; it returns
# "added" / "removed" / "fiddled" / None.

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
        self.ref = None       # stability tracker: value and since-when
        self.ref_t = 0
        self.active_t = 0
        self.last_mm = None   # latest valid median, for debugging / UI

    def _read(self):
        """Median of the last MEDIAN_N valid readings, or None if no new data."""
        s = self.s
        if not s.check_for_data_ready():
            return None
        mm = s.get_distance()
        status = s.get_range_status()
        s.clear_interrupt()
        if C.CUP_DEBUG:
            print("cup raw {:4d} mm st={} mode={} settled={}".format(mm, status, self.mode, self.settled))
        if status != 0:
            return None
        self.buf.append(mm)
        if len(self.buf) > C.MEDIAN_N:
            self.buf.pop(0)
        if len(self.buf) < C.MEDIAN_N:
            return None
        return sorted(self.buf)[C.MEDIAN_N // 2]

    def _stable(self, mm, now):
        """True once mm has stayed within +/-NOISE_MM of one value for SETTLE_MS."""
        if self.ref is None or abs(mm - self.ref) > C.NOISE_MM:
            self.ref = mm
            self.ref_t = now
            return False
        return time.ticks_diff(now, self.ref_t) >= C.SETTLE_MS

    def tick(self, now):
        mm = self._read()
        if mm is None:
            return None
        self.last_mm = mm

        if self.mode == BASELINE:
            if self._stable(mm, now):
                self._settle(mm, "baseline")
            return None

        if self.mode == SETTLED:
            if mm < self.settled - C.HAND_MM:
                self.mode = ACTIVE
                self.active_t = now
                self.ref = None
                if C.CUP_DEBUG:
                    print("cup: hand in ({} mm vs settled {})".format(mm, self.settled))
            elif abs(mm - self.settled) > C.DELTA_MM:
                if self._stable(mm, now):        # level moved with no hand seen
                    self._settle(mm, "drift")
            else:
                self.ref = None
            return None

        # ACTIVE
        if self._stable(mm, now):
            old = self.settled
            self._settle(mm, "after interaction")
            if mm < old - C.DELTA_MM:
                return "added"
            if mm > old + C.DELTA_MM:
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
