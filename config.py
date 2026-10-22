# config.py — every tunable in one place.

# --- Timing -------------------------------------------------------------
LOOP_MS = 20                # main loop period
EVENT_SHOW_MS = 6000        # CUP_EVENT / SAY screens return to IDLE after this
COUNT_AFTER_MS = 3000       # within a praise event, switch to the count line after this
IDLE_LINE_MS = 45_000       # rotate the idle line this often

# --- Wi-Fi --------------------------------------------------------------
WIFI_CONNECT_TIMEOUT_MS = 15_000   # per network attempt
WIFI_RETRY_MS = 60_000             # wait this long after a full failed pass
HOSTNAME = "zeki"
TZ_OFFSET_H = -6                   # Boulder, MDT. (-7 after Nov 1.) Used for the daily count rollover.

# --- Cup detection (VL53L1X, top-down) ----------------------------------
# Starting values from the spec. TUNE once the sensor is mounted: set
# CUP_DEBUG = True and watch the serial log while using the cup.
CUP_DEBUG = False
TOF_TIMING_BUDGET_MS = 50
TOF_INTER_MEAS_MS = 60
MEDIAN_N = 5
HAND_MM = 30        # reading this much closer than settled = hand in the cup
NOISE_MM = 12       # readings within +/- this are "stable". Spec said 5; a hand held
                    # still measured +/-11 mm (stdev) on Day 3, so 5 rarely settled
DELTA_MM = 8        # level change that counts as ADDED / REMOVED
SETTLE_MS = 1500    # how long readings must stay stable before comparing
ACTIVE_TIMEOUT_MS = 10_000  # give up on an interaction that never settles
MIN_SETTLE_MM = 40  # never take a baseline closer than this (hand/object on the lens)
TOF_FAR_MM = 1500   # "nothing in range" readings count as this far

# --- Feedback -------------------------------------------------------------
# State colors (Twist LED + body glow). Full-scale RGB; glow is scaled down.
COLOR_IDLE = (255, 80, 0)       # soft orange
COLOR_PRAISE = (0, 255, 40)     # green
COLOR_INSPIRE = (0, 60, 255)    # blue
COLOR_SUBMISSION = (160, 0, 255)  # purple
COLOR_OFFLINE = (120, 0, 0)     # dim red
TWIST_BRIGHTNESS = 0.6
GLOW_MAX = 0.15                 # WS2812 brightness cap (it's inches from the face)
GLOW_MIN = 0.04                 # idle breathing floor
GLOW_BREATH_MS = 4000           # one full breath

# Chimes: the buzzer resonates at 2730 Hz, keep notes in C7-G7. Volume 3 = MID.
CHIME_VOLUME = 3
CHIME_PRAISE = ((2093, 120), (2637, 120), (3136, 160))   # C7 E7 G7 rising
CHIME_ONLINE = ((2637, 90), (3136, 120))

# --- Twist input --------------------------------------------------------
TWIST_POLL_MS = 30
LONG_PRESS_MS = 800             # hold this long = back / cancel

# --- Inspire me (Day 3) -----------------------------------------------------
INSPIRE_TIMEOUT_MS = 30_000     # no input for this long -> back to IDLE
INSPIRE_INTRO_MS = 2000
INSPIRE_OUTRO_MS = 7000       # click to dismiss sooner
IDEAS_FILE = "ideas.json"

# "Use what's on my desk": ideas qualify only if every part is in here.
INVENTORY = ("oled", "tof", "twist", "buzzer", "rgb-led")

# (answer key, question, ((value, label), ...)). Labels <= 14 chars so
# "<label>" fits one 16-char row. Values match the tags in ideas.json.
QUESTIONS = (
    ("time", "How long have you got?",
     (("15min", "15 min"), ("afternoon", "An afternoon"), ("weekend", "A weekend"))),
    ("does", "What should it do?",
     (("sense", "Sense"), ("show", "Show"), ("move", "Move"),
      ("noise", "Make noise"), ("online", "Go online"))),
    ("vibe", "Vibe?",
     (("useful", "Useful"), ("silly", "Silly"), ("wearable", "Wearable"), ("desk", "Desk toy"))),
    ("parts", "Parts?",
     (("desk", "My desk only"), ("any", "Anything goes"))),
)
# Twist LED color per option index while answering (feedback as you turn).
OPTION_COLORS = ((255, 80, 0), (0, 200, 60), (0, 80, 255), (200, 0, 200), (255, 200, 0))

CHIME_IDEA = ((3136, 90), (2637, 90), (3136, 160))
CHIME_TICK = ((2093, 25),)      # confirm click

# --- Community ideas (Day 4) -----------------------------------------------
POLL_MS = 45_000                # how often to ask the Apps Script feed for new ideas
POLL_TIMEOUT_S = 8              # per socket operation; a poll blocks Zeki 4-7 s normally
POLL_QUIET_MS = 10_000          # only poll after this long with no knob input
POLL_BACKOFF_MAX_MS = 600_000   # failed polls back off 2x per failure, up to 10 min
POLL_MIN_BLOCK = 40_000         # only poll if IDF RAM has a free block this big (TLS
                                # starves below ~25 KB: hangs / OSError(16))
RAM_REBOOT_MS = 300_000         # RAM still too low after this (idle, quiet): reboot to free it
ANNOUNCE_GAP_MS = 5 * 60_000    # at most one "New idea from..." chime per 5 min;
                                # the rest wait quietly behind the "N new" badge
COMMUNITY_FILE = "community.json"
COMMUNITY_MAX = 50              # newest ideas kept offline
SUBMISSION_HEADER_MS = 2500     # "Ooh, one from Blake!" before the idea text
PAGE_MS = 3500                  # long ideas turn pages this often (turn = next page)
BROWSE_TIMEOUT_MS = 20_000
CHIME_SUBMISSION = ((2637, 90), (3136, 90), (2637, 90), (3136, 160))
STALL_LOG_MS = 300              # log any main-loop pause longer than this
HEARTBEAT_MS = 60_000           # one "hb:" status line in the log this often
# Hardware watchdog: if the main loop doesn't come round for this long, the
# ESP32 reboots itself (state is all in files, so Zeki picks up where he
# was). Day 4: an HTTPS handshake hung forever on a weak hotspot; the socket
# timeout doesn't cover the TLS handshake. 0 = off (e.g. for long dev
# sessions: once started, the watchdog keeps running at the REPL too).
# 30 s: a normal poll takes ~7 s, the slowest normal failure ~15 s.
WATCHDOG_S = 30
