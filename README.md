# WhatsApp Username Sniper

A high-performance, automated WhatsApp username availability checker powered by **ADB** (Android Debug Bridge) and UI inspection. 

Operates directly on your physical Android device over a standard USB or wireless ADB connection. **No root, no modified APKs, and no Frida required.**

---

## Highlights & Features

- **Zero Third-Party Dependencies** — Built entirely with the Python standard library. No `pip install` required.
- **High-Throughput Persistent Shell** — Piped interactive ADB shell eliminates per-command process overhead for maximum speed.
- **6 Versatile Generation Modes** — Random combo generator, custom wordlists, English & German dictionary generators, and exhaustive bruteforce.
- **Smart Auto-Calibration** — Automatically locates text field coordinates via UIAutomator dump with manual fallback support.
- **Real-Time Terminal Dashboard** — Live ANSI status monitor displaying hits, total checked, scan speed (req/s), elapsed time, and ETA.
- **Automated Anti-Throttle Protection** — Configurable work/rest intervals (e.g., 15m work / 5m rest) with live countdown timers to protect against rate limits.
- **Multi-Channel Discord Notifications** — Route hits to dedicated Discord webhook channels based on username length or mode.
- **Dual Logging & State Persistence** — Automatically records all hits to both `hits.txt` and `hits.csv` alongside automatic checkpoint saving for resuming wordlist and bruteforce runs.
- **Automatic Deduplication** — Tracks checked candidates in `checked.txt` so names are never redundantly queried across runs.
- **Audio Alerts** — Immediate system beep notification whenever an available username is discovered.

---

## How It Works

WhatsApp verifies username availability in real time directly within the application's profile settings. 

```
┌─────────────────┐       ADB Shell Pipe        ┌────────────────────────┐
│  Python Sniper  │  ─────────────────────────► │     Android Device     │
│   (PC Client)   │  ◄───────────────────────── │  WhatsApp Profile Edit │
└────────┬────────┘      UIAutomator State      └────────────────────────┘
         │
         ├───► Available Hit?  ───►  hits.txt & hits.csv
         ├───► Audio Alert     ───►  System Beep
         └───► Discord Hook    ───►  Channel Embed Notification
```

1. Connects to your Android device via an optimized ADB connection.
2. Injects candidate usernames into the native WhatsApp username field.
3. Parses the UIAutomator hierarchy to read the instantaneous validation status.
4. Categorizes the username as available, taken, or throttled.
5. Logs hits, notifies configured webhooks, and proceeds to the next candidate.

---

## Prerequisites

| Requirement | Details |
| :--- | :--- |
| **Python** | Version 3.9 or newer |
| **ADB** | Android Platform Tools installed and accessible in system `PATH` |
| **Android Phone** | USB Debugging enabled, connected via USB cable (or wireless ADB) |
| **WhatsApp** | Official WhatsApp installed and logged into an active account |

> [!NOTE]
> Root access is **not required**. The tool interacts strictly through standard Android Accessibility and ADB input mechanisms.

---

## Installation & Setup

