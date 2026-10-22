"""Build and upload Zeki to the board.

    %USERPROFILE%\\.venvs\\zeki\\Scripts\\python.exe tools/deploy.py [--port COM12] [--no-reset]

App modules are precompiled to .mpy with mpy-cross (must match the firmware:
mpy-cross 1.29.x for MicroPython v1.29). Compiling large .py files on the
board at boot permanently grows MicroPython's heap into the internal RAM that
Wi-Fi and HTTPS need. Day 2 that broke Wi-Fi; Day 4 it broke HTTPS (ENOMEM).

config.py, secrets.py and main.py stay plain .py so they can be edited on
the spot. Any stale .py copy of a compiled module is deleted from the board,
because MicroPython imports X.py before X.mpy.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
BIN = Path(sys.executable).parent

COMPILED = ["hw", "ui", "net", "cup", "inspire", "community", "lines", "zeki"]
PLAIN = ["main.py", "config.py", "secrets.py", "ideas.json"]


def tool(name):
    for cand in (BIN / (name + ".exe"), BIN / name):
        if cand.exists():
            return str(cand)
    sys.exit("can't find {} next to {} (pip install it into the zeki venv)".format(name, sys.executable))


def run(*cmd):
    print(">", " ".join(Path(c).name if os.sep in str(c) else str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM12")
    ap.add_argument("--no-reset", action="store_true")
    args = ap.parse_args()

    mpy_cross, mpremote = tool("mpy-cross"), tool("mpremote")
    BUILD.mkdir(exist_ok=True)
    for m in COMPILED:
        run(mpy_cross, "-o", str(BUILD / (m + ".mpy")), str(ROOT / (m + ".py")))
    missing = [f for f in PLAIN if not (ROOT / f).exists()]
    if missing:
        sys.exit("missing: " + ", ".join(missing))

    stale = ", ".join(repr(m + ".py") for m in COMPILED)
    cleanup = "import os\nfor f in ({},):\n    try:\n        os.remove(f)\n    except OSError:\n        pass".format(stale)
    cmd = [mpremote, "connect", args.port, "exec", cleanup, "+", "cp"]
    cmd += [str(BUILD / (m + ".mpy")) for m in COMPILED] + [str(ROOT / f) for f in PLAIN] + [":"]
    if not args.no_reset:
        cmd += ["+", "reset"]
    run(*cmd)
    print("deployed {} compiled + {} plain files to {}".format(len(COMPILED), len(PLAIN), args.port))


if __name__ == "__main__":
    main()
