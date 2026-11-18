<p align="center">
  <img src="app/assets/logo_128.png" width="96" height="96" alt="Krolix Download Manager Logo" />
</p>

<h1 align="center">Krolix Download Manager</h1>

<p align="center">
  <b>Modern, High-Performance Multi-Threaded Download Accelerator & Stream Sniffer for Windows</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt" alt="PyQt6" />
  <img src="https://img.shields.io/badge/Extension-Manifest%20V3-4285F4?logo=googlechrome" alt="Manifest V3" />
  <img src="https://img.shields.io/badge/License-Proprietary-red.svg" alt="License" />
</p>

---

## Overview

**Krolix Download Manager** is a desktop download acceleration suite engineered specifically for Windows 10 and 11 environments. It combines a high-throughput multi-segment connection engine, dynamic stream sniffer, lossless audio/video remuxing, seamless browser interception, and a refined macOS-inspired Fluent Dark interface.

Krolix dynamically splits file downloads into parallel segments, maximizing connection throughput while maintaining file integrity.

---

## Key Features

### 1. Accelerated Multi-Threaded Connection Engine
* **Up to 32 Parallel Segments**: Dynamic chunk segmentation with instant parallel throughput.
* **Intelligent Auto-Resume**: Full support for HTTP 206 Partial Content with automatic byte-range reconstruction.
* **Anti-Forbidden Auto-Recovery**: Automatic header renewal and token refresh for expiring CDN URLs (HTTP 401, 403, 410).
* **Hardware-Accelerated Verification**: Integrated C# native engine for rapid MD5, SHA-1, and SHA-256 cryptographic hash calculations.

### 2. Stream Sniffer & Lossless Remuxing
* **Adaptive HLS & DASH Protocols**: Interception of `.m3u8` playlists and `.mpd` manifests with multi-bitrate resolution pickers.
* **Lossless Audio-Video Synchronization**: Direct TS segment remuxing to MP4 with exact timestamp alignment (`-avoid_negative_ts make_zero -fflags +genpts -bsf:a aac_adtstoasc`).
* **Faststart Header Placement**: Automatic MP4 `moov` atom placement at the beginning of the file for instant seekability in media players.
* **Live Stream Capture**: Real-time stream recording with clean finalization and container conversion.

### 3. Manifest V3 Browser Integration
* **One-Click Interception**: Chrome, Microsoft Edge, and Brave browser integration via Native Messaging Host (`com.krolix.downloader`).
* **Session & Cookie Passthrough**: Forwards authentication cookies, user-agent data, and referer headers to bypass hotlinking and CDN restrictions.
* **Floating Quality Action Panel**: Responsive overlay button on web media players for one-click resolution selection.

### 4. BitTorrent & Magnet Link Protocol
* **Integrated Torrent Client**: Native support for `.torrent` metadata files and `magnet:` URI schemes.
* **Selective File Extraction**: Interactive tree view for inspecting and selecting specific files from multi-file torrent swarms.
* **Configurable Seeding Rules**: User-defined seeding durations and bandwidth throttling limits.

### 5. Unified macOS & Fluent Dark Interface
* **Unified 48px Header**: Integrated traffic light window controls, transparent brand mascot, centered search bar, 3-dot overflow actions menu, and configuration button.
* **Real-Time Telemetry**: Instant transfer rates, estimated time of arrival (ETA), per-thread progress indicators, and responsive bandwidth graphs.
* **Category Routing**: Automatic categorization (Video, Music, Compressed, Documents, Programs), queue scheduling, and speed limiters.

### 6. Automation & Windows COM Interface
* **COM Automation Bridge**: Windows COM interface `Krolix.LinkTransmitter` accessible via PowerShell, VBScript, C#, or C++.
* **Command-Line Switches**:
  * `/d <url>` : Download URL
  * `/p <path>` : Destination directory
  * `/f <name>` : Target file name
  * `/n` : Silent mode (skip confirmation dialog)
  * `/a` : Add to queue only
  * `/s` : Start queue processing

---

## Project Structure

```text
DOWNLOAD MANAGER/
├── app/
│   ├── api/                 # Automation SDKs (PowerShell, Node.js, C++ headers)
│   ├── assets/              # High-resolution icons, logos, fonts, and sound effects
│   ├── core/                # Download engines, segment workers, database & models
│   ├── native/              # C# native engine & COM bridge source and binaries
│   ├── ui/                  # PyQt6 macOS Fluent Dark windows, dialogs, and widgets
│   └── utils/               # Windows native integration and browser helpers
├── extension/               # Manifest V3 browser extension (Chrome, Edge, Brave)
├── tests/                   # Automated unit and integration test suite
├── build_exe.py             # Packaging automation script (PyInstaller + C# compiler)
├── installer.py             # Graphical Windows setup wizard
├── main.py                  # Application entry point
├── requirements.txt         # Python package dependencies
├── .gitignore               # Git ignore rules
└── README.md                # Project documentation
```

---

## Running from Source Code

### Prerequisites
* Python 3.10, 3.11, or 3.12 (64-bit)
* Windows 10 or Windows 11
* FFmpeg (optional, for external video stream remuxing)

### Installation Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Robertkurniawan00/Krolix-Download-Manager.git
   cd Krolix-Download-Manager
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch Krolix**:
   ```bash
   python main.py
   ```

---

## Browser Extension Setup

1. Open your Chromium-based browser (Google Chrome, Microsoft Edge, or Brave).
2. Navigate to the extensions page:
   * **Chrome**: `chrome://extensions`
   * **Edge**: `edge://extensions`
   * **Brave**: `brave://extensions`
3. Enable the **Developer mode** toggle.
4. Click **Load unpacked**.
5. Select the `extension/` directory from this repository.
6. The extension is now active and connected to Krolix.

---

## Copyright & Commercial License

Copyright (c) 2026 Robert Kurniawan. All Rights Reserved.

This software and its associated source code, design assets, and compiled binaries are proprietary and commercial products. No open-source license is granted.

Unauthorized copying, distribution, modification, reverse engineering, decompilation, public display, or commercial exploitation of any portion of this software without prior written permission from the copyright holder is strictly prohibited.

To purchase a commercial license, obtain usage permissions, or discuss business inquiries, please contact the developer directly.
