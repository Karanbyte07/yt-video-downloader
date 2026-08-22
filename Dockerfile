FROM python:3.11-slim

# Install system dependencies: ffmpeg, curl, unzip, git (for Deno and bgutil token generator)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Deno (JS runtime for yt-dlp EJS/n-challenge signature solving)
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh

# Clone bgutil PO token generator source for script-deno provider
RUN git clone https://github.com/brainicism/bgutil-ytdlp-pot-provider.git /app/bgutil-ytdlp-pot-provider

WORKDIR /app

# Copy requirements and install latest Python dependencies + Gunicorn
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt gunicorn

# Pre-cache EJS challenge solver scripts from GitHub
RUN yt-dlp --remote-components ejs:github --no-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>/dev/null || true

# Copy application files
COPY . .

# Ensure downloads directory exists
RUN mkdir -p static/downloads

# Expose app port
EXPOSE 5000

# Run with Gunicorn WSGI server in production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "app:app"]