### 1. Install Python
Download and install Python 3.9+ from [python.org](https://python.org). Ensure the option **"Add Python to PATH"** is checked during installation.

### 2. Set Up Android Debug Bridge (ADB)
1. Download the [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools).
2. Extract the folder to a permanent location (e.g., `C:\platform-tools` or `/usr/local/bin`).
3. Add the extracted directory to your system's `PATH` environment variable.
4. Verify installation in your terminal:
   ```bash
   adb version
   ```

### 3. Enable USB Debugging on Your Device
1. Open **Settings** → **About Phone**.
2. Tap **Build Number** 7 times until Developer Options are enabled.
3. Navigate to **Settings** → **Developer Options**.
4. Enable **USB Debugging** (and **USB Debugging (Security settings)** if on MIUI/HyperOS/ColorOS).

### 4. Authorize Device
Connect your phone via USB and run:
```bash
adb devices
```
If prompted on your phone screen, tap **"Always allow from this computer"** and select **Allow**. The terminal output must report the device as `device` (not `unauthorized` or `offline`).

---

## Quick Start

1. **Navigate to the Username Screen on Your Device:**
   ```
   WhatsApp → Settings → Profile → Username → Edit (pencil icon)
   ```
   *(Ensure the input field is visible on the screen before launching the script).*

2. **Run the Sniper:**
   ```bash
   python sniper.py
   ```

3. **Select Mode & Parameters:**
   Select your preferred generation mode and configure delay (recommended: `0.5s`).

4. **Calibrate:**
   The script will auto-detect the coordinate box of the input field. If auto-detection fails, manually input the X/Y coordinates as prompted.

---

## Operation Modes

| # | Mode | Description | Configuration Options |
| :-: | :--- | :--- | :--- |
| **1** | **Combo** | Generates an infinite stream of random combinations | Length (`3`–`8`), Charset (Letters `a-z`, Digits `0-9`, Mixed `a-z0-9`, or Custom) |
| **2** | **Wordlist** | Iterates through a custom wordlist file line by line | File path, starting line / resume progress, min/max length filtering |
| **3** | **Settings** | Configuration panel for webhooks and timers | Up to 10 Discord webhook slots & custom work/rest break schedules |
| **4** | **EN Dict** | Top ~10,000 most common English words (auto-cached) | Min/max length filtering, automatic shuffle per complete pass |
| **5** | **DE Dict** | Top 50,000 most common German words (auto-cached) | Min/max length filtering, frequency-based word dictionary |
| **6** | **Bruteforce**| Exhaustive search through every combination systematically | Custom charset, min/max length, automatic checkpoint save/resume |

---

## Discord Webhook Integration

Configure webhooks in **Mode 3 (Settings)** to receive instant rich notifications when an available username is claimed or discovered.

### Webhook Routing Slots:
- **Slots 1–6 (`3-char` to `8-char`):** Dispatches alerts for Combo mode results matched by character length.
- **Slot 7 (`Wordlist`):** Dispatches alerts triggered in Mode 2.
- **Slot 8 (`EN Dict`):** Dispatches alerts triggered in Mode 4.
- **Slot 9 (`DE Dict`):** Dispatches alerts triggered in Mode 5.
- **Slot 10 (`Bruteforce`):** Dispatches alerts triggered in Mode 6.

All webhook endpoints are validated with an interactive test function upon configuration and stored persistently in `settings.json`.

---

## Anti-Throttle Protection (Auto-Pause)

To avoid temporary rate-limiting from WhatsApp servers, the built-in scheduler pauses activity periodically:

- **Default Work Interval:** 15 minutes of active checking.
- **Default Rest Interval:** 5 minutes cooldown period.
- **Live Display:** Displays an active `MM:SS` countdown timer during breaks.
- **Customizable:** Adjust interval durations in **Mode 3 → Break config** (`b`).

---

## Project Structure & File Reference

| File | Description |
| :--- | :--- |
| `sniper.py` | Main application script containing the ADB engine, UI reader, and CLI interface. |
| `hits.txt` | Human-readable log of all available usernames discovered, formatted with timestamps. |
| `hits.csv` | Structured CSV archive containing timestamp, username, and discovery mode. |
| `checked.txt` | Persistent cache of all tested usernames to prevent duplicate requests across runs. |
| `settings.json` | Local configuration store for webhook endpoints and break timers. |
| `wordlist.txt` | Default local wordlist file (bundled with 1,000 curated words). |
| `wordlist_progress.json` | Automatic bookmark tracking last processed line for wordlist runs. |
| `bf_checkpoint.json` | Saved state index allowing seamless resumption of bruteforce sessions. |
| `dict_en.txt` / `dict_de.txt` | Cached local dictionaries downloaded on first initialization. |
| `webhook_errors.log` | Diagnostic log recording any failed HTTP webhook deliveries. |

---

## Tips & Best Practices

- **Screen Awake:** Keep your phone screen awake while scanning (enable *"Stay awake while charging"* in Developer Options).
- **Recommended Delay:** A delay of `0.5s` offers an optimal balance between throughput and rate-limit safety.
- **Resuming Worklists:** If you terminate a wordlist or bruteforce scan, relaunching the mode will automatically offer to resume from your exact progress checkpoint.
- **Network Stability:** Ensure a stable internet connection on the mobile device so WhatsApp can return username availability checks without timeouts.

---

## Disclaimer

> [!WARNING]
> This project is developed strictly for educational and security research purposes. Automating interactions with WhatsApp may violate their [Terms of Service](https://www.whatsapp.com/legal/terms-of-service). The authors and contributors assume no liability for account restrictions, suspensions, or misuse of this software. Use responsibly.
