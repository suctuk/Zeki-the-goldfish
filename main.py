# main.py — runs after boot.py on every power-up / reset.
# The app lives in zeki.py, frozen into the custom firmware (tools/build_fw.sh).
#
# gc.threshold: collect garbage after every 16 KB allocated. Without it, the
# ESP32 port grows the MicroPython heap into the internal (IDF) RAM whenever
# the heap fills with garbage, and never gives it back; HTTPS then has no
# room for its TLS buffers (Day 4: largest free IDF block stuck at ~23 KB).
import gc
gc.threshold(16 * 1024)
import zeki
zeki.start()
