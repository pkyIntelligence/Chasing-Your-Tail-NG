# Hardware & Capture Setup

CYT is an **analysis** tool. It does not touch a Wi-Fi radio directly — it reads the
SQLite `*.kismet` databases that **Kismet** produces. This guide covers the hardware you
need to actually capture data, why your everyday machines aren't suitable for capture, and
the recommended split-role setup.

> **TL;DR** — Capture on a dedicated Linux box (a Raspberry Pi), analyze in WSL2.
> A complete rig is ~$70–95: **Pi 5 1GB ($45)** + **Alfa AWUS036NHA adapter (~$25)** +
> optional **USB GPS puck (~$12)** + a 32GB+ SD card.

---

## 1. The two roles: capture vs. analysis

| Role | What runs | Where |
|---|---|---|
| **Capture** | Kismet + Wi-Fi radio (+ GPS) | Dedicated native-Linux box (Raspberry Pi) |
| **Analysis** | CYT (`surveillance_analyzer.py`, `probe_analyzer.py`, KML/reports) | Anywhere — **WSL2 is fine** |

They do **not** need to be the same machine. Kismet writes `.kismet` files; you copy them
to the analysis box and point CYT at them. This is the workflow CYT is designed around (note
the `paths.kismet_logs` glob in `config.json` and the auto-start crontab in `CLAUDE.md`).

### Why not capture on WSL2 or macOS?
- **WSL2** is a lightweight VM. USB passthrough exists (`usbipd-win`), but the default WSL2
  kernel ships **no Wi-Fi adapter drivers and no `mac80211` monitor-mode support**. Capturing
  would require compiling a custom WSL2 kernel — fragile and breaks on updates. Use WSL2 for
  **analysis only**.
- **macOS** locks down monitor mode and almost never has drivers for external USB
  monitor-mode adapters. Not a viable Kismet capture platform.

Monitor mode is a **kernel-driver** capability, not an app feature — Kismet can only use what
the OS exposes. Native Linux on bare metal (a Pi) is where the driver ecosystem actually works.

> **Phones?** An **Android** device (rooted + OTG monitor-mode adapter) can act as a
> pocketable capture drone feeding this same Kismet server; **iOS cannot capture** (no
> monitor mode) but makes a fine viewer. See `MOBILE.md`.

---

## 2. Recommended capture board — Raspberry Pi

Pricing reflects the 2026 DRAM shortage, which has inflated **high-RAM** SKUs. Kismet is
**CPU-bound, not RAM-bound**, so the cheap low-memory boards are the smart buy.

| Board | Price (mid-2026) | For Kismet |
|---|---|---|
| **Pi 5 — 1GB** | **$45** | ⭐ **Recommended.** Cheapest Pi 5, fastest CPU (quad Cortex-A76) |
| **Pi 4 — 2GB** | **$55** | ⭐ Alternative. Most-documented wardriving platform; extra RAM headroom |
| Pi 4 — 1GB | $35 | Budget floor; older A72 CPU |
| Pi 5 — 8GB / 16GB | $130 / $305 | Overkill + crisis-inflated — **skip** |
| Pi Zero 2 W | ~$15–20 | ⚠️ CPU-starved for Kismet — **not recommended** |

