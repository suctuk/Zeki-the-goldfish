# Zeki: Goldfish Desk Pet — Build Spec

Hand-off spec for Claude Code. Target: SparkFun final-round demo, ~Fri Oct 16 2026.

Zeki is a 3D-printed goldfish whose arms hold an OLED and a Qwiic Twist. Zeki means "intelligent" in Turkish. He is a goldfish. He forgets things. That joke is the brand voice: cheerful, earnest, slightly unreliable.

## Scope

| Tier | Feature |
|---|---|
| **Must** | Cup detection → Zeki praises you on OLED + chime (clean-desk reinforcement) |
| **Must** | Twist "inspire me" flow → 3 questions → matched project idea |
| **Must** | Network status shown on screen at all times; cached ideas when offline |
| **Should** | Google Form → Sheet → Apps Script JSON → ESP32 polls, chimes, displays new community idea |
| **Should** | Server-side moderation (blocklist + approve column) |
| **Should** | Body glow: onboard WS2812 shines through a translucent PLA window, mirrors state colors |
| **Nice** | Second VL53L1X facing the door → "welcome!" chime |
| **Nice** | Enclosure published to Printables / Thingiverse; Hookup-Guide-style write-up |

## Hardware

| Part | Role | I2C addr (**confirmed by scan, Day 1**) |
|---|---|---|
| SparkFun Thing Plus ESP32 WROOM USB-C (WRL-20168), ESP32-WROOM-32E module | Brain, Wi-Fi, Qwiic port | n/a |
| Qwiic OLED 1.3" 128x64 | Zeki's face / text | **0x3D**, **SSD1306** controller (see below) |
| Qwiic Distance Sensor VL53L1X | Cup sensor | **0x29** |
| Qwiic Twist | Input + RGB mood light | **0x3F** |
| Qwiic Buzzer | Chimes | **0x34** |
| MAX17048 LiPo fuel gauge (onboard, not on the chain) | Battery voltage/SoC, unused | **0x36**, shows up in every scan; expected |
| Spare VL53L1X (Nice tier) | Door sensor | 0x29 default, **conflicts with cup sensor** |

No address conflicts among the four Qwiic parts. Scan returns 5 devices (4 Qwiic + onboard fuel gauge).

**OLED controller is SSD1306, not SH1106.** DigiKey and retailer listings say SH1106; on the hardware, the SH1106 driver leaves the panel blank (it never enables the SSD1306 charge pump) and micropython-lib `ssd1306` draws cleanly with no column offset.

All Qwiic, one daisy chain, no soldering for Must/Should.

**Second VL53L1X:** both default to 0x29. To run two, hold one in shutdown (XSHUT pin to a GPIO), reassign the other's address in software at boot, then release. That's a solder job on the XSHUT pad. Only attempt after Should tier works.

## Firmware stack

- **Primary:** MicroPython on the ESP32. Blake named MicroPython unprompted on the phone screen.
- **Fallback:** Arduino (ESP32 core + SparkFun Arduino libraries) if any Qwiic driver is missing or broken in MicroPython.
- **Step 0 gate: PASSED (Day 1, Sun Oct 11).** MicroPython v1.29.0 flashed, I2C scan clean, working driver for all four parts. **Decision: stay on MicroPython.** Arduino fallback not needed.
- **Day 4 (Wed Oct 21): custom firmware.** Stock v1.29.0 + Zeki's modules and the SparkFun drivers **frozen into flash** (`tools/zeki_manifest.py`, built by `tools/build_fw.sh`). Needed for HTTPS; see "Custom firmware" below.

### Custom firmware (Day 4)

**Why.** With the stock firmware every HTTPS poll failed with `OSError(12)` (ENOMEM). Measured on the board:

| Point | MicroPython heap free | IDF internal RAM free / largest block | HTTPS |
|---|---|---|---|
| Wi-Fi only | 111 KB | 83 KB / 59 KB | OK |
| All of Zeki loaded (stock, `.mpy` files) | 48 KB | 24 KB / 14 KB | ENOMEM |
| All of Zeki loaded (**custom, frozen**) | **93 KB** | **84 KB / 64 KB** | **OK, 4/4** |

- Modules cost ~80 KB of RAM as `.mpy` (VL53L1X 14.3 KB, Buzzer 9.8, `lines` 9.6, `zeki` 7.2, `qwiic_i2c` 6.9, Twist 6.2, ...). `.mpy` bytecode is copied into RAM; frozen bytecode runs from flash.
- The ESP32 port's MicroPython heap and ESP-IDF's internal heap are one pool: when the heap fragments it grows itself into IDF RAM (grabbing the 59 KB block) and HTTPS can't get its contiguous block anymore. Didn't help: precompiling, import order, line-by-line JSON parsing, reserving a TLS socket at boot, even dropping the SparkFun drivers entirely. Only moving code to flash did.
- ROMFS (run `.mpy` from flash without a custom build) is **not enabled** in the stock ESP32 firmware.

