# Praise flow without a cup: inject fake cup events into the real Zeki loop.
# Watch: ADDED (green LEDs + chime, praise line, then count line after 3 s),
# then FIDDLED (green, no chime), then REMOVED (orange, quiet), then idle.
# Today's count is restored afterwards so the test doesn't pollute state.json.
import time
import main

z = main.Zeki()
saved = dict(z.store)
z.pending = []                       # skip the boot line
z.state_t = time.ticks_add(time.ticks_ms(), -60_000)
for ev in ("added", "fiddled", "removed"):
    z._push("cup", ev)

t0 = time.ticks_ms()
last = None
while time.ticks_diff(time.ticks_ms(), t0) < 20_000:
    now = time.ticks_ms()
    z.tick(now)
    if (z.state, z.screen.rows) != last:
        last = (z.state, z.screen.rows)
        print("{:6d} ms  {:9s} {}".format(time.ticks_diff(now, t0), z.state, " / ".join(z.screen.rows)))
    time.sleep_ms(20)

z.store.update(saved)
z._save()
print("count restored to", z.store["count"])
