"""Build and upload Zeki to the board.

    %USERPROFILE%\\.venvs\\zeki\\Scripts\\python.exe tools/deploy.py [--frozen] [--port COM12] [--no-reset]

--frozen: the board runs Zeki's custom firmware (tools/build_fw.sh), where the
app modules and SparkFun drivers are frozen into flash. Only the editable
plain files are uploaded, and any root-level copy of a frozen module is
deleted: sys.path is ['', '.frozen', '/lib'], so a root copy would override
the frozen one (and cost RAM again).

Without --frozen (stock firmware): app modules are precompiled to .mpy with
mpy-cross (must match the firmware: mpy-cross 1.29.x for MicroPython v1.29)
and uploaded. Compiling large .py files on the board at boot grows the heap
into the internal RAM that Wi-Fi and HTTPS need.

config.py, secrets.py and main.py always stay plain .py so they can be edited
on the spot. The SparkFun drivers in /lib are left alone either way: frozen
copies win over /lib, and keeping them makes rolling back to stock firmware
just a reflash plus a plain deploy.
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
    ap.add_argument("--frozen", action="store_true", help="board runs the custom firmware")
    args = ap.parse_args()

    mpremote = tool("mpremote")
    missing = [f for f in PLAIN if not (ROOT / f).exists()]
    if missing:
        sys.exit("missing: " + ", ".join(missing))

    files = [str(ROOT / f) for f in PLAIN]
    if args.frozen:
        exts = (".py", ".mpy")          # anything in the root beats the frozen module
    else:
        exts = (".py",)                 # X.py beats X.mpy
        mpy_cross = tool("mpy-cross")
        BUILD.mkdir(exist_ok=True)
        for m in COMPILED:
            run(mpy_cross, "-o", str(BUILD / (m + ".mpy")), str(ROOT / (m + ".py")))
        files = [str(BUILD / (m + ".mpy")) for m in COMPILED] + files

    stale = ", ".join(repr(m + e) for m in COMPILED for e in exts)
    cleanup = ("import os\n"
               "for f in ({},):\n"
               "    try:\n"
               "        os.remove(f)\n"
               "    except OSError:\n"
               "        pass").format(stale)
    cmd = [mpremote, "connect", args.port, "exec", cleanup, "+", "cp"] + files + [":"]
    if not args.no_reset:
        cmd += ["+", "reset"]
    run(*cmd)
    if args.frozen:
        print("deployed {} plain files to {} (app modules come from the frozen firmware)".format(
            len(PLAIN), args.port))
    else:
        print("deployed {} compiled + {} plain files to {}".format(len(COMPILED), len(PLAIN), args.port))


if __name__ == "__main__":
    main()
