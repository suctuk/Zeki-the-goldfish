# main.py — runs after boot.py on every power-up / reset.
# The app lives in zeki.py, shipped precompiled as zeki.mpy: compiling
# big .py files at boot permanently grows the heap into the internal RAM
# that Wi-Fi and HTTPS need (Day 4: HTTPS failed with ENOMEM).
import zeki
zeki.start()
