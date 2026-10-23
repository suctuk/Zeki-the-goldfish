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
# Board: a copy of MicroPython's ESP32_GENERIC plus tools/sdkconfig.zeki
# (mbedTLS dynamic buffers etc.), made in ~/zeki-build/boards so MicroPython's
# own source stays untouched.
#
# Output: firmware/zeki-ESP32_GENERIC-v1.29.0-frozen.bin in the repo (gitignored);
# the previous build is kept as ...-frozen-prev.bin. Flash with tools/flash.py.
set -euo pipefail

WORK=~/zeki-build
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export ZEKI_REPO="$REPO"
export ZEKI_DRIVERS=/mnt/c/Users/suctu/zeki-build/drivers
BOARD=ESP32_GENERIC_ZEKI
BOARD_DIR="$WORK/boards/$BOARD"
OUT="$REPO/firmware/zeki-ESP32_GENERIC-v1.29.0-frozen.bin"

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

# Custom board = ESP32_GENERIC + Zeki's sdkconfig fragment (appended last, so it wins).
# Assembled in a temp dir, then copied over only where the CONTENT changed: rewriting
# unchanged files makes CMake reconfigure and forces a full ~10 min rebuild.
STAGE="$(mktemp -d)"
cp -r "$WORK/micropython/ports/esp32/boards/ESP32_GENERIC/." "$STAGE/"
cp "$REPO/tools/sdkconfig.zeki" "$STAGE/sdkconfig.zeki"
cat >> "$STAGE/mpconfigboard.cmake" <<'EOF'

# Zeki: mbedTLS dynamic buffers etc. (tools/sdkconfig.zeki in the Zeki repo)
list(APPEND SDKCONFIG_DEFAULTS ${MICROPY_BOARD_DIR}/sdkconfig.zeki)
EOF
mkdir -p "$BOARD_DIR"
(cd "$STAGE" && find . -type f) | while read -r f; do
    if ! cmp -s "$STAGE/$f" "$BOARD_DIR/$f"; then
        mkdir -p "$(dirname "$BOARD_DIR/$f")"
        cp "$STAGE/$f" "$BOARD_DIR/$f"
        echo "board file updated: $f"
    fi
done
rm -rf "$STAGE"

cd "$WORK/micropython"
make -C mpy-cross -j"$(nproc)"
cd ports/esp32
make submodules BOARD_DIR="$BOARD_DIR"
make -j"$(nproc)" BOARD_DIR="$BOARD_DIR" FROZEN_MANIFEST="$REPO/tools/zeki_manifest.py"

echo "--- resolved mbedTLS settings:"
grep -E "CONFIG_MBEDTLS_(DYNAMIC_BUFFER|DYNAMIC_FREE_CONFIG_DATA|DYNAMIC_FREE_CA_CERT|SSL_PROTO_DTLS|SSL_KEEP_PEER_CERTIFICATE)[= ]" \
    "build-$BOARD/sdkconfig" || true

mkdir -p "$REPO/firmware"
[ -f "$OUT" ] && cp "$OUT" "${OUT%.bin}-prev.bin"
cp "build-$BOARD/firmware.bin" "$OUT"
echo
echo "built: $OUT ($(stat -c %s "$OUT") bytes)"
