<p align="center">
  <img src="app/assets/logo_128.png" width="96" height="96" alt="Krolix Download Manager Logo" />
</p>

<h1 align="center">Krolix Download Manager</h1>

<p align="center">
  <b>Modern, High-Performance Multi-threaded Download Manager & Stream Sniffer for Windows</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt" alt="PyQt6" />
  <img src="https://img.shields.io/badge/Extension-Manifest%20V3-4285F4?logo=googlechrome" alt="Manifest V3" />
  <img src="https://img.shields.io/badge/License-Proprietary-red.svg" alt="License" />
</p>

---

## Ringkasan (Overview)

**Krolix Download Manager** adalah suite akselerasi unduhan desktop berkinerja tinggi yang dirancang khusus untuk lingkungan Windows 10 dan 11. Aplikasi ini memadukan mesin koneksi multi-segmen paralel berkecepatan tinggi, pengendus media dinamis (*dynamic media sniffer*), remuxing audio/video lossless, integrasi peramban tanpa hambatan, serta antarmuka modern bernuansa macOS dengan sentuhan Fluent Dark.

Krolix secara dinamis memecah tugas unduhan menjadi segmen-segmen paralel, memaksimalkan penggunaan bandwidth internet yang tersedia sambil tetap menjaga integritas berkas secara presisi.

---

## Fitur Utama (Key Features)

### 1. Mesin Akselerasi Multi-Threaded
* **Hingga 32 Segmen Paralel**: Pembagian potongan data dinamis dengan streaming paralel instan.
* **Smart Auto-Resume**: Dukungan penuh untuk HTTP 206 Partial Content dengan rekonstruksi rentang bita otomatis.
* **Anti-Forbidden Auto-Recovery**: Pembaruan header dan refresh token otomatis untuk tautan CDN yang memiliki masa kedaluwarsa (`401`, `403`, `410`).
* **Verifikasi Integritas Terakselerasi**: Mesin native C# terintegrasi untuk verifikasi hash berkecepatan tinggi (MD5, SHA-1, SHA-256).

### 2. Intelligent Stream Sniffer & Lossless Remuxing
* **Dukungan HLS & DASH**: Mencegat playlist `.m3u8` dan manifes `.mpd` dengan pemilih resolusi multi-bitrate.
* **Lossless Audio-Video Sync**: Penggabungan segmen TS ke MP4 secara mulus dengan penataan timestamp presisi (`-avoid_negative_ts make_zero -fflags +genpts -bsf:a aac_adtstoasc`).
* **Penyisipan Faststart**: Penataan header MP4 otomatis (*moov atom at beginning*) untuk memungkinkan pemutaran instan (*instant seek*) pada pemutar media.
* **Perekaman Siaran Langsung**: Perekaman live stream secara real-time dengan penghentian dan konversi rapi.

### 3. Integrasi Peramban Manifest V3
* **Intersepsi Sekali Klik**: Integrasi otomatis untuk Google Chrome, Microsoft Edge, dan Brave melalui Native Messaging Host (`com.krolix.downloader`).
* **Penerusan Kredensial & Cookie**: Meneruskan sesi login, header referer, dan cookie secara otomatis untuk melewati proteksi hotlinking.
* **Panel Aksi Melayang**: Tombol unduhan responsif pada pemutar media web untuk pemilihan resolusi instan.

### 4. Dukungan BitTorrent & Magnet Link
* **Klien Torrent Terpadu**: Dukungan langsung untuk berkas `.torrent` dan tautan `magnet:`.
* **Ekstraksi Berkas Selektif**: Pratinjau dan pemilihan berkas spesifik dari kawanan torrent.
* **Pengaturan Rasio & Seeding**: Batas waktu seeding yang dapat dikonfigurasi serta pembatasan kecepatan unggah.

