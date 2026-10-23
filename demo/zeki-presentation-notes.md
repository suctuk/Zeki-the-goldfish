# Zeki the Goldfish: presentation and demo notes

Source material for slides and the talk. Written Thu Oct 22 2026, the day before
the SparkFun final-round demo. The full engineering log is `zeki-build-spec.md`;
this file pulls out what's worth saying.

---

## 1. The one-liner

**Zeki is a 3D-printed goldfish desk pet who keeps your desk tidy and gives you project ideas.**
Drop something in the cup in his belly and he cheers. Turn his knob and he asks you
three questions, then suggests a project. Scan his QR code and your idea shows up
on his screen. "Zeki" means *smart* in Turkish. He is a goldfish. He forgets things.
That joke is the brand voice: cheerful, earnest, slightly unreliable, and the joke
is always on Zeki, never on the user.

---

## 2. Hardware: what each part does

Everything is Qwiic: one I2C daisy chain, no soldering.

| Part | Role in Zeki | I2C address | Interesting fact |
|---|---|---|---|
| **SparkFun Thing Plus ESP32 WROOM USB-C** (WRL-20168) | The brain: runs MicroPython, Wi-Fi, Qwiic port | n/a | ESP32-D0WD-V3, dual-core 240 MHz, 520 KB SRAM, **no PSRAM**, 2.4 GHz Wi-Fi only. The memory limit became the main engineering story (section 6). |
| **Qwiic OLED 1.3" 128x64** | Zeki's face: status bar + text | 0x3D | **SSD1306**, as SparkFun's product documentation specifies. The build first assumed SH1106 (common on 1.3" OLEDs), which left the screen blank (section 6). |
| **Qwiic VL53L1X distance sensor** | Cup sensor: looks down into the clutter well | 0x29 | Time-of-flight: fires invisible 940 nm laser pulses and times the reflection. 27° cone, about 40 mm minimum range, reports a *range status* with every reading. |
| **Qwiic Twist** | The knob: turn, click, long-press; RGB "mood" LED | 0x3F | Rotary encoder + button + RGB LED run by an onboard microcontroller that you talk to over I2C. |
| **Qwiic Buzzer** | Chimes | 0x34 | A *resonant* magnetic transducer: loud at 2730 Hz, almost silent far below it (section 6). |
| **MAX17048 fuel gauge** (on the Thing Plus) | Not used, but shows up in every I2C scan | 0x36 | Expected 4 devices, found 5: confirmed by reading its version register. |
| **Onboard WS2812 RGB LED** (GPIO2) | "Tail glow": the board and LED poke out of Zeki's tail (the translucent PLA window was cut for time) | n/a | Mirrors Zeki's mood: orange idle (breathing), green praise, blue inspire, purple new idea, dim red offline. Capped at 15% brightness. |

### How the circuit works
- **One I2C bus** (SDA = GPIO21, SCL = GPIO22, 400 kHz) chains all four Qwiic boards. Each board has a unique address, so they share two wires.
- **Qwiic power is switched by GPIO0.** The Thing Plus has its own regulator for the Qwiic port, enabled by GPIO0. Firmware must drive GPIO0 high and wait ~100 ms before talking I2C, or the whole chain is unpowered. Verified: GPIO0 low gives an empty scan, high gives all devices.
- **USB-C power.** Wi-Fi transmit peaks around 380 mA; the board's regulator is rated 700 mA. Fine on a USB wall adapter or power bank.
- **The ESP32 talks to Google over Wi-Fi** through a phone hotspot (2.4 GHz, WPA2), with HTTPS.

---

## 3. Software: how it's organised

MicroPython v1.29 on the ESP32, in a **custom firmware build** (section 5).

