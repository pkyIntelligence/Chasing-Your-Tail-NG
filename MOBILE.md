# Mobile Setup — Android Capture & iOS/Android Companion App

CYT splits into two roles (see `HARDWARE.md`): **capture** (a Wi-Fi radio in monitor mode
feeding Kismet) and **analysis/viewing** (CYT reading the `*.kismet` SQLite DB). This guide
covers running those roles on phones.

> **TL;DR**
> - **Android can capture** — as a Kismet *remote-capture drone* feeding your existing
>   Kismet server. Requires root + an external monitor-mode USB adapter (OTG). **Path A.**
> - **iOS can only view** — monitor mode is architecturally absent from iOS (true even
>   jailbroken). iOS is a first-class *companion app* (viewer), never a sensor.
> - Either way, the **server and all CYT analysis code stay unchanged** — the contract is
>   the `.kismet` SQLite file, not where the radio lives.

---

## 1. Why the asymmetry (read this first)

Capturing **other devices'** probe requests needs **802.11 monitor mode**, which is a
**kernel-driver capability**, not an app feature.

| Platform | Monitor mode | Why |
|---|---|---|
| **Android** | ✅ Possible | Lock is *policy*: root + firmware patch (nexmon) or an external USB adapter via OTG removes it |
| **iOS** | ❌ Impossible | Lock is *architectural*: iOS ships no monitor-mode framework and no raw-USB / userspace-driver path. A jailbreak has nothing to "unlock" — the plumbing was never written |

> **The PCAPdroid trap.** "No-root Android Wi-Fi capture" searches surface **PCAPdroid** —
> but it captures **your own device's** traffic via a local VPN. It does **not** do monitor
> mode and **cannot see other devices' probe requests**. It is useless for CYT. Ignore it.

So: **capture is Android-only; viewing is any platform.**

---

## 2. Path A — Android as a remote-capture drone

The phone becomes a pocketable sensor. Kismet still runs on your Pi/laptop and still writes
the same `.kismet` files CYT already consumes — **zero backend changes**.

```
[Android + OTG monitor-mode adapter]          ← capture (this section)
        │  802.11 frames streamed over TCP (Kismet remote source)
        ▼
[Kismet server on Pi/laptop]                   ← writes *.kismet SQLite (unchanged)
        │
        ▼
[CYT analysis] → reports / KML / GeoJSON       ← unchanged (surveillance_analyzer.py, etc.)
```

### 2.1 What you need on the phone

| Item | Requirement | Notes |
|---|---|---|
| **Root + capture OS** | **Kali NetHunter** (recommended) | Ships Kismet's capture binaries + adapter drivers in the chroot |
| **Wi-Fi adapter** | External monitor-mode USB adapter via **OTG** | e.g. **Alfa AWUS036NHA** (AR9271) — same adapter `HARDWARE.md` recommends |
| **OTG cable** | USB-OTG (USB-C or micro-USB) | Powers + connects the adapter |

> **Internal radio (nexmon) is the fragile path.** On Broadcom/Cypress phones, nexmon can
> put the *built-in* radio into monitor mode without an adapter — but patches lag firmware,
> and `nexutil` can falsely report success while the radio stays in managed mode. Prefer the
> **external adapter**; treat nexmon as best-effort.

