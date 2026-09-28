# PyMedia Downloader v1.0

Download video, audio, and images from YouTube, TikTok, Instagram, X, Facebook, Vimeo, Reddit, SoundCloud, Twitch — and any other site supported by `yt-dlp`. Comes as both a **CLI** and a **web GUI**.

## Features

- **Universal URL support** — 1000+ websites via `yt-dlp`
- **Quality picker** — 360p / 480p / 720p / 1080p / 2K / 4K / Best
- **Format picker** — MP4 / WebM / MKV for video; MP3 / M4A / WAV / FLAC for audio
- **Video → Audio extraction** — grab MP3 in one step
- **Image download + resize** — keep original, or scale to 720p / 1080p / 2K / 4K
- **Batch downloads** — paste many URLs, they download in order
- **Live progress** — percentage, speed, ETA, size
- **Resume support** — partial downloads continue
- **Download history** — every file, with re-download
- **Light / dark theme**

## Prerequisites

- Python 3.10+
- **ffmpeg** (needed for merging video+audio and MP3 conversion)

  - Ubuntu/Debian: `sudo apt install -y ffmpeg`
  - macOS: `brew install ffmpeg`
  - Windows: download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH

## Install

```bash
pip install -r requirements.txt
```

## Run — Web GUI

```bash
python app.py
```

Open http://127.0.0.1:5000

## Run — CLI

```bash
python pymedia_downloader.py
```

## Folder structure

```
downloads/
├── videos/
├── audio/
└── images/
```

Each download is saved automatically to the right subfolder.

## Cloud deployment (Render)

`ffmpeg` is not available on Render's default Python runtime. To deploy on Render with ffmpeg, use a **Dockerfile**:

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY . .

CMD gunicorn --workers 1 --timeout 600 --bind 0.0.0.0:$PORT app:app
```

And change `render.yaml` to `env: docker`.

## License

MIT
