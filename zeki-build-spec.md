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

**Why not SparkFun's OLED driver:** [sparkfun/qwiic_oled_base_py](https://github.com/sparkfun/qwiic_oled_base_py) (`QwiicLargeOled`) works on this panel, but measured on-device: full redraw **101 ms / ~34 KB RAM** vs `ssd1306` **26 ms / ~3.7 KB**. `ssd1306` is also a `framebuf` subclass (lines, rects, blit, text), which the status bar and UI need. Removed from the board.

**Driver gotchas found on Day 1:**
- `qwiic_i2c.getI2CDriver()` with no args opens the ESP32's *default* I2C pins, not 21/22. `hw.qwiic()` creates one driver with `sda=21, scl=22` and every SparkFun driver gets it via `i2c_driver=`. `hw.i2c()` exposes the raw `machine.I2C` for `ssd1306`.
- Twist `get_count()` returns **uint16**: turning below 0 gives 65535. Convert: `if c > 32767: c -= 65536`.
- VL53L1X `sensor_init()` returns `None` on success (not 0). Check `if err:`.
- VL53L1X `get_range_status()`: 0 = valid. Pointed at a ceiling ~2 m away in short mode it returns **status 4 (out of bounds)** on every read plus the odd `0 mm`. Filter on status 0 in cup logic. Read valid down to ~23 mm with a hand; still design for the 40 mm minimum.
- VL53L1X driver exposes `set_roi()` → the ROI-scan stretch goal is possible.
- **Buzzer is a resonant transducer (2730 Hz).** C5–G5 (523–784 Hz) at any sane volume is inaudible. Chimes must live in the **C7–G7 (2.1–3.1 kHz)** band. Volume at C7–G7: MIN/LOW too quiet, **MID = right (public-friendly)**, MAX at resonance = very loud.

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
- **Editing/REPL:** `mpremote connect COM12 cp file.py :file.py`, `mpremote connect COM12 run tests/test_x.py`. The very first mpremote connect after a flash can fail with "could not enter raw repl" while the filesystem is created; just rerun. Thonny as a visual backup.
- **Android hotspot:** Settings → Hotspot → set band to **2.4 GHz**, security to **WPA2-Personal** (not WPA3-only). Put it first in `secrets.py` for the demo.
- **Hotspot gotcha (hit on Day 1):** board joined `Senas`, got an IP, DNS resolved, but every TCP connect to the internet timed out (ETIMEDOUT); only the phone itself was reachable. Fixed once the phone had a working upstream. If the board is "connected" but nothing loads, check the phone actually has internet to share before debugging firmware. **Before the demo, test the hotspot on cellular** (Day 1 HTTPS passed with the phone's upstream on library Wi-Fi, not cellular). Some carriers block or cap tethering.

### Body glow (Should)

- Onboard WS2812 on GPIO2, driven with MicroPython's `neopixel` module (1 pixel).
- Mirrors the Twist LED states: soft orange idle, green praise, blue inspire, purple new submission, dim red offline. Slow "breathing" fade in idle.
- Keep brightness low (~10–20%): it's inches from the face and a full-white WS2812 is harsh.
- **Enclosure:** the LED is fixed on the board, so place the board so the LED sits behind a translucent PLA window (or add a short light pipe). Wall the cavity off from the clutter well so light can't leak onto the ToF sensor's view.

### File layout (MicroPython)

```
/main.py          state machine + main loop
/config.py        thresholds, poll interval, inventory, URLs
/secrets.py       Wi-Fi SSID/pass list, Apps Script URL (gitignored)
/hw.py            init + thin wrappers: oled, cup, twist, buzzer  (Day 1: power, shared bus, scan, per-part constructors)
/ui.py            screens, status bar, text wrapping, Zeki lines
/net.py           Wi-Fi connect/reconnect, poll submissions, cache
/inspire.py       question flow + idea matcher
/ideas.json       seeded idea list (offline source of truth)
/state.json       last seen submission id, daily cup count
/apps_script.gs   Google side (not on device)
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

**Sheet columns:** Timestamp | Idea | Name (optional) | Flagged | Approved | Id

**Apps Script:**
- `onFormSubmit` trigger: assign Id, run blocklist check, set Flagged. Auto-approve if not flagged (demo mode) or leave for manual approval (normal mode). Toggle via a script property.
- `doGet(e)`: return approved rows with `id > e.parameter.since` as JSON, max 5, text trimmed to ~120 chars.
- Deploy as web app, "Anyone" access. No auth on device.

**Device:**
- Poll with `?since=<last_id>`; store `last_id` in `state.json` so reboots don't replay.
- New row → SUBMISSION screen: chime, "New idea from <name or 'a friend'>!", word-wrapped text, scroll with Twist if long.
- Append to local community cache (cap ~50) so ideas survive offline and feed the matcher.

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
| Sun–Mon | Flash MicroPython, I2C scan, one test script per part. Decide MicroPython vs Arduino. |
| Mon–Tue | Status bar, cup detection, praise flow. Start printing enclosure. |
| Tue–Wed | Inspire flow + `ideas.json` (seed 20–30 ideas). |
| Wed–Thu | Form, Sheet, Apps Script, polling, offline cache. |
| Thu–Fri | Assemble in enclosure, tune thresholds, rehearse demo, photos for write-up. |

## Write-up (Hookup-Guide style)

Introduction · Required materials (with SparkFun links) · Hardware hookup (Qwiic chain photo) · Software setup (MicroPython flash, libs) · Code walkthrough by feature · Google Sheets setup · Printing the enclosure · Troubleshooting · Resources and going further

## Open questions

- Cup inner depth and what goes in it (pens vs. loose desk clutter)
- Power: **decided, USB-C.** Route the cable out the back with strain relief; keep the port reachable for reflashing.
- Enclosure: **decided, cup built into the body.** Fallback if time runs short: fish leaning against a separate cup, holding the OLED and Twist, sensor clipped to the cup rim.
- ~~OLED driver chip (SSD1306 vs SH1106)~~ **Resolved Day 1: SSD1306**, micropython-lib `ssd1306`.
- Hotspot internet over **cellular** at the demo location: untested (Day 1 used the phone's Wi-Fi upstream).

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

**Files on the board:** `/hw.py`, `/secrets.py`, `/lib/{qwiic_i2c/, qwiic_vl53l1x.py, qwiic_twist.py, qwiic_buzzer.py, ssd1306.mpy, requests/}`.
**Test scripts (repo, run from host):** `tests/test_oled.py`, `test_tof.py`, `test_twist.py`, `test_buzzer.py`, `test_glow.py`, `test_wifi.py`, `test_https.py`.