### 5. Antarmuka Modern macOS & Fluent Dark
* **Bilah Header macOS 48px Terpadu**: Tombol navigasi window kapsul, logo transparan, pencarian terpusat, menu aksi 3-titik, dan tombol konfigurasi.
* **Telemetri Real-Time**: Kecepatan transfer langsung, estimasi waktu selesai (ETA), status thread, dan grafik bandwidth interaktif.
* **Manajemen Unduhan Fleksibel**: Pengelompokan kategori otomatis, antrean terjadwal (*scheduler*), serta pembatas kecepatan unduh (*speed limiter*).

### 6. Otomasi & Antarmuka COM Windows
* **COM Automation Bridge**: Antarmuka Windows COM `Krolix.LinkTransmitter` dapat diakses langsung melalui PowerShell, VBScript, C#, maupun C++.
* **Argumen Baris Perintah (CLI)**:
  * `/d <url>` : Alamat URL unduhan
  * `/p <path>` : Folder tujuan penyimpanan
  * `/f <name>` : Nama berkas keluaran
  * `/n` : Mode hening tanpa dialog konfirmasi
  * `/a` : Tambahkan ke antrean saja
  * `/s` : Mulai proses antrean

---

## Arsitektur Proyek

```text
DOWNLOAD MANAGER/
├── app/
│   ├── api/                 # Automation SDKs (PowerShell, Node.js, C++ headers)
│   ├── assets/              # Ikon, logo, font, dan audio notifikasi
│   ├── core/                # Mesin unduh, segment worker, database & model
│   ├── native/              # Kode sumber C# native engine & COM bridge
│   ├── ui/                  # Tampilan antarmuka PyQt6, dialog, dan widget
│   └── utils/               # Modul integrasi Windows dan peramban
├── extension/               # Ekstensi browser Manifest V3 (Chrome, Edge, Brave)
├── tests/                   # Rangkaian pengujian unit dan integrasi
├── build_exe.py             # Otomasi kompilasi PyInstaller dan C# native engine
├── installer.py             # Wizard penginstal Windows berantarmuka grafis
├── main.py                  # Titik masuk utama aplikasi
├── requirements.txt         # Daftar dependensi Python
├── .gitignore               # Aturan pengabaian berkas Git
└── README.md                # Dokumentasi proyek
```

---

## Panduan Menjalankan dari Source Code

### Prasyarat
* Python 3.10, 3.11, atau 3.12 (64-bit)
* Sistem Operasi Windows 10 atau Windows 11
* FFmpeg (opsional untuk remuxing segmen video eksternal)

### Langkah-langkah

1. **Clone Repositori**:
   ```bash
   git clone https://github.com/Robertkurniawan00/Krolix-Download-Manager.git
   cd Krolix-Download-Manager
   ```

2. **Buat dan Aktifkan Virtual Environment**:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Pasang Dependensi**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Jalankan Aplikasi**:
   ```bash
   python main.py
   ```

---

## Pemasangan Ekstensi Peramban

1. Buka peramban Chromium (Google Chrome, Microsoft Edge, atau Brave).
2. Masuk ke halaman pengelolaan ekstensi:
   * **Chrome**: `chrome://extensions`
   * **Edge**: `edge://extensions`
   * **Brave**: `brave://extensions`
3. Aktifkan saklar **Mode pengembang** (*Developer mode*).
4. Klik tombol **Muat yang belum dibongkar** (*Load unpacked*).
5. Pilih folder `extension/` dari direktori proyek ini.
6. Ekstensi siap digunakan dan otomatis terhubung ke Krolix.

---

## Hak Cipta & Lisensi Komersial

Hak Cipta (c) 2026 Robert Kurniawan. Seluruh Hak Cipta Dilindungi Undang-Undang (*All Rights Reserved*).

Perangkat lunak ini merupakan produk berpemilik (*proprietary*) dan komersial. Tidak disediakan lisensi open source untuk perangkat lunak ini. 

Dilarang keras menyalin, mendistribusikan ulang, memodifikasi, mendekompilasi, menerbitkan ulang, atau memperjualbelikan kode sumber maupun biner aplikasi ini baik sebagian maupun keseluruhan tanpa izin tertulis resmi dari pemilik hak cipta.

Untuk pembelian lisensi penggunaan, lisensi komersial, atau kerja sama bisnis, silakan hubungi pengembang secara langsung.
