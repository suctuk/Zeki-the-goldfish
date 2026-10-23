# Zeki: speaker bullets (SparkFun final round, Fri Oct 23)

Format: tour, then their questions, then this. 15 min talk + 5 min Q&A. 8 people in the room, videographer (Cassy) likely filming.
Zeki is the star. Slides are backup only (list at the bottom).
Source: zeki-presentation-notes.md. Drafted in a separate Claude chat, Oct 22.

---

## 0:00 to 1:00 | Hook
- Play the Le Poisson Steve short (5 s): https://www.youtube.com/shorts/V4ygI1MzwFA
- "You might know Le Poisson Steve. This is his cyborg Turkish brother, Zeki."
- "Zeki means *smart* in Turkish. He's a goldfish. He forgets things."
- Named after my own goldfish. Steve's body (Printables, Tedi Studio; character by @vigzvigz and @tomomp3) because my little sister loves him.
- One-liner: keeps your desk tidy, gives you project ideas.
- Brand rule, said out loud: the joke is always on Zeki, never on the user.
- Callback to the tour if anything fits.

## 1:00 to 1:30 | Hand out the QR cards
- "Scan this and give Zeki a project idea. We'll check on it at the end."
- With 8 people: he chimes at most once per 5 min on purpose, the rest wait behind an "N new" badge. Say it's a design choice.

## 1:30 to 4:00 | Live demo: cup + inspire
- Drop a pen in. He cheers, counts. "That's 12 today! Or 127."
- "Detect the interaction, not the object." A hand reaching in always reads closer than the contents, so the cup can fill up and he still notices.
- Put items in by hand, toward the middle. Light or shiny (eraser, pen, binder clip), not thin black cables.
- Note (Day 5 tuning): add vs. remove can't be told apart top-down, so every completed reach counts as tidying. No "bye!" line.
- Click the knob, answer three questions, get an idea.
- 30 seeded ideas: 11 mine (Mak Pack v2 is in there), 19 real SparkFun builds, parts checked against the live catalog. Retired SFA30 swapped for SFA40.
- If the cup misses: reach in again slowly, it re-learns.

## 4:00 to 5:30 | How it works
- Thing Plus ESP32 + four Qwiic boards. One daisy chain. No soldering.
- OLED face, distance sensor in the cup, Twist knob, buzzer. The board's LED pokes out of his tail and glows with his mood.
- **Under $130 in SparkFun parts ($128.80)**, plus filament.
- Hookup-guide aside: Qwiic power on this board is switched by GPIO0. Forget it and the whole chain looks dead.
- MicroPython. One loop every 20 ms. Nothing blocks it. Unplug a part and he carries on.

## 5:30 to 7:30 | How I actually built it (transparency)
- The honest timeline:
  - 3 hrs research and ideation
  - 5 hrs active code and hardware time, with Claude Code
  - 5 hrs modeling in Rhino 8
  - 2 print iterations, ~5 hrs each, on a Bambu Lab H2S
- "Custom firmware, a moderation backend, 15 bugs tracked down. That doesn't fit in 5 hours by hand. I built this with Claude Code, and I want to be clear about who did what."
- **What I did:**
  - Designed the interaction framework: what Zeki does and how you interact with him
  - Wrote much of his dialog and the starting project ideas
  - Set up the environment so Claude Code could write and flash the firmware
  - Built the Google Form that feeds community ideas in
  - The 3D model, the prints, the assembly
  - Supervised: reviewed, tested, and decided what was true
- **What Claude Code did:** the firmware and app code, the custom MicroPython build, the Apps Script that connects the Form, the test harness.
- **Where supervision mattered:** AI is confident and sometimes wrong. It guessed SH1106. Even last night its notes said SparkFun's listing was wrong. I checked the product page; the listing was right.
- Why it matters here: SparkFun customers are building with AI now. Content from someone who knows where it helps and where it breaks is useful to them.

## 7:30 to 10:30 | What broke (4 stories, ~45 s each)
Throughline: "Every fix was measured before it was made."

1. **Blank screen.** Assumed SH1106, the common 1.3" chip. SparkFun's docs said SSD1306 the whole time. "Lesson one: read the hookup guide."
2. **Silent buzzer.** It's resonant. Normal melody notes are nearly mute; 2730 Hz is loud. Moved every chime to 2 to 3 kHz.
3. **Phantom knob presses.** Read the Twist firmware source. The pressed bit *toggles*; the driver *clears* it, which inverts it. Frame as: here's what I'd flag to the product team.
4. **Out of memory.** No PSRAM, HTTPS needs a big block. Custom MicroPython with code frozen into flash. Free memory 48 KB to 93 KB.

## 10:30 to 12:00 | Payoff + offline
- Hold the knob: "check for new ideas now." Read theirs off his screen.
- If it doesn't arrive: show the Sheet (moderation flags, approval column), browse cached ideas, tell it as the memory story. He recovers on his own.
- Moderation lives on Google's side: links, emails, phones, handles, 403-word blocklist, human approval column.
- Hotspot off: "Lost the internet. Or forgot where I put it." Local features keep working. On: "Found it!"

