# net.py — non-blocking Wi-Fi. Call tick(now) every loop.
#
# Tries secrets.WIFI in order, WIFI_CONNECT_TIMEOUT_MS each. After a full
# failed pass, waits WIFI_RETRY_MS. Never blocks the loop (except a short
# NTP request, 3 s after connecting, until the clock is set).
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
    """Fetches the Apps Script feed on a background thread, so the ~3 s HTTPS
    round trip (TLS + Google's 302 to googleusercontent.com) never freezes the
    main loop. The thread touches only the network, never I2C.

    start(since) kicks off one request; take() returns None (nothing yet),
    an Exception, or (ideas, pending) once it's done.
    """

    def __init__(self, url):
        import requests          # load once on the main thread, not inside the poll
        self.url = url
        self.busy = False
        self.started = 0
        self._result = None

    def start(self, since):
        if self.busy:
            return False
        self.busy = True
        self.started = time.ticks_ms()
        try:
            import _thread
            _thread.stack_size(config.POLL_STACK)
            _thread.start_new_thread(self._run, (since,))
        except Exception as e:            # out of memory for a thread: try next time
            self.busy = False
            self._result = e
            return False
        return True

    def _run(self, since):
        try:
            import requests
            r = requests.get("{}?since={}".format(self.url, since), timeout=config.POLL_TIMEOUT_S)
            try:
                if r.status_code != 200:
                    raise OSError("HTTP {}".format(r.status_code))
                data = r.json()
            finally:
                r.close()
            self._result = (data.get("ideas") or [], int(data.get("pending") or 0))
        except Exception as e:
            self._result = e
        self.busy = False

    def take(self):
        r, self._result = self._result, None
        return r
