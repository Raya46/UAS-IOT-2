#!/usr/bin/env python3
"""Download free dashcam videos from Pexels for simulation.

Each video represents a different public transport route.
Pexels videos are free to use without attribution.
"""
import os
import sys
import urllib.request

VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "dashcam_videos")

# Pexels free dashcam / driving / traffic videos (direct download links)
# These are carefully selected for urban traffic scenes with vehicles
SOURCES = [
    {
        "filename": "route_bundaran_hi.mp4",
        "url": "https://videos.pexels.com/video-files/2053100/2053100-hd_1920_1080_30fps.mp4",
        "label": "Bundaran HI — Thamrin",
    },
    {
        "filename": "route_sudirman.mp4",
        "url": "https://videos.pexels.com/video-files/857032/857032-hd_1920_1080_25fps.mp4",
        "label": "Sudirman — Semanggi",
    },
    {
        "filename": "route_tol_cawang.mp4",
        "url": "https://videos.pexels.com/video-files/3048225/3048225-hd_1920_1080_24fps.mp4",
        "label": "Tol Cawang — Halim",
    },
    {
        "filename": "route_thamrin.mp4",
        "url": "https://videos.pexels.com/video-files/3121459/3121459-hd_1920_1080_24fps.mp4",
        "label": "Thamrin — Monas",
    },
    {
        "filename": "route_jagorawi.mp4",
        "url": "https://videos.pexels.com/video-files/2519660/2519660-hd_1920_1080_30fps.mp4",
        "label": "Jagorawi — Bogor",
    },
    {
        "filename": "route_jorr.mp4",
        "url": "https://videos.pexels.com/video-files/1321208/1321208-hd_1920_1080_25fps.mp4",
        "label": "JORR Lingkar Luar",
    },
]


def download_video(url: str, dest: str, label: str):
    if os.path.exists(dest):
        sz = os.path.getsize(dest)
        if sz > 100_000:  # >100KB = probably valid
            print(f"  ✓ {label} already downloaded ({sz / 1_000_000:.1f} MB)")
            return True

    print(f"  ↓ Downloading {label} ...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        with open(dest, "wb") as f:
            f.write(data)
        print(f"  ✓ {label} saved ({len(data) / 1_000_000:.1f} MB)")
        return True
    except Exception as exc:
        print(f"  ✗ {label} FAILED: {exc}")
        return False


def main():
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    print(f"Downloading dashcam videos to {VIDEOS_DIR}\n")

    success = 0
    for src in SOURCES:
        dest = os.path.join(VIDEOS_DIR, src["filename"])
        if download_video(src["url"], dest, src["label"]):
            success += 1

    print(f"\nDone: {success}/{len(SOURCES)} videos downloaded.")
    return 0 if success >= 3 else 1  # need at least 3 videos


if __name__ == "__main__":
    sys.exit(main())
