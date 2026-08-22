FROM python:3.11-slim

# Install system dependencies: ffmpeg, curl, unzip (needed for Deno install)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno (JS runtime for yt-dlp EJS/n-challenge signature solving)
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh

# Verify Deno is installed and accessible
RUN deno --version

WORKDIR /app

# Copy requirements and install latest Python dependencies + Gunicorn
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt gunicorn

# Pre-cache EJS challenge solver scripts from GitHub (required by yt-dlp for JS signature solving)
RUN yt-dlp --remote-components ejs:github --no-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>/dev/null || true

# Copy application files
COPY . .

# Ensure downloads directory exists
RUN mkdir -p static/downloads

# Expose app port
EXPOSE 5000

# Run with Gunicorn WSGI server in production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "app:app"]