**Pick the Pi 5 1GB** unless you want the most-documented path or plan dense mobile
wardriving runs, in which case take the **Pi 4 2GB**. Avoid 4GB+ boards (you don't need the
memory and it's the inflated component) and the Zero 2 W (too weak for Kismet).

Run **Raspberry Pi OS Lite** (headless) or **Kali Linux ARM** (Kismet + drivers preloaded —
less setup).

> **Use the Pi's onboard Wi-Fi for management (SSH), not capture.** The built-in Broadcom
> chip only does monitor mode via flaky `nexmon` patches and drops off the network while
> sniffing. Keep onboard Wi-Fi for login + file transfer; do all capture on an external USB
> adapter. Two radios, two jobs.

---

## 3. The radio and GPS

| Item | Recommendation | Notes |
|---|---|---|
| **Wi-Fi adapter** | **Alfa AWUS036NHA** (Atheros AR9271, ~$25) | Most reliably-supported monitor-mode adapter on Linux; plug-and-play on Kali/Pi OS |
| **GPS** (optional) | Any **u-blox USB GPS puck** (~$12) | Needed only for the location/KML features; read via `gpsd` |
| **Storage** | **32GB+ SD card** (or USB SSD for heavy use) | A busy 24h capture can write several GB — see §6 |

Without GPS, `avg_lat`/`avg_lon` stay 0 and CYT records devices as **report-only** (no map).
That fallback is logged at debug level in `surveillance_analyzer._load_appearances_with_gps`.

---

## 4. Capture setup (on the Pi)

```bash
# 1. Flash Raspberry Pi OS Lite (or Kali ARM) to the SD card, boot headless, SSH in
#    over the Pi's onboard Wi-Fi.

# 2. Install Kismet + gpsd (Pi OS; Kali has these preloaded)
sudo apt update && sudo apt install -y kismet gpsd gpsd-clients

# 3. Plug in the Alfa adapter + GPS, then confirm the radio is present
iw dev                      # external adapter should appear, e.g. wlan1

# 4. Confirm monitor-mode capability
sudo iw phy                 # look for "monitor" under "Supported interface modes"

# 5. Confirm a GPS fix (skip if no GPS)
sudo systemctl enable --now gpsd
cgps -s                     # wait for a 3D fix with real lat/lon
```

Kismet puts the adapter into monitor mode itself when you give it the source interface.
The repo's `start_kismet_clean.sh` launches Kismet on `wlan1`:

```bash
sudo /usr/local/bin/kismet -c wlan1 --daemonize
# Web UI: http://<pi-ip>:2501
```

Adjust `-c wlan1` to whatever `iw dev` shows for your **external** adapter (not the onboard
`wlan0`). Kismet writes `*.kismet` files to its working directory.

---

## 5. Analysis loop (Pi → WSL2)

```bash
# On WSL2: pull the capture files from the Pi
scp pi@<pi-ip>:~/kismet_logs/*.kismet  /path/to/Chasing-Your-Tail-NG/kismet_data/

# Point config.json at them
#   "paths": { "kismet_logs": "./kismet_data/*.kismet", ... }

# Run the analysis
python3 surveillance_analyzer.py            # GPS-correlated surveillance + KML
python3 probe_analyzer.py                   # probe-request / SSID analysis
```

Open the generated `kml_files/*.kml` in Google Earth; reports land in
`surveillance_reports/`. (HTML reports also need `pandoc` installed; Markdown + KML do not.)

---

## 6. Memory & storage for long sessions

RAM use is driven by the number of **unique devices held in memory**, not session length —
packets stream to disk, not RAM. Approximate footprint:

```
RAM ≈ ~300 MB (OS + Kismet base) + (unique devices × ~5–10 KB)
```

| Scenario (≤24h) | Unique devices | 1GB board verdict |
|---|---|---|
| Stationary, normal area (counter-surveillance) | hundreds–few thousand | ✅ Comfortable |
| Stationary, busy urban | ~5k–30k | ✅ Fine |
| Mobile wardriving, dense city | 50k–100k+ | ⚠️ Tight on 1GB → use Pi 4 2GB |

**Note:** MAC randomization inflates device counts — each randomized probe MAC looks like a
new device, so dense *mobile* captures balloon. Stationary persistence detection (CYT's core
use case) stays modest, so **1GB is sufficient for ≤24h** in that mode.

**Safety valves** if you ever do push the limits — bound RAM in Kismet's config regardless of
duration:
- `tracker_max_devices=N` — hard cap on in-RAM device count (evicts oldest)
- device timeout — expires stale devices from RAM after inactivity

**Disk, not RAM, is the real 24h constraint:** a busy full-day capture can produce a
multi-GB `.kismet` file. Use a **32GB+ SD card**, or a USB SSD for heavy/continuous use.

---

## 7. Quick shopping list

| Item | ~Price |
|---|---|
| Raspberry Pi 5 1GB (or Pi 4 2GB) | $45 / $55 |
| Alfa AWUS036NHA USB adapter | $25 |
| USB GPS puck (optional) | $12 |
| 32GB+ SD card | $8–12 |
| USB power bank (for portable use) | varies |
| **Total** | **~$70–95** |

---

## 8. Legal & ethical note

Passive 802.11 monitoring laws vary by jurisdiction. This tooling is for legitimate security
research, network administration, and personal-safety / counter-surveillance use on devices
and in places where you are authorized to monitor. You are responsible for compliance with
all applicable laws. See the disclaimer in `README.md`.
