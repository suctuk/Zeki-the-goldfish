# net.py — non-blocking Wi-Fi. Call tick(now) every loop.
#
# Tries secrets.WIFI in order, WIFI_CONNECT_TIMEOUT_MS each. After a full
# failed pass, waits WIFI_RETRY_MS. Never blocks the loop (except a short
# NTP request, 3 s after connecting, until the clock is set). Poller.poll()
# below DOES block (4-7 s); zeki.py only calls it when idle and quiet.
#
# tick() returns "online" / "offline" for Zeki to comment on:
#   - boot -> first connect: silent (no "it's back!" when it never left)
#   - "offline" only once a reconnect pass has failed, so blips stay quiet
#   - "online" when coming back after an announced "offline"

import time
import network
import config
import secrets

_FAIL = tuple(getattr(network, n) for n in
              ("STAT_WRONG_PASSWORD", "STAT_NO_AP_FOUND", "STAT_CONNECT_FAIL")
              if hasattr(network, n))


class Net:
    def __init__(self):
        try:
            network.hostname(config.HOSTNAME)
        except Exception:
            pass
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.state = "idle"          # "idle" (waiting to retry) | "connecting" | "up"
        self.i = 0                   # index into secrets.WIFI
        self.t = 0                   # when the current attempt started
        self.next_try = time.ticks_ms()
        self.reported = None         # None at boot, then True/False = last announced
        self.time_synced = False
        self.next_ntp = 0
        self.ssid = None
        self.tries = 0               # connect() calls for the current network
        self.try_t = 0
        if self.wlan.isconnected():  # still up from before a soft reset: keep it
            try:
                self.ssid = self.wlan.config("ssid")
            except Exception:
                self.ssid = "?"
            self._up(time.ticks_ms())

    @property
    def online(self):
        return self.state == "up"

    def rssi(self):
        try:
            return self.wlan.status("rssi")
        except Exception:
            return -100

    def tick(self, now):
        if self.state == "up":
            if self.wlan.isconnected():
                if not self.time_synced and time.ticks_diff(now, self.next_ntp) >= 0:
                    self._sync_time(now)
                return None
            print("net: lost", self.ssid)
            self.state = "idle"
            self.i = 0
            self.next_try = now           # reconnect right away, announce only if that fails
            return None

        if self.state == "connecting":
            if self.wlan.isconnected():
                return self._up(now)
            elapsed = time.ticks_diff(now, self.t)
            status = self.wlan.status()
            # The ESP32 can report a spurious auth failure (202) when connect()
            # follows a disconnect too quickly: retry the same network first.
            failed = status in _FAIL and time.ticks_diff(now, self.try_t) > 1500
            if failed and self.tries < 3 and elapsed < config.WIFI_CONNECT_TIMEOUT_MS:
                print("net: {} status {}, retrying".format(self.ssid, status))
                self._connect()
                return None
            if failed or elapsed > config.WIFI_CONNECT_TIMEOUT_MS:
                print("net: {} failed (status {})".format(self.ssid, self.wlan.status()))
                self.i += 1
                if self.i < len(secrets.WIFI):
                    self._start(now)
                    return None
                self.i = 0
                self.state = "idle"
                self.next_try = time.ticks_add(now, config.WIFI_RETRY_MS)
                if self.reported is not False:
                    self.reported = False
                    return "offline"
            return None

        if time.ticks_diff(now, self.next_try) >= 0:
            self._start(now)
        return None

    def _start(self, now):
        self.ssid = secrets.WIFI[self.i][0]
        print("net: trying", self.ssid)
        self.tries = 0
        self.state = "connecting"
        self.t = now
        self._connect()

    def _connect(self):
        self.tries += 1
        self.try_t = time.ticks_ms()
        try:
            self.wlan.disconnect()
        except OSError:
            pass
        time.sleep_ms(100)
        try:
            self.wlan.connect(self.ssid, secrets.WIFI[self.i][1])
        except OSError as e:
            print("net: connect error", e)

    def _up(self, now):
        self.state = "up"
        print("net: up on {} ({}), rssi {}".format(self.ssid, self.wlan.ifconfig()[0], self.rssi()))
        if not self.time_synced:
            self.next_ntp = time.ticks_add(now, 3000)   # first NTP right at connect times out
        was = self.reported
        self.reported = True
        return "online" if was is False else None

    def _sync_time(self, now):
        """Set the RTC to UTC over NTP (blocks ~1 s max). Retries every 15 s."""
        try:
            import ntptime
            ntptime.timeout = 1
            ntptime.settime()
            self.time_synced = True
            print("net: time synced (UTC)", time.localtime()[:6])
        except Exception as e:
            print("net: ntp failed", e)
            self.next_ntp = time.ticks_add(now, 15_000)


class Poller:
    """Fetches the Apps Script feed: poll(since) -> (ideas, pending) or an
    Exception. BLOCKING, on the main thread, for 4-7 s (two TLS handshakes:
    script.google.com, then Google's 302 to script.googleusercontent.com).
    The caller only polls when Zeki is idle and quiet, and shows "syncing".

    Why not a background thread (tried Day 4): thread stack (16 KB) + TLS
    buffers took ALL of the internal RAM (heartbeat showed idf 0k mid-poll),
    so polls hung or failed with OSError(16), neopixel writes failed with
    ENOMEM, and a second thread made the ESP32 abort() and reboot. On the
    main thread with nothing else running, polls succeeded every time.
    """

    def __init__(self, url):
        import requests          # load once at boot, not in the middle of a poll
        self.url = url
        self.last_ok = None      # ticks_ms of the last successful poll
        self.last_err = None     # repr of the last failure
        self.last_ms = 0         # how long the last poll took

    def poll(self, since):
        """Each poll's two TLS connections hold ~43 KB of IDF internal RAM
        until their socket objects are garbage-collected. Day 4 bug: the
        gc.collect() ran while `r` was still a live local, so nothing was
        freed, nothing else triggered a GC for minutes, and the NEXT poll
        starved (OSError(16) or a hung handshake). So: drop `r` first, and
        the caller collects again from the main loop and checks the RAM
        (largest_block()) before every poll."""
        import gc
        t = time.ticks_ms()
        r = None
        try:
            import requests
            r = requests.get("{}?since={}".format(self.url, since), timeout=config.POLL_TIMEOUT_S)
            if r.status_code != 200:
                raise OSError("HTTP {}".format(r.status_code))
            data = r.json()
            self.last_ok = time.ticks_ms()
            return (data.get("ideas") or [], int(data.get("pending") or 0))
        except Exception as e:
            self.last_err = repr(e)
            return e
        finally:
            if r is not None:
                try:
                    r.close()
                except Exception:
                    pass
            r = None
            self.last_ms = time.ticks_diff(time.ticks_ms(), t)
            gc.collect()


def largest_block():
    """Largest free block of IDF internal RAM, after a GC (TLS needs ~25-40 KB
    contiguous). Returns a big number off-device so the PC simulation works."""
    import gc
    gc.collect()
    try:
        import esp32
        return max(i[2] for i in esp32.idf_heap_info(esp32.HEAP_DATA))
    except ImportError:
        return 1 << 20
