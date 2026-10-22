# Frozen-module manifest for Zeki's custom MicroPython build (tools/build_fw.sh).
#
# Why: on the Thing Plus ESP32 (no PSRAM) the app + SparkFun drivers took
# ~80 KB of RAM as .mpy files, leaving no contiguous block for HTTPS (TLS
# needs 35-59 KB) -> every poll failed with OSError(12) ENOMEM. Frozen
# bytecode runs from flash, so that RAM comes back.
#
# Stays OUT of the freeze (plain files on the board, editable any time):
#   main.py, config.py, secrets.py, ideas.json
# Frozen modules can still be overridden: sys.path is ['', '.frozen', '/lib'],
# so uploading e.g. cup.py to the board root wins over the frozen copy.
#
# Paths come from the environment (set by build_fw.sh):
#   ZEKI_REPO    this repo
#   ZEKI_DRIVERS folder with the SparkFun driver repos, pinned commits:
#     Qwiic_I2C_Py 670c3c0, qwiic_vl53l1x_py 58ae3ba, qwiic_twist_py 2264fa3,
#     Qwiic_Buzzer_Py 09248dc

import os

REPO = os.environ["ZEKI_REPO"]
DRIVERS = os.environ["ZEKI_DRIVERS"]

# Everything the stock ESP32_GENERIC firmware freezes (asyncio, requests,
# ntptime, neopixel, ...), so nothing that worked before goes missing.
include("$(PORT_DIR)/boards/manifest.py")

# micropython-lib display driver.
require("ssd1306")

# SparkFun Qwiic drivers. qwiic_i2c: only the files its mip package ships.
package("qwiic_i2c", files=("__init__.py", "i2c_driver.py", "micropython_i2c.py"),
        base_path=os.path.join(DRIVERS, "Qwiic_I2C_Py"))
module("qwiic_vl53l1x.py", base_path=os.path.join(DRIVERS, "qwiic_vl53l1x_py"))
module("qwiic_twist.py", base_path=os.path.join(DRIVERS, "qwiic_twist_py"))
module("qwiic_buzzer.py", base_path=os.path.join(DRIVERS, "Qwiic_Buzzer_Py"))

# Zeki's own modules.
for m in ("hw", "ui", "net", "cup", "inspire", "community", "lines", "zeki"):
    module(m + ".py", base_path=REPO)
