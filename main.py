# main.py — runs automatically after boot.py on every power-up / reset.
#
# States (Day 2): BOOT -> IDLE <-> CUP_EVENT, IDLE <-> SAY (online/offline lines).
# INSPIRE / BROWSE / SUBMISSION arrive on later days.
# Events queue up while a screen is showing and play in order afterwards.
#
# Missing hardware is never fatal: each part is optional, and an exception
# inside one loop tick is logged and the loop carries on. Ctrl-C (mpremote)
# still stops it.

import gc
import json
import time

import config as C
import hw
import lines
import ui

IDLE, SAY, CUP_EVENT = "idle", "say", "cup_event"
STATE_FILE = "state.json"
QUEUE_MAX = 5


def _try(label, fn):
    try:
        return fn()
    except Exception as e:
        print("boot: no {} ({})".format(label, e))
        return None


def today():
    """Local [y, m, d], or None if the RTC was never set (no NTP yet)."""
    t = time.time()
    if time.localtime(t)[0] < 2025:
        return None
    return list(time.localtime(t + C.TZ_OFFSET_H * 3600)[:3])


class Zeki:
    def __init__(self):
        # Wi-Fi FIRST: the ESP32 Wi-Fi driver needs internal RAM, and the
        # MicroPython heap grows into it as drivers load. Started later, it
        # fails with "WiFi Out of Memory".
        self.net = None
        try:
            import net
            self.net = net.Net()
        except Exception as e:   # e.g. no secrets.py: run fully offline
            print("boot: no wifi ({})".format(e))

        self.screen = ui.Screen(_try("oled", hw.oled))
        self.screen.say("hi, I'm Zeki")
        self.screen.render(time.ticks_ms())

        twist = _try("twist", hw.twist)
        self.mood = hw.Mood(twist, C)
        buzzer = _try("buzzer", hw.buzzer)
        self.chime = hw.Chime(buzzer, C.CHIME_VOLUME) if buzzer else None
        self.cup = None
        tof = _try("VL53L1X", hw.tof)
        if tof:
            import cup
            self.cup = cup.Cup(tof)

        self.store = self._load()
        self.queue = []
        self.state = SAY
        self.state_t = time.ticks_ms()
        self.show_ms = 3000          # splash, then the boot line
        self.pending = ["boot"]
        self.count_due = None
        self.praising = False        # green LEDs for added/fiddled, not for removed
        self.idle_t = 0
        self.bars = 0
        self.bars_t = time.ticks_add(time.ticks_ms(), -2000)
        gc.collect()
        print("boot: ready, count today {}, mem_free {}".format(self.store["count"], gc.mem_free()))

    # --- persistence ---------------------------------------------------
    def _load(self):
        try:
            with open(STATE_FILE) as f:
                s = json.load(f)
        except (OSError, ValueError):
            s = {}
        s.setdefault("day", None)
        s.setdefault("count", 0)
        return s

    def _save(self):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self.store, f)
        except OSError as e:
            print("state: save failed", e)

    def _roll_day(self):
        d = today()
        if d is None or d == self.store["day"]:
            return
        if self.store["day"] is not None:
            print("state: new day {}, count {} -> 0".format(d, self.store["count"]))
            self.store["count"] = 0
        self.store["day"] = d
        self._save()

    # --- screens -----------------------------------------------------------
    def _show(self, state, text, ms):
        self.state = state
        self.state_t = time.ticks_ms()
        self.show_ms = ms
        self.screen.say(text)

    def _enter_idle(self, now):
        self.state = IDLE
        self.idle_t = now
        self.screen.say(lines.pick("idle"))

    def _handle(self, kind, what):
        self.praising = what in ("added", "fiddled")
        if kind == "boot":
            self._show(SAY, lines.pick("boot"), C.EVENT_SHOW_MS)
        elif kind == "net":
            self._show(SAY, lines.pick(what), C.EVENT_SHOW_MS)
            if what == "online" and self.chime:
                self.chime.play(C.CHIME_ONLINE)
        elif what == "added":
            self._roll_day()
            self.store["count"] += 1
            self._save()
            self._show(CUP_EVENT, lines.pick("added"), C.EVENT_SHOW_MS)
            self.count_due = time.ticks_add(time.ticks_ms(), C.COUNT_AFTER_MS)
            if self.chime:
                self.chime.play(C.CHIME_PRAISE)
            print("cup: ADDED, count today", self.store["count"])
        elif what == "fiddled":
            self._show(CUP_EVENT, lines.pick("fiddled"), C.COUNT_AFTER_MS)
            print("cup: FIDDLED")
        elif what == "removed":
            self._show(CUP_EVENT, lines.pick("removed"), C.COUNT_AFTER_MS)
            print("cup: REMOVED")

    def _push(self, kind, what):
        if len(self.queue) < QUEUE_MAX:
            self.queue.append((kind, what))

    # --- loop ----------------------------------------------------------------
    def tick(self, now):
        if self.net:
            ev = self.net.tick(now)
            if ev:
                self._push("net", ev)
            if self.net.time_synced and self.store["day"] != today():
                self._roll_day()
        if self.cup:
            ev = self.cup.tick(now)
            if ev:
                self._push("cup", ev)

        if self.state != IDLE:
            if self.count_due is not None and time.ticks_diff(now, self.count_due) >= 0:
                self.count_due = None
                self.screen.say(lines.pick("count", n=self.store["count"]))
            if time.ticks_diff(now, self.state_t) >= self.show_ms:
                self.count_due = None
                if self.pending:
                    self._handle(self.pending.pop(0), None)
                else:
                    self._enter_idle(now)
        if self.state == IDLE:
            if self.queue:
                self._handle(*self.queue.pop(0))
            elif time.ticks_diff(now, self.idle_t) >= C.IDLE_LINE_MS:
                self._enter_idle(now)

        online = self.net is not None and self.net.online
        if self.state == CUP_EVENT and self.praising:
            self.mood.set(C.COLOR_PRAISE)
        elif online or self.net is None or self.net.reported is not False:
            self.mood.set(C.COLOR_IDLE, breathe=self.state == IDLE)
        else:
            self.mood.set(C.COLOR_OFFLINE, breathe=self.state == IDLE)
        self.mood.tick(now)
        if self.chime:
            self.chime.tick(now)

        if self.net is None:
            self.screen.status("offline")
        elif online:
            if time.ticks_diff(now, self.bars_t) >= 2000:
                self.bars_t = now
                self.bars = ui.wifi_bars(self.net.rssi())
            self.screen.status("up", self.bars)
        elif self.net.state == "connecting":
            self.screen.status("connecting")
        else:
            self.screen.status("offline")
        self.screen.render(now)

    def run(self):
        errors = 0
        while True:
            now = time.ticks_ms()
            try:
                self.tick(now)
                errors = 0
            except Exception as e:
                errors += 1
                print("tick error:", repr(e))
                time.sleep_ms(min(2000, 100 * errors))
            time.sleep_ms(C.LOOP_MS)


if __name__ == "__main__":     # true at boot; tests can `import main` without running
    gc.collect()
    Zeki().run()