**What's frozen:** stock `boards/manifest.py` (asyncio, requests, ntptime, neopixel, ...), `ssd1306`, SparkFun `qwiic_i2c` / `qwiic_vl53l1x` / `qwiic_twist` / `qwiic_buzzer` (pinned commits in the manifest), and `hw ui net cup inspire community lines zeki`.
**Not frozen (plain files, edit any time):** `main.py` (2-line stub: `import zeki; zeki.start()`), `config.py`, `secrets.py`, `ideas.json`.
**Hot-fix without reflashing:** `sys.path` is `['', '.frozen', '/lib']`, so uploading e.g. `cup.py` to the board root overrides the frozen copy (costs its RAM again; delete it after the real fix is rebuilt).

**Build (WSL Ubuntu, ~15 min first time, ~2 min incremental):**
`wsl -d Ubuntu -- bash /mnt/c/Users/suctu/OneDrive/Documents/GitHub/Zeki-the-goldfish/tools/build_fw.sh`
Sources live in WSL `~/zeki-build`: MicroPython v1.29.0 (0fd6c57), ESP-IDF v5.5.2 (MicroPython's recommended version). SparkFun driver repos in `C:\Users\suctu\zeki-build\drivers`. Output: `firmware/zeki-ESP32_GENERIC-v1.29.0-frozen.bin` (gitignored). Docker Desktop failed to start on this PC (stale `dockerInference` socket), so the build uses WSL directly.

**Flash (keeps the board's files, partition table is byte-identical to stock):**
`esptool --port COM12 --baud 460800 write-flash 0x1000 firmware/zeki-ESP32_GENERIC-v1.29.0-frozen.bin`
then `python tools/deploy.py --frozen` (uploads the 4 plain files, deletes root copies of frozen modules).

**Roll back to stock (~5 min, no download):**
`esptool --port COM12 --baud 460800 write-flash 0x1000 firmware/ESP32_GENERIC-20260824-v1.29.0.bin`
then `python tools/deploy.py` (no `--frozen`: compiles + uploads the app as `.mpy`; drivers are still in `/lib`). Everything except live community ideas works on stock.

### Drivers (confirmed working on MicroPython v1.29.0)

| Part | Driver | Source | Install |
|---|---|---|---|
| I2C layer (shared) | `qwiic_i2c` v2.0.0 | [sparkfun/Qwiic_I2C_Py](https://github.com/sparkfun/Qwiic_I2C_Py) | pulled in as a dep of the mip installs below |
| VL53L1X | `qwiic_vl53l1x` v2.0.0 | [sparkfun/qwiic_vl53l1x_py](https://github.com/sparkfun/qwiic_vl53l1x_py) | `mpremote mip install github:sparkfun/qwiic_vl53l1x_py` |
| Twist | `qwiic_twist` v2.0.0 | [sparkfun/qwiic_twist_py](https://github.com/sparkfun/qwiic_twist_py) | `mpremote mip install github:sparkfun/qwiic_twist_py` |
| Buzzer | `qwiic_buzzer` (Feb 2024, no mip manifest) | [sparkfun/Qwiic_Buzzer_Py](https://github.com/sparkfun/Qwiic_Buzzer_Py) | copy `qwiic_buzzer.py` to `:lib/` by hand |
| OLED | `ssd1306` (micropython-lib) | [micropython-lib](https://github.com/micropython/micropython-lib/tree/master/micropython/drivers/display/ssd1306) | `mpremote mip install ssd1306` |
| HTTP | `requests` (micropython-lib) | [micropython-lib](https://github.com/micropython/micropython-lib/tree/master/python-ecosys/requests) | `mpremote mip install requests` |
| Body glow | `neopixel` | built into firmware | n/a |

**Day 2: the three SparkFun device drivers run on the board as precompiled `.mpy`**, not `.py`. Compiling `qwiic_vl53l1x.py` (50 KB of source) on-device at boot ate enough RAM to starve Wi-Fi. Build with the matching compiler (`pip install mpy-cross==1.29.0.post2`, must match firmware v1.29 / mpy 6.3), then replace the `.py` in `:lib/`:
`mpy-cross -o qwiic_vl53l1x.mpy qwiic_vl53l1x.py` (same for `qwiic_twist`, `qwiic_buzzer`). 92 KB source → 18 KB bytecode. Re-run if the firmware version changes.

**Why not SparkFun's OLED driver:** [sparkfun/qwiic_oled_base_py](https://github.com/sparkfun/qwiic_oled_base_py) (`QwiicLargeOled`) works on this panel, but measured on-device: full redraw **101 ms / ~34 KB RAM** vs `ssd1306` **26 ms / ~3.7 KB**. `ssd1306` is also a `framebuf` subclass (lines, rects, blit, text), which the status bar and UI need. Removed from the board.

**Driver gotchas found on Day 1:**
- `qwiic_i2c.getI2CDriver()` with no args opens the ESP32's *default* I2C pins, not 21/22. `hw.qwiic()` creates one driver with `sda=21, scl=22` and every SparkFun driver gets it via `i2c_driver=`. `hw.i2c()` exposes the raw `machine.I2C` for `ssd1306`.
- Twist `get_count()` returns **uint16**: turning below 0 gives 65535. Convert: `if c > 32767: c -= 65536`.
- **Twist button (found Day 3, from [Qwiic_Twist firmware](https://github.com/sparkfun/Qwiic_Twist) `interrupts.ino`):** the PRESSED status bit is *toggled* on every pin change, so it's a live "held" flag. Clearing it (as the driver's `is_pressed()` does) inverts it and causes phantom long-presses. The "ms since last button event" register only resets on release, so it can't time a hold. `hw.Knob` reads status once per poll, never clears PRESSED, and times holds itself.
- VL53L1X range status (ST codes): 0/6 valid, 2 signal fail and 4 out of bounds (= nothing in range), 3 below minimum range, 1 sigma fail, 7 wraparound. Sensor measured at a steady **16.5 readings/s** (60 ms) over 60 s, no stalls.
- VL53L1X `sensor_init()` returns `None` on success (not 0). Check `if err:`.
- VL53L1X `get_range_status()`: 0 = valid. Pointed at a ceiling ~2 m away in short mode it returns **status 4 (out of bounds)** on every read plus the odd `0 mm`. Filter on status 0 in cup logic. Read valid down to ~23 mm with a hand; still design for the 40 mm minimum.
- VL53L1X driver exposes `set_roi()` → the ROI-scan stretch goal is possible.
- **Buzzer is a resonant transducer (2730 Hz).** C5–G5 (523–784 Hz) at any sane volume is inaudible. Chimes must live in the **C7–G7 (2.1–3.1 kHz)** band. Volume at C7–G7: MIN/LOW too quiet, **MID = right (public-friendly)**, MAX at resonance = very loud.

**Firmware gotchas found on Day 2:**
- **Start Wi-Fi before loading anything else.** The ESP32 Wi-Fi driver needs internal RAM, and the MicroPython heap grows into it as modules load. With Wi-Fi started after the drivers, boot failed with `WiFi Out of Memory`. `main.py` creates `net.Net()` first.
- **First NTP request right after connecting times out.** `net.py` waits 3 s after connect, then retries every 15 s until the clock is set.
- **Spurious Wi-Fi status 202 (auth fail)** when `connect()` follows a `disconnect()` quickly. `net.py` retries the same network up to 3× (1.5 s apart) before moving on, and reuses a link that is already up after a soft reset.
- `main.py` only starts the loop under `if __name__ == "__main__"` (true at boot), so tests can `import main` and drive `Zeki` with fake events.
- Heap: ~77 KB free after boot with Wi-Fi up and every driver loaded.

### Board notes (Thing Plus ESP32 WROOM USB-C, WRL-20168)

| Item | Value | Source |
|---|---|---|
| CPU | Dual-core Xtensa LX6, 240 MHz | WROOM-32E datasheet |
| RAM / flash | 520 KB SRAM, 16 MB flash. **MicroPython heap: ~165 KB free at boot, ~97 KB free steady-state after Wi-Fi + first TLS connection** (no PSRAM) | Thing Plus pinout; measured Day 1 |
| Chip (measured) | ESP32-D0WD-V3 rev 3.1, MAC 8c:94:df:8e:fe:ac | esptool |
| Wireless | Wi-Fi 802.11 b/g/n (2.4 GHz only) + Bluetooth 4.2 / BLE | WROOM-32E datasheet |
| USB | CH340C USB-serial bridge (may need a driver) | Hookup guide |
| Qwiic | SDA = GPIO21, SCL = GPIO22, own 700 mA regulator | Pinout, hookup guide |
| **Qwiic power** | **Enabled by GPIO0.** Firmware must drive GPIO0 high before `I2C()` init or the bus is dead. **Confirmed:** GPIO0 LOW → empty scan; HIGH → all devices. GPIO0 stays high through a soft reset (pull-up). | Pinout; measured Day 1 |
| Onboard | Blue LED = GPIO13, WS2812 RGB LED = GPIO2, boot button = GPIO0, microSD CS = GPIO5 | Pinout |
| Power | Wi-Fi TX peaks ~380 mA; board regulator 700 mA | Pinout, WROOM-32E datasheet |
| XSHUT pin for 2nd sensor | **GPIO4** (labeled FREE). Avoid strapping pins 0, 2, 5, 12, 15. | Pinout, WROOM-32E datasheet §3.3 |

**MicroPython implications:**
- Use the generic ESP32 MicroPython build; flash with esptool over the CH340 port. Install the CH340 driver first if the port doesn't show up.
- First lines of `hw.py`: set GPIO0 as output, drive high, short delay, then init I2C on 21/22. Then run an I2C scan. If the scan comes back empty, this is the first suspect.
- TLS fits: ~97 KB heap stays free after HTTPS, flat across repeated GETs (no per-request leak). **Day 1 result: micropython-lib `requests` follows cross-domain redirects** (301/302/303/307/308, re-resolves host from `Location`, handles chunked bodies). Tested httpbin.org → 302 → example.com over HTTPS: 200 OK, ~2.6 s. Still to do: hit the real Apps Script URL once it exists (Day 4).
- `requests` sets `CERT_NONE`: TLS is encrypted but the server cert is **not verified**. Fine for public idea text; don't send anything secret from the device.
- Onboard WS2812 on GPIO2 can drive a body glow through a translucent PLA section (MicroPython `neopixel` module). Keep it away from the cup interior; light leaking into the clutter well can affect the ToF sensor.
- 2.4 GHz only: see dev setup below for the hotspot.

### Dev setup (decided: Windows + Android hotspot)

- **CH340 driver:** plug the board in, open Device Manager → Ports (COM & LPT). If no "USB-SERIAL CH340 (COMx)" appears, install SparkFun's CH340 driver and replug. **Day 1: driver already present, board is `COM12`** (VID 1A86 / PID 7523). The other COM ports on this PC are Bluetooth.
- **Tools live in a venv:** `%USERPROFILE%\.venvs\zeki` (Python 3.14, esptool 5.5.0, mpremote 1.29.0). The `python` on PATH is ESP-IDF's (`C:\Espressif\tools\python`); don't pip-install into it.
- **Flashing:** `esptool --port COM12 erase-flash`, then `esptool --port COM12 --baud 460800 write-flash 0x1000 ESP32_GENERIC-20260824-v1.29.0.bin` (from micropython.org/download/ESP32_GENERIC).
- **Editing/REPL:** `mpremote connect COM12 cp file.py :file.py`, `mpremote connect COM12 run tests/test_x.py`. "could not enter raw repl" means mpremote caught the board mid-boot (first boot after a flash, or the port open reset it): just rerun. Thonny as a visual backup.
- **Android hotspot:** Settings → Hotspot → set band to **2.4 GHz**, security to **WPA2-Personal** (not WPA3-only). Put it first in `secrets.py` for the demo.
- **Hotspot gotcha (hit on Day 1):** board joined `Senas`, got an IP, DNS resolved, but every TCP connect to the internet timed out (ETIMEDOUT); only the phone itself was reachable. Fixed once the phone had a working upstream. If the board is "connected" but nothing loads, check the phone actually has internet to share before debugging firmware. **Before the demo, test the hotspot on cellular** (Day 1 HTTPS passed with the phone's upstream on library Wi-Fi, not cellular). Some carriers block or cap tethering.

### Body glow (Should)

- Onboard WS2812 on GPIO2, driven with MicroPython's `neopixel` module (1 pixel).
- Mirrors the Twist LED states: soft orange idle, green praise, blue inspire, purple new submission, dim red offline. Slow "breathing" fade in idle.
- Keep brightness low (~10–20%): it's inches from the face and a full-white WS2812 is harsh.
- **Enclosure:** the LED is fixed on the board, so place the board so the LED sits behind a translucent PLA window (or add a short light pipe). Wall the cavity off from the clutter well so light can't leak onto the ToF sensor's view.

### File layout (MicroPython)

```
/main.py          2-line boot stub: import zeki; zeki.start()   (plain file)
/zeki.py          state machine + main loop (was main.py until Day 4)   (frozen)
/config.py        thresholds, poll interval, inventory, URLs         (plain file)
/secrets.py       Wi-Fi SSID/pass list, Apps Script URL (gitignored) (plain file)
/hw.py            init + thin wrappers: oled, tof, twist, buzzer; Mood, Chime, Knob   (frozen)
/cup.py           cup interaction state machine                      (frozen)
/ui.py            screens, status bar, wrapping, paging, ASCII clean (frozen)
/net.py           Wi-Fi connect/reconnect, NTP, background feed Poller (frozen)
/community.py     community idea cache (community.json, newest 50)   (frozen)
/inspire.py       question flow + idea matcher                       (frozen)
/lines.py         Zeki's lines                                       (frozen)
/ideas.json       seeded idea list (offline source of truth)         (plain file)
/state.json       daily cup count, last fetched community id, unseen ids (written by Zeki)
/community.json   cached community ideas (written by Zeki)
apps_script.gs    Google side (not on device)
tools/            deploy.py, build_fw.sh, zeki_manifest.py
firmware/         stock + custom .bin (gitignored)
```

## State machine

```
BOOT → IDLE
IDLE → CUP_EVENT        (object placed in cup)
IDLE → SUBMISSION       (new approved row from poll)
IDLE → INSPIRE          (Twist click)
IDLE → BROWSE           (Twist rotate: scroll recent community ideas)
CUP_EVENT / SUBMISSION → IDLE after ~6 s
INSPIRE → IDLE on finish or 30 s idle timeout
```

Events queue; never interrupt INSPIRE with a submission. Show a small "1 new" badge instead and play it after.

### Status bar (always visible, top 10 px)

- Wi-Fi icon: solid = connected, blinking/X = offline
- Badge for unseen submissions
- Twist LED mirrors state: soft orange idle, green praise, blue inspire, purple new submission, dim red offline

## Feature: cup detection (Must)

**Mounting: top-down.** Sensor in the rim/lip of the body opening (Zeki "looking into" his belly), angled down at the cup floor. Top of the tallest item must stay ≥4 cm from the sensor (VL53L1X minimum range). Matte, dark interior; glossy or translucent PLA confuses ToF.

**Geometry:** enclosure ~4 in (~100 mm) tall, cup 3–3.5 in (76–89 mm) deep. Contents: pens *and* loose clutter.

**Pens break top-down sensing.** A pen (~140 mm) in an 89 mm cup sticks ~50 mm above the rim, right into the sensor's view and inside its minimum range. Fix: **divide the cup.**
- **Pen sleeve** at the back, outside the sensor's cone. Not level-sensed.
- **Clutter well** at the front, sensor looking straight down into it from the head/lip. This is where ADDED / REMOVED works cleanly.
- A hand reaching for the pen sleeve can still pass through the cone, so pens get praised via the FIDDLED path. Aim the cone so the reach crosses it.
- VL53L1X field of view is wide (~27°). Over ~80 mm that's a ~40 mm circle at the floor. Size the clutter well to roughly that, or narrow the ROI in software if the driver allows.

**Second sensor (door):** feasible. Both default to 0x29; solder the spare's SHUT pad to a free GPIO (see board notes), hold it low at boot, readdress the cup sensor, release. Door mode is still Nice tier.

Why not the others: bottom-mounted gets covered by the first item and reads it forever. Side-mounted is a break-beam at one height: it sees a hand go by, but can't tell a full cup from a half-full one.

**Detect the interaction, not the object.** A hand reaching in always reads much closer than the contents. Use that as the trigger, then compare settled levels before and after.

```
SETTLED  → hand detected (distance < settled_mm - HAND_MM)        → ACTIVE
ACTIVE   → readings stable within ±NOISE_MM for SETTLE_MS (~1.5 s) → compare
compare:
  new < settled - DELTA_MM  → ADDED    (praise + chime, count++)
  new > settled + DELTA_MM  → REMOVED  (quiet "bye!" or nothing)
  otherwise                 → FIDDLED  (small wiggle line, no count)
settled_mm = new  (rebaseline every time)
```

- Start values to tune: HAND_MM ~30, NOISE_MM ~5, DELTA_MM ~8, sample every 50–100 ms, median of 5.
- Rebaselining after every interaction means the cup can fill up and Zeki still notices the next item.
- Known limit: a short item dropped next to taller ones may not change the level, so it reads FIDDLED. For clean-desk reinforcement, consider praising on ADDED *and* FIDDLED; only REMOVED stays quiet.
- Stretch: VL53L1X supports a programmable ROI. Scanning 2–4 zones across the opening could give a crude fill map. Only if the driver exposes ROI.
- Daily counter of items put away. Goldfish joke: Zeki occasionally "forgets" the count and makes up a number, then corrects himself.
- Line pool, rotated so it doesn't repeat back to back: "Let's go!", "Desk: cleaner. Me: proud.", "I'll remember this forever. (I won't.)"
- Chime: short rising 3-note. **Confirmed: C7–E7–G7, 120 ms each, `VOLUME_MID`** (see buzzer gotcha above).

## Feature: inspire me (Must)

No keyboard. Every question is multiple choice, 3–5 options, one per screen.

- **Rotate** = cycle options. **Click** = confirm. **Long press** = back / cancel.
- Twist LED color shifts per option for a little feedback.

Questions (draft):

1. **How long have you got?** 15 min / an afternoon / a weekend
2. **What should it do?** sense / show / move / make noise / talk to the internet
3. **Vibe?** useful / silly / wearable / desk toy
4. *(Optional)* **Parts?** "use what's on my desk" / anything goes

"Use what's on my desk" solves the specific-part problem without a parts picker: `config.py` holds an `INVENTORY` list (Twist, VL53L1X, OLED, buzzer, etc.), and the matcher filters to ideas whose required parts are a subset of it.

### Idea format (`ideas.json`)

```json
{
  "id": "plant-pinger",
  "text": "Soil moisture sensor that buzzes when your plant is thirsty",
  "time": "afternoon",
  "does": ["sense", "noise"],
  "vibe": ["useful", "desk"],
  "parts": ["soil-moisture", "buzzer"],
  "source": "sparkfun"
}
```

**Matcher:** score = 2 × time match + 1 per `does` overlap + 1 per `vibe` overlap; filter by parts if selected; pick randomly among top scores so repeat runs vary. If nothing scores, fall back to random-word mashup ("a [silly] [desk toy] that [moves] using a [load cell]") so Zeki always answers.

**Sources:** `source: "sparkfun"` ideas built from catalog products (good for product marketing) and `source: "community"` ideas pulled from approved form submissions and cached locally.

## Feature: community submissions (Should)

```
Google Form → Sheet → Apps Script (filter + JSON) → ESP32 polls every 30 s
```

**Sheet columns:** Timestamp | Your idea | Your name (optional) | How long would it take? | What does it do? | Vibe? | Flagged | Approved | Id

**As built (Day 4):** see `apps_script.gs` header for install steps. Form questions 3-5 use the same options as Zeki's questions, so community ideas carry the same tags and join "inspire me".
- **Flagged** = reason or `no`: links / email / phone (10+ digits) / @handle (checked on raw text), then the Blocklist tab (LDNOOBW list imported by `importBlocklist()`, column B = custom terms). Whole-word matching, leetspeak + stretched-letter normalization; no false hits on the 30 seeded ideas or on part numbers / voltages / dates.
- **Approved** is a dropdown: `yes` (Zeki shows it) / `no` (rejected) / blank (waiting, counted as "N to review"). `setDemoMode()` auto-approves clean submissions; `setReviewMode()` (recommended for public use) approves nothing automatically.
- **Id is assigned at approval**, not submission, so a late manual approval still gets a new, higher Id and Zeki's `?since=` picks it up.
- **`doGet(?since=N)`** returns `{"ideas": [...max 5, oldest first, text <= 120, name <= 20...], "pending": N}`.
- **Burst alert:** 4+ submissions within 60 min emails the owner a link to the Sheet + latest ideas, then 60 min cooldown.
- **Resilience:** transient Google storage errors (`DEADLINE_EXCEEDED`, seen during setup) are retried 3x; every submission also re-processes any of the last 25 rows a hiccup skipped.
- 44/44 end-to-end tests against a fake Sheet in Node (scratch harness).
- Deployed as web app, Execute as: Me, Access: Anyone (read-only JSON of approved ideas; no doPost). URL in `secrets.py`. Google answers with a 302 to `script.googleusercontent.com`; `requests` follows it.

**Device:**
- Poll with `?since=<last_id>`; store `last_id` in `state.json` so reboots don't replay. **As built:** every 30 s on a background thread (`net.Poller`); a full page of 5 triggers a follow-up 2 s later. Polls are held back during INSPIRE and BROWSE: the TLS handshake still pauses the main loop 0.4-1.1 s even on a thread.
- New row → SUBMISSION screen: chime, "New idea from <name or 'a friend'>!", word-wrapped text, scroll with Twist if long. **As built:** purple LEDs, `new_idea` line, then the idea paged (title "From <name>", pages turn every 3.5 s, turn = next page). **At most one announcement per 5 min**; the rest wait behind the "N new" badge.
- Append to local community cache (cap ~50) so ideas survive offline and feed the matcher. **As built:** `community.json`; in the matcher community ideas have parts `["?"]`, so they never pass "My desk only".
- **BROWSE:** turn the knob in IDLE to scroll community ideas newest-first; viewing clears them from the badge; click/hold or 20 s idle exits.
- **"N to review"** row under the idle line while the feed reports pending submissions.
- Non-ASCII text from the form: Turkish folds (lines.fold), curly quotes / dashes / accents map to ASCII, anything else (emoji) is dropped.

**Moderation:**
- Filtering happens in Apps Script, not on the ESP32: easier to update, no device memory cost.
- Blocklist source: an open-source profanity list (e.g. the LDNOOBW list on GitHub) pasted into a sheet tab, plus a few custom terms. Normalize text (lowercase, strip punctuation, collapse repeated letters) before matching.
- Approve column is the real safety net. Blocklists miss things.

## Cast (`lines.py`)

- All of Zeki's lines live in `lines.py`: pools per event, `pick(pool, **fmt)` never repeats a line back to back.
- Turkish lines carry an English gloss on the next line. Turkish reviewed and approved.
- **Demo decision: ASCII fallback** via `lines.fold()` before drawing. Custom Turkish glyphs are a post-demo upgrade.
- No brand names in Zeki's lines.

## Offline behavior (Must)

- Wi-Fi connect at boot with timeout; never block the loop on network.
- `secrets.py` holds multiple networks (home, phone hotspot, SparkFun guest). Try in order.
- Offline: status icon shows it, Zeki says something in voice ("Lost the internet. Or I forgot where I put it."), all local features keep working, retry every 60 s.
- Captive-portal guest Wi-Fi will likely fail. Demo on phone hotspot.

## Demo plan

1. Zeki idling on the desk, status bar showing connected.
2. Drop a pen in the cup → praise + chime.
3. Click Twist → answer 3 questions → idea.
4. Hand interviewers a QR code to the form → they submit → Zeki chimes and shows it live.
5. Kill the hotspot → offline icon, Zeki still works.

## Build order

| Day | Goal |
|---|---|
| Sun–Mon | Flash MicroPython, I2C scan, one test script per part. Decide MicroPython vs Arduino. **Done Sun.** |
| Mon–Tue | Status bar, cup detection, praise flow. Start printing enclosure. **Code done Sun; cup thresholds need tuning once the sensor is mounted.** |
| Tue–Wed | Inspire flow + `ideas.json` (seed 20–30 ideas). **Done Sun: 30 ideas, flow tested on hardware.** |
| Wed–Thu | Form, Sheet, Apps Script, polling, offline cache. |
| Thu–Fri | Assemble in enclosure, tune thresholds, rehearse demo, photos for write-up. |

## Write-up (Hookup-Guide style)

Introduction · Required materials (with SparkFun links) · Hardware hookup (Qwiic chain photo) · Software setup (MicroPython flash, libs) · Code walkthrough by feature · Google Sheets setup · Printing the enclosure · Troubleshooting · Resources and going further

## Open questions

- Cup inner depth and what goes in it (pens vs. loose desk clutter)
- Power: **decided, USB-C.** Route the cable out the back with strain relief; keep the port reachable for reflashing.
- Enclosure: **decided, cup built into the body.** Fallback if time runs short: fish leaning against a separate cup, holding the OLED and Twist, sensor clipped to the cup rim.
- ~~OLED driver chip (SSD1306 vs SH1106)~~ **Resolved Day 1: SSD1306**, micropython-lib `ssd1306`.
- Hotspot internet over **cellular** at the demo location: phone browsed fine on cellular on Day 4 but tethered traffic didn't pass while driving; later it worked (HTTPS polls OK at -80 dBm). Re-check at the venue.

## Day 1 bring-up log (Sun Oct 11 2026)

| # | Step | Result | Notes |
|---|---|---|---|
| 1 | COM port | PASS | `COM12`, CH340 driver already installed |
| 2 | Flash MicroPython | PASS | v1.29.0 ESP32_GENERIC, hash verified, REPL OK |
| 3 | `hw.py` + I2C scan | PASS | GPIO0 → 100 ms → I2C 21/22 @ 400 kHz. 5 devices (4 Qwiic + onboard MAX17048 @ 0x36) |
| 4 | Identify addresses / OLED chip | PASS | No conflicts. OLED is **SSD1306** (SH1106 driver: blank) |
| 5 | Driver + test per part | PASS | OLED text, VL53L1X 10 s @ 200 ms (status 0, 23–226 mm), Twist count/clicks/orange LED, Buzzer chime. **Buzzer first test silent**: notes below resonance; fixed by moving to C7–G7 @ MID |
| 6 | WS2812 GPIO2 orange @ 15% | PASS | (38, 12, 0) |
| 7 | Wi-Fi hotspot | PASS | `Senas`, 4.8 s, RSSI −58. `secrets.py` gitignored |
| 8 | HTTPS cross-domain redirect | PASS (after fix) | First attempt failed: hotspot had no upstream internet. After fix, 302 followed, 200 OK. Heap 134.8 KB → 98.5 KB, then flat ~97 KB over 5 more GETs |

**Files on the board:** `/main.py` (boot splash "hi, I'm Zeki"; becomes the state machine on Day 2), `/hw.py`, `/secrets.py`, `/lib/{qwiic_i2c/, qwiic_vl53l1x.py, qwiic_twist.py, qwiic_buzzer.py, ssd1306.mpy, requests/}`.
**Test scripts (repo, run from host):** `tests/test_oled.py`, `test_tof.py`, `test_twist.py`, `test_buzzer.py`, `test_glow.py`, `test_wifi.py`, `test_https.py`.

## Day 2 log (Sun Oct 11 2026, evening)

| Piece | Status | Notes |
|---|---|---|
| `config.py` | Done | All tunables: timings, Wi-Fi, cup thresholds, state colors, chimes |
| `net.py` | Done, tested | Non-blocking connect, networks in order, 15 s timeout, 60 s retry, NTP clock. Boot connect is silent; "offline" only after a failed reconnect pass; "online" when it comes back. Forced disconnect → silent reconnect verified |
| `ui.py` | Done, checked on screen | Status bar: Wi-Fi bars from RSSI, sweeping bars while connecting, blinking X offline, inverted "N new" badge (for Day 4). Body: word-wrap to 16 chars × 6 rows, centered, Turkish folded to ASCII. Every line in `lines.py` fits (worst case 4 rows) |
| `hw.Mood` / `hw.Chime` | Done, checked | Twist LED + breathing body glow; chime plays without blocking the loop |
| `cup.py` | Logic done, **thresholds not tuned** | Spec state machine + silent drift rebaseline + 10 s timeout for interactions that never settle. 9/9 simulated scenarios pass on the PC. Live: baselined at 115 mm on the desk; a hand in/out gave FIDDLED |
| `main.py` | Done, checked | Boot: splash "hi, I'm Zeki" (3 s) → boot line → IDLE. IDLE ↔ CUP_EVENT / SAY with an event queue (max 5). ADDED: green + chime + praise line, count line after 3 s. FIDDLED: green, no chime. REMOVED: quiet. Daily count in `state.json`, resets at local midnight once NTP has set the clock |
| `tests/test_praise.py` | Done | Injects ADDED/FIDDLED/REMOVED into the real loop; restores the count afterwards |

**To do once the cup + sensor mount exist:**
1. Set `CUP_DEBUG = True` in `config.py`, upload, watch the serial log (`mpremote connect COM12 repl`) while dropping items in, reaching in, and taking items out.
2. Tune `HAND_MM`, `DELTA_MM`, `NOISE_MM`, `SETTLE_MS` from what the log shows. Record the cup depth and sensor-to-floor distance here (still open questions).
3. Check that a pen reach toward the sleeve crosses the cone (FIDDLED path).

## Day 3 log (Sun Oct 11 2026, night)

| Piece | Status | Notes |
|---|---|---|
| `ideas.json` | Done | 30 ideas: 11 of Sena's (`source: "maker"`), 19 catalog/desk (`"sparkfun"`). Every idea fits one screen (title + ≤5 rows). Parts checked against the live SparkFun catalog: SFA30 is retired, so Fresh Air uses the SFA40 (Qwiic); the barcode breakout is retired with no confirmed replacement, so Bin Finder uses a generic `barcode-scanner` tag. Mak Pack v2 = the 2nd-interview fanny pack (135–140 °F mac and cheese) with that deck's "future work" as the parts list |
| Matcher | Done | Spec scoring (2× time + does + vibe), "My desk only" = parts ⊆ `INVENTORY`, random within a score, mashup fallback. Coverage: every one of 60 answer combos scores ≥ 2 (time match) in both "any" and "desk" pools |
| `hw.Knob` | Done, tested | turn / click / long (≥ 0.8 s) events; see Twist firmware gotcha above |
| `inspire.py` | Done, tested on hardware | Intro line → 4 questions (`<option>` highlighted, `n/N` footer, Twist LED color per option) → idea with chime. Turn = next idea, click = outro line (7 s, click to skip), long = back a question / cancel on Q1. 30 s no input → IDLE. 11/11 host-simulated scenarios pass |
| `main.py` | Updated | Click in IDLE → INSPIRE. Click on a praise/announcement screen dismisses it. Cup/net events wait during INSPIRE |
| Cup fix | Done | **Bug (seen live):** baseline settled at 0–16 mm (hand on the lens); out-of-range readings were dropped, so it never recovered and looked "stuck". Now "nothing in range" = 1500 mm, "too close" = 0 mm, and no baseline under 40 mm. Also: ADDED counts at detection, and events that pile up during INSPIRE collapse into one cup screen. 13/13 cup scenarios pass (incl. both regressions) |
| `tests/test_cup_live.py` | Done | Live raw/median/mode/baseline/event view on the OLED for 60 s. **Use this to tune once the sensor is mounted** |
| `tests/test_knob.py` | Done | Twist events shown live on the OLED |

Notes:
- **Second cup fix (same night):** a hand held still wouldn't register. A recording showed a held hand varies **±11 mm** (min 33, max 97, avg 51 mm) and ~16% of readings drop out as "nothing in range". The spec's ±5 mm stability band rarely held for 1.5 s. `NOISE_MM` is now **12**, and a settled level is the **mean of the stable window** (not its first reading), so the 8 mm `DELTA_MM` comparison stays precise. Replaying the real recording through the new logic gives ADDED; confirmed live afterwards (praise on a held hand).
- Holding a hand still in the sensor's view for 1.5 s reads as ADDED. That's inherent to "detect the interaction" and should matter less once the sensor looks down into a cup.
- Today's cup count is inflated by testing (11); it resets at local midnight.

## Day 4 log (Wed Oct 21 2026)

| Piece | Status | Notes |
|---|---|---|
| Google Form + Sheet | Done (Sena) | 5 questions, 120/20 char limits, no sign-in, privacy note |
| `apps_script.gs` | Done, deployed | Moderation, yes/no/blank review, Id-at-approval, `pending` count, burst email, retries + self-heal. Node test harness 44/44 |
| `community.py`, `net.Poller`, SUBMISSION / BROWSE / badges in `zeki.py` | Done, live-tested | Live: "Hello World" announced with chime, #2 waited behind "1 new". PC simulation of the real loop 35/35 |
| `ui.py` paging + ASCII clean | Done | |
| HTTPS from the board | **Fixed with custom firmware** | Stock firmware: ENOMEM on every poll (measurements above) |
| `tools/build_fw.sh`, `tools/zeki_manifest.py`, `tools/deploy.py --frozen` | Done | WSL Ubuntu + ESP-IDF v5.5.2; flash keeps files; stock image kept for rollback |

Gotchas found on Day 4:
- **Apps Script editor's Run button runs the dropdown's function**: after deleting the placeholder it still said `myFunction` ("Attempted to execute myFunction, but it was deleted"). Save, then pick `setup`.
- **A script created from the Form (or script.google.com) has no active spreadsheet**: `SpreadsheetApp.getActive()` is null. Create it from the Sheet's Extensions menu.
- Google's consent screen also lists "display third-party web content in prompts and sidebars"; not needed, leave it unticked.
- `DEADLINE_EXCEEDED` "reading from storage" is a transient Google error; retry.
- When "Wi-Fi up" but nothing loads: check `poll: failed` in the log. `OSError(12)` = out of memory (fixed by the custom firmware); `OSError(116)` / `113` = no internet behind the hotspot.
- Docker Desktop crashed on start (stale `AppData\Local\Docker\run\dockerInference`); bypassed with WSL.
