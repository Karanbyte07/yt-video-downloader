# insTube

Fast browser-based video downloader built with Flask and yt-dlp.



## Why this project

insTube provides a clean web interface to preview and download supported video links without exposing command-line complexity to end users. It is designed for quick local use, clear UX, and practical backend handling of media formats.

## Highlights

- URL metadata preview before download (title, thumbnail, stream preview when available)
- One-click server-side download flow
- Automatic FFmpeg detection for improved merge/remux behavior
- Download delivery with attachment headers for reliable browser save prompts
- Lightweight Flask architecture with simple folder organization

## Tech stack

- Backend: Flask
- Media engine: yt-dlp
- Frontend: Vanilla JavaScript, HTML, CSS
- Optional media tooling: FFmpeg

## Project structure

```text
.
|-- app.py
|-- requirements.txt
|-- templates/
|   `-- index.html
`-- static/
   |-- script.js
   |-- style.css
   |-- brand/
   `-- downloads/   # runtime output (gitignored)
```

## Getting started

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
python app.py
```

Open: http://127.0.0.1:5000

## How it works

1. User submits a video URL from the web UI.
2. Frontend calls POST /api/info to fetch metadata/preview.
3. User clicks Download.
4. Frontend calls POST /api/download.
5. Backend downloads media via yt-dlp into static/downloads.
6. Backend returns a file URL and browser download starts.

## API overview

- GET / : renders main interface
- POST /api/info : fetches metadata and preview URL without downloading
- POST /api/download : downloads requested media and returns download path
- GET /static/downloads/<filename> : serves downloaded file as attachment

## Configuration and notes

- FFmpeg is optional but recommended for better format compatibility.
- Download artifacts are stored in static/downloads and excluded from Git.
- This project is intended for development/local usage by default.

## Troubleshooting

- 403 or extractor errors: update yt-dlp and retry.
- Missing expected merge behavior: verify FFmpeg is installed and on PATH.
- Invalid URL errors: confirm the link is supported by yt-dlp.

## Disclaimer

Use responsibly and comply with platform terms, local laws, and content rights.

If this project helps you, please consider giving the repository a star.