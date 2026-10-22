#!/bin/bash
# Build Zeki's custom MicroPython firmware (v1.29.0 + frozen modules) in WSL Ubuntu.
#
#   wsl -d Ubuntu -- bash /mnt/c/Users/suctu/OneDrive/Documents/GitHub/Zeki-the-goldfish/tools/build_fw.sh
#
# One-time setup (needs sudo, done by you):
#   sudo apt-get install -y git wget flex bison gperf python3 python3-pip python3-venv cmake \
#       ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0 build-essential
# Sources (fetched once into ~/zeki-build):
#   micropython v1.29.0, esp-idf v5.5.2 (MicroPython's recommended version)
#
# Output: firmware/zeki-ESP32_GENERIC-v1.29.0-frozen.bin in the repo (gitignored).
# Flash it with esptool at 0x1000 WITHOUT erase-flash, so the board's files stay.
set -euo pipefail

WORK=~/zeki-build
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export ZEKI_REPO="$REPO"
export ZEKI_DRIVERS=/mnt/c/Users/suctu/zeki-build/drivers
BOARD=ESP32_GENERIC
OUT="$REPO/firmware/zeki-$BOARD-v1.29.0-frozen.bin"

[ -d "$WORK/esp-idf" ] || { echo "missing $WORK/esp-idf (run fetch_idf.sh)"; exit 1; }
[ -d "$WORK/micropython" ] || { echo "missing $WORK/micropython (run fetch_micropython.sh)"; exit 1; }
for d in Qwiic_I2C_Py qwiic_vl53l1x_py qwiic_twist_py Qwiic_Buzzer_Py; do
    [ -d "$ZEKI_DRIVERS/$d" ] || { echo "missing driver repo $ZEKI_DRIVERS/$d"; exit 1; }
done

# ESP-IDF toolchain for the ESP32 only (first run downloads it, ~500 MB).
if [ ! -f "$WORK/.idf_installed" ]; then
    (cd "$WORK/esp-idf" && ./install.sh esp32)
    touch "$WORK/.idf_installed"
fi
# shellcheck disable=SC1091
. "$WORK/esp-idf/export.sh" > /dev/null

cd "$WORK/micropython"
make -C mpy-cross -j"$(nproc)"
cd ports/esp32
make submodules BOARD=$BOARD
make -j"$(nproc)" BOARD=$BOARD FROZEN_MANIFEST="$REPO/tools/zeki_manifest.py"

mkdir -p "$REPO/firmware"
cp "build-$BOARD/firmware.bin" "$OUT"
echo
echo "built: $OUT ($(stat -c %s "$OUT") bytes)"
grep -E "^Used|firmware.bin|Project build complete" -r "build-$BOARD/log" 2>/dev/null | tail -3 || true
