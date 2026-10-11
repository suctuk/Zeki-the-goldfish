# HTTPS: GET a URL that 302-redirects to a different domain and confirm
# requests follows it (Apps Script does the same: script.google.com ->
# script.googleusercontent.com). Prints free heap before and after.
import gc
import time
import network
import requests
import secrets

URL = "https://httpbin.org/redirect-to?url=https%3A%2F%2Fexample.com%2F&status_code=302"

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
if not wlan.isconnected():
    ssid, pw = secrets.WIFI[0]
    wlan.connect(ssid, pw)
    t0 = time.ticks_ms()
    while not wlan.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < 15_000:
        time.sleep_ms(200)
print("wifi:", wlan.isconnected(), wlan.ifconfig()[0])

gc.collect()
before = gc.mem_free()
print("mem_free before:", before)

t0 = time.ticks_ms()
r = requests.get(URL)
body = r.text
dt = time.ticks_diff(time.ticks_ms(), t0)
status = r.status_code
r.close()

during = gc.mem_free()
print("status:", status, "in", dt, "ms,", len(body), "bytes")
print("followed to example.com:", "Example Domain" in body)
print("mem_free after (body held):", during)
del body, r
gc.collect()
print("mem_free after gc.collect():", gc.mem_free())
