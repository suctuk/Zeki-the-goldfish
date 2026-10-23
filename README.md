# Zeki-the-goldfish
This is the code for Zeki, who is a goldfish desk friend who helps me keep my space organized! We are using the SparkFun Thing Plus - ESP32 WROOM (USB-C), SparkFun Qwiic OLED - (1.3in., 128x64), SparkFun Distance Sensor Breakout - 4 Meter, VL53L1X (Qwiic), SparkFun Qwiic Twist - RGB Rotary Encoder Breakout, and SparkFun Qwiic Buzzer.

**What Zeki does:**
- **Cup:** a distance sensor watches his clutter cup. When you tidy something into it, he praises you and counts it.
- **Inspire me:** click the knob, answer three questions, and he suggests a project.
- **Community ideas:** anyone can scan a QR code and send him an idea through a Google Form. Approved ideas show up on his screen.

The full engineering log (every measurement and decision, day by day) is in [`zeki-build-spec.md`](zeki-build-spec.md). The presentation notes are in [`demo/zeki-presentation-notes.md`](demo/zeki-presentation-notes.md).

## How it fits together

```
main.py -> zeki.py (state machine + main loop)
             |- hw.py         board + Qwiic parts (OLED, distance sensor, knob, buzzer, LED)
             |- ui.py         what's on the screen
             |- cup.py        cup sensing
             |- inspire.py    "inspire me" questions + matching (ideas.json)
             |- net.py        Wi-Fi + fetching community ideas
             |- community.py  saved community ideas (community.json)
             |- lines.py      everything Zeki says
             '- config.py     every setting

Google Form -> Sheet -> apps_script.gs (moderate, approve, number) -> JSON feed -> net.py
```

Zeki runs MicroPython v1.29.0. The app and the SparkFun drivers are **frozen into a custom firmware** (built with `tools/build_fw.sh`). Loaded the normal way, they used so much RAM that HTTPS no longer fit. Only `main.py`, `config.py`, `secrets.py` and `ideas.json` are plain files on the board, so settings can be changed without rebuilding.

## Files

### Zeki's code (runs on the ESP32)

