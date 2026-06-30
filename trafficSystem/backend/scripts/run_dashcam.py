#!/usr/bin/env python3
"""
Live Dashcam Detection - CLI Entry Point

Usage:
    python run_dashcam.py --source 0                    # Webcam
    python run_dashcam.py --source video.mp4             # Video file
    python run_dashcam.py --source rtsp://192.168.1.1    # RTSP stream
    python run_dashcam.py --source 0 --headless           # Headless mode (no GUI)
    python run_dashcam.py --source 0 --redis              # Publish to Redis
"""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

BACKEND_DIR = str(Path(__file__).parent.parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)  # noqa: E402

from ai.live_dashcam.dashcam_detector import DashcamDetector, SceneAnalysis  # noqa: E402
from ai.live_dashcam.scene_analyzer import TrafficStats  # noqa: E402
from ai.utils.config import Config  # noqa: E402


def parse_source(source_arg: str):
    if str(source_arg).isdigit():
        return int(source_arg)
    path = Path(source_arg)
    if not path.exists():
        with_mp4 = Path(str(source_arg) + ".mp4")
        if with_mp4.exists():
            return str(with_mp4)
    return source_arg


def resize_keep_aspect(frame: np.ndarray, target_width: int) -> np.ndarray:
    if not target_width or target_width <= 0:
        return frame
    h, w = frame.shape[:2]
    if w <= target_width:
        return frame
    scale = target_width / float(w)
    return cv2.resize(frame, (target_width, int(h * scale)))


def main():
    parser = argparse.ArgumentParser(description="Live Dashcam Detection")
    parser.add_argument(
        "--source", default=None, help="Camera index, RTSP URL, or video path"
    )
    parser.add_argument(
        "--config", default="ai/config.yaml", help="Path to config.yaml"
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run without GUI window"
    )
    parser.add_argument(
        "--max-frames", type=int, default=None, help="Max frames to process"
    )
    parser.add_argument(
        "--process-every-n", type=int, default=2, help="Process every Nth frame"
    )
    parser.add_argument(
        "--resize", type=int, default=960, help="Resize width (0 = no resize)"
    )
    parser.add_argument(
        "--redis", action="store_true", help="Publish detections to Redis"
    )
    parser.add_argument("--redis-host", default="localhost", help="Redis host")
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis port")
    parser.add_argument("--redis-topic", default="traffic.dashcam", help="Redis topic")
    args = parser.parse_args()

    config = None
    if Path(args.config).exists():
        config = Config(args.config)
    else:
        print(f"[INFO] Config {args.config} not found, using defaults")

    detector = DashcamDetector(config)
    traffic_stats = TrafficStats()
    redis_client = None

    if args.redis:
        try:
            import redis as rmod

            redis_client = rmod.Redis(
                host=args.redis_host, port=args.redis_port, decode_responses=True
            )
            redis_client.ping()
            print(f"[INFO] Connected to Redis at {args.redis_host}:{args.redis_port}")
        except Exception as exc:
            print(f"[WARN] Redis connection failed: {exc}")
            redis_client = None

    source = args.source if args.source is not None else 0
    source_for_cv = parse_source(str(source))
    source_label = str(source)

    print(f"[INFO] Opening source: {source_label}")
    cap = cv2.VideoCapture(source_for_cv)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open source: {source_label}")
        sys.exit(1)

    is_rtsp = isinstance(source_for_cv, str) and (
        source_for_cv.startswith("rtsp://") or source_for_cv.startswith("http://")
    )

    frame_count = 0
    last_time = time.time()
    imshow_warning = False

    window_name = "Live Dashcam Detection"
    if not args.headless:
        cv2.namedWindow(window_name)

    print("[INFO] Press 'q' to quit | 's' to save snapshot")

    while True:
        ok, frame = cap.read()
        if not ok:
            if is_rtsp:
                print("[WARN] Stream disconnected. Reconnecting...")
                time.sleep(2)
                cap = cv2.VideoCapture(source_for_cv)
                continue
            else:
                print("[INFO] End of stream")
                break

        frame_count += 1
        if args.max_frames and frame_count > args.max_frames:
            print(f"[INFO] Max frames {args.max_frames} reached")
            break

        if args.resize:
            frame = resize_keep_aspect(frame, args.resize)

        now = time.time()
        fps = 1.0 / (now - last_time) if (now - last_time) > 0 else 0.0
        last_time = now

        # Run detection only on every Nth frame, but still display all frames for smooth video
        run_detection = True
        if args.process_every_n > 1 and (frame_count - 1) % args.process_every_n != 0:
            run_detection = False

        if run_detection:
            analysis = detector.detect(frame)
            traffic_stats.update(
                {
                    "vehicle_count": analysis.vehicle_count,
                    "pedestrian_count": analysis.pedestrian_count,
                }
            )

            detector.draw_detections(frame, analysis)
            detector.draw_scene_panel(frame, analysis, fps, source_label)

            if redis_client and analysis.total_objects > 0:
                payload = analysis.to_dict()
                payload["timestamp"] = time.time()
                payload["source"] = source_label
                payload["frame"] = frame_count
                try:
                    redis_client.publish(args.redis_topic, json.dumps(payload))
                except Exception:
                    pass
        else:
            # Show a minimal panel even on skipped frames so FPS counter updates
            empty = SceneAnalysis()
            detector.draw_scene_panel(frame, empty, fps, source_label)

        if not args.headless:
            try:
                cv2.imshow(window_name, frame)
                key = cv2.waitKey(1) & 0xFF
            except Exception as exc:
                if not imshow_warning:
                    print(f"[WARN] GUI failed: {exc}. Switching to headless.")
                    imshow_warning = True
                key = 0xFF

            if key == ord("q"):
                print("[INFO] Quit requested")
                break
            elif key == ord("s"):
                snapshot_path = f"outputs/dashcam_snapshot_{frame_count}.jpg"
                cv2.imwrite(snapshot_path, frame)
                print(f"[INFO] Snapshot saved: {snapshot_path}")
        else:
            if frame_count % 30 == 0:
                print(f"[INFO] Frame {frame_count} | FPS={fps:.1f}")

    cap.release()
    if not args.headless:
        cv2.destroyAllWindows()
    print(f"[INFO] Processed {frame_count} frames. Done.")


if __name__ == "__main__":
    main()
