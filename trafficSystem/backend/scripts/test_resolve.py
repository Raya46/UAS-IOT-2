import subprocess
import time

def test():
    video_id = "swJ1-ejSm1Q"
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"Streaming via yt-dlp piped to ffmpeg: {youtube_url}")
    
    # Launch yt-dlp piped to ffmpeg
    yt_cmd = [
        "yt-dlp",
        "-q",
        "--no-warnings",
        "--extractor-args", "youtube:player_client=android",
        "-f", "best[height<=720]/best",
        "-o", "-",
        youtube_url
    ]
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",
        "-vf", "scale=960:540",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-an",
        "-sn",
        "-"
    ]
    
    try:
        yt_proc = subprocess.Popen(yt_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=yt_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        
        # Close our reference to yt_proc.stdout so it can receive SIGPIPE if ffmpeg exits
        yt_proc.stdout.close()
        
        w, h = 960, 540
        frame_size = w * h * 3
        
        print("Reading frame from pipe...")
        start = time.time()
        # Read one frame
        raw = ffmpeg_proc.stdout.read(frame_size)
        elapsed = time.time() - start
        
        if len(raw) == frame_size:
            print(f"SUCCESS: Read frame of size {len(raw)} bytes in {elapsed:.2f} seconds")
        else:
            print(f"FAIL: Read only {len(raw)} bytes instead of {frame_size} in {elapsed:.2f} seconds")
            
        # Clean up
        yt_proc.kill()
        ffmpeg_proc.kill()
        
    except Exception as e:
        print(f"FAIL: exception: {e}")

if __name__ == "__main__":
    test()
