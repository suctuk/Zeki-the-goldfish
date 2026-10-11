# Onboard WS2812 (GPIO2): fade up to orange at 15% brightness
import time
from machine import Pin
from neopixel import NeoPixel

ORANGE = (255, 80, 0)
BRIGHTNESS = 0.15
STEPS = 60

px = NeoPixel(Pin(2), 1)
for i in range(STEPS + 1):
    k = BRIGHTNESS * i / STEPS
    px[0] = tuple(int(c * k) for c in ORANGE)
    px.write()
    time.sleep_ms(25)
print("WS2812: orange at 15% =", px[0])
