import os
import shutil
import yt_dlp
import urllib.parse
from flask import Flask, request, jsonify, render_template, send_from_directory
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('instube')

# ----------------------------
# Flask setup
# ----------------------------
app = Flask(__name__, template_folder='templates', static_folder='static')

# Centralized paths
DOWNLOAD_FOLDER = os.path.join(app.static_folder, 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Cookie configuration for YouTube authentication
COOKIES_FILE = os.environ.get("COOKIES_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')

def _apply_cookies_if_present(ydl_opts: dict):
    """Configure yt-dlp player clients.

    Home-browser cookies do NOT work on VPS/datacenter IPs because YouTube
    ties sessions to IP addresses. Using them causes immediate session rejection.

    Instead, we always use visionos (HLS streams, no JS/cookies needed) as the
    primary client, which works reliably on VPS IPs for public videos.

    Cookies would only help if they were exported from a browser session on the
    same VPS IP — which is impractical without a browser on the server.
    """
    # web_embedded bypasses VPS bot detection — YouTube allows embedded player API from any IP.
    # visionos uses HLS streams as fallback. android/ios as additional fallbacks.
    ydl_opts.pop("cookiefile", None)
    ydl_opts["extractor_args"] = {
        "youtube": {
            "player_client": ["web_embedded", "visionos", "android", "ios"]
        }
    }
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 50:
        logger.info(f"Note: cookies.txt found but not used (home IP cookies cause VPS session rejection)")











# ----------------------------
# Helper: sanitize and download
# ----------------------------
def sanitize_filename(name: str) -> str:
    """Remove problematic characters from filenames."""
    # Keep only alphanumeric, spaces, and some safe chars
    safe = "".join(c for c in name if c.isalnum() or c in (" ", ".", "_", "-")).rstrip()
    # Replace multiple spaces with single space
    safe = ' '.join(safe.split())
    # Ensure the filename isn't too long for some filesystems
    if len(safe) > 200:
        safe = safe[:197] + "..."
    return safe


def _has_ffmpeg() -> bool:
    """Check whether ffmpeg is available on PATH."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        logger.info(f"FFmpeg detected at: {ffmpeg}")
        return True
    logger.warning("FFmpeg not detected; falling back to progressive formats (audio codec may not be MP3).")
    return False

def download_with_yt_dlp(url: str, format_type: str = None, media_type: str = None) -> dict:
    """
    Download a video from the given URL and return metadata.
    Supports multiple formats with fallback.
    """
    use_ffmpeg = _has_ffmpeg()
    
    # Determine format string based on user selection
    if media_type == "audio":
        # Audio-only downloads
        if format_type == "320kbps":
            format_str = "bestaudio[ext=mp3]/bestaudio/best"
        elif format_type == "128kbps":
            format_str = "worstaudio[ext=mp3]/worstaudio/best"
        else:
            format_str = "bestaudio[ext=mp3]/bestaudio/best"
    else:
        # Video downloads with specific resolution
        if format_type == "1080p":
            if use_ffmpeg:
                format_str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
            else:
                format_str = "best[height<=1080][acodec!=none]/best[height<=1080]"
        elif format_type == "720p":
            if use_ffmpeg:
                format_str = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
            else:
                format_str = "best[height<=720][acodec!=none]/best[height<=720]"
        elif format_type == "480p":
            if use_ffmpeg:
                format_str = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
            else:
                format_str = "best[height<=480][acodec!=none]/best[height<=480]"
        else:
            # Default: best quality
            if use_ffmpeg:
                format_str = "bestvideo+bestaudio/best"
            else:
                format_str = "best[acodec!=none]/best"


    # Set output template based on media type
    if media_type == "audio":
        outtmpl = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")
    else:
        outtmpl = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")
    
    ydl_opts = {
        # Constrain selection as above
        "format": format_str,
        "outtmpl": outtmpl,
        "quiet": True,
        "noplaylist": True,
        # Prefer ffmpeg if available (yt-dlp will handle merging/remuxing)
        "prefer_ffmpeg": use_ffmpeg,
        # Optimizations for faster downloads
        "no_warnings": True,
        "extract_flat": False,
        "writeinfojson": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "ignoreerrors": False,
        "no_check_certificate": True,
        "prefer_insecure": False,
        # Skip unnecessary processing
        "skip_unavailable_fragments": True,
        "keep_fragments": False,
        # Extractor arguments to bypass YouTube bot/rate-limit restrictions (HTTP 429)
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "mweb", "web"]
            }
        },
    }

    _apply_cookies_if_present(ydl_opts)


    if use_ffmpeg:
        if media_type == "audio":
            # For audio-only downloads, ensure MP3 output
            ydl_opts.update(
                {
                    "merge_output_format": "mp3",
                    "postprocessor_args": [
                        "-c:a",
                        "libmp3lame",
                        "-b:a",
                        "320k" if format_type == "320kbps" else "128k",
                    ],
                }
            )
        else:
            # For video downloads, merge best video+audio into MKV
            ydl_opts.update({
                "merge_output_format": "mkv"
            })
    else:
        # Without FFmpeg, rely on progressive formats that already include audio
        # Note: audio codec will likely be AAC/Opus, not MP3.
        ydl_opts.pop("prefer_ffmpeg", None)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
    except Exception as first_err:
        if "cookiefile" in ydl_opts:
            logger.warning(f"Download with cookies failed ({first_err}). Retrying without cookies using mobile client fallback...")
            ydl_opts.pop("cookiefile", None)
            ydl_opts["extractor_args"] = {
                "youtube": {
                    "player_client": ["tv", "visionos", "android", "ios"]
                }
            }


            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
        else:
            raise

        
        # Get actual downloaded filename (may differ from prepared filename)
        # This handles cases where yt-dlp renamed the file due to conflicts
        actual_filename = os.path.basename(filename)
        
        # Check if the file exists with the expected name
        expected_path = os.path.join(DOWNLOAD_FOLDER, actual_filename)
        if not os.path.exists(expected_path):
            logger.warning(f"Expected file not found: {expected_path}")
            # Try looking for any matching file with a similar name
            if media_type == "audio":
                # Look for audio files
                audio_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.endswith((".mp3", ".m4a", ".ogg"))]
                if audio_files:
                    # Sort by creation time, newest first
                    audio_files.sort(key=lambda x: os.path.getctime(os.path.join(DOWNLOAD_FOLDER, x)), reverse=True)
                    actual_filename = audio_files[0]
                    logger.info(f"Using alternative audio file found: {actual_filename}")
            else:
                # Look for video files
                video_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.endswith((".mp4", ".webm", ".mkv"))]
                if video_files:
                    # Sort by creation time, newest first
                    video_files.sort(key=lambda x: os.path.getctime(os.path.join(DOWNLOAD_FOLDER, x)), reverse=True)
                    actual_filename = video_files[0]
                    logger.info(f"Using alternative video file found: {actual_filename}")
        else:
            logger.info(f"Downloaded file found: {actual_filename}")
        
        # Make sure we have a clean, properly encoded URL
        safe_url = urllib.parse.quote(actual_filename)
        download_url = f"/static/downloads/{safe_url}"

    result = {
        "title": info.get("title"),
        "filename": actual_filename,
        "download_url": download_url,
        "ext": info.get("ext"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader"),
        "audio_note": ("merged mkv (bestvideo+bestaudio)" if use_ffmpeg else "progressive (no merge)"),
    }

    # Add warnings when FFmpeg is missing or chosen format isn't MP4
    if not use_ffmpeg:
        ext = (info.get("ext") or "").lower()
        acodec = (info.get("acodec") or "").lower()
        if acodec in ("opus", "vorbis"):
            result["warning"] = (
                "FFmpeg not detected. Downloaded a single-file format; audio codec may be Opus/Vorbis. "
                "Install FFmpeg to merge best video+audio into MKV."
            )

    return result


def extract_info_no_download(url: str) -> dict:
    """Extract video metadata and try to provide a preview URL without downloading."""
    ydl_opts = {
        "quiet": True,
        "noplaylist": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["web_embedded", "visionos", "android", "ios"]
            }
        },


    }

    _apply_cookies_if_present(ydl_opts)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as first_err:
        if "cookiefile" in ydl_opts:
            logger.warning(f"Extraction with cookies failed: {first_err}. Retrying without cookies using mobile client fallback...")
            ydl_opts.pop("cookiefile", None)
            ydl_opts["extractor_args"] = {
                "youtube": {
                    "player_client": ["web_embedded", "visionos", "android", "ios"]
                }
            }



            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        else:
            logger.error(f"Error extracting info: {str(first_err)}")
            raise


    # Determine preview URL and best available quality/format
    preview_url = None
    best_height = None
    best_ext = None
    if isinstance(info, dict):
        # Check for direct URL first
        preview_url = info.get("url")
        
        # If merged/requested formats provided, prefer mp4 progressive if present
        formats = info.get("requested_formats") or []
        if not preview_url and formats:
            # First try to get a video format with both audio and video
            for f in formats:
                if (f and f.get("url") and f.get("vcodec") != "none" and 
                    f.get("acodec") != "none"):
                    preview_url = f.get("url")
                    logger.info(f"Found combined a/v preview format: {f.get('format_id')}")
                    break
                    
            # If no combined format, get any format with video
            if not preview_url:
                for f in formats:
                    if f and f.get("url") and f.get("vcodec") != "none":
                        preview_url = f.get("url")
                        logger.info(f"Found video-only preview format: {f.get('format_id')}")
                        break
        
        # Fallback: scan all formats for a likely progressive mp4/webm
        if not preview_url:
            all_formats = info.get("formats") or []
            
            # First try formats with both video and audio
            for f in all_formats:
                if not f:
                    continue
                if (f.get("vcodec") != "none" and f.get("acodec") != "none" and
                    f.get("url")):
                    ext = (f.get("ext") or "").lower()
                    if ext in ("mp4", "webm"):
                        preview_url = f.get("url")
                        logger.info(f"Found fallback preview format: {f.get('format_id')}")
                        break
            
            # Last resort: any video format
            if not preview_url:
                for f in all_formats:
                    if not f:
                        continue
                    if f.get("vcodec") == "none":
                        continue
                    if f.get("url"):
                        preview_url = f.get("url")
                        logger.info(f"Found last-resort preview format: {f.get('format_id')}")
                        break

    # Independently compute highest available height across ALL video formats (even video-only)
    try:
        all_formats_full = info.get("formats") or []
        max_height = 0
        height_to_exts = {}
        for f in all_formats_full:
            if not f:
                continue
            if f.get("vcodec") == "none":
                continue
            h = f.get("height") or 0
            try:
                h = int(h)
            except Exception:
                h = 0
            if h <= 0:
                continue
            max_height = max(max_height, h)
            ext = (f.get("ext") or "").lower()
            height_to_exts.setdefault(h, set()).add(ext)

        if max_height > 0:
            exts_at = height_to_exts.get(max_height, set())
            best_ext = "mp4" if "mp4" in exts_at else (next(iter(exts_at)) if exts_at else None)
            best_height = max_height
    except Exception as _:
        pass

    # Map height to user-friendly label
    def _quality_label(height):
        if not height:
            return None
        if height >= 4320:
            return "8K"
        if height >= 2160:
            return "4K"
        if height >= 1440:
            return "2K"
        if height >= 1080:
            return "FHD"
        if height >= 720:
            return "HD"
        if height >= 480:
            return "SD"
        return f"{height}p"

    return {
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader"),
        "webpage_url": info.get("webpage_url"),
        "preview_url": preview_url,
        "best_ext": best_ext,
        "best_height": best_height,
        "best_quality_label": _quality_label(best_height),
    }


# ----------------------------
# Routes
# ----------------------------
@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html")

@app.route("/static/downloads/<path:filename>")
def download_file(filename):
    """Serve files with proper download headers."""
    # Decode the URL-encoded filename
    decoded_filename = urllib.parse.unquote(filename)
    
    # Create full path to the file
    file_path = os.path.join(DOWNLOAD_FOLDER, decoded_filename)
    
    # Check if file exists
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return "File not found", 404
        
    # Always force download with Content-Disposition header
    return send_from_directory(
        directory=DOWNLOAD_FOLDER,
        path=decoded_filename,
        as_attachment=True,
        download_name=decoded_filename
    )


@app.route("/api/download", methods=["POST"])
def download_video():
    """API endpoint to handle the download request."""
    data = request.get_json(force=True)
    url = data.get("url")
    format_type = data.get("format")  # e.g., "1080p", "720p", "320kbps"
    media_type = data.get("type")     # "video" or "audio"

    if not url:
        return jsonify({"error": "URL is required."}), 400

    try:
        result = download_with_yt_dlp(url, format_type, media_type)
        logger.info(f"Download successful: {result['filename']}")
        
        # Add Content-Disposition header suggestion to ensure browser offers download
        result['download_url'] = f"/static/downloads/{urllib.parse.quote(result['filename'])}?download=true"
        if result.get("audio_note") != "mp3" and media_type == "audio":
            result["warning"] = (
                "Downloaded using progressive format. Audio codec may not be MP3 because FFmpeg was not detected."
            )
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return jsonify({"error": f"Download failed: {str(e)}"}), 500


@app.route("/api/info", methods=["POST"])
def info_video():
    """API endpoint to fetch metadata/preview for a URL without downloading."""
    data = request.get_json(force=True)
    url = data.get("url")
    if not url:
        return jsonify({"error": "URL is required."}), 400
    try:
        result = extract_info_no_download(url)
        print(f"Result: {result}")
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Info fetch failed: {str(e)}"}), 500


# ----------------------------
# Entry point
# ----------------------------
if __name__ == "__main__":
    # List existing downloads
    try:
        download_files = os.listdir(DOWNLOAD_FOLDER)
        logger.info(f"Found {len(download_files)} existing downloads: {download_files[:5]}")
    except Exception as e:
        logger.error(f"Error listing download folder: {str(e)}")
    
    # Run Flask with full logging
    app.run(debug=True)
