# main.py — runs automatically after boot.py on every power-up / reset.
#
# States: BOOT -> IDLE <-> CUP_EVENT, IDLE <-> SAY (online/offline lines),
#         IDLE --click--> INSPIRE -> IDLE
#         IDLE --turn---> BROWSE (scroll community ideas) -> IDLE
#         IDLE --new community idea--> SUBMISSION -> IDLE
# Events queue up while a screen is showing and play in order afterwards;
# INSPIRE is never interrupted. A click on a SAY/CUP_EVENT/SUBMISSION screen
# dismisses it. New community ideas are announced at most once per
# ANNOUNCE_GAP_MS; the rest wait behind the "N new" badge (BROWSE shows them).
#
# Missing hardware is never fatal: each part is optional, and an exception
# inside one loop tick is logged and the loop carries on. Ctrl-C (mpremote)
# still stops it.

import gc
import json
import time

import config as C
import community
import hw
import lines
import ui

IDLE, SAY, CUP_EVENT, INSPIRE = "idle", "say", "cup_event", "inspire"
BROWSE, SUBMISSION = "browse", "submission"
STATE_FILE = "state.json"
QUEUE_MAX = 5
FEED_PAGE = 5            # Apps Script MAX_PER_POLL: a full page means more may be waiting


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
        self.poller = None
        try:
            import net
            import secrets
            self.net = net.Net()
            url = getattr(secrets, "APPS_SCRIPT_URL", "")
            if url:
                self.poller = net.Poller(url)
        except Exception as e:   # e.g. no secrets.py: run fully offline
            print("boot: no wifi ({})".format(e))

        self.screen = ui.Screen(_try("oled", hw.oled))
        self.screen.say("hi, I'm Zeki")
        self.screen.render(time.ticks_ms())

        twist = _try("twist", hw.twist)
        self.mood = hw.Mood(twist, C)
        self.knob = _try("knob", lambda: hw.Knob(twist, C.LONG_PRESS_MS)) if twist else None
        self.knob_t = 0
        self.inspire = None
        buzzer = _try("buzzer", hw.buzzer)
        self.chime = hw.Chime(buzzer, C.CHIME_VOLUME) if buzzer else None
        self.cup = None
        tof = _try("VL53L1X", hw.tof)
        if tof:
            import cup
            self.cup = cup.Cup(tof)

        now = time.ticks_ms()
        self.store = self._load()
        self.community = community.load()
        self.queue = []
        self.state = SAY
        self.state_t = now
        self.show_ms = 3000          # splash, then the boot line
        self.pending = ["boot"]
        self.count_due = None
        self.praising = False        # green LEDs for added/fiddled, not for removed
        self.idle_t = 0
        self.idle_line = ""
        self.bars = 0
        self.bars_t = time.ticks_add(now, -2000)
        self.poll_t = time.ticks_add(now, -C.POLL_MS)          # first poll as soon as online
        self.poll_fails = 0
        self.announce_t = time.ticks_add(now, -C.ANNOUNCE_GAP_MS)
        self.to_review = 0           # from the feed: submissions waiting for Sena
        self.sub_item = None
        self.sub_rows = []
        self.sub_phase = 0
        self.browse_i = 0
        self.browse_t = 0
        gc.collect()
        print("boot: ready, count today {}, {} community ideas ({} unseen), mem_free {}".format(
            self.store["count"], len(self.community), len(self.store["unseen"]), gc.mem_free()))

    # --- persistence ---------------------------------------------------
    def _load(self):
        try:
            with open(STATE_FILE) as f:
                s = json.load(f)
        except (OSError, ValueError):
            s = {}
        s.setdefault("day", None)
        s.setdefault("count", 0)
        s.setdefault("last_id", 0)   # newest community idea id fetched (?since=)
        s.setdefault("unseen", [])   # community idea ids not shown yet
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
        self.idle_line = lines.pick("idle")
        self._draw_idle()

    def _draw_idle(self):
        rows = ui.wrap(self.idle_line)
        if self.to_review:
            rows = rows[:ui.MAX_ROWS - 2] + ["", "{} to review".format(self.to_review)]
        self.screen.show(rows)

    def _handle(self, kind, what):
        self.praising = what in ("added", "fiddled")
        if kind == "boot":
            self._show(SAY, lines.pick("boot"), C.EVENT_SHOW_MS)
        elif kind == "net":
            self._show(SAY, lines.pick(what), C.EVENT_SHOW_MS)
            if what == "online" and self.chime:
                self.chime.play(C.CHIME_ONLINE)
        elif what == "added":                   # already counted when detected
            self._show(CUP_EVENT, lines.pick("added"), C.EVENT_SHOW_MS)
            self.count_due = time.ticks_add(time.ticks_ms(), C.COUNT_AFTER_MS)
            if self.chime:
                self.chime.play(C.CHIME_PRAISE)
        elif what == "fiddled":
            self._show(CUP_EVENT, lines.pick("fiddled"), C.COUNT_AFTER_MS)
            print("cup: FIDDLED")
        elif what == "removed":
            self._show(CUP_EVENT, lines.pick("removed"), C.COUNT_AFTER_MS)
            print("cup: REMOVED")

    def _push(self, kind, what):
        if len(self.queue) < QUEUE_MAX:
            self.queue.append((kind, what))

    _CUP_RANK = {"removed": 0, "fiddled": 1, "added": 2}

    def _cup_event(self, what):
        """Count ADDED immediately; queue at most one cup screen (the best one)."""
        if what == "added":
            self._roll_day()
            self.store["count"] += 1
            self._save()
            print("cup: ADDED, count today", self.store["count"])
        for i, (kind, queued) in enumerate(self.queue):
            if kind == "cup":
                if self._CUP_RANK[what] > self._CUP_RANK[queued]:
                    self.queue[i] = ("cup", what)
                return
        self._push("cup", what)

    # --- community ideas -------------------------------------------------
    def _poll(self, now):
        res = self.poller.take()
        if res is not None:
            self._on_poll(res, now)
        if (self.net.online and not self.poller.busy
                and time.ticks_diff(now, self.poll_t) >= C.POLL_MS):
            self.poll_t = now
            self.poller.start(self.store["last_id"])

    def _on_poll(self, res, now):
        if isinstance(res, Exception):
            self.poll_fails += 1
            print("poll: failed x{} {!r}".format(self.poll_fails, res))
            return
        self.poll_fails = 0
        items, to_review = res
        if to_review != self.to_review:
            self.to_review = to_review
            if self.state == IDLE:
                self._draw_idle()
        if not items:
            return
        ids = [i["id"] for i in items if isinstance(i, dict) and isinstance(i.get("id"), int)]
        if ids:
            self.store["last_id"] = max([self.store["last_id"]] + ids)
        added = community.merge(self.community, items)
        if added:
            community.save(self.community)
            unseen = self.store["unseen"] + [i["id"] for i in added]
            self.store["unseen"] = [u for u in unseen if community.find(self.community, u)]
            print("poll: {} new idea(s), {} unseen, {} to review".format(
                len(added), len(self.store["unseen"]), to_review))
        self._save()
        if len(items) >= FEED_PAGE:              # a full page: fetch the rest soon
            self.poll_t = time.ticks_add(now, 2000 - C.POLL_MS)

    def _announce(self, now):
        item = None
        while self.store["unseen"] and item is None:
            item = community.find(self.community, self.store["unseen"].pop(0))
        self._save()
        if item is None:
            return
        self.announce_t = now
        self.sub_item = item
        self.sub_rows = ui.wrap(item["text"])
        self.sub_phase = 0
        pages = (len(self.sub_rows) + ui.MAX_ROWS - 2) // (ui.MAX_ROWS - 1)
        self._show(SUBMISSION, lines.pick("new_idea", name=item.get("name") or ""),
                   C.SUBMISSION_HEADER_MS + max(6000, pages * C.PAGE_MS + 1500))
        if self.chime:
            self.chime.play(C.CHIME_SUBMISSION)
        print("submission: showing #{}".format(item["id"]))

    def _start_browse(self, now):
        if not self.community:
            self._show(SAY, "No ideas from friends yet. Scan the QR code!", 4000)
            return
        self.state = BROWSE
        self.browse_i = 0                       # newest first
        self.browse_t = now
        self._browse_show()

    def _browse_show(self):
        item = self.community[len(self.community) - 1 - self.browse_i]
        if item["id"] in self.store["unseen"]:
            self.store["unseen"].remove(item["id"])
            self._save()
        self.screen.paged(community.title(item), ui.wrap(item["text"]))

    def _browse_tick(self, now, events):
        for ev in events:
            self.browse_t = now
            if ev[0] == "turn":
                n = len(self.community)
                self.browse_i = (self.browse_i + (1 if ev[1] > 0 else -1)) % n
                self._browse_show()
            else:                                  # click or long press: done
                self._enter_idle(now)
                return
        if time.ticks_diff(now, self.browse_t) > C.BROWSE_TIMEOUT_MS:
            self._enter_idle(now)

    # --- loop ----------------------------------------------------------------
    def tick(self, now):
        if self.net:
            ev = self.net.tick(now)
            if ev:
                self._push("net", ev)
            if self.net.time_synced and self.store["day"] != today():
                self._roll_day()
            if self.poller:
                self._poll(now)
        if self.cup:
            ev = self.cup.tick(now)
            if ev:
                self._cup_event(ev)
        events = []
        if self.knob and time.ticks_diff(now, self.knob_t) >= C.TWIST_POLL_MS:
            self.knob_t = now
            events = self.knob.poll()

        if self.state == INSPIRE:
            if not self.inspire.tick(now, events):
                self.inspire = None
                gc.collect()
                self._enter_idle(now)
        elif self.state == BROWSE:
            self._browse_tick(now, events)
        elif any(e[0] == "click" for e in events):
            if self.state == IDLE:
                import inspire
                self.state = INSPIRE
                self.inspire = inspire.Inspire(self.screen, self.chime)
            else:                                   # dismiss the current screen
                self.pending = []
                self.count_due = None
                self._enter_idle(now)
        else:
            turn = sum(e[1] for e in events if e[0] == "turn")
            if turn and self.state == IDLE:
                self._start_browse(now)
            elif turn and self.state == SUBMISSION and self.sub_phase == 1:
                self.screen.next_page(1 if turn > 0 else -1)

        if self.state in (SAY, CUP_EVENT, SUBMISSION):
            elapsed = time.ticks_diff(now, self.state_t)
            if self.count_due is not None and time.ticks_diff(now, self.count_due) >= 0:
                self.count_due = None
                self.screen.say(lines.pick("count", n=self.store["count"]))
            if self.state == SUBMISSION and self.sub_phase == 0 and elapsed >= C.SUBMISSION_HEADER_MS:
                self.sub_phase = 1
                self.screen.paged(community.title(self.sub_item), self.sub_rows)
            if elapsed >= self.show_ms:
                self.count_due = None
                if self.pending:
                    self._handle(self.pending.pop(0), None)
                else:
                    self._enter_idle(now)
        if self.state == IDLE:
            if self.queue:
                self._handle(*self.queue.pop(0))
            elif self.store["unseen"] and time.ticks_diff(now, self.announce_t) >= C.ANNOUNCE_GAP_MS:
                self._announce(now)
            elif time.ticks_diff(now, self.idle_t) >= C.IDLE_LINE_MS:
                self._enter_idle(now)

        online = self.net is not None and self.net.online
        if self.state == INSPIRE:
            self.mood.set(self.inspire.color)
        elif self.state == CUP_EVENT and self.praising:
            self.mood.set(C.COLOR_PRAISE)
        elif self.state in (SUBMISSION, BROWSE):
            self.mood.set(C.COLOR_SUBMISSION)
        elif online or self.net is None or self.net.reported is not False:
            self.mood.set(C.COLOR_IDLE, breathe=self.state == IDLE)
        else:
            self.mood.set(C.COLOR_OFFLINE, breathe=self.state == IDLE)
        self.mood.tick(now)
        if self.chime:
            self.chime.tick(now)

        badge = len(self.store["unseen"])
        if self.net is None:
            self.screen.status("offline", badge=badge)
        elif online:
            if time.ticks_diff(now, self.bars_t) >= 2000:
                self.bars_t = now
                self.bars = ui.wifi_bars(self.net.rssi())
            self.screen.status("up", self.bars, badge)
        elif self.net.state == "connecting":
            self.screen.status("connecting", badge=badge)
        else:
            self.screen.status("offline", badge=badge)
        self.screen.render(now)

    def run(self):
        errors = 0
        last = time.ticks_ms()
        while True:
            now = time.ticks_ms()
            gap = time.ticks_diff(now, last)
            if gap > C.STALL_LOG_MS:
                print("loop: stalled {} ms (state {})".format(gap, self.state))
            last = now
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
