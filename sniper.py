56#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WhatsApp Username Sniper  v1.0
Automated username availability checker — ADB + UIAutomator
No root required.
"""

import sys
import os
import time
import itertools
import random
import string
import subprocess
import re
import shutil
import json
import csv
import collections
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# Dictionary sources (downloaded on first use)
# ─────────────────────────────────────────────────────────────────────────────
_EN_DICT_URL = "https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-no-swears.txt"
_DE_DICT_URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2016/de/de_50k.txt"


# ─────────────────────────────────────────────────────────────────────────────
# Windows: enable ANSI / Virtual Terminal Processing
# Without this, escape codes print as literal text (←[96m etc.)
# ─────────────────────────────────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        import ctypes
        _k32 = ctypes.windll.kernel32
        _h   = _k32.GetStdHandle(-11)          # STD_OUTPUT_HANDLE
        _m   = ctypes.c_ulong()
        _k32.GetConsoleMode(_h, ctypes.byref(_m))
        _k32.SetConsoleMode(_h, _m.value | 0x4) # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
_AUTHOR = "WA Sniper"


# ─────────────────────────────────────────────────────────────────────────────
# Colours
# ─────────────────────────────────────────────────────────────────────────────
GRN = "\033[92m"
RED = "\033[91m"
YEL = "\033[93m"
CYN = "\033[96m"
WHT = "\033[97m"
MAG = "\033[95m"
DIM = "\033[2m"
BLD = "\033[1m"
RST = "\033[0m"


def _beep():
    """Play a short alert beep on hit — silent fail if audio is unavailable."""
    try:
        if sys.platform == "win32":
            import winsound
            winsound.Beep(1000, 350)
        else:
            sys.stdout.write("\a")
            sys.stdout.flush()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Persistent file paths
# ─────────────────────────────────────────────────────────────────────────────
_CHECKED_FILE  = Path(__file__).parent / "checked.txt"
_PROGRESS_FILE = Path(__file__).parent / "wordlist_progress.json"
_BF_CKPT_FILE  = Path(__file__).parent / "bf_checkpoint.json"


# ─────────────────────────────────────────────────────────────────────────────
# Terminal helpers
# ─────────────────────────────────────────────────────────────────────────────
def _w(s):
    """Write a raw string (control sequences, no newline)."""
    sys.stdout.write(s)
    sys.stdout.flush()

def _clr():
    _w("\033[2J\033[H")

def _term_h():
    try:
        return shutil.get_terminal_size().lines
    except Exception:
        return 40

def _hr(ch="─", n=66):
    return ch * n

def _ts():
    return datetime.now().strftime("%H:%M:%S")

# Bar geometry — computed once in _print_header, then used by _fmt_stats / _update_stats
_ANSI_RE = re.compile(r'\033\[[^m]*m')
_BAR_W   = 0   # equalized visible width for both info + stats bars
_BAR_PAD = ""  # left-centering whitespace prefix

def _vlen(s):
    """Visible length of s — strips ANSI escape codes."""
    return len(_ANSI_RE.sub('', s))


# ─────────────────────────────────────────────────────────────────────────────
# Logo + header builder
#
# Printed once before scanning.  Returns the number of lines printed so we
# know where to place the stats bar and where to start the scroll region.
# ─────────────────────────────────────────────────────────────────────────────
_ART = [
    r"  ██╗    ██╗  █████╗      ███████╗███╗  ██╗██╗",
    r"  ██║    ██║ ██╔══██╗     ██╔════╝████╗ ██║██║",
    r"  ██║ █╗ ██║ ███████║     ███████╗██╔██╗██║██║",
    r"  ██║███╗██║ ██╔══██║     ╚════██║██║╚████║╚═╝",
    r"  ╚███╔███╔╝ ██║  ██║     ███████║██║ ╚███║██╗",
    r"   ╚══╝╚══╝  ╚═╝  ╚═╝     ╚══════╝╚═╝  ╚══╝╚═╝",
]


def _print_header(total=0, mode_info=""):
    """
    Print the full header (logo + mode info + stats bar).
    Returns (stats_row, scroll_start) — both 1-based terminal row numbers.
    """
    global _BAR_W, _BAR_PAD
    row = 1

    def ln(text=""):
        nonlocal row
        print(text)
        row += 1

    # ── Compute equalized bar width + centering BEFORE printing anything ─────
    term_w = shutil.get_terminal_size().columns
    # Sample natural stats width (temporarily zero globals to avoid recursion)
    _bw_save, _bp_save = _BAR_W, _BAR_PAD
    _BAR_W, _BAR_PAD   = 0, ""
    stats_nat          = _fmt_stats(0, 0, 0.0, 0.0, total)
    _BAR_W, _BAR_PAD   = _bw_save, _bp_save

    mode_vlen  = _vlen(mode_info) if mode_info else 0
    stats_vlen = _vlen(stats_nat)
    _BAR_W     = max(mode_vlen, stats_vlen)
    _BAR_PAD   = " " * max(0, (term_w - _BAR_W) // 2)

    # Equalize mode_info to _BAR_W by padding before the closing  |
    closer = f"  {DIM}|{RST}"
    if mode_info and mode_vlen < _BAR_W and mode_info.endswith(closer):
        mode_info = mode_info[:-len(closer)] + " " * (_BAR_W - mode_vlen) + closer

    sep_line = _BAR_PAD + f"{DIM}{'─' * _BAR_W}{RST}"

    # ── Print ─────────────────────────────────────────────────────────────────
    ln()
    for art_line in _ART:
        art_offset = " " * max(0, (_BAR_W - _vlen(art_line)) // 2)
        ln(_BAR_PAD + art_offset + f"{CYN}{BLD}{art_line}{RST}")
    ln()
    ln(_BAR_PAD + f"{GRN}{BLD}{'U S E R N A M E   S N I P E R':^{_BAR_W}}{RST}")
    ln(_BAR_PAD + f"{YEL}{'v1.0':^{_BAR_W}}{RST}")
    ln()
    ln(sep_line)
    if mode_info:
        ln(_BAR_PAD + mode_info)
    ln(sep_line)

    stats_row = row
    ln(_fmt_stats(0, 0, 0.0, 0.0, total))  # placeholder — uses _BAR_W + _BAR_PAD

    ln(sep_line)

    scroll_start = row
    return stats_row, scroll_start


def _fmt_stats(hits, checked, speed, elapsed, total=0):
    h = int(elapsed // 3600)
    m = int((elapsed % 3600) // 60)
    s = int(elapsed % 60)
    # Pad plain strings BEFORE adding ANSI — keeps separator positions stable
    hits_s = f"{hits:<6}"
    if total:
        tw    = len(str(total))
        chk_s = f"{checked:>{tw}}/{total}"
    else:
        chk_s = str(checked)
    chk_s  = f"{chk_s:<16}"
    spd_s  = f"{speed:>8.1f}/s"
    tim_s  = f"{h:02d}:{m:02d}:{s:02d}"
    sep    = f"  {DIM}|{RST}  "
    # ETA — always present when total is known so bar width stays stable
    if total:
        if speed > 0 and checked < total:
            rem    = (total - checked) / speed
            eh, er = divmod(int(rem), 3600)
            em, es = divmod(er, 60)
            eta_s  = f"{eh:02d}:{em:02d}:{es:02d}"
        else:
            eta_s  = "--:--:--"
        eta_part = sep + f"{DIM}ETA{RST}  {MAG}{BLD}{eta_s}{RST}"
    else:
        eta_part = ""
    inner  = (
        f"  {DIM}|{RST}  {DIM}HITS{RST}  {GRN}{BLD}{hits_s}{RST}"
        + sep + f"{CYN}{BLD}{chk_s}{RST}"
        + sep + f"{YEL}{BLD}{spd_s}{RST}"
        + sep + f"{WHT}{BLD}{tim_s}{RST}"
        + eta_part
    )
    closer = f"  {DIM}|{RST}"
    raw    = inner + closer
    # Pad to equalized target width so both bars are always the same visible width
    gap = _BAR_W - _vlen(raw)
    if gap > 0:
        raw = inner + " " * gap + closer
    return _BAR_PAD + raw


def _update_stats(stats_row, hits, checked, speed, elapsed, total=0):
    """Overwrite the stats bar without moving the results cursor."""
    text = _fmt_stats(hits, checked, speed, elapsed, total)
    _w(f"\033[s"              # save cursor
       f"\033[{stats_row};1H" # go to stats row
       f"\033[2K"             # clear line
       f"{text}"              # new stats
       f"\033[u")             # restore cursor


# ─────────────────────────────────────────────────────────────────────────────
# Settings  (persisted to settings.json next to the script)
# ─────────────────────────────────────────────────────────────────────────────

_SETTINGS_FILE = Path(__file__).parent / "settings.json"

def _load_settings() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_settings(data: dict):
    _SETTINGS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _download_dict(url: str, dest: Path, label: str) -> int:
    """Download word list, keep only a-z words (3-25 chars), shuffle, save."""
    print(f"  {DIM}[*]{RST} Downloading {label} dictionary ...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WA-Sniper/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  {RED}[!]{RST} Download failed: {e}")
        return 0
    words = []
    for line in raw.splitlines():
        # support both "word" and "word frequency" formats
        parts = line.strip().split()
        if not parts:
            continue
        w = parts[0].lower()
        if w and 3 <= len(w) <= 25 and w.isalpha() and w.isascii():
            words.append(w)
    random.shuffle(words)
    dest.write_text("\n".join(words), encoding="utf-8")
    print(f"  {GRN}[✓]{RST} {len(words):,} words saved → {dest.name}")
    return len(words)


# ─────────────────────────────────────────────────────────────────────────────
# Persistent ADB shell
#
# One 'adb shell' process lives for the entire session.  Shell-side commands
# (input tap/text/keyevent, uiautomator dump) are piped through stdin so no
# new Windows process is spawned per command (~80-150 ms overhead saved each).
# adb pull / adb devices still use subprocess.run — they can't run inside the
# shell.
# ─────────────────────────────────────────────────────────────────────────────

class _PersistentShell:
    _SENTINEL = "__SNIPER_DONE__"

    def __init__(self):
        self._proc = None

    def _start(self):
        try:
            self._proc = subprocess.Popen(
                ["adb", "shell"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except Exception:
            self._proc = None

    def _alive(self):
        return self._proc is not None and self._proc.poll() is None

    def _ensure(self):
        if not self._alive():
            self._start()

    def run(self, cmd: str, timeout: float = 10.0) -> str:
        """Send cmd, wait for sentinel echo, return captured stdout."""
        self._ensure()
        if not self._alive():
            return ""
        try:
            payload = f"{cmd} ; echo {self._SENTINEL}\n".encode()
            self._proc.stdin.write(payload)
            self._proc.stdin.flush()
            out      = []
            deadline = time.time() + timeout
            while time.time() < deadline:
                line = self._proc.stdout.readline()
                if not line:
                    break
                decoded = line.decode(errors="replace").rstrip("\r\n")
                if decoded == self._SENTINEL:
                    break
                out.append(decoded)
            return "\n".join(out)
        except Exception:
            self._proc = None
            return ""

    def send(self, cmd: str):
        """Fire-and-forget: write cmd to stdin without reading output."""
        self._ensure()
        if not self._alive():
            return
        try:
            self._proc.stdin.write(f"{cmd}\n".encode())
            self._proc.stdin.flush()
        except Exception:
            self._proc = None

    def close(self):
        if self._proc:
            try:
                self._proc.stdin.write(b"exit\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=2)
            except Exception:
                pass
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None


# ─────────────────────────────────────────────────────────────────────────────
# Sniper
# ─────────────────────────────────────────────────────────────────────────────

class Sniper:

    _SAVE_TEXTS = {
        "save",        "speichern",   "guardar",
        "enregistrer", "salvar",
        "\u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c",
        "\u062d\u0641\u0638",
        "\u4fdd\u5b58",
        "\uc800\uc7a5",
    }

    def __init__(self, delay=0.5, work_sec=900, break_sec=300):
        self.delay        = delay
        self.hits         = []
        self.checked      = 0
        self.t0           = None
        self._field_x     = None
        self._field_y     = None
        self._baseline    = None
        self._shell       = _PersistentShell()
        self.webhook      = None      # Discord webhook URL (set from settings)
        self.mode_str     = ""        # current mode label (for CSV export)
        self.work_sec     = work_sec  # active scanning period before a break
        self.break_sec    = break_sec # rest duration during break
        self._retry_queue = collections.deque()  # uncertain results to re-check

    # ── ADB ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_adb():
        """Return the adb executable path.  Checks PATH first, then common
        Android SDK locations on Windows / macOS / Linux."""
        # 1. Already on PATH?
        if shutil.which("adb"):
            return "adb"
        # 2. Common locations
        candidates = []
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            candidates.append(
                os.path.join(local_app, "Android", "Sdk", "platform-tools", "adb.exe")
            )
        script_dir = str(Path(__file__).parent)
        candidates += [
            # Next to sniper.py (easiest fix for users)
            os.path.join(script_dir, "adb.exe"),
            os.path.join(script_dir, "platform-tools", "adb.exe"),
            # Windows standard locations
            r"C:\platform-tools\adb.exe",
            r"C:\Android\platform-tools\adb.exe",
            r"C:\Android\Sdk\platform-tools\adb.exe",
            os.path.expanduser(r"~\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
            # macOS / Linux
            os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
            os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
            "/usr/local/bin/adb",
            "/usr/bin/adb",
        ]
        for c in candidates:
            if c and os.path.isfile(c):
                return c
        return None   # not found anywhere

    def _adb(self, *args, timeout=12):
        exe = self._find_adb()
        if exe is None:
            return None
        try:
            return subprocess.run(
                [exe] + list(args),
                capture_output=True, text=True, timeout=timeout,
            )
        except Exception:
            return None

    def _check_adb(self):
        # Step 1: is adb available?
        exe = self._find_adb()
        if exe is None:
            print(f"  {RED}[!]{RST} ADB not found on this computer.")
            print(f"  {DIM}  ----------------------------------------{RST}")
            print(f"  {WHT}  HOW TO FIX:{RST}")
            print(f"  {DIM}  1. Download Android Platform Tools:{RST}")
            print(f"  {CYN}       https://developer.android.com/tools/releases/platform-tools{RST}")
            print(f"  {DIM}  2. Extract the zip — you get a folder called platform-tools{RST}")
            print(f"  {DIM}  3. EASIEST: copy adb.exe into this folder:{RST}")
            print(f"  {WHT}       {Path(__file__).parent}{RST}")
            print(f"  {DIM}     OR add platform-tools to your system PATH.{RST}")
            print(f"  {DIM}  ----------------------------------------{RST}")
            return False

        # Step 2: run adb devices
        r = self._adb("devices")
        if r is None:
            print(f"  {RED}[!]{RST} adb command failed unexpectedly.")
            return False

        lines = r.stdout.splitlines()

        # Fully connected and authorized
        devs = [l for l in lines if "\tdevice" in l]
        if devs:
            print(f"  {GRN}[+]{RST} Device  : {devs[0].split(chr(9))[0]}")
            return True

        # Connected but not yet authorized (dialog not accepted on phone)
        unauth = [l for l in lines if "\tunauthorized" in l]
        if unauth:
            dev_id = unauth[0].split("\t")[0]
            print(f"  {YEL}[!]{RST} Device found but {YEL}UNAUTHORIZED{RST}: {dev_id}")
            print(f"  {DIM}  → On your phone, tap {WHT}Allow{RST}{DIM} on the 'Allow USB Debugging?' dialog.{RST}")
            print(f"  {DIM}    If no dialog appears, unplug and replug the USB cable.{RST}")
            return False

        # Offline / bad driver
        offline = [l for l in lines if "\toffline" in l]
        if offline:
            dev_id = offline[0].split("\t")[0]
            print(f"  {YEL}[!]{RST} Device is {YEL}OFFLINE{RST}: {dev_id}")
            print(f"  {DIM}  → Try: unplug USB, run  adb kill-server  in a terminal, then replug.{RST}")
            return False

        # Nothing at all
        print(f"  {RED}[!]{RST} No ADB device detected.")
        print(f"  {DIM}  Make sure:{RST}")
        print(f"  {DIM}    • USB cable is plugged in{RST}")
        print(f"  {DIM}    • USB Debugging is ON  (Settings → Developer Options){RST}")
        print(f"  {DIM}    • USB mode is 'File Transfer' (MTP), not 'Charging only'{RST}")
        print(f"  {DIM}    • You tapped Allow on the USB Debugging prompt on your phone{RST}")
        return False

    def _wait_for_device(self, timeout=300):
        """Block until an ADB device reconnects or timeout (seconds) expires."""
        print()
        print(f"  {YEL}{BLD}[DISCONNECTED]{RST}  ADB device lost — waiting for reconnect ...")
        deadline = time.time() + timeout
        attempt  = 0
        while time.time() < deadline:
            attempt += 1
            time.sleep(5)
            r = self._adb("devices")
            if r:
                devs = [l for l in r.stdout.splitlines() if "\tdevice" in l]
                if devs:
                    print()
                    print(f"  {GRN}[+]{RST}  Reconnected: {devs[0].split(chr(9))[0]}")
                    self._shell = _PersistentShell()
                    self._find_field()
                    return True
            remaining = max(0, int(deadline - time.time()))
            rm, rs = divmod(remaining, 60)
            _w(f"\r  {DIM}  Attempt {attempt} — {rm:02d}:{rs:02d} remaining ...{RST}  ")
        print(f"\n  {RED}[!]{RST}  Device did not reconnect in time. Stopping.")
        return False

    def _adb_input(self, username):
        try:
            if self._field_x is not None:
                self._shell.send(
                    f"input tap {self._field_x} {self._field_y}")
                time.sleep(0.2)
            self._shell.send(
                "input keyevent KEYCODE_MOVE_END "
                + " ".join(["KEYCODE_DEL"] * 30)
            )
            time.sleep(0.1)
            # Single-quote so the shell doesn't expand special chars
            safe = username.replace("'", "'\\''")
            self._shell.send(f"input text '{safe}'")
            time.sleep(0.15)
            return True
        except Exception:
            return False

    # ── UIAutomator ───────────────────────────────────────────────────────────

    def _find_field(self):
        try:
            self._shell.run("uiautomator dump --compressed /sdcard/uidump.xml")
            # No explicit sleep — _shell.run() blocks until the dump completes
            tmp = Path(__file__).parent / "uidump.xml"
            self._adb("pull", "/sdcard/uidump.xml", str(tmp))
            root = ET.parse(str(tmp)).getroot()
            for node in root.iter("node"):
                cls  = node.get("class",        "")
                rid  = node.get("resource-id",  "").lower()
                cdsc = node.get("content-desc", "").lower()
                if "EditText" in cls and not any(
                        w in rid + cdsc for w in ("search", "such")):
                    m = re.findall(r'\[(\d+),(\d+)\]', node.get("bounds", ""))
                    if len(m) == 2:
                        self._field_x = (int(m[0][0]) + int(m[1][0])) // 2
                        self._field_y = (int(m[0][1]) + int(m[1][1])) // 2
                        return True
        except Exception:
            pass
        return False

    def _dump_ui(self, name="ud.xml"):
        local = Path(__file__).parent / name
        self._shell.run(f"uiautomator dump --compressed /sdcard/{name}")
        self._adb("pull", "/sdcard/" + name, str(local))
        return local

    def _parse_nodes(self, path):
        nodes = {}
        try:
            for node in ET.parse(str(path)).getroot().iter("node"):
                b   = node.get("bounds", "")
                cls = node.get("class",  "")
                if not b:
                    continue
                nodes[b + "|" + cls] = {
                    "rid":       node.get("resource-id", ""),
                    "text":      node.get("text",        "").strip(),
                    "class":     cls,
                    "bounds":    b,
                    "enabled":   node.get("enabled",   "false").lower() == "true",
                    "clickable": node.get("clickable",  "false").lower() == "true",
                }
        except Exception:
            pass
        return nodes

    def _capture_baseline(self):
        self._baseline = self._parse_nodes(self._dump_ui("baseline.xml"))
        print(f"  {GRN}[+]{RST} Baseline : {len(self._baseline)} nodes")

    def _find_save_btn(self, nodes):
        fy    = self._field_y or 300
        label = None

        for key, n in nodes.items():
            text = n["text"].lower()
            rid  = n["rid"]

            if text and any(p in text for p in (
                "nicht verf\u00fcgbar", "not available",
                "already taken",        "bereits vergeben",
                "username not available",
            )):
                return False

            if text in (
                "verf\u00fcgbar", "username available",
                "benutzername verf\u00fcgbar",
                "dieser benutzername ist verf\u00fcgbar",
            ):
                return True

            if ("upr_edit_save_button" in rid or
                    ("save_button" in rid
                     and "container" not in rid
                     and "stub"      not in rid)):
                return n["enabled"]

            if text in self._SAVE_TEXTS:
                try:
                    m = re.findall(r'\[(\d+),(\d+)\]', n["bounds"])
                    if m and int(m[0][1]) >= fy - 100:
                        label = n
                except Exception:
                    pass

        if label is not None:
            try:
                m  = re.findall(r'\[(\d+),(\d+)\]', label["bounds"])
                cx = (int(m[0][0]) + int(m[1][0])) // 2
                cy = (int(m[0][1]) + int(m[1][1])) // 2
            except Exception:
                cx, cy = 0, 0
            best      = None
            best_area = float("inf")
            for key, n in nodes.items():
                if n is label or not n["clickable"]:
                    continue
                try:
                    m  = re.findall(r'\[(\d+),(\d+)\]', n["bounds"])
                    x1, y1 = int(m[0][0]), int(m[0][1])
                    x2, y2 = int(m[1][0]), int(m[1][1])
                except Exception:
                    continue
                if x1 <= cx <= x2 and y1 <= cy <= y2:
                    area = (x2 - x1) * (y2 - y1)
                    if area < best_area:
                        best_area, best = area, n
            if best is not None:
                return best["enabled"]

        if self._baseline:
            for key, n in nodes.items():
                if key in self._baseline or not n["clickable"]:
                    continue
                try:
                    m = re.findall(r'\[(\d+),(\d+)\]', n["bounds"])
                    if m and int(m[0][1]) >= fy - 100:
                        return n["enabled"]
                except Exception:
                    pass

        return None

    def _poll(self, username, total_wait=5.5):
        deadline = time.time() + total_wait
        first    = True
        while time.time() < deadline:
            time.sleep(1.8 if first else 0.5)  # 0.5 s — faster with persistent shell
            first = False
            state = self._find_save_btn(self._parse_nodes(self._dump_ui()))
            if state is True:
                return {"available": True,  "username": username}
            if state is False:
                return {"available": False, "username": username}
        return None

    # ── Setup ─────────────────────────────────────────────────────────────────

    def calibrate(self):
        print()
        print(f"  {WHT}{BLD}SETUP{RST}")
        print(f"  {DIM}{_hr('─', 40)}{RST}")

        if not self._check_adb():
            sys.exit(1)

        print(f"  {DIM}[*]{RST} Detecting username field ...")
        if self._find_field():
            print(f"  {GRN}[+]{RST} Field at ({self._field_x}, {self._field_y})")
        else:
            print(f"  {YEL}[!]{RST} Auto-detect failed. Enter coordinates:")
            try:
                x = input(f"      {CYN}X{RST} [default 540]: ").strip()
                y = input(f"      {CYN}Y{RST} [default 600]: ").strip()
                self._field_x = int(x) if x else 540
                self._field_y = int(y) if y else 600
            except (ValueError, EOFError):
                self._field_x, self._field_y = 540, 600
            print(f"  {GRN}[+]{RST} Using ({self._field_x}, {self._field_y})")

        print(f"  {DIM}[*]{RST} Capturing UI baseline ...")
        self._capture_baseline()
        print()

    # ── Core ──────────────────────────────────────────────────────────────────

    def check(self, username):
        self.checked += 1
        if not self._adb_input(username):
            # Input failed — likely a disconnection; wait and retry once
            if not self._wait_for_device():
                raise KeyboardInterrupt   # bail cleanly if device never returns
            if not self._adb_input(username):
                return None
        res = self._poll(username)
        if res is None:
            self._find_field()
        return res

    # ── Generators ────────────────────────────────────────────────────────────

    def gen_combo(self, length, charset):
        """Infinite stream of random strings — truly random picks each time."""
        while True:
            yield "".join(random.choices(charset, k=length))

    def gen_bruteforce(self, max_length, charset, min_length=3, skip=0):
        """Exhaustive generator.  skip= combos already done (checkpoint resume).
        Uses itertools.islice for fast-forward so no slow Python loop is needed."""
        overall = 0
        for length in range(min_length, max_length + 1):
            group_size = len(charset) ** length
            if skip >= overall + group_size:
                overall += group_size
                continue
            offset = max(0, skip - overall)
            it = itertools.islice(
                itertools.product(charset, repeat=length), offset, None
            )
            for combo in it:
                yield "".join(combo)
            overall += group_size

    def gen_dict_random(self, path, min_len=3, max_len=25):
        """Random word stream — shuffles full dict, yields every word once, then reshuffles.
        No word is repeated until the entire dictionary has been exhausted."""
        words = [
            ln.strip() for ln in open(path, encoding="utf-8", errors="ignore")
            if ln.strip() and min_len <= len(ln.strip()) <= max_len
        ]
        if not words:
            return
        while True:
            random.shuffle(words)
            yield from words

    def gen_wordlist(self, path, start_line=1, min_len=3, max_len=25):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, 1):
                if i < start_line:
                    continue
                u = line.strip()
                if u and min_len <= len(u) <= max_len:
                    yield u

    # ── Output ────────────────────────────────────────────────────────────────

    def _save_hit(self, username):
        ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Plain-text log
        txt_path = Path(__file__).parent / "hits.txt"
        with open(txt_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}]  {username}\n")
        # CSV log: timestamp, username, mode
        csv_path  = Path(__file__).parent / "hits.csv"
        write_hdr = not csv_path.exists()
        with open(csv_path, "a", newline="", encoding="utf-8") as cf:
            w = csv.writer(cf)
            if write_hdr:
                w.writerow(["timestamp", "username", "mode"])
            w.writerow([ts, username, self.mode_str])
        # Alert beep
        _beep()

    def _notify_webhook(self, username):
        """POST a Discord webhook message when a username is available."""
        if not self.webhook:
            return
        _webhook_post(self.webhook, username)

    # ── Run ─────────────────────────────────────────────────────────────────────────

    def run(self, length=None, charset=None, wordlist=None, start_line=1, dict_random=None,
            bruteforce=False, bf_min=3, bf_max=None, bf_skip=0,
            pattern=None, min_len=3, max_len=25):

        # ── Load deduplicate set ────────────────────────────────────────────
        _checked_set = set()
        try:
            if _CHECKED_FILE.exists():
                with open(_CHECKED_FILE, "r", encoding="utf-8", errors="ignore") as cf:
                    for ln in cf:
                        u = ln.strip()
                        if u:
                            _checked_set.add(u)
        except Exception:
            pass
        _pending_checked: list = []   # buffer — flushed in batches of 100

        # ── Compile pattern filter ──────────────────────────────────────────
        _pattern = None
        if pattern:
            try:
                _pattern = re.compile(pattern)
            except re.error:
                _pattern = None

        if dict_random:
            _wc           = sum(1 for ln in open(dict_random, encoding="utf-8", errors="ignore") if ln.strip())
            gen_fn        = lambda: self.gen_dict_random(dict_random, min_len, max_len)
            total         = 0
            charset_label = f"{_wc:,} words"
            mode_str      = "dict-rand"
        elif wordlist:
            gen_fn        = lambda: self.gen_wordlist(wordlist, start_line, min_len, max_len)
            total         = sum(
                1 for ln in open(wordlist, encoding="utf-8", errors="ignore")
                if ln.strip() and min_len <= len(ln.strip()) <= max_len
            )
            mode_str      = "wordlist"
            charset_label = f"{total:,} words"
        elif bruteforce:
            base  = len(charset)
            total = max(0, sum(base ** n for n in range(bf_min, bf_max + 1)) - bf_skip)
            has_alpha     = any(c.isalpha() for c in charset)
            has_digit     = any(c.isdigit() for c in charset)
            charset_label = (
                "a-z + 0-9" if (has_alpha and has_digit)
                else "a-z"   if has_alpha
                else "0-9"
            )
            mode_str      = "bruteforce"
            gen_fn        = lambda: self.gen_bruteforce(bf_max, charset, bf_min, bf_skip)
        else:
            gen_fn        = lambda: self.gen_combo(length, charset)
            total         = 0   # infinite — truly random, no fixed total
            has_alpha     = any(c.isalpha() for c in charset)
            has_digit     = any(c.isdigit() for c in charset)
            charset_label = (
                "a-z + 0-9" if (has_alpha and has_digit)
                else "a-z"   if has_alpha
                else "0-9"
            )
            mode_str      = f"{length}-char"

        self.mode_str = mode_str   # stored for CSV export
        self.t0       = time.time()

        mode_info = (
            f"  {DIM}|{RST}  {DIM}MODE{RST}  {WHT}{BLD}{mode_str:<10}{RST}"
            f"  {DIM}|{RST}  {DIM}CHARSET{RST}  {WHT}{BLD}{charset_label:<14}{RST}"
            f"  {DIM}|{RST}  {DIM}DELAY{RST}  {WHT}{BLD}{self.delay:.1f}s{RST}"
            f"  {DIM}|{RST}"
        )
        _clr()
        stats_row, scroll_start = _print_header(total, mode_info)

        # Activate scroll region: only lines from scroll_start to bottom scroll
        _w(f"\033[{scroll_start};{_term_h()}r")
        # Position cursor at the top of the scroll region
        _w(f"\033[{scroll_start};1H")

        _last_break = time.time()
        _wl_line    = start_line   # for wordlist progress saving
        _bf_done    = bf_skip      # for bruteforce checkpoint saving
        _completed  = False        # flag: run ended naturally (not interrupted)

        def _flush_pending():
            nonlocal _pending_checked
            if not _pending_checked:
                return
            try:
                with open(_CHECKED_FILE, "a", encoding="utf-8") as cf:
                    cf.writelines(u + "\n" for u in _pending_checked)
                _pending_checked = []
            except Exception:
                _pending_checked = []

        try:
            for username in gen_fn():
                # ── Break check ───────────────────────────────────────────
                if time.time() - _last_break >= self.work_sec:
                    _flush_pending()
                    _w("\033[r")
                    print()
                    print(f"  {YEL}{BLD}[PAUSE]{RST}  {self.work_sec // 60} min reached — resting {self.break_sec // 60} min to avoid throttling ...")
                    try:
                        for remaining in range(self.break_sec, 0, -1):
                            bm, bs = divmod(remaining, 60)
                            _w(f"\r  {DIM}  Resuming in  {RST}{WHT}{BLD}{bm:02d}:{bs:02d}{RST}   ")
                            time.sleep(1)
                    except KeyboardInterrupt:
                        raise
                    _w(f"\r{' ' * 40}\r")
                    print(f"  {GRN}[✓]{RST}  Break over — resuming ...")
                    print()
                    _w(f"\033[{scroll_start};{_term_h()}r")
                    _w(f"\033[{scroll_start};1H")
                    _last_break = time.time()

                # ── Dedup skip ────────────────────────────────────────────
                if username in _checked_set:
                    continue

                # ── Pattern filter ────────────────────────────────────────
                if _pattern and not _pattern.search(username):
                    continue

                res = self.check(username)
                ts  = _ts()

                # ── Dedup tracking (buffered) ─────────────────────────────
                _checked_set.add(username)
                _pending_checked.append(username)
                if len(_pending_checked) >= 100:
                    _flush_pending()

                # ── Bruteforce checkpoint ─────────────────────────────────
                if bruteforce:
                    _bf_done += 1
                    if _bf_done % 500 == 0:
                        try:
                            _BF_CKPT_FILE.write_text(
                                json.dumps({"skip": _bf_done}), encoding="utf-8"
                            )
                        except Exception:
                            pass

                # ── Wordlist progress ─────────────────────────────────────
                if wordlist:
                    _wl_line += 1
                    if _wl_line % 100 == 0:
                        try:
                            _PROGRESS_FILE.write_text(
                                json.dumps({"wordlist": wordlist, "line": _wl_line}),
                                encoding="utf-8",
                            )
                        except Exception:
                            pass

                if res is None:
                    self._retry_queue.append(username)
                    print(f"  {DIM}[{ts}]  ?  {YEL}{username}{RST}  {DIM}→ queued for retry{RST}")
                elif res["available"]:
                    self.hits.append(username)
                    self._save_hit(username)
                    self._notify_webhook(username)
                    print(
                        f"  {DIM}[{ts}]  >>  {RST}"
                        f"{GRN}{BLD}{username.upper():<20}{RST}"
                        f"  {GRN}{BLD}<-- AVAILABLE!{RST}"
                    )
                else:
                    print(f"  {DIM}[{ts}]  x  {RST}{RED}{username}{RST}")

                # Refresh the pinned stats bar
                elapsed = time.time() - self.t0
                speed   = self.checked / elapsed if elapsed > 0 else 0.0
                _update_stats(stats_row, len(self.hits),
                              self.checked, speed, elapsed, total)

                if self.delay > 0:
                    time.sleep(self.delay)

            # ── Drain retry queue ─────────────────────────────────────────
            if self._retry_queue:
                print()
                print(f"  {YEL}[↩  RETRY]{RST}  Re-checking {len(self._retry_queue)} uncertain usernames ...")
                retried: set = set()
                while self._retry_queue:
                    username = self._retry_queue.popleft()
                    if username in retried:
                        continue
                    retried.add(username)
                    res = self.check(username)
                    ts  = _ts()
                    if res is None:
                        print(f"  {DIM}[{ts}]  ?  {YEL}[retry]{RST}  {username}  {DIM}(still unknown){RST}")
                    elif res["available"]:
                        self.hits.append(username)
                        self._save_hit(username)
                        self._notify_webhook(username)
                        print(
                            f"  {DIM}[{ts}]  >>  {RST}"
                            f"{GRN}{BLD}{username.upper():<20}{RST}"
                            f"  {GRN}{BLD}<-- AVAILABLE! [retry]{RST}"
                        )
                    else:
                        print(f"  {DIM}[{ts}]  x  {RST}{RED}[retry] {username}{RST}")
                    elapsed = time.time() - self.t0
                    speed   = self.checked / elapsed if elapsed > 0 else 0.0
                    _update_stats(stats_row, len(self.hits),
                                  self.checked, speed, elapsed, total)
                    if self.delay > 0:
                        time.sleep(self.delay)

            _completed = True

        except KeyboardInterrupt:
            pass

        finally:
            _flush_pending()
            # Restore scroll region to full screen
            _w("\033[r")
            # Move cursor well below the results area
            _w(f"\033[{scroll_start + 5};1H")
            # Tear down the persistent shell
            self._shell.close()
            # Clear bruteforce checkpoint only on natural completion
            if bruteforce and _completed:
                try:
                    if _BF_CKPT_FILE.exists():
                        _BF_CKPT_FILE.unlink()
                except Exception:
                    pass

        # ── Summary ────────────────────────────────────────────────────────────────
        elapsed = time.time() - self.t0
        speed   = self.checked / elapsed if elapsed > 0 else 0.0
        print()
        print(f"  {DIM}{_hr()}{RST}")
        print(f"  {WHT}{BLD}RESULTS{RST}")
        print(f"  {DIM}{_hr('─', 40)}{RST}")
        print(f"  Checked    :  {self.checked}")
        print(f"  Available  :  {GRN}{BLD}{len(self.hits)}{RST}")
        print(f"  Speed      :  {speed:.1f} checks/s")
        print(f"  Duration   :  {int(elapsed // 60)}m {int(elapsed % 60)}s")
        if self.hits:
            print(f"  {DIM}{_hr('─', 40)}{RST}")
            for h in self.hits:
                print(f"  {GRN}  >>  {h}{RST}")
            print(f"\n  {DIM}→ Saved to hits.txt  +  hits.csv{RST}")
        print(f"  {DIM}{_hr()}{RST}")

def _webhook_post(url: str, username: str, test: bool = False):
    """Send a Discord webhook POST. Returns (ok: bool, error: str)."""
    try:
        msg = (
            f"\u2705 **Test** — webhook works!"
            if test else
            f"\u2705 **`{username}`** is available!"
        )
        payload = json.dumps({
            "content": msg,
            "embeds": [{
                "title": "\u2705 Username Available!" if not test else "\U0001f4e1 Webhook Test",
                "description": f"**`{username}`**",
                "color": 5763719 if not test else 3447003,
                "footer": {"text": "WA Sniper"},
            }]
        }).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "WA-Sniper/1.0",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=8)
        return True, ""
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode(errors="replace")
        except Exception:
            pass
        err = f"HTTP {e.code} {e.reason} — {body[:200]}"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    try:
        _log = Path(__file__).parent / "webhook_errors.log"
        with open(_log, "a", encoding="utf-8") as _f:
            _f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]  {username}  {err}\n")
    except Exception:
        pass
    return False, err


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def main():
    _clr()
    for line in _ART:
        print(f"{CYN}{BLD}{line}{RST}")
    print()
    print(f"{GRN}{BLD}{'U S E R N A M E   S N I P E R':^50}{RST}")
    print(f"{YEL}{'v1.0':^50}{RST}")
    print()
    print(f"{DIM}{_hr()}{RST}")

    def section(title):
        print()
        print(f"  {WHT}{BLD}{title}{RST}")
        print(f"  {DIM}{_hr('\u00b7', 40)}{RST}")
        print()

    def prompt(text, default=None, valid=None):
        sfx = f"  {DIM}[{default}]{RST}" if default is not None else ""
        while True:
            try:
                raw = input(f"  {CYN}\u203a{RST}  {text}{sfx} : ").strip()
            except EOFError:
                raw = ""
            if not raw and default is not None:
                return str(default)
            if valid is None or raw in valid:
                return raw
            print(f"  {RED}Invalid \u2014 choose: {', '.join(str(v) for v in valid)}{RST}")

    # \u2500\u2500 Wordlist info \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    _wl_default = Path(__file__).parent / "wordlist.txt"
    if _wl_default.exists():
        _wl_count = sum(
            1 for ln in open(_wl_default, encoding="utf-8", errors="ignore")
            if ln.strip() and 3 <= len(ln.strip()) <= 25
        )
        _wl_info = f"{_wl_count:,} words"
    else:
        _wl_count = 0
        _wl_info  = "wordlist.txt"

    # \u2500\u2500 Load persisted settings \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    settings = _load_settings()
    _last    = settings.get("last_run", {})

    # \u2500\u2500 Mode loop (returns here after Settings) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    wordlist    = None
    length      = None
    charset     = None
    start_line  = 1
    dict_active = None   # Path to downloaded dict (EN or DE)
    bruteforce  = False
    bf_min      = 3
    bf_max      = None
    bf_skip     = 0      # bruteforce checkpoint skip count
    pattern     = None   # optional regex filter
    min_len     = 3      # min length filter for wordlist/dict
    max_len     = 25     # max length filter for wordlist/dict

    while True:
        section("MODE")
        _wh_keys  = [f"webhook_{n}" for n in range(3, 9)] + ["webhook_wordlist", "webhook_dict_en", "webhook_dict_de", "webhook_bruteforce"]
        _wh_count = sum(1 for k in _wh_keys if settings.get(k))
        wh_state  = f"{GRN}{_wh_count}/10{RST}" if _wh_count else f"{YEL}none{RST}"
        _en_path  = Path(__file__).parent / "dict_en.txt"
        _de_path  = Path(__file__).parent / "dict_de.txt"
        _en_info  = f"{sum(1 for l in open(_en_path,encoding='utf-8',errors='ignore') if l.strip()):,} words" if _en_path.exists() else f"{YEL}not downloaded{RST}"
        _de_info  = f"{sum(1 for l in open(_de_path,encoding='utf-8',errors='ignore') if l.strip()):,} words" if _de_path.exists() else f"{YEL}not downloaded{RST}"
        print(f"  {DIM}  1  \u2192  Combo      random combinations{RST}")
        print(f"  {DIM}  2  \u2192  Wordlist   {_wl_info}{RST}")
        print(f"  {DIM}  4  \u2192  EN Dict    English words  ({_en_info}){RST}")
        print(f"  {DIM}  5  \u2192  DE Dict    German words   ({_de_info}){RST}")
        print(f"  {DIM}  6  \u2192  Bruteforce every possible combination (exhaustive){RST}")
        print(f"  {DIM}  3  \u2192  Settings   webhooks {wh_state} configured{RST}")
        print()
        mode = prompt("Mode [1/2/3/4/5/6]", valid=["1", "2", "3", "4", "5", "6"])

        # \u2500\u2500 Settings \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        if mode == "3":
            _slots = [
                (f"webhook_{n}", f"{n}-char") for n in range(3, 9)
            ] + [
                ("webhook_wordlist",    "Wordlist  "),
                ("webhook_dict_en",     "EN Dict   "),
                ("webhook_dict_de",     "DE Dict   "),
                ("webhook_bruteforce",  "Bruteforce"),
            ]

            while True:
                section("SETTINGS")
                print(f"  {DIM}  Discord Webhooks  \u2014  each slot posts to a separate channel{RST}")
                print()
                for i, (key, label) in enumerate(_slots, 1):
                    val  = settings.get(key, "")
                    disp = (
                        f"{WHT}{val[:46]}\u2026{RST}" if len(val) > 50
                        else f"{WHT}{val}{RST}"  if val
                        else f"{YEL}not set{RST}"
                    )
                    print(f"  {DIM}  {i}  \u2192  {label:<10}{RST}  {disp}")
                print()
                # Break config display
                _work_min = settings.get("break_work_min", 15)
                _rest_min = settings.get("break_rest_min", 5)
                print(f"  {DIM}  b  \u2192  Break config   work:{GRN}{_work_min} min{RST}{DIM} / rest:{YEL}{_rest_min} min{RST}")
                print()
                print(f"  {DIM}  0  \u2192  Back{RST}")
                print()
                try:
                    raw_choice = input(f"  {CYN}\u203a{RST}  Slot [0-10 / b] : ").strip().lower()
                except EOFError:
                    raw_choice = "0"

                if not raw_choice or raw_choice == "0":
                    break

                # Break config submenu
                if raw_choice == "b":
                    print()
                    try:
                        rw = input(f"  {CYN}\u203a{RST}  Work interval  {DIM}[minutes, default {_work_min}]{RST} : ").strip()
                        settings["break_work_min"] = max(1, int(rw)) if rw else _work_min
                    except (ValueError, EOFError):
                        pass
                    try:
                        rb = input(f"  {CYN}\u203a{RST}  Rest interval  {DIM}[minutes, default {_rest_min}]{RST} : ").strip()
                        settings["break_rest_min"] = max(0, int(rb)) if rb else _rest_min
                    except (ValueError, EOFError):
                        pass
                    _save_settings(settings)
                    print(f"  {GRN}[\u2713]{RST}  Break config saved.")
                    print()
                    continue

                try:
                    idx = int(raw_choice) - 1
                    if not 0 <= idx < len(_slots):
                        raise ValueError
                except ValueError:
                    print(f"  {RED}Invalid choice.{RST}")
                    continue

                key, label = _slots[idx]
                cur = settings.get(key, "")
                print()
                print(f"  {DIM}  Configuring :{RST}  {WHT}{BLD}{label}{RST}")
                if cur:
                    print(f"  {DIM}  Current     :{RST}  {WHT}{cur}{RST}")
                else:
                    print(f"  {DIM}  Current     :{RST}  {YEL}not configured{RST}")
                print(f"  {DIM}  blank = keep  \u00b7  'clear' = remove{RST}")
                print()
                try:
                    raw_wh = input(f"  {CYN}\u203a{RST}  Webhook URL : ").strip()
                except EOFError:
                    raw_wh = ""
                if raw_wh.lower() == "clear":
                    settings.pop(key, None)
                    _save_settings(settings)
                    print(f"  {GRN}[\u2713]{RST}  Webhook removed.")
                elif raw_wh:
                    settings[key] = raw_wh
                    _save_settings(settings)
                    print(f"  {GRN}[\u2713]{RST}  Webhook saved.")
                    print()
                    try:
                        raw_test = input(
                            f"  {CYN}\u203a{RST}  Test webhook now?  {DIM}[y/N]{RST} : "
                        ).strip().lower()
                    except EOFError:
                        raw_test = ""
                    if raw_test == "y":
                        print(f"  {DIM}  Sending test message ...{RST}")
                        ok, err = _webhook_post(raw_wh, "testuser", test=True)
                        if ok:
                            print(f"  {GRN}[\u2713]{RST}  Discord received the message!")
                        else:
                            print(f"  {RED}[!]{RST}  Failed: {err}")
                else:
                    print(f"  {DIM}  No changes.{RST}")
                print()

            continue   # back to mode selection

        # \u2500\u2500 Wordlist \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        if mode == "2":
            section("WORDLIST")
            print(f"  {DIM}  Default : wordlist.txt  ({_wl_info}){RST}")
            print()
            try:
                raw = input(
                    f"  {CYN}\u203a{RST}  Path  {DIM}[Enter = wordlist.txt]{RST} : "
                ).strip()
            except EOFError:
                raw = ""
            wordlist = raw if raw else str(_wl_default)
            if not Path(wordlist).exists():
                print(f"  {RED}File not found: {wordlist}{RST}")
                sys.exit(1)

            # Resume from saved progress?
            _prog_line = 1
            try:
                if _PROGRESS_FILE.exists():
                    _prog = json.loads(_PROGRESS_FILE.read_text(encoding="utf-8"))
                    if _prog.get("wordlist") == wordlist and _prog.get("line", 1) > 1:
                        _prog_line = _prog["line"]
                        print(f"  {GRN}[\u2713]{RST}  Saved progress found: line {_prog_line:,}")
            except Exception:
                pass

            print()
            try:
                raw_sl = input(
                    f"  {CYN}\u203a{RST}  Start from line  {DIM}[{_prog_line}]{RST} : "
                ).strip()
                start_line = int(raw_sl) if raw_sl else _prog_line
                start_line = max(1, start_line)
            except (ValueError, EOFError):
                start_line = _prog_line
            if start_line > 1:
                print(f"  {GRN}\u203a{RST}  Skipping to line {start_line}")

            # Length filter
            print()
            try:
                raw_mnl = input(f"  {CYN}\u203a{RST}  Min length  {DIM}[3]{RST} : ").strip()
                min_len = int(raw_mnl) if raw_mnl else 3
                min_len = max(1, min_len)
            except (ValueError, EOFError):
                min_len = 3
            try:
                raw_mxl = input(f"  {CYN}\u203a{RST}  Max length  {DIM}[25]{RST} : ").strip()
                max_len = int(raw_mxl) if raw_mxl else 25
                max_len = max(min_len, max_len)
            except (ValueError, EOFError):
                max_len = 25

        elif mode in ("4", "5"):
            # \u2500\u2500 EN / DE Dictionary \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            lang     = "EN" if mode == "4" else "DE"
            dict_url = _EN_DICT_URL if mode == "4" else _DE_DICT_URL
            dest     = Path(__file__).parent / ("dict_en.txt" if mode == "4" else "dict_de.txt")
            section(f"{lang} DICTIONARY")
            if dest.exists():
                wc = sum(1 for ln in open(dest, encoding="utf-8", errors="ignore") if ln.strip())
                print(f"  {GRN}[\u2713]{RST}  Cached: {dest.name}  ({wc:,} words)")
                print(f"  {DIM}  1  \u2192  Use cached  |  2  \u2192  Re-download{RST}")
                print()
                try:
                    rc = input(f"  {CYN}\u203a{RST}  [1/2] : ").strip()
                except EOFError:
                    rc = "1"
                if rc == "2":
                    if _download_dict(dict_url, dest, lang) == 0:
                        continue
            else:
                if _download_dict(dict_url, dest, lang) == 0:
                    continue
            dict_active = str(dest)

            # Length filter
            print()
            try:
                raw_mnl = input(f"  {CYN}\u203a{RST}  Min length  {DIM}[3]{RST} : ").strip()
                min_len = int(raw_mnl) if raw_mnl else 3
                min_len = max(1, min_len)
            except (ValueError, EOFError):
                min_len = 3
            try:
                raw_mxl = input(f"  {CYN}\u203a{RST}  Max length  {DIM}[25]{RST} : ").strip()
                max_len = int(raw_mxl) if raw_mxl else 25
                max_len = max(min_len, max_len)
            except (ValueError, EOFError):
                max_len = 25

        elif mode == "6":
            # \u2500\u2500 Bruteforce \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            bruteforce = True
            section("BRUTEFORCE")
            print(f"  {YEL}[!]{RST}  Exhaustive mode \u2014 every combination is tried exactly once.")
            print(f"  {DIM}      Large charsets / high lengths = billions of combos.{RST}")
            print()

            # Check for checkpoint resume
            bf_skip = 0
            if _BF_CKPT_FILE.exists():
                try:
                    _ckpt      = json.loads(_BF_CKPT_FILE.read_text(encoding="utf-8"))
                    _ckpt_skip = _ckpt.get("skip", 0)
                    if _ckpt_skip > 0:
                        print(f"  {GRN}[\u2713]{RST}  Checkpoint found: {_ckpt_skip:,} combinations already done.")
                        try:
                            rc = input(f"  {CYN}\u203a{RST}  Resume from checkpoint?  {DIM}[Y/n]{RST} : ").strip().lower()
                        except EOFError:
                            rc = "y"
                        if rc != "n":
                            bf_skip = _ckpt_skip
                            print(f"  {GRN}\u203a{RST}  Resuming from combo #{bf_skip + 1:,}")
                        else:
                            try:
                                _BF_CKPT_FILE.unlink()
                            except Exception:
                                pass
                        print()
                except Exception:
                    pass

            # Charset
            print(f"  {DIM}  1  \u2192  Letters   a-z         (26 chars){RST}")
            print(f"  {DIM}  2  \u2192  Digits    0-9         (10 chars){RST}")
            print(f"  {DIM}  3  \u2192  Mixed     a-z + 0-9   (36 chars){RST}")
            print(f"  {DIM}  4  \u2192  Custom    enter your own characters{RST}")
            print()
            cs = prompt("Charset [1/2/3/4]", default="1", valid=["1", "2", "3", "4"])
            if cs == "4":
                try:
                    raw_cs = input(
                        f"  {CYN}\u203a{RST}  Characters (e.g. abc123) : "
                    ).strip()
                except EOFError:
                    raw_cs = string.ascii_lowercase
                # Deduplicate while preserving order
                seen = set()
                charset = "".join(
                    c for c in raw_cs if not (c in seen or seen.add(c))
                ) or string.ascii_lowercase
            else:
                charset = (
                    string.ascii_lowercase                    if cs == "1" else
                    string.digits                             if cs == "2" else
                    string.ascii_lowercase + string.digits
                )

            # Min / max length
            print()
            try:
                raw_min = input(
                    f"  {CYN}\u203a{RST}  Min length  {DIM}[3]{RST} : "
                ).strip()
                bf_min = int(raw_min) if raw_min else 3
                bf_min = max(1, bf_min)
            except (ValueError, EOFError):
                bf_min = 3

            try:
                raw_max = input(
                    f"  {CYN}\u203a{RST}  Max length  {DIM}[4]{RST} : "
                ).strip()
                bf_max = int(raw_max) if raw_max else 4
                bf_max = max(bf_min, bf_max)
            except (ValueError, EOFError):
                bf_max = 4

            # Show estimated total
            base = len(charset)
            est  = sum(base ** n for n in range(bf_min, bf_max + 1))
            rem  = est - bf_skip
            print()
            print(f"  {DIM}  Charset     :{RST}  {WHT}{BLD}{charset[:40]}{'...' if len(charset)>40 else ''}{RST}  ({base} chars)")
            print(f"  {DIM}  Range       :{RST}  {WHT}{BLD}{bf_min} \u2013 {bf_max} chars{RST}")
            print(f"  {DIM}  Total       :{RST}  {WHT}{BLD}{est:,}{RST} combinations")
            if bf_skip:
                print(f"  {DIM}  Remaining   :{RST}  {WHT}{BLD}{rem:,}{RST} combinations")
            if rem > 10_000_000:
                print(f"  {YEL}[!]{RST}  That's {rem:,} combos \u2014 this will take a very long time.")

        else:
            # \u2500\u2500 Length \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            section("LENGTH")
            for n in range(3, 9):
                print(f"  {DIM}  {n}  \u2192  {n}-char   (\u221e random){RST}")
            print()
            length = int(prompt("Length [3-8]", default="4",
                                valid=[str(i) for i in range(3, 9)]))

            # \u2500\u2500 Charset \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            section("CHARSET")
            print(f"  {DIM}  1  \u2192  Letters   a-z         (random lowercase){RST}")
            print(f"  {DIM}  2  \u2192  Digits    0-9         (random digits){RST}")
            print(f"  {DIM}  3  \u2192  Mixed     a-z + 0-9   (random mix){RST}")
            print()
            cs = prompt("Charset [1/2/3]", default="3", valid=["1", "2", "3"])
            charset = (
                string.ascii_lowercase                    if cs == "1" else
                string.digits                             if cs == "2" else
                string.ascii_lowercase + string.digits
            )

        break   # mode selected, proceed

    # \u2500\u2500 Pattern filter (optional regex) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    section("FILTER  (optional)")
    print(f"  {DIM}  Regex to only try matching usernames, e.g.  ^a.*  or  [aeiou]{{2,}}{RST}")
    print(f"  {DIM}  Leave blank to try everything.{RST}")
    print()
    try:
        raw_pat = input(f"  {CYN}\u203a{RST}  Regex pattern  {DIM}[none]{RST} : ").strip()
    except EOFError:
        raw_pat = ""
    if raw_pat:
        try:
            re.compile(raw_pat)
            pattern = raw_pat
            print(f"  {GRN}[\u2713]{RST}  Filter active: {WHT}{raw_pat}{RST}")
        except re.error as e:
            print(f"  {YEL}[!]{RST}  Invalid regex ({e}) \u2014 filter disabled.")
            pattern = None
    else:
        pattern = None

    # \u2500\u2500 Delay \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    section("DELAY")
    print(f"  {DIM}  Recommended: 0.3 \u2013 1.0 s  (too fast \u2192 WhatsApp may throttle){RST}")
    print()
    _last_delay = _last.get("delay", 0.5)
    try:
        raw   = input(f"  {CYN}\u203a{RST}  Seconds per check  {DIM}[{_last_delay}]{RST} : ").strip()
        delay = float(raw) if raw else _last_delay
        delay = max(0.0, delay)
    except (ValueError, EOFError):
        delay = _last_delay
    print(f"  {GRN}\u203a{RST}  {delay:.1f} s / check")

    # \u2500\u2500 Ready \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    section("READY")
    print(f"  {YEL}[!]{RST}  Open WhatsApp")
    print(f"       Settings  \u2192  Profile  \u2192  Username  \u2192  pencil icon (edit)")
    input(f"\n  {CYN}\u203a{RST}  Press ENTER when the username screen is open ... ")

    # \u2500\u2500 Save last-run settings \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    settings["last_run"] = {"mode": mode, "delay": delay, "desc": f"Mode {mode}  delay {delay:.1f}s"}
    _save_settings(settings)

    _work_sec  = settings.get("break_work_min", 15) * 60
    _break_sec = settings.get("break_rest_min",  5) * 60

    sniper = Sniper(delay=delay, work_sec=_work_sec, break_sec=_break_sec)
    # Pick the webhook for the active mode/length
    if dict_active:
        key = "webhook_dict_en" if mode == "4" else "webhook_dict_de"
        sniper.webhook = settings.get(key) or None
    elif wordlist:
        sniper.webhook = settings.get("webhook_wordlist") or None
    elif bruteforce:
        sniper.webhook = settings.get("webhook_bruteforce") or None
    else:
        sniper.webhook = settings.get(f"webhook_{length}") or None
    sniper.calibrate()
    sniper.run(length=length, charset=charset, wordlist=wordlist,
               start_line=start_line, dict_random=dict_active,
               bruteforce=bruteforce, bf_min=bf_min, bf_max=bf_max, bf_skip=bf_skip,
               pattern=pattern, min_len=min_len, max_len=max_len)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _w("\033[r")   # always reset scroll region on exit
        print("\n\n  Aborted.")
        sys.exit(0)