| File | What it does |
|---|---|
| `main.py` | Two lines plus a memory setting: `gc.threshold(16 KB)`, then `import zeki; zeki.start()` |
| `zeki.py` | The app: state machine, main loop, persistence, heartbeat, watchdog |
| `hw.py` | Hardware setup and thin wrappers: Qwiic power, the shared I2C bus, OLED, sensor, Twist, buzzer; `Mood` (LED colours), `Chime` (non-blocking notes), `Knob` (turn / click / long-press events) |
| `cup.py` | The cup interaction detector (section 4.1) |
| `inspire.py` | The "inspire me" questions and idea matcher (section 4.2) |
| `net.py` | Wi-Fi connect / reconnect, clock sync, the feed poller |
| `community.py` | The offline cache of community ideas (newest 50, on the board's flash) |
| `ui.py` | Screen: status bar, word wrap, page turning, ASCII clean-up |
| `lines.py` | Every line Zeki says, English and Turkish, never the same line twice in a row |
| `config.py` | Every tunable number in one place (editable without rebuilding) |
| `ideas.json` | 30 seeded project ideas |
| `apps_script.gs` | The Google side: moderation, approval, the JSON feed, alerts |
| `tools/` | `build_fw.sh` (firmware build), `flash.py` (flash + deploy), `deploy.py`, `make_qr.py` |

### The state machine
```
BOOT -> IDLE
IDLE -> CUP_EVENT    something put in / taken out of the cup
IDLE -> INSPIRE      click the knob
IDLE -> BROWSE       turn the knob: scroll community ideas
IDLE -> SUBMISSION   a new community idea arrived
IDLE -> SAY          "lost the internet" / "found it!"
everything -> IDLE   after a few seconds, a click, or a timeout
```
- One **main loop every ~20 ms**: read the sensor, poll the knob, update Wi-Fi, run the current screen, update LEDs and chime, redraw only if something changed.
- **Events queue up** while a screen is showing; "inspire me" is never interrupted.
- **Nothing ever blocks the loop**, with one deliberate exception (the feed check, section 4.3), which only runs when Zeki is idle and nobody is touching him.
- **Missing hardware is never fatal.** Unplug a part and Zeki carries on without it.
- **Everything that matters is saved to files** (today's count, cached ideas, what he's shown), so a reboot loses nothing.

---

## 4. Features and how they work

### 4.1 Cup detection: "detect the interaction, not the object"
The sensor looks straight down into the clutter well (redesigned to top-down after
testing a side mount, section 6), 59 mm above the floor. The algorithm:

```
SETTLED  -> a reading much closer than the settled level = a hand  -> ACTIVE
ACTIVE   -> readings steady again for 1.5 s -> compare to before:
              closer than before   -> ADDED   (praise + chime + count)
              farther than before  -> REMOVED (quiet "bye!")
              about the same       -> FIDDLED (small "tidy hands" line)
           then re-baseline to the new level
```
- **Why it works:** a hand reaching in always reads much closer than the contents, so it's an unmistakable trigger. Re-baselining after every interaction means the cup can fill up and Zeki still notices the next item.
- **Robustness built in:** median of 5 readings; out-of-range readings count as "far" instead of being dropped; never takes an "empty cup" level closer than 40 mm (a hand on the lens); gives up and re-learns if an interaction never settles; ADDED is counted the instant it's detected.
- **Tuned on real data:** the cone sees only a ~28 mm circle of the floor and a quick reach shows up for 1-6 readings, so a guided recording was replayed through the logic on the PC across 64 setting combinations. Chosen: 0 false triggers, every reach that entered the cone caught. Every completed interaction counts as tidying (with a 3 s cooldown), since the sensor can't always tell adding from removing.
- **Daily counter with a goldfish twist:** "That's 12 today! Or 127. One of those."

### 4.2 Inspire me
Click the knob, answer three questions (what should it do / vibe / parts: what's on my
desk or anything goes), and Zeki suggests a project. (A "how long have you got?" question was
cut: build time depends too much on experience to ask strangers on a public form.)
- **Matcher:** score = 1 per "does" match + 1 per "vibe" match; random among the best so repeat runs differ; "what's on my desk" keeps only ideas buildable from the parts on the desk.
- **30 seeded ideas:** 11 of your own (Mak Pack v2, Hot Flash Jacket, Stitch Counter, Sunrise Curtains, Bin Finder, Cyberdeck, Solar Weather, Phone Jail, Gary the useless robot, Hall Watcher, Fresh Air Check) and 19 from the SparkFun catalog, every part checked against the live catalog (e.g. the SFA30 formaldehyde sensor is retired, so it uses the SFA40).
- Every one of the 60 possible answer combinations gets a real match; if nothing matched, Zeki would invent a mash-up ("a silly gadget that wiggles using a load cell").
- **Community ideas join the pool**, so other people's ideas become Zeki's suggestions too.

### 4.3 Community ideas: Google Form to Zeki's screen
```
QR code -> Google Form -> Google Sheet -> Apps Script (moderate, approve, number)
        -> JSON web feed -> Zeki checks it -> chime + "Ooh, one from Blake!"
```
- **Moderation happens on Google's side, not on the ESP32:** easier to update, costs the device nothing.
  - Flags links, email addresses, phone numbers and @handles (spam and doxxing patterns), then an open-source profanity list (LDNOOBW, 403 terms) plus custom words. Whole-word matching, leetspeak and stretched-letter tricks caught, no false hits on part numbers like "SEN-15805" or "3.3V".
  - **Demo mode** auto-approves clean ideas; **review mode** waits for a human yes/no. The Approved column is the real safety net.
  - Ideas are numbered **when approved**, not when submitted, so a late approval still reaches Zeki.
- **Burst alert:** 4+ submissions in an hour emails the owner a link to the Sheet.
- **"N to review"** shows on Zeki when submissions are waiting for a human.
- **On the device:** he checks every 45 s when idle. **A new arrival rings once** (the newest, at most one chime a minute); everything else waits behind an "N new" badge like an inbox, and old ideas are never read out again on a timer (switched on to a backlog, he says "5 new ideas while you were away! Turn my knob." once, quietly); turn the knob to browse; the newest 50 ideas are kept offline; **hold the knob = "check for new ideas now"**.


#### The handshake, step by step (Form -> Script -> Zeki)

```
 phone            Google Form        Sheet + Apps Script                 Zeki (ESP32)
   |  scan QR, submit  |                     |                                  |
   |------------------>|  new row            |                                  |
   |                   |-------------------->| onFormSubmit:                    |
   |                   |                     |  1. check for links, emails,     |
   |                   |                     |     phones, @handles, bad words  |
   |                   |                     |  2. Flagged = reason or "no"     |
   |                   |                     |  3. demo mode + clean -> Approved|
   |                   |                     |     = yes -> next Id (e.g. 12)   |
   |                   |                     |                                  |
   |                   |                     |   every 45 s when idle, or hold  |
   |                   |                     |   the knob: GET /exec?since=11   |
   |                   |                     |<---------------------------------|
   |                   |                     | doGet: approved rows, Id > 11,   |
   |                   |                     | oldest first, max 5, + "pending" |
   |                   |                     |--------------------------------->|
   |                   |                     |  {"ideas":[{id:12,...}],         | save to community.json,
   |                   |                     |   "pending":0}                   | last_id = 12, chime +
   |                   |                     |                                  | "Ooh, one from Colette!"
```

1. **Submit.** The QR code opens a public Google Form (idea, optional name, "what does it do?", vibe). Google adds the answers as a new row in the linked Sheet.
2. **Check (on Google, instantly).** The submit fires the script's `onFormSubmit` trigger. It looks for contact info and spam patterns (links, email addresses, phone numbers, @handles) and runs the profanity list. The result goes in the **Flagged** column.
3. **Approve.**
   - **Demo mode:** a clean idea is approved automatically.
   - **Review mode:** **Approved** stays blank until Sena picks yes or no in the Sheet. Changing that cell runs the script's `onEdit` trigger.
4. **Number.** An approved row gets the next **Id** (1, 2, 3...), under a lock so two submissions at once can't get the same number. It's numbered when *approved*, not when submitted, so an idea approved hours later still gets the newest number.
5. **Zeki asks.** Every 45 s, when idle and nobody is touching him (or right away if you hold the knob), Zeki makes one HTTPS request to the script's public web-app URL: `.../exec?since=11`. That means "anything newer than the last one I have?" Before asking, he checks that there's enough free memory for the encryption (at least a 40 KB block).
6. **The script answers.** `doGet` reads the Sheet and replies with a small JSON document: approved ideas with an Id above 11, oldest first, at most 5. Long text is trimmed, and the Form's answer labels are turned into Zeki's tags ("Make noise" -> `noise`). The reply also includes **pending**, how many submissions wait for a human; Zeki shows that as "N to review". Example: `{"ideas":[{"id":12,"name":"Colette","text":"Digital Jewelry!","does":["show"],"vibe":["wearable"]}],"pending":0}`
7. **Zeki saves and announces.**
   - He adds the new ideas to `community.json` (the newest 50 are kept, so they survive reboots and offline time) and remembers `last_id = 12`.
   - He chimes and shows the newest one. The rest wait behind the "N new" badge.
   - If he got a full page of 5, he asks again 2 s later for the rest.
   - The ideas also join the "inspire me" pool.

**Why it's built this way (talking points):**
- **Zeki only ever asks; nothing calls in.** There's no server to run and no open port on the device. The only secret on the board is the script URL, and it only ever returns approved, trimmed ideas.
- **The `since` number is the whole protocol.** Google doesn't need to remember what Zeki has seen. If a reply is lost, or Zeki reboots, he asks again with the same number and gets the same ideas. Nothing is shown twice, and nothing is skipped.
- **Moderation lives where it's cheap and easy to change.** The script can be updated in a browser in seconds. The ESP32 only receives clean ideas that already have their tags.
- **One request takes 4-7 s, sometimes ~20 s.** Google's `/exec` URL redirects to a second server (`script.googleusercontent.com`), so it's **two** HTTPS connections. Each needs ~43 KB of the ESP32's internal RAM, which is why the custom firmware exists (section 5). Zeki only asks while idle, and shows a down-arrow while he waits.
- **When it fails, it fails politely.** He waits 8 s at most, then retries with growing gaps (up to 10 min). The status bar shows an X, and everything else keeps working from the saved ideas.
- **Submit to screen takes about 15 s to 1.5 min.** That's up to a 45 s wait for his next check, plus the request time. Holding the knob skips the wait, which makes a good live demo.

### 4.4 Always-visible network status and offline mode
- Status bar: Wi-Fi signal bars, sweeping bars while reconnecting, a blinking X when offline (or when Wi-Fi is up but the internet isn't), a down-arrow while fetching.
- Turn the hotspot off: Zeki says "Lost the internet. Or forgot where I put it.", turns dim red, and **everything else keeps working** (cup, inspire, cached ideas). Turn it back on: "Found it!" plus a chime. Rehearsed and verified.

### 4.5 Reliability layer
- **Hardware watchdog:** if the main loop ever freezes for 30 s, the ESP32 reboots itself. All state is in files, so he comes back as he was. (Fits the character: "Hi! I forgot everything. Fresh start!")
- **Heartbeat** line in the serial log every minute: state, Wi-Fi, last check, memory. "Is it working?" is answered in seconds.

---

## 5. The custom firmware (and why)

Stock MicroPython copies every module into RAM to run it. Zeki plus the SparkFun
drivers took **~80 KB of RAM** before doing anything, on a board with no PSRAM, and
HTTPS needs a large contiguous block of its own. Every request failed with
out-of-memory.

**Fix:** a custom MicroPython build (same v1.29.0, same official SparkFun drivers)
with the code **frozen into flash**, where it runs without taking RAM. Built in WSL
Ubuntu with Espressif's ESP-IDF v5.5.2.

| With all of Zeki loaded | Stock firmware | Custom firmware |
|---|---|---|
| Free Python memory | 48 KB | **93 KB** |
| Free internal RAM (largest block) | 24 KB (14 KB) | **84 KB (64 KB)** |
| HTTPS | out of memory every time | works |

`config.py`, `secrets.py` and `ideas.json` stay editable on the board. `tools/flash.py`
flashes and deploys in one step (they must match, see section 6). The stock image is kept for a 5-minute rollback.

---

## 6. What broke, and how it was found ("Three things that broke", extended edition)

> **Correction (Oct 22, from a separate Claude chat, not Claude Code):** earlier drafts said the OLED is "sold as SH1106." That was wrong. Sena checked SparkFun's product page (https://www.sparkfun.com/sparkfun-qwiic-oled-1-3in-128x64.html#content-documentation) and it correctly lists the SSD1306. The bug was our assumption, not the listing. Talk framing: "SparkFun's docs had the answer all along. Lesson one: read the hookup guide."

Each one: symptom, cause, fix, and how it was proven. This is the strongest material
for an engineering interview: every fix is backed by a measurement, not a guess.

| # | Symptom | Real cause | Fix | Evidence |
|---|---|---|---|---|
| 1 | **OLED stayed blank** | Assumed SH1106 (common on 1.3" OLEDs); SparkFun's docs specify SSD1306, and the SH1106 driver never turns on the SSD1306's charge pump | Use the `ssd1306` driver | Drew test patterns with both drivers; only SSD1306 worked, matching the product docs |
| 2 | **Buzzer silent** | Resonant transducer: notes at 523-784 Hz are almost inaudible; 2730 Hz at max is very loud | Chimes in the C7-G7 band (2.1-3.1 kHz) at medium volume | Register read-back proved the I2C writes landed; a 1 s tone at resonance was heard |
| 3 | **Wi-Fi "out of memory" at boot** | Loading drivers first let MicroPython's heap grow into the RAM Wi-Fi needs | Start Wi-Fi first; precompile drivers | Boot log before and after |
| 4 | **Hotspot "connected" but no internet** | The phone had no upstream to share (on the move / tethering) | Check the phone first; status-bar X now shows "Wi-Fi up, internet down" | DNS worked, every TCP connection timed out, even to 1.1.1.1 |
| 5 | **Phantom long-presses on the knob** | The Twist firmware *toggles* its "pressed" bit on every press and release; the official driver *clears* it, which inverts it | Read status once per poll, never clear that bit, time holds on the ESP32 | Read SparkFun's Twist firmware source (`interrupts.ino`) |
| 6 | **Cup "stuck", stopped reacting** | A hand on the lens became the "empty cup" level; far readings were then thrown away, so it never recovered | Out-of-range counts as far; never baseline under 40 mm | Live log, then 13/13 simulated scenarios including both regressions |
| 7 | **Holding a hand still didn't register** | A held hand wobbles about +/-11 mm; the "steady" band was +/-5 mm | Widen to +/-12 mm, settle on the window's average | Recorded the sensor, replayed the recording through the logic on the PC |
| 8 | **HTTPS out of memory** | No PSRAM; ~80 KB of code in RAM | Custom firmware with frozen modules | RAM measured step by step: the exact driver load where it ran out |
| 9 | **Background thread for HTTPS: hangs, EBUSY, a crash** | Thread stack + encryption buffers used *all* internal RAM (heartbeat showed 0 KB free) | Check on the main loop, only when idle and quiet | Heartbeat logs; Ctrl-C tracebacks |
| 10 | **Zeki froze forever in a network request** | The TLS handshake ignores the socket timeout when a weak hotspot stalls | Hardware watchdog reboots after 30 s; state survives | Deliberately froze the loop: rebooted itself after 30 s; later caught a real hang |
| 11 | **Crash at boot after a firmware update** | New firmware, old `config.py` on the board | `tools/flash.py` always flashes and deploys together | The crash traceback named the missing setting |
| 12 | **First check worked, later ones failed** | Each check's ~43 KB of encryption buffers stayed in memory until garbage-collected, and the clean-up ran while they were still in use | Release before cleaning up; check memory before each request | RAM logged before/after each check: 82 KB -> 23 KB, then the 3rd check hung; after the fix 8/8 at the same rhythm |
| 13 | **Memory crept away after "inspire me"** | MicroPython on ESP32 grows its heap into internal RAM instead of cleaning garbage first | `gc.threshold(16 KB)`: collect garbage regularly | RAM held steady at 82 KB / 54 KB across checks |
| 14 | **Side-mounted cup sensor read nonsense** | Mounted on the bowl wall: the far side was 31-35 mm away, inside the sensor's ~40 mm blind zone, and items sat in its view | Redesigned the print: sensor at the top looking down, floor 60-70 mm away | Guided recordings: empty 35 mm steady, anything in the cup read 0 |
| 15 | Google Apps Script setup gotchas | Run button still pointed at the deleted placeholder; a script made from the Form has no spreadsheet; transient Google storage errors | Pick `setup` after saving; create the script from the Sheet; retries + self-healing in the script | Error messages; 44/44 tests of the script against a fake Sheet |

**Status of live community ideas at time of writing:** they work most of the time
(several ideas arrived and were announced live, including your mom's "Daily pill
reminder"), but on a phone hotspot some checks still fail: out-of-memory inside the
networking stack, timeouts, and occasional Google errors. A firmware memory setting (mbedTLS "dynamic buffers")
didn't raise the success rate (7 of 20 checks on the hotspot; the rest were timeouts,
Google 404s and out-of-memory errors), but in a side-by-side test it **never froze**,
while the previous firmware froze on its first check. Zeki ships with the dynamic-buffer
build: a failed check is now a polite "Couldn't reach the idea box", not a frozen screen. Whatever
happens, Zeki recovers on his own; community ideas he has already fetched always work.

---

## 7. Numbers worth quoting

- **5 I2C devices** on one bus (4 Qwiic + the onboard fuel gauge).
- Distance sensor: **16.5 readings per second**, 27° cone, a held hand wobbles **+/-11 mm**.
- **30 seeded ideas**, 11 of them yours; all **60 answer combinations** get a real match.
- Moderation: **403** blocklist terms + links/emails/phones/handles; **44/44** tests of the Google script.
- **65** automated checks of the main loop and **15** cup scenarios, run on a PC with fake hardware before anything touched the board.
- Custom firmware: free Python memory **48 KB -> 93 KB**; internal RAM largest block **14 KB -> 64 KB**.
- A feed check takes **4-12 s** on a hotspot (two encrypted connections, because Google redirects); Zeki only does it when idle.
- Watchdog: **30 s** freeze -> self-reboot, ~10 s back to normal, nothing lost.

---

## 8. Demo script (from the spec's demo plan, with fallbacks)

| Step | Do | Say | If it misbehaves |
|---|---|---|---|
| 1 | Zeki idling, status bar shows connected | "This is Zeki. Zeki means smart in Turkish. He's a goldfish." | Offline? Step 5 is your proof it doesn't matter |
| 2 | Put a pen or eraser in the cup **by hand, toward the middle** | "Detect the interaction, not the object: a hand reaching in reads much closer than the contents." | No reaction: reach in once more toward the middle. Avoid thin black items (black absorbs the infrared) |
| 3 | Click the knob, answer the questions | "Every idea is tagged; the matcher scores time, what it does, and the vibe." | Hold the knob to go back a question |
| 4 | Hand over the goldfish QR card; they submit an idea; **hold the knob** | "It goes through moderation on Google's side, then Zeki fetches it." | Doesn't arrive: show the Sheet (flagging, approval) and turn the knob to browse ideas he already has. Tell the memory story |
| 5 | Turn the hotspot off, then on | "Offline, everything local keeps working." | n/a: rehearsed |

Before the interview: run `setDemoMode()` in the Apps Script editor (instant approval), have the goldfish QR card printed, charge the phone, bring a spare USB-C cable. Afterwards: `setReviewMode()` before sharing the Form publicly.

---

## 9. Design decisions worth explaining

- **Detect the interaction, not the object.** Measuring the fill level is fragile; a hand reaching in is unmistakable.
- **Moderation server-side.** Easier to update, costs the device nothing, and a human approval column is the real safety net.
- **Never block the loop; offline-first.** Zeki is a desk pet first and an internet device second.
- **Evidence before fixes.** Every bug above was measured (recordings, RAM logs, tracebacks, firmware source) before anything was changed, and fixes were proven with tests on the PC and soak tests on the board.
- **Personality as a feature.** Failures are in character: offline is "or I forgot where I put it", a reboot is "fresh start!", the count "might be 127".

---

## 10. Where to find things
- Engineering log, every measurement, day by day: `zeki-build-spec.md`
- QR cards: `demo/zeki-form-qr-goldfish.png`, `demo/zeki-form-qr.png`
- The Google side: `apps_script.gs` (install steps at the top)
- Firmware build and flashing: `tools/build_fw.sh`, `tools/flash.py`
- Live sensor view for tuning: `tests/test_cup_live.py`; guided recording: `tests/record_cup.py`
