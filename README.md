# Phosphor OS v4 — OC / UC / UV, Extended LCD Telemetry & Full Device Control for Canaan Avalon Nano 3S

<p align="center">
  <a href="https://ko-fi.com/neuragrowth">
    <img src="https://img.shields.io/badge/Support%20on%20Ko--fi-NeuraGrowth-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Support on Ko-fi" />
  </a>
  &nbsp;
  <img src="https://img.shields.io/badge/Hardware-Avalon%20Nano%203S-1e88e5?style=for-the-badge" alt="Avalon Nano 3S" />
  &nbsp;
  <img src="https://img.shields.io/badge/Release-v4-2e7d32?style=for-the-badge" alt="Release v4" />
</p>

> **Custom `app_ubi` firmware build for Canaan Avalon Nano 3S** based on **Phosphor OS**, adding an **8-mode hardware-aligned UC / UV / Eff OC / OC tuning switch**, **full RGB LED effect & brightness control**, **custom 240×240 logo upload (Screen 6)**, **Web UI Reboot & Power Off**, and **3 new live 240×240 round LCD telemetry screens** (Power Bus, 12× A3197S Core Temps, and Live W/V/A Power Chart).

*(Polska wersja opisu znajduje się poniżej / Polish description below.)*

---

## 6-Screen 240×240 Round LCD Rotation

<p align="center">
  <img src="images/lcd_screens_v4.png" width="100%" alt="Phosphor OS v4 — 6-Screen 240x240 Round LCD Rotation" />
</p>

Short-pressing the front capacitive touch button cycles through all **6 screens**:

| # | Screen | `show_id` | Description |
| :-: | :--- | :-: | :--- |
| **1** | **Main Dashboard** | `1` | Phosphor OS main screen (date, mode, time, DC Power, Hashrate, ASIC Max °C, Fan %, Stratum, IP, segmented ring) |
| **2** | **Power Bus Telemetry** | `25` | Active mode & preset (`HIGH \| EFF OC`), large DC Watts (`32 px`), symmetric `VBUS (V)` & `IBUS (A)`, `Vcore (mV) \| J/TH`, `FAN % \| Max °C` |
| **3** | **12× A3197S Cores** | `26` | Live PLL `MHz` & `Vcore`, symmetric 3×4 grid of all 12 ASIC chip temperatures from `g_pvt_temp` (color-coded: mint `<75°C`, amber `75–81°C`, red `≥82°C`), `Min / Avg / Max °C`, and `TH/s` |
| **4** | **Power Live Chart** | `27` | Real-time 48-second 3-series LVGL `lv_chart` (`176×104 px`): **Watts** (`#F3A965`, 0–150 W), **Volts** (`#8DC5FF`, 20–30 V), and **Amps** (`#9AEF9E`, 0–6 A), with live numeric legend and `TH/s \| °C` footer |
| **5** | **Digital Clock** | `2` | Phosphor OS digital clock with 60-second perimeter tick ring, weekday, seconds badge & date |
| **6** | **Custom Logo** | `3` | Default logo (`logo_b.png`) or **your own 240×240 PNG uploaded directly from the Web UI** |

---

## Web Dashboard & Tabs

### Overview (Telemetry, Live Charts, 8-Mode Tuning + OC Disclaimer, Cooling, Full RGB LED, Custom Logo & Power Controls)
<p align="center">
  <img src="images/webui_overview.png" width="100%" alt="Phosphor OS v4 Web UI — Overview Tab" />
</p>

### ASICs, Diagnostics & Pools Tabs
<p align="center">
  <img src="images/webui_asics.png" width="49%" alt="Phosphor OS Web UI — ASICs Tab (12x A3197S)" />
  &nbsp;
  <img src="images/webui_diagnostics.png" width="49%" alt="Phosphor OS Web UI — Diagnostics Tab" />
</p>
<p align="center">
  <img src="images/webui_pools.png" width="70%" alt="Phosphor OS Web UI — Pools Tab" />
</p>

---

## Downloads (Firmware v4 & Official Flashing Tool)

| File | Description | Size | SHA-256 |
| :--- | :--- | ---: | :--- |
| [`firmware/Phosphor_OS_Nano3S_OC_v4.kdimg`](firmware/Phosphor_OS_Nano3S_OC_v4.kdimg) | **Firmware v4** (`app_ubi` only, `0x04200000`) | 4.69 MB | `103CBA666DC81089DD6C61AD7974C7998CA71F1361F9A131442BE2BFC64D883F` |
| [`tools/AvalonHomeSeriesFirmwareUpgradeTool-windows-v2.2.1-0-gc3a400c-c137.zip`](tools/AvalonHomeSeriesFirmwareUpgradeTool-windows-v2.2.1-0-gc3a400c-c137.zip) | **Original Canaan Avalon Home Series Firmware Upgrade Tool (Windows v2.2.1)** | 50.19 MB | Official Canaan flasher |

