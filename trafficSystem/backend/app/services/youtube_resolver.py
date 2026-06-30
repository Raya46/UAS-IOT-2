import json
import subprocess
import re
from typing import Optional


_YT_DLP_CACHE: dict[str, str] = {}


def resolve_youtube_stream(youtube_url: str) -> Optional[str]:
    if youtube_url in _YT_DLP_CACHE:
        return _YT_DLP_CACHE[youtube_url]

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--no-warnings",
                "-g",
                youtube_url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            url = result.stdout.strip().split("\n")[0]
            if url:
                _YT_DLP_CACHE[youtube_url] = url
                return url
    except subprocess.TimeoutExpired:
        print(f"[YOUTUBE] yt-dlp timeout for {youtube_url}")
    except Exception as e:
        print(f"[YOUTUBE] resolve error: {e}")

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--no-warnings",
                "-J",
                youtube_url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            formats = info.get("formats", [])
            for fmt in formats:
                url = fmt.get("url", "")
                protocol = fmt.get("protocol", "")
                if url and protocol in ("https", "http", "m3u8", "m3u8_native"):
                    _YT_DLP_CACHE[youtube_url] = url
                    return url
    except Exception as e:
        print(f"[YOUTUBE] format fallback error: {e}")

    return None


def extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/live/)([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def build_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