## 12:00 to 14:00 | What I'd change, and what this becomes
- **The pivot:** the distance sensor started as a door sensor. Chime when someone walks in. I switched it to the cup because a pet that helps keep my space organized is more useful.
- **What I'd change:** the VCNL4040 proximity sensor (SEN-15177, $4.95) instead of the VL53L1X. The VL53L1X is a 4 m sensor with a ~40 mm blind zone, sitting in a cup: right for a doorway, wrong for a cup. The VCNL4040 is built for 0 to 20 cm with zero dead zone, and $25 cheaper.
- **Caveat:** the VCNL4040 reads reflected brightness, the same way soap dispensers that failed on darker skin work. Calibrate to each cup and test with a range of hands before shipping it.
- **It's already content:**
  - Hookup guide (wiring, GPIO0, driver choice)
  - "Qwiic gotchas" tutorial from the bug list
  - Short videos: each "what broke" is a 30 s clip; print and assembly footage already exists
  - Community ideas as an engagement loop
- Tie to the room: amplification (shareable character), product marketing (real parts, real build), video (Zeki is very filmable).

## 14:00 to 15:00 | Close
- Personality as a feature: offline is "forgot where I put it," a reboot is "fresh start!"
- Let Zeki say the last line.

---

## Q&A prep (5 min)
- **How long did it take?** ~13 hrs hands-on + ~10 hrs printing. (Breakdown above.)
- **What did it cost?** $128.80 in SparkFun parts + filament.
- **How much did you write vs. the AI?** Framework, dialog, ideas, environment, Google Form: me. Code and firmware: Claude Code, supervised by me. Don't round up.
- **"What did supervising Claude Code actually look like?"** (~45 s, bullets marked * are add-ons to confirm)
  - **Watched the terminal.** Every command it ran on my machine and on the board, so I knew what it was touching and could stop it.
  - **Commits as documentation.** I organized commits by build day ("Day 1: test I2C, test internet" through "Day 5: polling test"), so the history reads like a build log.
  - **Checkpoints before risky changes.** * Committed "saving current before custom firmware" before the firmware swap, and kept the stock image for a 5-minute rollback.
  - **Ran the real-world tests.** The AI can't reach into the cup. I did the hand-in-cup recordings, the knob presses, turning the hotspot off and on, and listening for the buzzer.
  - **Held it to evidence.** * Fixes had to come with a measurement: a sensor recording, a RAM log, a traceback. When it claimed something, I checked the source, like the OLED listing.
  - **Kept the scope.** * I decided what Zeki is and isn't. The AI proposes; I choose.
  - Close it with: "Claude Code was my pair programming buddy. It typed fast and knew a lot; I steered, tested, and checked its work. Like any pair, sometimes it was confidently wrong, and catching that was my half of the job."
- **Why MicroPython over Arduino?**
- **What would v2 be?** VCNL4040 in the cup, reliable feed on weak Wi-Fi (PSRAM board), battery.
- **Does the VCNL4040 still work with your algorithm?** Mostly. It gives relative proximity, not millimeters, so the hand trigger is easy. Caveat: it measures reflected brightness, so it's more sensitive to dark surfaces and skin tone than ToF; test with many hands. Bonus: its ambient light sensor could let Zeki sleep when the lights go off.
- **Will you publish it?** Code yes. The enclosure is a remix: the Printables page doesn't state a remix license, so check with Tedi Studio before posting.
- **How would you explain it to a beginner?** "He notices your hand, not the pen."

## Parts (all SparkFun)
| Part | SKU | Price |
|---|---|---|
| Thing Plus ESP32 WROOM (USB-C) | WRL-20168 | $29.95 |
| Qwiic Cable Kit | KIT-15081 | $12.95 |
| Qwiic OLED 1.3" 128x64 | LCD-23453 | $19.95 |
| Distance Sensor VL53L1X (Qwiic) | SEN-14722 | $29.95 |
| Qwiic Twist RGB Rotary Encoder | DEV-15083 | $25.50 |
| Qwiic Buzzer | BOB-24474 | $10.50 |
| **Total** | | **$128.80** |
| v2 swap: VCNL4040 Proximity (Qwiic) for the VL53L1X | SEN-15177 | $4.95 (total $103.80) |

## Before you walk in
- `setDemoMode()` in Apps Script.
- QR cards for 8.
- Ask for 2.4 GHz guest Wi-Fi; hotspot as fallback. Phone charged.
- Spare USB-C cable, power bank.
- Laptop with the Steve short and backup slides downloaded (don't rely on venue Wi-Fi for video). Ask about a screen or HDMI when you arrive.
- Afterwards: `setReviewMode()`.

## Backup slides (only if needed)
0. Le Poisson Steve short (opener)
1. Title: Zeki + one-liner
2. Qwiic chain diagram + parts/price table
3. Process videos: 3D printing, test assemblies, OLED code tests
4. Build timeline (the hours breakdown)
5. Cup algorithm + a sensor recording plot
6. Twist firmware snippet (the toggle bit)
7. Memory table: stock vs custom firmware
8. Moderation pipeline: QR to Form to Sheet to feed to Zeki
9. Credits: Le Poisson Steve base model