Because `Phosphor_OS_Nano3S_OC_v4.kdimg` contains **only the `app_ubi` partition** (1 partition, identical to Phosphor OS), flashing it **preserves** your `data_ubi`, factory ASIC calibration, Wi-Fi/LAN configuration, pools, `rootfs_ubi`, Linux kernel, and bootloader.

---

## What's Included in v4

### 1. 8-Mode Tuning Switch (`UC / UV / Eff OC / OC`)
Disassembly of `power_set_vol` (`0x0004c0b6`) in `mm_miner` revealed that the onboard VRM DAC operates in exact **26 mV** hardware steps around `3600 mV` (`step = (V - 3600) / 26`). All voltage offsets are aligned to exact multiples of `26 mV`:

| Conf Value | Button | PLL Offset | Vcore Offset (DAC Steps) | Power Cap Offset | Purpose |
| :---: | :---: | :---: | :---: | :---: | :--- |
| `oc 1` | **UC -2** | `-40 MHz` | `-52 mV` (`-2` steps) | `-12 W` | Ultra-cool / quiet low-power operation |
| `oc 2` | **UC -1** | `-20 MHz` | `-26 mV` (`-1` step) | `-6 W` | Mild underclock + undervolt |
| `oc 3` | **UV** | `0 MHz` | `-26 mV` (`-1` step) | `-3 W` | Pure undervolt at factory clocks (better J/TH) |
| *(none)* | **Stock** | `0 MHz` | `0 mV` (`0` steps) | `0 W` | Factory Phosphor OS calibration |
| `oc 4` | **Eff OC** | `+20 MHz` | `-26 mV` (`-1` step) | `+4 W` | **Efficiency OC** — sweet spot for `HIGH` under 140 W USB-PD |
| `oc 5` | **OC +1** | `+20 MHz` | `+26 mV` (`+1` step) | `+7 W` | Mild overclock |
| `oc 6` | **OC +2** | `+35 MHz` | `+52 mV` (`+2` steps) | `+10 W` | Medium overclock (best on `LOW` / `MED` or cooled `HIGH`) |
| `oc 7` | **OC +3** | `+50 MHz` | `+78 mV` (`+3` steps) | `+12 W` | Maximum preset (watch ASIC temps & 140 W PD limit) |

**Hard-coded safety clamps in `mm_miner`:**
- Power limit: `45 W – 145 W` · Core voltage (`Vcore`): `3200 mV – 3750 mV` · PLL frequency: `120 MHz – 520 MHz`
- Factory thermal protection (`100%` fan by `90 °C`) remains 100% active.

### 2. Full RGB LED Control (Effect, Color & Brightness)
- Direct Web UI control over `ascset|0,ledset,<effect>-<brightness>-50-<R>-<G>-<B>`:
  - **Effects**: `Solid` (`1`), `Flash` (`2`), `Breath` (`3`), `Rainbow` (`4`), `Off` (`0`)
  - **Full 24-bit RGB color picker** & **10–100% brightness slider**, synchronized automatically with `LEDUser[...]` from `estats`.

### 3. Custom Logo Upload for Screen 6 (`240×240 PNG`)
- Click **Upload Logo** in the **Device** card and pick any image (`.png`, `.jpg`, `.webp`).
- The browser automatically center-crops and masks it into a circular **240×240 PNG**, uploads it to `/data/userconfig/wallpaper/wallpaper_0.png`, and persists it across reboots.
- Click **Reset Logo** at any time to restore the built-in logo.

### 4. Power Management (Reboot & Power Off)
- **Reboot** (`ascset|0,reboot,0`) and **Power Off** (`sync && poweroff`) buttons in the **Device** card with confirmation dialogs for safe shutdown without corrupting UBIFS.

---

## Technical Architecture

Built deterministically from the base Phosphor OS `app_ubi` image using a custom two-pass **RISC-V64 macro-assembler** in [`scripts/build_phosphor_oc_v4.py`](scripts/build_phosphor_oc_v4.py) and exact-size **UBIFS in-place deflate recompression** in [`scripts/test_exact_deflate.py`](scripts/test_exact_deflate.py):