| File | What it does |
|---|---|
| `main.py` | Runs at power-up. Sets how often memory is cleaned up (needed for HTTPS), then starts `zeki.py`. |
| `zeki.py` | The app: state machine and main loop. Decides what's on screen (idle, praise, inspire, new idea, browsing ideas), handles knob input and queues events. It also decides when to check for ideas, announces new ones, keeps today's count, and runs the watchdog and heartbeat log. |
| `hw.py` | Board start-up. Powers the Qwiic connector, sets up I2C, and opens each part: OLED, distance sensor, Twist knob, buzzer and the onboard LED. If a part is missing, Zeki keeps running without it. Also handles knob events (turn, click, hold), LED colours and chimes. |
| `ui.py` | The screen: status bar (Wi-Fi bars, offline X, fetching arrow, "N new" badge), word-wrapped messages, and multi-page idea text that pages itself. Cleans text so accents and emoji display. |
| `cup.py` | Cup sensing, built to detect the *interaction* rather than the object. It learns the empty cup's level, notices a hand reaching in, and compares the level once things settle. Tall items that fill the cup get their own handling. |
| `inspire.py` | "Inspire me": asks the questions, matches the answers against the built-in and community ideas, and invents a mash-up if nothing matches. |
| `net.py` | Wi-Fi that never blocks the loop (reconnects, sets the clock). `Poller` fetches the community-idea feed from Google. |
| `community.py` | Saves approved community ideas in `community.json` (the newest 50, so they survive reboots and offline time) and converts them for the inspire matcher. |
| `lines.py` | Everything Zeki says: praise, the daily count, online and offline lines, new-idea headers, plus Turkish-letter folding for the screen. |
| `config.py` | Every setting in one place: cup tuning, check timing, memory limits, colours, chimes, the inspire questions and the parts inventory. A plain file on the board, so it can be changed without a firmware rebuild. |
| `ideas.json` | The 30 built-in project ideas (11 of Sena's own, 19 from the SparkFun catalog), one per line, with tags for matching and the parts they need. |
| `secrets.py` | Wi-Fi networks and the Apps Script URL. **Not in git** (`.gitignore`). |

Zeki creates two files on the board himself: `state.json` (today's count, newest idea number seen, unread ideas) and `community.json` (saved community ideas).

### The Google side

| File | What it does |
|---|---|
| `apps_script.gs` | Lives in the Google Sheet behind the Form (Extensions > Apps Script). Checks every submission for links, contact info and bad words. Approves clean ones automatically (demo mode) or waits for a human (review mode), and numbers approved ideas. Serves `?since=N` as JSON for Zeki and emails an alert if 4+ ideas arrive within an hour. Install steps are at the top of the file. |

### Tools (run on the PC)

| File | What it does |
|---|---|
| `tools/flash.py` | **The one to use.** Flashes the firmware *and* copies the matching plain files, so they never get out of step. `--stock` rolls back to stock MicroPython. |
| `tools/deploy.py` | Copies files to the board without flashing. `--frozen` copies only the plain files (for the custom firmware); without it, it compiles and uploads the whole app. |
| `tools/build_fw.sh` | Builds the custom firmware in WSL Ubuntu (MicroPython v1.29.0 + ESP-IDF v5.5.2, with the app and drivers frozen in). Only rewrites changed board files, so a rebuild takes about 2 minutes. |
| `tools/zeki_manifest.py` | The list of what gets frozen into the firmware: Zeki's modules, the SparkFun Qwiic drivers and the OLED driver. |
| `tools/sdkconfig.zeki` | ESP-IDF settings for the custom build: mbedTLS dynamic buffers, so HTTPS borrows RAM only while it's in use. |
| `tools/make_qr.py` | Makes the printable "Give Zeki an idea!" QR cards (square and goldfish-shaped) for the Form. |

### Tests and data

| File | What it does |
|---|---|
| `tests/test_oled.py`, `test_tof.py`, `test_twist.py`, `test_buzzer.py`, `test_glow.py`, `test_wifi.py`, `test_https.py` | Day 1 bring-up: one part per script (screen, distance sensor, knob, buzzer, LED, Wi-Fi, HTTPS through Google's redirect). |
| `tests/test_knob.py` | Knob events (turn, click, hold) shown live on the OLED. |
| `tests/test_cup_live.py` | Live view of the distance sensor and cup logic on the OLED, for tuning. |
| `tests/test_praise.py` | Sends fake cup events into the real app to check the praise flow, then restores today's count. |
| `tests/record_cup.py` | Guided cup recording: the OLED says what to do in each phase, and every raw reading is logged for replay on the PC. |
| `tests/data/cup_topdown_2026-10-22.txt` | The real recording from the top-down cup. Used to tune the cup settings and as a regression test. |

### Demo

| File | What it does |
|---|---|
| `demo/zeki-presentation-notes.md` | Full presentation and talk notes: hardware, software, features, the Form-to-Zeki handshake, the custom firmware, what broke, numbers, demo script. |
| `demo/zeki-speaker-bullets.md` | Short speaker bullets for the final-round talk. |
| `demo/zeki-demo-notes.docx` | The demo notes as a Word document. |
| `demo/zeki-form-qr.png`, `demo/zeki-form-qr-goldfish.png` | QR cards for the idea Form. |

### Firmware (not in git: large binaries)

| File | What it does |
|---|---|
| `firmware/zeki-ESP32_GENERIC-v1.29.0-frozen.bin` | Current custom firmware (from `tools/build_fw.sh`). |
| `firmware/zeki-ESP32_GENERIC-v1.29.0-frozen-prev.bin` | The previous build, kept for a quick rollback. |
| `firmware/ESP32_GENERIC-20260824-v1.29.0.bin` | Stock MicroPython, for `tools/flash.py --stock`. |

### Other

| File | What it does |
|---|---|
| `zeki-build-spec.md` | Spec plus day-by-day engineering log. The source of truth. |
| `.gitignore` | Keeps `secrets.py`, compiled `.mpy` files, `build/` and firmware images out of git. |
| `.gitattributes` | Keeps shell scripts on Linux line endings, so `build_fw.sh` runs in WSL. |

## Everyday commands

Tools live in a Python venv at `%USERPROFILE%\.venvs\zeki`. The board is on `COM12`.

```bash
%USERPROFILE%\.venvs\zeki\Scripts\python.exe tools/flash.py
```

```bash
%USERPROFILE%\.venvs\zeki\Scripts\python.exe tools/deploy.py --frozen
```

```bash
wsl -d Ubuntu -- bash /mnt/c/Users/suctu/OneDrive/Documents/GitHub/Zeki-the-goldfish/tools/build_fw.sh
```

`flash.py` flashes and deploys. `deploy.py --frozen` copies plain-file changes only (`config.py`, `ideas.json`). `build_fw.sh` rebuilds the firmware after changing any frozen `.py`; then run `flash.py`.
