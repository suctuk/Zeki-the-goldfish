"""Flash Zeki's firmware AND deploy the matching files, in one step.

    %USERPROFILE%\\.venvs\\zeki\\Scripts\\python.exe tools/flash.py            custom (frozen) firmware
    %USERPROFILE%\\.venvs\\zeki\\Scripts\\python.exe tools/flash.py --stock    roll back to stock v1.29.0

Always use this instead of esptool alone: the firmware and the plain files
on the board (config.py etc.) must match. Day 4, flashing new firmware with
an old config.py on the board crashed Zeki at boot (AttributeError).

Writes at 0x1000 WITHOUT erase-flash: the partition table is identical to
stock, so the board's files (state.json, community.json, secrets.py, /lib)
survive.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FW = ROOT / "firmware"
CUSTOM = FW / "zeki-ESP32_GENERIC-v1.29.0-frozen.bin"
STOCK = FW / "ESP32_GENERIC-20260824-v1.29.0.bin"
BIN = Path(sys.executable).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM12")
    ap.add_argument("--stock", action="store_true", help="flash the stock MicroPython image (rollback)")
    args = ap.parse_args()

    image = STOCK if args.stock else CUSTOM
    if not image.exists():
        sys.exit("missing {} ({})".format(image.name, "download it from micropython.org" if args.stock
                                          else "build it: wsl -d Ubuntu -- bash tools/build_fw.sh"))
    esptool = BIN / ("esptool.exe" if (BIN / "esptool.exe").exists() else "esptool")
    print("> flashing", image.name)
    subprocess.run([str(esptool), "--port", args.port, "--baud", "460800",
                    "write-flash", "0x1000", str(image)], check=True)
    deploy = [sys.executable, str(ROOT / "tools" / "deploy.py"), "--port", args.port]
    if not args.stock:
        deploy.append("--frozen")
    subprocess.run(deploy, check=True)
    print("flashed {} and deployed matching files".format("stock firmware" if args.stock else "Zeki firmware"))


if __name__ == "__main__":
    main()