No-root options exist (`liber80211`, Kismet's **Android PCAP** app) but are **2.4 GHz-only**
and still need an external adapter — fine for casual use, weaker than NetHunter.

### 2.2 Server side (one-time, on the Pi/laptop running Kismet)

Enable remote capture in `kismet.conf` (or a drop-in under `kismet_site.conf`):

```ini
# Listen for remote capture drones. 0.0.0.0 = any interface; lock this down on untrusted nets.
remote_capture_listen=0.0.0.0
remote_capture_port=3501
```

Restart Kismet. It now accepts drone connections on `3501` **in addition to** any local
sources. The web UI / `.kismet` output is identical to a local capture.

### 2.3 Phone side (per session, in the NetHunter terminal / chroot)

```bash
# 1. Plug the adapter into the phone via OTG, confirm it enumerates
iw dev                       # external adapter should appear, e.g. wlan1

# 2. Confirm monitor-mode capability
iw phy | grep -A8 "Supported interface modes"   # look for "* monitor"

# 3. Stream it to your Kismet server as a remote source
kismet_cap_linux_wifi --connect <server-ip>:3501 --source=wlan1
```

That's the whole drone. Frames flow to the server; the server writes the `.kismet` DB; CYT
reads it exactly as before. Multiple drones can feed one server (several phones / a phone +
the Pi's own adapter).

> **Security:** the remote-capture port is unauthenticated by default. Only expose it on a
> trusted LAN or tunnel it (SSH / WireGuard / Tailscale). Do **not** open `3501` to the
> internet.

### 2.4 What changes in CYT

**Nothing in the analysis code.** The drone just changes *where frames originate*. Confirm
`config.json` still points at wherever the **server** writes its captures:

```jsonc
// config.json — unchanged from a local-capture setup
"paths": { "kismet_logs": "./kismet_data/*.kismet" }
```

If you run analysis on the same box as the Kismet server, point the glob at Kismet's output
dir. If you analyze elsewhere (e.g. WSL2), copy the files as in `HARDWARE.md` §5.

### 2.5 Caveats that survive Path A

- **MAC randomization** (default since Android 10) still inflates device counts and weakens
  persistence-by-stable-MAC detection — independent of *where* you capture. See `HARDWARE.md` §6.
- **2.4 GHz-only adapters** miss 5/6 GHz probes. Use a dual-band monitor-mode adapter if you
  need both (heavier driver setup).
- **Battery + heat** — continuous monitor-mode capture drains a phone fast. Plan power for
  long sessions.

---

## 3. iOS (and Android) — Companion app (viewer only)

iOS cannot capture, but it makes an excellent **viewer**. The same app design works on
Android and the browser, so one backend serves all three.

```
[CYT analysis on server]
        │  REST + GeoJSON
        ▼
[iOS app]   [Android app]   [browser]          ← thin viewers, no privileged access
```

### 3.1 Why iOS works as a viewer

A viewer only does two things, both fully supported on iOS:

| Capability | iOS support |
|---|---|
| HTTP/JSON to your server | ✅ `URLSession` |
| Render points / paths / polygons on a map | ✅ **MapKit + `MKGeoJSONDecoder`** (iOS 13+) |
| Display Markdown/HTML reports | ✅ `WKWebView` |
| LAN access to the server | ✅ declare `NSLocalNetworkUsageDescription` (iOS 14+ prompt) |

> **GeoJSON, not KML.** CYT's showpiece output is **KML** for Google Earth, but MapKit has
> **no native KML support** — it *does* natively decode **GeoJSON**. So the companion path
> wants a GeoJSON serializer alongside the existing KML one.

### 3.2 Backend work required (not yet built)

The companion app needs a small service in front of CYT. Scoped from the current code:

1. **REST wrapper** (FastAPI/Flask) around the existing entry points —
   `surveillance_analyzer.py` (`SurveillanceAnalyzer.analyze_kismet_data()`) and
   `probe_analyzer.py` (`ProbeAnalyzer.analyze_probes()`). Both already return structured
   dicts.
2. **GeoJSON serializer** beside the KML exporter in `gps_tracker.py` (the KML generator
   consumes structured `GPSLocation` / `LocationSession` dataclasses, so a parallel GeoJSON
   `FeatureCollection` emitter drops in cleanly — same inputs, different output).
3. **Three light decouplings** for clean service use:
   - parameterize the hardcoded `config.json` path in `probe_analyzer.py`
   - let the caller override the hardcoded `surveillance_reports/` and `kml_files/` output dirs
   - bridge the `getpass` credential prompt via the `CYT_TEST_MODE` / `CYT_MASTER_PASSWORD`
     env vars (already supported by `secure_credentials.py`)

> Make **GeoJSON/JSON the primary API contract** and keep KML/HTML/Markdown as downloadable
> exports. Then one API feeds iOS, Android, and a browser identically.

### 3.3 Distribution (iOS)

For personal counter-surveillance use you don't need the App Store — sideload via Xcode to
your own device or distribute via TestFlight. (Avoids review friction around a tool labeled
"surveillance.")

---

## 4. End-to-end picture

```
 CAPTURE (Android only)          SERVER (unchanged)            VIEW (any platform)
┌───────────────────────┐      ┌────────────────────┐      ┌──────────────────────┐
│ Android + OTG adapter  │─TCP─▶│ Kismet → *.kismet  │      │ iOS app  (MapKit)    │
│ (NetHunter drone)      │      │ CYT analysis        │─REST▶│ Android app          │
└───────────────────────┘      │ + GeoJSON serializer│      │ browser              │
   Pi/laptop adapter ─────────▶ └────────────────────┘      └──────────────────────┘
```

- **Capture role:** Android (Path A) or a stationary Pi (`HARDWARE.md`). **iOS cannot.**
- **Server role:** unchanged — Kismet + CYT, byte-for-byte.
- **Viewer role:** iOS, Android, or browser, once the REST + GeoJSON layer (§3.2) is built.

---

## 5. Legal & ethical note

Passive 802.11 monitoring laws vary by jurisdiction, and capturing from a mobile device
makes it easy to wander into spaces where you are **not** authorized to monitor. This tooling
is for legitimate security research, network administration, and personal-safety /
counter-surveillance use where you are authorized. You are responsible for compliance with
all applicable laws. See the disclaimer in `README.md` and the note in `HARDWARE.md` §8.
