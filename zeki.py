# zeki.py — the app: state machine + main loop. main.py (2 lines) imports
# this at boot; deploy ships it precompiled as zeki.mpy (see tools/deploy.py).
#
# States: BOOT -> IDLE <-> CUP_EVENT, IDLE <-> SAY (online/offline lines),
#         IDLE --click--> INSPIRE -> IDLE
#         IDLE --turn---> BROWSE (scroll community ideas) -> IDLE
#         IDLE --new community idea--> SUBMISSION -> IDLE
#         IDLE --hold the knob--> check for ideas now (announces at once, or
#                                 "No new ideas yet") -> IDLE / SUBMISSION
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
        import inspire
        inspire.seeded()             # load ideas.json once, now, while the heap is unfragmented
        self.queue = []
        self.state = SAY
        self.state_t = now
        self.show_ms = 3000          # splash, then the boot line
        self.pending = ["boot"]
        # Woke from a "quick nap" (manual check rebooted to free RAM)? Then skip
        # the boot line and check for ideas as soon as Wi-Fi is up. napped also
        # stops a second nap if RAM is somehow still short (no reboot loops).
        self.napped = bool(self.store.pop("check_on_boot", False))
        self.check_after_nap = self.napped
        if self.napped:
            self.pending = []
            self._save()
        self.count_due = None
        self.praising = False        # green LEDs for added/fiddled, not for removed
        self.idle_t = 0
        self.idle_line = ""
        self.bars = 0
        self.bars_t = time.ticks_add(now, -2000)
        self.poll_t = time.ticks_add(now, -C.POLL_MS)          # first poll as soon as idle
        self.poll_wait = C.POLL_MS   # grows on failures (backoff)
        self.poll_fails = 0
        self.input_t = time.ticks_add(now, -C.POLL_QUIET_MS)   # last knob event
        self.manual_poll = False     # hold the knob in idle = "check for ideas now"
        self.manual_t = None         # when a manual check started waiting for RAM
        self.gc_due = False          # collect on the next tick after a poll
        self.ram_t = time.ticks_add(now, -2000)
        self.ram_was_ok = True
        self.ram_low_t = None        # since when RAM has been too low to poll
        self.ram_low_last = now      # last low reading (episode = no gap > 10 s)
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
    def _poll_due(self, now):
        """A poll blocks Zeki for 4-7 s (see net.Poller), so only when nothing
        is going on: idle, nothing queued, knob untouched for POLL_QUIET_MS, no
        cup interaction in progress, no chime playing, and enough RAM."""
        return (self.net.online and self.state == IDLE and not self.queue
                and time.ticks_diff(now, self.input_t) >= C.POLL_QUIET_MS
                and (self.cup is None or self.cup.mode != "active")
                and (self.chime is None or self.chime.next_at is None)
                and time.ticks_diff(now, self.poll_t) >= self.poll_wait
                and self._ram_ok(now))

    def _ram_ok(self, now):
        """Is there a free IDF block big enough for TLS? (net.largest_block()
        runs a GC, so check at most every 2 s.) Day 4: polls that started
        with ~23 KB hung or failed with OSError(16)."""
        if time.ticks_diff(now, self.ram_t) < 2000:
            return self.ram_was_ok
        self.ram_t = now
        import net
        big = net.largest_block()
        self.ram_was_ok = big >= getattr(C, "POLL_MIN_BLOCK", 40_000)
        if self.ram_was_ok:
            self.ram_low_t = None
            return True
        print("poll: waiting for RAM (largest free block {} bytes)".format(big))
        # One continuous episode only: a low reading after a gap (RAM may have
        # recovered unobserved in between) starts the timer again.
        if self.ram_low_t is None or time.ticks_diff(now, self.ram_low_last) > 10_000:
            self.ram_low_t = now
        self.ram_low_last = now
        if time.ticks_diff(now, self.ram_low_t) > getattr(C, "RAM_REBOOT_MS", 300_000):
            # Only reached when Zeki is idle and quiet (see _poll_due). The heap
            # grew into IDF RAM and won't give it back: a reboot (~10 s, all
            # state is in files) is the reliable way to get it back.
            print("poll: RAM never came back, rebooting to free it")
            self._save()
            import machine
            machine.reset()
        return False

    def _poll_now(self, manual=False):
        """Blocking poll. manual=True: you held the knob in idle ("check now"):
        say so on screen, then announce a new idea right away (no 5 min gap),
        or say there's nothing new."""
        if manual:
            self.screen.say("Checking for new ideas...")
        self._status(time.ticks_ms(), syncing=True)
        self.screen.render(time.ticks_ms())           # show the arrow before blocking
        res = self.poller.poll(self.store["last_id"])
        now = time.ticks_ms()
        self.poll_t = now
        self.manual_t = None
        self.ram_low_t = None
        self.gc_due = True                        # next tick: free the TLS buffers
        self.ram_t = time.ticks_add(now, -2000)   # next RAM check must be fresh
        added = self._on_poll(res, now)
        if self.poll_fails:
            self.poll_wait = min(C.POLL_MS << min(self.poll_fails, 8), C.POLL_BACKOFF_MAX_MS)
        else:
            self.poll_wait = C.POLL_MS
        self._status(now)                              # arrow off; badge / X up to date
        if manual:
            print("poll: manual check ->", "failed" if added is None else "{} new".format(added))
            if added is None:
                self._show(SAY, "Couldn't reach the idea box. Try again in a bit.", 4000)
            elif added or self.store["unseen"]:
                self.announce_t = time.ticks_add(now, -C.ANNOUNCE_GAP_MS)   # show it now
                self._draw_idle()
            else:
                self._show(SAY, "No new ideas yet. (I checked. I think.)", 3500)

    def _on_poll(self, res, now):
        """Handle a poll result. Returns how many ideas were new (None = failed)."""
        if isinstance(res, Exception):
            self.poll_fails += 1
            print("poll: failed x{} {!r}".format(self.poll_fails, res))
            return None
        self.poll_fails = 0
        items, to_review = res
        if to_review != self.to_review:
            self.to_review = to_review
            if self.state == IDLE:
                self._draw_idle()
        if not items:
            return 0
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
        return len(added)

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
        if self.cup:
            ev = self.cup.tick(now)
            if ev:
                self._cup_event(ev)
        events = []
        if self.knob and time.ticks_diff(now, self.knob_t) >= C.TWIST_POLL_MS:
            self.knob_t = now
            events = self.knob.poll()
            if events:
                self.input_t = now

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
                self.inspire = inspire.Inspire(self.screen, self.chime, self.community)
            else:                                   # dismiss the current screen
                self.pending = []
                self.count_due = None
                self._enter_idle(now)
        elif self.state == IDLE and any(e[0] == "long" for e in events):
            self.manual_poll = True                  # hold in idle = check for ideas now
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

        self._status(now)
        self.screen.render(now)
        if self.check_after_nap and self.state == IDLE and self.poller and self.net.online:
            self.check_after_nap = False         # the check the nap was for
            self.manual_poll = True
        if self.gc_due:                          # free the last poll's TLS buffers,
            self.gc_due = False                  # from a frame that no longer holds them
            gc.collect()
        if self.manual_poll:
            if not (self.poller and self.net.online):
                self.manual_poll = False
                self._show(SAY, lines.pick("offline"), 4000)
            elif self._ram_ok(now):
                self.manual_poll = False
                self._poll_now(manual=True)
            elif self.manual_t is None:          # RAM still held: say so, give it a moment
                self.manual_t = now
                self.screen.say("One moment...")
            elif not self.napped and time.ticks_diff(now, self.manual_t) > 4000:
                # RAM is chopped up and won't come back by itself; the first
                # poll after a fresh boot always works. Reboot (~10 s, all state
                # is in files) and check first thing after waking.
                print("poll: manual check needs RAM, napping (reboot) to free it")
                self.screen.say("Making room... (quick nap)")
                self.screen.render(now)
                self.store["check_on_boot"] = True
                self._save()
                import machine
                machine.reset()
            elif time.ticks_diff(now, self.manual_t) > 20_000:
                self.manual_poll = False
                self._show(SAY, "Couldn't reach the idea box. Try again in a bit.", 4000)
        elif self.poller and self._poll_due(now):
            self._poll_now()

    def _status(self, now, syncing=False):
        badge = len(self.store["unseen"])
        online = self.net is not None and self.net.online
        if self.net is None:
            self.screen.status("offline", badge=badge)
        elif online:
            if time.ticks_diff(now, self.bars_t) >= 2000:
                self.bars_t = now
                self.bars = ui.wifi_bars(self.net.rssi())
            self.screen.status("up", self.bars, badge, noinet=self.poll_fails >= 2, syncing=syncing)
        elif self.net.state == "connecting":
            self.screen.status("connecting", badge=badge)
        else:
            self.screen.status("offline", badge=badge)

    def heartbeat(self, now):
        """One status line, so "is it working?" is answered by the log."""
        p = self.poller
        if p is None:
            poll = "off"
        elif p.last_ok is not None:
            poll = "ok {}s ago, took {} ms, next in {}s".format(
                time.ticks_diff(now, p.last_ok) // 1000, p.last_ms,
                max(0, self.poll_wait - time.ticks_diff(now, self.poll_t)) // 1000)
        else:
            poll = "none yet"
        if p is not None and self.poll_fails:
            poll += ", {} fails ({})".format(self.poll_fails, p.last_err)
        net = "none" if self.net is None else self.net.state
        rssi = self.net.rssi() if self.net is not None and self.net.online else 0
        try:
            import esp32
            info = esp32.idf_heap_info(esp32.HEAP_DATA)
            idf = "{}k/{}k".format(sum(i[1] for i in info) // 1024, max(i[2] for i in info) // 1024)
        except Exception:
            idf = "?"
        gc.collect()
        print("hb: {} | net {} {}dBm | poll {} | ideas {} unseen {} review {} | count {} | "
              "heap {}k idf {}".format(self.state, net, rssi, poll, len(self.community),
                                       len(self.store["unseen"]), self.to_review,
                                       self.store["count"], gc.mem_free() // 1024, idf))

    def run(self):
        errors = 0
        last = time.ticks_ms()
        hb_t = last
        wdt = None
        wdt_s = getattr(C, "WATCHDOG_S", 0)   # getattr: an older config.py must not crash boot
        if wdt_s:
            from machine import WDT
            wdt = WDT(timeout=wdt_s * 1000)
            print("boot: watchdog on, reboots if the loop stalls {} s".format(wdt_s))
        while True:
            if wdt:
                wdt.feed()
            now = time.ticks_ms()
            gap = time.ticks_diff(now, last)
            if gap > C.STALL_LOG_MS:
                print("loop: stalled {} ms (state {})".format(gap, self.state))
            last = now
            if time.ticks_diff(now, hb_t) >= C.HEARTBEAT_MS:
                hb_t = now
                try:
                    self.heartbeat(now)
                except Exception as e:
                    print("hb: failed", repr(e))
            try:
                self.tick(now)
                errors = 0
            except Exception as e:
                errors += 1
                print("tick error:", repr(e))
                time.sleep_ms(min(2000, 100 * errors))
            time.sleep_ms(C.LOOP_MS)


def start():
    try:
        import machine
        if machine.reset_cause() == machine.WDT_RESET:
            print("boot: restarted by the watchdog (the loop had frozen)")
    except Exception:
        pass
    gc.collect()
    Zeki().run()
