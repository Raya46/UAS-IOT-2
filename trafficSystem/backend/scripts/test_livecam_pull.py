import sys
import asyncio
import cv2
import time
import subprocess
from datetime import datetime

sys.path.insert(0, ".")
from ai.utils.config import Config
from app.livecam_session import LiveCamSession

def _resolve_cctv_stream_url(url: str) -> str:
    if "/embed.html" not in url:
        return url
    index_url = url.replace("/embed.html", "/index.m3u8").replace(
        "/embed", "/index.m3u8"
    )
    return index_url

async def main():
    config = Config("ai/config.yaml")
    session = LiveCamSession("test_session")
    session.source_label = "bendungan_hilir_1"  # Set to CCTV profile
    
    raw_url = "https://cctv.balitower.co.id/Bendungan-Hilir-003-700014_1/embed.html"
    stream_url = _resolve_cctv_stream_url(raw_url)
    print(f"Resolved Stream URL: {stream_url}")
    
    is_hls = ".m3u8" in stream_url.lower()
    
    # Run stream pull logic
    _ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    _ref = "Referer: https://cctv.balitower.co.id/\r\n"
    
    w, h = 960, 540
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-user_agent",
        _ua,
        "-headers",
        _ref,
        "-probesize",
        "150000",
        "-analyzeduration",
        "150000",
    ]
    if is_hls:
        cmd += ["-re"]
    else:
        cmd += ["-fflags", "nobuffer", "-flags", "low_delay"]
    cmd += [
        "-i",
        stream_url,
        "-vf",
        f"scale={w}:{h}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-an",
        "-sn",
        "-",
    ]
    
    print(f"Launching ffmpeg: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    await asyncio.sleep(0.5)
    if proc.poll() is not None:
        print(f"ffmpeg exited immediately. code={proc.poll()}, stderr={proc.stderr.read()}")
        return
        
    print("Reading frames...")
    frame_size = w * h * 3
    for i in range(5):
        try:
            print(f"Reading frame {i}...")
            raw = proc.stdout.read(frame_size)
            if len(raw) < frame_size:
                print("Short read!")
                break
            
            import numpy as np
            frame = np.frombuffer(raw, dtype=np.uint8).reshape((h, w, 3)).copy()
            print("Processing frame...")
            start = time.time()
            result = session.process_raw_frame(frame)
            elapsed = time.time() - start
            print(f"Frame {i} processed in {elapsed:.3f}s. Result keys: {list(result.keys())}")
            if "error" in result:
                print(f"Error: {result['error']}")
        except Exception as e:
            print("Exception occurred:")
            import traceback
            traceback.print_exc()
            break
            
    proc.kill()

if __name__ == "__main__":
    asyncio.run(main())
