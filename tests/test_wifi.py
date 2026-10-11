# Wi-Fi: connect to the first reachable network in secrets.WIFI
import time
import network
import secrets

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
visible = {s[0].decode(): s for s in wlan.scan()}
print("visible 2.4 GHz SSIDs:", sorted(visible))

for ssid, pw in secrets.WIFI:
    if ssid not in visible:
        print("not visible:", ssid)
        continue
    print("connecting to", ssid, "rssi", visible[ssid][3])
    wlan.connect(ssid, pw)
    t0 = time.ticks_ms()
    while not wlan.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < 15_000:
        time.sleep_ms(200)
    if wlan.isconnected():
        print("connected in {} ms".format(time.ticks_diff(time.ticks_ms(), t0)))
        print("ifconfig:", wlan.ifconfig())
        break
    print("failed, status", wlan.status())
    wlan.disconnect()
else:
    print("Wi-Fi: no network connected")
