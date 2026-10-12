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
NOISE_MM = 5        # readings within +/- this are "stable"
DELTA_MM = 8        # level change that counts as ADDED / REMOVED
SETTLE_MS = 1500    # how long readings must stay stable before comparing
ACTIVE_TIMEOUT_MS = 10_000  # give up on an interaction that never settles

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