- **Block A (`0x00607900–0x00607ed8`, `bno=478`)**: `phosphor_apply_oc`, LCD rotation/dispatch hooks, `read_lcdv2`, `make_lbl`, OC/UC offset table, and rodata strings (`"STATUS=S,"` at `0x006078a8` preserved untouched).
- **Block B (`0x000cf000–0x000cfd80`, `bno=191`)**: Placed inside the unused LVGL `lv_spangroup` widget (`lv_draw_span`) in `.text`; contains `init_power_screen`, `update_power_screen`, `init_cores_screen`, `update_cores_screen`, `init_chart_screen`, and `update_chart_screen`.
- **5 minimal hooks in `mm_miner`**: `cali_param_get` (`0x3b9e0`), `lcd_regular_show_switch` (`0x450b6`/`0x450f2`), `lcd_hardware_update` (`0x45432`), `get_screen_index` (`0x4a9b4`), `lcd_switch_screen` (`0x4a5f6`).
- **Web UI (`dashboard.html`, `ino=77`)**: Exact `44,022 B` length with auto-balanced UBIFS 4 KB deflate blocks (`bno=5..10`), verified with `node --check` and full UBIFS CRC32/zlib validation (`1,561` nodes, `0` errors).

---

## Flashing Instructions

1. Download [`firmware/Phosphor_OS_Nano3S_OC_v4.kdimg`](firmware/Phosphor_OS_Nano3S_OC_v4.kdimg) and unpack [`tools/AvalonHomeSeriesFirmwareUpgradeTool-windows-v2.2.1-0-gc3a400c-c137.zip`](tools/AvalonHomeSeriesFirmwareUpgradeTool-windows-v2.2.1-0-gc3a400c-c137.zip).
2. Verify SHA-256 of the `.kdimg` file: `103CBA666DC81089DD6C61AD7974C7998CA71F1361F9A131442BE2BFC64D883F`.
3. Run **Avalon Home Series Firmware Upgrade Tool**, select `Phosphor_OS_Nano3S_OC_v4.kdimg`, connect your Avalon Nano 3S in upgrade mode, and flash (only `app_ubi` is updated).
4. After reboot:
   - Open the Web UI to configure **Tuning (UC / UV / OC)**, **RGB LED**, **Custom Logo**, or **Cooling**.
   - Tap the front touch button to cycle through all 6 LCD screens.

---

## Opis po polsku

Kompletna nakładka firmware **Phosphor OS v4** dla koparki **Canaan Avalon Nano 3S** (tylko partycja `app_ubi` pod `0x04200000` — wgranie **nie kasuje** kalibracji, Wi-Fi, pul ani partycji `data_ubi`). W katalogu `tools/` dołączony jest oryginalny program do wgrywania dla Windows.

### Co zawiera wersja v4
1. **8-stopniowy przełącznik `Tuning (UC / UV / OC)` + ostrzeżenie OC w panelu Web**:
   - Dopasowany do sprzętowego kroku przetwornicy VRM DAC (**26 mV**): `UC -2`, `UC -1`, `UV`, `Stock`, `Eff OC`, `OC +1`, `OC +2`, `OC +3`, z wbudowanymi limitami bezpieczeństwa (`45–145 W`, `3200–3750 mV`, `120–520 MHz`).
2. **Pełne sterowanie LED RGB** w karcie `Device`:
   - Wybór trybu świecenia (`Solid`, `Flash`, `Breath`, `Rainbow`, `Off`), pełna paleta kolorów RGB oraz suwak jasności (`10–100%`).
3. **Wgrywanie własnego logo na 6. ekran (`Upload Logo` / `Reset Logo`)**:
   - Wybierz dowolny plik graficzny (`.png` / `.jpg` / `.webp`) — panel sam przytnie i przeskaluje go do okrągłego `240×240 PNG` i zapisze w `/data/userconfig/wallpaper/wallpaper_0.png`.
4. **Zarządzanie zasilaniem z panelu**:
   - Bezpieczny **Reboot** (`ascset|0,reboot,0`) oraz **Power Off** (`sync && poweroff`) z oknem potwierdzenia.
5. **6 ekranów na okrągłym wyświetlaczu LCD 240×240**:
   - `1` Główny Phosphor OS → `2` Zasilanie (`Power Bus`) → `3` 12 Rdzeni (`A3197S CORES`) → `4` Wykres prądowy na żywo (`POWER LIVE` — W/V/A) → `5` Zegar cyfrowy → `6` Własne logo.

---

## Support the Project / Wesprzyj projekt

If this firmware helped you get more out of your Avalon Nano 3S, consider buying a coffee on Ko-fi!  
Jeśli ten projekt okazał się pomocny dla Twojej koparki Avalon Nano 3S, możesz postawić kawę na Ko-fi:

<p align="center">
  <a href="https://ko-fi.com/neuragrowth">
    <img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ko--fi.com%2Fneuragrowth-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="ko-fi.com/neuragrowth" />
  </a>
</p>

---

## Disclaimer / Ostrzeżenie

> **WARNING:** Overclocking, undervolting, and modifying ASIC miner firmware are performed **strictly at your own risk** and may permanently damage your hardware or void any warranty. The authors provide this software "as is" with **no warranty and accept no liability** for any hardware damage, data loss, or electrical issues. Always monitor ASIC temperatures and USB-PD power supply load (especially on `OC +2` / `OC +3`).
