import sys
import asyncio
import cv2
import time
import subprocess

sys.path.insert(0, ".")
from ai.utils.config import Config
from ai.live_dashcam.dashcam_detector import DashcamDetector
from app.services.youtube_resolver import resolve_youtube_stream, build_youtube_url

async def main():
    print("Starting test...", flush=True)
    config = Config("ai/config.yaml")
    print("Loading DashcamDetector (this may take 20-30s on CPU)...", flush=True)
    detector = DashcamDetector(config)
    
    youtube_id = "swJ1-ejSm1Q"
    video_url = build_youtube_url(youtube_id)
    print(f"Resolving YouTube URL: {video_url}")
    
    stream_url = await asyncio.to_thread(resolve_youtube_stream, video_url)
    print(f"Resolved Stream URL: {stream_url}")
    if not stream_url:
        print("Failed to resolve stream URL!")
        return
        
    is_hls = ".m3u8" in stream_url.lower()
    
    w, h = 960, 540
    yt_cmd = [
        "yt-dlp",
        "--no-warnings",
        "-q",
        "--extractor-args", "youtube:player_client=android",
        "-f", "best[height<=720]/best",
        "-o", "-",
        "--no-part",
        video_url,
    ]
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",
        "-vf", f"scale={w}:{h}",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-an",
        "-sn",
        "-"
    ]
    
    print(f"Launching yt-dlp piped to ffmpeg...", flush=True)
    yt_proc = subprocess.Popen(yt_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    proc = subprocess.Popen(ffmpeg_cmd, stdin=yt_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    yt_proc.stdout.close()
    
    await asyncio.sleep(0.5)
    if proc.poll() is not None:
        print(f"ffmpeg exited immediately. code={proc.poll()}, stderr={proc.stderr.read()}")
        return
        
    print("Reading frames...")
    frame_size = w * h * 3
    for i in range(3):
        try:
            print(f"Reading frame {i}...")
            raw = proc.stdout.read(frame_size)
            if len(raw) < frame_size:
                print("Short read!")
                break
            
            import numpy as np
            frame = np.frombuffer(raw, dtype=np.uint8).reshape((h, w, 3)).copy()
            print("Processing frame with DashcamDetector...")
            start = time.time()
            analysis = detector.detect(frame)
            detector.draw_detections(frame, analysis)
            elapsed = time.time() - start
            print(f"Frame {i} processed in {elapsed:.3f}s. Vehicles: {analysis.vehicle_count}")
        except Exception as e:
            print("Exception occurred:")
            import traceback
            traceback.print_exc()
            break
            
    proc.kill()
    try:
        yt_proc.kill()
    except Exception:
        pass

if __name__ == "__main__":
    asyncio.run(main())
