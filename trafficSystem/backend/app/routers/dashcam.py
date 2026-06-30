import asyncio
import json
import os
import re
import subprocess
import uuid
from typing import Dict, List, Optional
from urllib.parse import quote

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.youtube_resolver import (
    resolve_youtube_stream,
    extract_video_id,
    build_youtube_url,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Local dashcam video sources for simulation
# ---------------------------------------------------------------------------

_VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "dashcam_videos")
_DASHCAM_EVIDENCE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "outputs", "dashcam_evidence"
)
_DASHCAM_EVIDENCE_IMAGES_DIR = os.path.join(_DASHCAM_EVIDENCE_DIR, "images")
_DASHCAM_EVIDENCE_PLATES_DIR = os.path.join(_DASHCAM_EVIDENCE_DIR, "plates")



class DashcamSourceResponse(BaseModel):
    id: str
    name: str
    route: str
    description: str
    color: str
    video_file: str
    video_url: str
    status: str



_DASHCAM_SOURCE_METADATA = {
    "angkot-parkir-sembarangan.mp4": {

        "id": "angkot-parkir",
        "name": "Angkot JakLingko 01",
        "route": "Jalan Raya Kota",
        "description": "Angkot parkir sembarangan",
        "color": "#dc2626",
    },
    "Bus Prima Jasa dan Toyota Camry, menyalip dari bahu jalan dan memaksa masuk.Entrance Rest A.mp4": {
        "id": "bus-menyalip",
        "name": "Bus Prima Jasa",
        "route": "Entrance Rest Area",
        "description": "Bus Prima Jasa dan Toyota Camry menyalip dari bahu jalan",
        "color": "#2563eb",
    },
    "mobil-putih-menerobos-lampu-merah-dari-arah-depan.mp4": {
        "id": "mobil-lampu-merah",
        "name": "TransJakarta Mikrotrans 03",
        "route": "Persimpangan Lampu Merah",
        "description": "Mobil putih menerobos lampu merah dari arah depan",
        "color": "#059669",
    },
    "mobil-yang-parkir-pada-kanan-kiri-ruas-jalan-tertib.mp4": {
        "id": "motor-putar-arah",
        "name": "TransJakarta Patrol 04",
        "route": "Ruas Jalan Kota",
        "description": "Motor putar arah sembarangan",
        "color": "#d97706",
    },
    "motor-potong-lajur-mobil-dari-kanan-ke-kiri.mp4": {
        "id": "motor-potong-lajur",
        "name": "TransJakarta Patrol 05",
        "route": "Jalan Raya",
        "description": "Motor potong lajur mobil dari kanan ke kiri",
        "color": "#7c3aed",
    },
    "taksi-berputar-arah-di-lampu-merah-yang-dilarang.mp4": {
        "id": "taksi-putar-arah",
        "name": "Taksi Bluebird 06",
        "route": "Persimpangan Lampu Merah",
        "description": "Taksi Bluebird berputar arah di lajur lampu merah yang dilarang",
        "color": "#0891b2",
    },
}

_DASHCAM_PLATE_CROP_RATIOS = {
    "angkot-parkir-sembarangan.mp4": (0.20, 0.45, 0.88, 0.95),
    "Bus Prima Jasa dan Toyota Camry, menyalip dari bahu jalan dan memaksa masuk.Entrance Rest A.mp4": (0.10, 0.35, 0.95, 0.95),
    "mobil-yang-parkir-pada-kanan-kiri-ruas-jalan-tertib.mp4": (0.15, 0.45, 0.90, 0.98),
    "taksi-berputar-arah-di-lampu-merah-yang-dilarang.mp4": (0.25, 0.45, 0.95, 0.98),
}


def _slugify_video_id(filename: str) -> str:
    stem, _ = os.path.splitext(filename)
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug or uuid.uuid5(uuid.NAMESPACE_URL, filename).hex[:12]


def _title_from_filename(filename: str) -> str:
    stem, _ = os.path.splitext(filename)
    return stem.replace("-", " ").replace("_", " ").title()


def _build_dashcam_sources() -> List[DashcamSourceResponse]:
    if not os.path.isdir(_VIDEOS_DIR):
        return []

    sources: List[DashcamSourceResponse] = []
    for filename in sorted(os.listdir(_VIDEOS_DIR), key=str.lower):
        if not filename.lower().endswith(".mp4"):
            continue

        video_path = os.path.join(_VIDEOS_DIR, filename)
        metadata = _DASHCAM_SOURCE_METADATA.get(filename, {})
        sources.append(
            DashcamSourceResponse(
                id=metadata.get("id", _slugify_video_id(filename)),
                name=metadata.get("name", _title_from_filename(filename)),
                route=metadata.get("route", "Dashcam Video"),
                description=metadata.get("description", _title_from_filename(filename)),
                color=metadata.get("color", "#2563eb"),
                video_file=filename,
                video_url=f"/api/dashcam/videos/{quote(filename, safe='')}",
                status="active" if os.path.isfile(video_path) else "unavailable",
            )
        )

    return sources


def _source_id_from_filename(filename: str) -> str:
    base = os.path.splitext(filename)[0].lower()
    return "".join(ch if ch.isalnum() else "-" for ch in base).strip("-")


@router.get("/api/dashcam/sources", response_model=List[DashcamSourceResponse])
async def get_dashcam_sources():

    """Return available local dashcam video sources."""
    return _build_dashcam_sources()


@router.get("/api/dashcam/evidence/{kind}/{filename}")
async def get_dashcam_evidence(kind: str, filename: str):
    if kind not in {"images", "plates"}:
        raise HTTPException(status_code=404, detail="Evidence type not found")

    directory = (
        _DASHCAM_EVIDENCE_IMAGES_DIR if kind == "images" else _DASHCAM_EVIDENCE_PLATES_DIR
    )
    safe_name = os.path.basename(filename)
    filepath = os.path.join(directory, safe_name)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Evidence file not found")
    return FileResponse(filepath)


def _dashcam_evidence_url(kind: str, filename: str) -> str:
    return f"/api/dashcam/evidence/{kind}/{filename}"


def _bbox_from_ratio(frame: np.ndarray, ratios: tuple[float, float, float, float]) -> list[int]:
    h, w = frame.shape[:2]
    x1 = max(0, min(w - 1, int(w * ratios[0])))
    y1 = max(0, min(h - 1, int(h * ratios[1])))
    x2 = max(x1 + 1, min(w, int(w * ratios[2])))
    y2 = max(y1 + 1, min(h, int(h * ratios[3])))
    return [x1, y1, x2, y2]


def _crop_by_ratio(frame: np.ndarray, ratios: tuple[float, float, float, float]) -> tuple[Optional[np.ndarray], list[int]]:
    x1, y1, x2, y2 = _bbox_from_ratio(frame, ratios)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None, [x1, y1, x2, y2]
    return crop, [x1, y1, x2, y2]


def _attach_dashcam_evidence(frame: np.ndarray, video_path: str, violations: list) -> None:
    if frame is None or frame.size == 0 or not violations:
        return

    os.makedirs(_DASHCAM_EVIDENCE_IMAGES_DIR, exist_ok=True)
    os.makedirs(_DASHCAM_EVIDENCE_PLATES_DIR, exist_ok=True)

    filename = os.path.basename(video_path)
    crop_ratio = _DASHCAM_PLATE_CROP_RATIOS.get(filename)
    frame_h, frame_w = frame.shape[:2]

    for violation in violations:
        event_id = getattr(violation, "event_id", uuid.uuid4().hex)
        image_name = f"{event_id}.jpg"
        image_path = os.path.join(_DASHCAM_EVIDENCE_IMAGES_DIR, image_name)
        if cv2.imwrite(image_path, frame):
            violation.evidence_image = _dashcam_evidence_url("images", image_name)
            violation.evidence_size = [frame_w, frame_h]

        if crop_ratio is None:
            continue

        crop, bbox = _crop_by_ratio(frame, crop_ratio)
        if crop is None:
            continue

        plate_name = f"{event_id}_plate.jpg"
        plate_path = os.path.join(_DASHCAM_EVIDENCE_PLATES_DIR, plate_name)
        if cv2.imwrite(plate_path, crop):
            violation.plate_crop = _dashcam_evidence_url("plates", plate_name)
            violation.plate_bbox = bbox



@router.get("/api/dashcam/videos/{filename:path}")
async def get_dashcam_video(filename: str):
    """Serve a video from backend/data/dashcam_videos."""
    safe_filename = os.path.basename(filename)
    video_path = os.path.abspath(os.path.join(_VIDEOS_DIR, safe_filename))
    upload_root = os.path.abspath(_VIDEOS_DIR)
    if not video_path.startswith(upload_root + os.sep) or not os.path.isfile(video_path):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(video_path, media_type="video/mp4", filename=safe_filename)

_DashcamDetector = None


def _get_dashcam_detector():
    global _DashcamDetector
    if _DashcamDetector is None:
        from ai.live_dashcam.dashcam_detector import DashcamDetector

        _DashcamDetector = DashcamDetector
    return _DashcamDetector


active_sessions: Dict[str, dict] = {}


@router.websocket("/ws/dashcam")
async def dashcam_websocket(websocket: WebSocket):
    await websocket.accept()
    session_id = str(uuid.uuid4())[:8]
    detector = None
    stream_task = None

    try:
        detector_cls = _get_dashcam_detector()
        detector = detector_cls()

        await websocket.send_json(
            {
                "type": "connected",
                "session_id": session_id,
                "message": "Send config with video_file, esp32_url, or youtube_id.",
            }
        )

        data = await websocket.receive_json()

        # --- Mode 1: Local video file (preferred) ---
        video_file = data.get("video_file")
        if video_file:
            video_path = os.path.join(_VIDEOS_DIR, os.path.basename(video_file))
            if not os.path.isfile(video_path):
                await websocket.send_json(
                    {"type": "error", "message": f"Video file not found: {video_file}"}
                )
                return

            await websocket.send_json({"type": "resolved", "video_file": video_file})
            active_sessions[session_id] = {
                "video_file": video_file,
                "detector": detector,
            }

            stream_task = asyncio.create_task(
                _local_video_loop(websocket, detector, video_path, session_id)
            )

        # --- Mode 2: ESP32 camera stream ---
        elif data.get("esp32_url"):
            esp32_url = data["esp32_url"]
            await websocket.send_json({"type": "resolved", "esp32_url": esp32_url})
            active_sessions[session_id] = {
                "esp32_url": esp32_url,
                "detector": detector,
            }
            stream_task = asyncio.create_task(
                _local_video_loop(
                    websocket, detector, esp32_url, session_id,
                    is_live_stream=True,
                )
            )

        else:
            # --- Mode 2: YouTube stream (legacy) ---
            youtube_id = data.get("youtube_id") or extract_video_id(
                data.get("youtube_url", "")
            )
            if not youtube_id:
                await websocket.send_json(
                    {"type": "error", "message": "No video_file or youtube_id provided"}
                )
                return

            video_url = build_youtube_url(youtube_id)
            await websocket.send_json({"type": "resolving", "youtube_id": youtube_id})

            resolved = await asyncio.to_thread(resolve_youtube_stream, video_url)
            if not resolved:
                await websocket.send_json(
                    {"type": "error", "message": "Could not resolve YouTube stream"}
                )
                return

            await websocket.send_json({"type": "resolved", "stream_url": resolved})
            active_sessions[session_id] = {
                "youtube_id": youtube_id,
                "youtube_url": video_url,
                "detector": detector,
            }

            stream_task = asyncio.create_task(
                _dashcam_stream_loop(websocket, detector, resolved, session_id)
            )

        # Listen for stop command while streaming
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=1.0)
                if msg.get("type") == "stop":
                    break
            except asyncio.TimeoutError:
                if stream_task.done():
                    break
                continue

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[DASHCAM] Session error {session_id}: {exc}")
        import traceback

        traceback.print_exc()
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        if stream_task is not None:
            stream_task.cancel()
            try:
                await stream_task
            except (asyncio.CancelledError, Exception):
                pass
        active_sessions.pop(session_id, None)
        print(f"[DASHCAM] Session {session_id} ended")


async def _local_video_loop(
    websocket: WebSocket, detector, video_path: str, session_id: str,
    *, is_live_stream: bool = False,
):
    """
    Smooth dashcam streaming with YOLO overlay.

    3-thread architecture for zero-stutter playback:
      Thread 1 (frame_reader):  cap.read → resize → draw cached → encode → queue
      Thread 2 (yolo_worker):   picks frames → runs YOLO → updates cached_analysis
      Async consumer:           queue.get → websocket.send

    YOLO never blocks frame production — the reader always uses the latest
    cached analysis result, so video plays at constant FPS.
    """
    import threading
    import queue
    import time
    import copy

    from ai.live_dashcam.violation_detector import DashcamViolationDetector

    DISPLAY_W, DISPLAY_H = 640, 360
    TARGET_FPS = 24
    DETECT_EVERY = 2
    JPEG_QUALITY = 70
    QUEUE_SIZE = 6

    frame_queue: queue.Queue = queue.Queue(maxsize=QUEUE_SIZE)
    stop_event = threading.Event()
    violation_detector = DashcamViolationDetector()

    # Shared state between threads (protected by lock)
    shared_lock = threading.Lock()
    shared_analysis = {"result": None, "metadata": None, "violations": [], "vio_time": 0}

    # Channel for submitting frames to YOLO worker
    detect_queue: queue.Queue = queue.Queue(maxsize=1)

    MAX_RECONNECT = 10
    label = "ESP32 live stream" if is_live_stream else video_path
    print(f"[DASHCAM] Starting 3-thread pipeline: {label} (session {session_id})")

    # ── Thread 2: YOLO Detection Worker ──
    def _yolo_worker():
        """Runs YOLO on submitted frames. Never blocks the frame reader."""
        while not stop_event.is_set():
            try:
                raw_frame, frame_count, elapsed, video_time, fps = detect_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                analysis = detector.detect(raw_frame)
            except Exception:
                continue

            # Build metadata
            vc = analysis.vehicle_count
            level = "LOW"
            if vc > 8: level = "MEDIUM"
            if vc > 12: level = "HIGH"
            if vc > 16: level = "SEVERE"

            try:
                new_violations = violation_detector.analyze(
                    analysis,
                    video_path,
                    video_time_seconds=video_time,
                )
            except Exception:
                new_violations = []

            if new_violations:
                _attach_dashcam_evidence(raw_frame, video_path, new_violations)
                print(f"[DASHCAM] {session_id}: {len(new_violations)} violations: {[v.violation_type for v in new_violations]}")

            metadata = {
                "type": "frame_result",
                "frame_count": frame_count,
                "fps": fps,
                "session_duration": round(elapsed),
                "video_time_seconds": round(video_time, 2),
                "vehicles": [
                    {
                        "class_name": v.class_name,
                        "confidence": round(v.confidence, 2),
                        "bbox": v.bbox,
                        "lane": v.lane,
                        "plate_number": getattr(v, "plate_number", None),
                        "track_id": getattr(v, "track_id", None),
                    }
                    for v in analysis.vehicles
                ],
                "pedestrians": [
                    {
                        "class_name": p.class_name,
                        "confidence": round(p.confidence, 2),
                        "bbox": p.bbox,
                        "track_id": getattr(p, "track_id", None),
                    }
                    for p in analysis.pedestrians
                ],
                "bicycles": [
                    {
                        "class_name": b.class_name,
                        "confidence": round(b.confidence, 2),
                        "bbox": b.bbox,
                        "track_id": getattr(b, "track_id", None),
                    }
                    for b in analysis.bicycles
                ],
                "traffic_lights": [
                    {
                        "class_name": tl.class_name,
                        "confidence": round(tl.confidence, 2),
                        "bbox": tl.bbox,
                    }
                    for tl in analysis.traffic_lights
                ],
                "traffic_signs": [
                    {
                        "class_name": s.class_name,
                        "confidence": round(s.confidence, 2),
                        "bbox": s.bbox,
                    }
                    for s in analysis.traffic_signs
                ],
                "traffic_light_color": analysis.traffic_light_state.color,
                "left_lane": getattr(analysis, "left_lane", []),
                "right_lane": getattr(analysis, "right_lane", []),
                "violations": [v.to_dict() for v in new_violations],
                "traffic": {
                    "vehicle_count": vc,
                    "pedestrian_count": analysis.pedestrian_count,
                    "stopped_count": 0,
                    "level": level,
                },
            }

            with shared_lock:
                shared_analysis["result"] = analysis
                shared_analysis["metadata"] = metadata
                if new_violations:
                    shared_analysis["violations"] = [v.to_dict() for v in new_violations]
                    shared_analysis["vio_time"] = time.monotonic()

    def _draw_violations(frame, violations, vio_time):
        """Draw violation banners on the frame."""
        age = time.monotonic() - vio_time
        if age > 8.0 or not violations:
            return
        # Fade alpha
        alpha = max(0.3, 1.0 - age / 8.0)
        h, w = frame.shape[:2]
        y_offset = 8
        for v in violations[:3]:  # Max 3 banners
            text = f"VIOLATION: {v.get('description', v.get('violation_type', ''))}"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.45
            thickness = 1
            (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
            # Red banner background
            bh = th + 12
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, y_offset), (w, y_offset + bh), (0, 0, 200), -1)
            cv2.addWeighted(overlay, alpha * 0.85, frame, 1 - alpha * 0.85, 0, frame)
            # White text
            cv2.putText(frame, text, (8, y_offset + th + 6), font, font_scale,
                        (255, 255, 255), thickness, cv2.LINE_AA)
            y_offset += bh + 2

    # ── Thread 1: Frame Reader (constant FPS, never blocks) ──
    def _open_capture(url):
        """Try OpenCV, fall back to MJPEG HTTP reader for ESP32 streams."""
        cap = cv2.VideoCapture(url)
        if cap.isOpened():
            return cap
        cap.release()
        if is_live_stream:
            from app.routers.livecam import MjpegHttpReader
            print(f"[DASHCAM] OpenCV failed, trying MJPEG HTTP reader")
            return MjpegHttpReader(url)
        return cv2.VideoCapture(url)

    def _frame_reader():
        """Reads video, draws cached overlays, encodes, enqueues. Never waits for YOLO."""
        frame_count = 0
        t_start = time.monotonic()
        reconnect_count = 0

        while not stop_event.is_set():
            cap = _open_capture(video_path)
            if not cap.isOpened():
                if is_live_stream and reconnect_count < MAX_RECONNECT:
                    reconnect_count += 1
                    print(f"[DASHCAM] ESP32 connect failed, retry {reconnect_count}/{MAX_RECONNECT}")
                    time.sleep(2)
                    continue
                frame_queue.put({"type": "error", "message": f"Cannot open: {video_path}"})
                return

            reconnect_count = 0
            source_fps = cap.get(cv2.CAP_PROP_FPS) or 25
            skip = 1 if is_live_stream else max(1, int(source_fps / TARGET_FPS))
            frame_interval = 1.0 / TARGET_FPS
            frame_idx = 0

            while not stop_event.is_set():
                t_frame = time.monotonic()
                ok, raw = cap.read()
                if not ok:
                    break

                frame_idx += 1
                if frame_idx % skip != 0:
                    continue

                frame_count += 1
                elapsed = time.monotonic() - t_start
                video_time = elapsed if is_live_stream else max(0.0, cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0)
                fps = round(frame_count / max(0.1, elapsed), 1)

                # Submit frame for YOLO (non-blocking, drop if busy)
                if frame_count % DETECT_EVERY == 1:
                    try:
                        detect_queue.put_nowait((raw.copy(), frame_count, elapsed, video_time, fps))
                    except queue.Full:
                        pass  # YOLO still busy, skip this detection

                # Resize for display
                display = cv2.resize(raw, (DISPLAY_W, DISPLAY_H))

                # Draw cached overlays (from latest YOLO result)
                pending_metadata = None
                current_violations = []
                current_vio_time = 0
                with shared_lock:
                    cached = shared_analysis["result"]
                    pending_metadata = shared_analysis["metadata"]
                    shared_analysis["metadata"] = None  # Consume once
                    current_violations = shared_analysis["violations"]
                    current_vio_time = shared_analysis["vio_time"]

                if cached is not None:
                    try:
                        detector.draw_detections(display, cached)
                    except Exception:
                        pass

                # Draw violation banners on frame
                if current_violations:
                    try:
                        _draw_violations(display, current_violations, current_vio_time)
                    except Exception:
                        pass

                # Encode JPEG
                _, jpeg = cv2.imencode(".jpg", display, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])

                # Enqueue
                item = {"jpeg": jpeg.tobytes()}
                if pending_metadata:
                    item["metadata"] = pending_metadata

                try:
                    frame_queue.put_nowait(item)
                except queue.Full:
                    try:
                        frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        frame_queue.put_nowait(item)
                    except queue.Full:
                        pass

                # Pace to target FPS
                dt = time.monotonic() - t_frame
                sleep_t = frame_interval - dt
                if sleep_t > 0.002:
                    time.sleep(sleep_t)

            cap.release()
            if stop_event.is_set():
                break

            if is_live_stream:
                reconnect_count += 1
                if reconnect_count > MAX_RECONNECT:
                    print(f"[DASHCAM] ESP32 max reconnects exceeded (session {session_id})")
                    break
                print(f"[DASHCAM] ESP32 stream dropped, reconnecting {reconnect_count}/{MAX_RECONNECT} (session {session_id})")
                time.sleep(2)
            else:
                print(f"[DASHCAM] Video ended, looping (session {session_id})")

        frame_queue.put(None)

    # Start worker threads
    yolo_thread = threading.Thread(target=_yolo_worker, daemon=True, name="yolo-worker")
    reader_thread = threading.Thread(target=_frame_reader, daemon=True, name="frame-reader")
    yolo_thread.start()
    reader_thread.start()

    # ── Async Consumer: send frames via WebSocket ──
    try:
        while True:
            try:
                item = await asyncio.to_thread(frame_queue.get, True, 2.0)
            except Exception:
                if stop_event.is_set():
                    break
                continue

            if item is None:
                break

            if "type" in item and item.get("type") == "error":
                await websocket.send_json(item)
                break

            await websocket.send_bytes(item["jpeg"])

            if "metadata" in item:
                await websocket.send_json(item["metadata"])

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        print(f"[DASHCAM] Pipeline error {session_id}: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        stop_event.set()
        reader_thread.join(timeout=3)
        yolo_thread.join(timeout=3)


async def _dashcam_stream_loop(
    websocket: WebSocket, detector, stream_url: str, session_id: str
):
    """Stream loop that uses yt-dlp pipe for YouTube and direct ffmpeg for others."""
    yt_proc = None
    ffmpeg_proc = None
    cap = None
    width, height = 960, 540
    frame_count = 0
    start_time = asyncio.get_event_loop().time()
    reconnect_attempts = 0
    max_reconnect = 5

    # Determine if this is a YouTube stream (resolved HLS from googlevideo)
    youtube_url = active_sessions.get(session_id, {}).get("youtube_url")
    is_youtube = youtube_url is not None

    try:
        import shutil

        use_ffmpeg = shutil.which("ffmpeg") is not None

        if use_ffmpeg:
            if is_youtube:
                yt_proc, ffmpeg_proc = await asyncio.to_thread(
                    _launch_ytdlp_ffmpeg_pipeline, youtube_url, width, height
                )
            else:
                ffmpeg_proc = await asyncio.to_thread(
                    _launch_ffmpeg_direct, stream_url, width, height
                )

            await asyncio.sleep(1.0 if is_youtube else 0.5)
            if ffmpeg_proc and ffmpeg_proc.poll() is not None:
                print(
                    "[DASHCAM] ffmpeg process exited immediately. Falling back to OpenCV."
                )
                _kill_procs(yt_proc, ffmpeg_proc)
                yt_proc = ffmpeg_proc = None

        if ffmpeg_proc is None:
            print("[DASHCAM] Falling back to cv2.VideoCapture")
            cap = cv2.VideoCapture(stream_url)

        while True:
            frame = None

            if ffmpeg_proc is not None:
                if ffmpeg_proc.poll() is not None:
                    if reconnect_attempts < max_reconnect:
                        reconnect_attempts += 1
                        print(
                            f"[DASHCAM] Reconnecting ({reconnect_attempts}/{max_reconnect})..."
                        )
                        _kill_procs(yt_proc, ffmpeg_proc)
                        yt_proc = ffmpeg_proc = None
                        await asyncio.sleep(2)
                        if is_youtube:
                            yt_proc, ffmpeg_proc = await asyncio.to_thread(
                                _launch_ytdlp_ffmpeg_pipeline,
                                youtube_url,
                                width,
                                height,
                            )
                        else:
                            ffmpeg_proc = await asyncio.to_thread(
                                _launch_ffmpeg_direct, stream_url, width, height
                            )
                        if ffmpeg_proc:
                            await asyncio.sleep(1.0 if is_youtube else 0.5)
                            if ffmpeg_proc.poll() is not None:
                                _kill_procs(yt_proc, ffmpeg_proc)
                                yt_proc = ffmpeg_proc = None
                            else:
                                continue
                    await websocket.send_json(
                        {"type": "error", "message": "Stream ended"}
                    )
                    break

                frame_size = width * height * 3
                try:
                    raw = await asyncio.wait_for(
                        asyncio.to_thread(ffmpeg_proc.stdout.read, frame_size),
                        timeout=20.0,
                    )
                except asyncio.TimeoutError:
                    print("[DASHCAM] ffmpeg frame read timed out. Unblocking...")
                    _kill_procs(yt_proc, ffmpeg_proc)
                    yt_proc = ffmpeg_proc = None
                    if reconnect_attempts < max_reconnect:
                        reconnect_attempts += 1
                        await asyncio.sleep(2)
                        if is_youtube:
                            yt_proc, ffmpeg_proc = await asyncio.to_thread(
                                _launch_ytdlp_ffmpeg_pipeline,
                                youtube_url,
                                width,
                                height,
                            )
                        else:
                            ffmpeg_proc = await asyncio.to_thread(
                                _launch_ffmpeg_direct, stream_url, width, height
                            )
                        if ffmpeg_proc:
                            await asyncio.sleep(1.0)
                            continue
                    try:
                        await websocket.send_json(
                            {"type": "error", "message": "Stream timed out."}
                        )
                    except Exception:
                        pass
                    break

                if len(raw) < frame_size:
                    if reconnect_attempts < max_reconnect:
                        reconnect_attempts += 1
                        _kill_procs(yt_proc, ffmpeg_proc)
                        yt_proc = ffmpeg_proc = None
                        await asyncio.sleep(2)
                        if is_youtube:
                            yt_proc, ffmpeg_proc = await asyncio.to_thread(
                                _launch_ytdlp_ffmpeg_pipeline,
                                youtube_url,
                                width,
                                height,
                            )
                        else:
                            ffmpeg_proc = await asyncio.to_thread(
                                _launch_ffmpeg_direct, stream_url, width, height
                            )
                        if ffmpeg_proc:
                            continue
                    try:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Stream ended or read failed.",
                            }
                        )
                    except Exception:
                        pass
                    break

                frame = np.frombuffer(raw, dtype=np.uint8).reshape(
                    (height, width, 3)
                ).copy()

                # Drain stale frames that accumulated while processing previous frame
                # This prevents pipe buffer overflow and real-time lag when YOLO inference is slow
                try:
                    while True:
                        stale = await asyncio.wait_for(
                            asyncio.to_thread(ffmpeg_proc.stdout.read, frame_size),
                            timeout=0.001,
                        )
                        if len(stale) < frame_size:
                            break
                        frame = np.frombuffer(stale, dtype=np.uint8).reshape(
                            (height, width, 3)
                        ).copy()
                except asyncio.TimeoutError:
                    pass
            else:
                if cap is None or not cap.isOpened():
                    if reconnect_attempts < max_reconnect:
                        reconnect_attempts += 1
                        await asyncio.sleep(2)
                        cap = cv2.VideoCapture(stream_url)
                        continue
                    await websocket.send_json(
                        {"type": "error", "message": "Stream ended"}
                    )
                    break

                ok, frame = cap.read()
                if not ok:
                    if reconnect_attempts < max_reconnect:
                        reconnect_attempts += 1
                        await asyncio.sleep(2)
                        cap.release()
                        cap = cv2.VideoCapture(stream_url)
                        continue
                    break
                frame = cv2.resize(frame, (width, height))

            reconnect_attempts = 0
            frame_count += 1
            elapsed = asyncio.get_event_loop().time() - start_time

            analysis = await asyncio.to_thread(detector.detect, frame)
            await asyncio.to_thread(detector.draw_detections, frame, analysis)

            source_label = active_sessions.get(session_id, {}).get(
                "youtube_id", "dashcam"
            )
            await asyncio.to_thread(
                detector.draw_scene_panel,
                frame,
                analysis,
                frame_count / max(1, elapsed),
                source_label,
            )

            _, jpeg_bytes = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80]
            )

            await websocket.send_bytes(jpeg_bytes.tobytes())

            vehicle_count = analysis.vehicle_count
            pedestrian_count = analysis.pedestrian_count
            stopped_count = 0
            level = "LOW"
            if vehicle_count > 12:
                level = "HIGH"
            if vehicle_count > 16:
                level = "SEVERE"

            tl_color = analysis.traffic_light_state.color

            await websocket.send_json(
                {
                    "type": "frame_result",
                    "frame_count": frame_count,
                    "fps": round(frame_count / max(1, elapsed), 1),
                    "session_duration": round(elapsed),
                    "vehicles": [
                        {
                            "class_name": v.class_name,
                            "confidence": round(v.confidence, 2),
                            "bbox": v.bbox,
                            "lane": v.lane,
                            "plate_number": getattr(v, "plate_number", None),
                            "track_id": getattr(v, "track_id", None),
                        }
                        for v in analysis.vehicles
                    ],
                    "pedestrians": [
                        {
                            "class_name": p.class_name,
                            "confidence": round(p.confidence, 2),
                            "bbox": p.bbox,
                            "track_id": getattr(p, "track_id", None),
                        }
                        for p in analysis.pedestrians
                    ],
                    "bicycles": [
                        {
                            "class_name": b.class_name,
                            "confidence": round(b.confidence, 2),
                            "bbox": b.bbox,
                            "track_id": getattr(b, "track_id", None),
                        }
                        for b in analysis.bicycles
                    ],
                    "traffic_lights": [
                        {
                            "class_name": tl.class_name,
                            "confidence": round(tl.confidence, 2),
                            "bbox": tl.bbox,
                        }
                        for tl in analysis.traffic_lights
                    ],
                    "traffic_signs": [
                        {
                            "class_name": s.class_name,
                            "confidence": round(s.confidence, 2),
                            "bbox": s.bbox,
                        }
                        for s in analysis.traffic_signs
                    ],
                    "traffic_light_color": tl_color,
                    "left_lane": getattr(analysis, "left_lane", []),
                    "right_lane": getattr(analysis, "right_lane", []),
                    "traffic": {
                        "vehicle_count": vehicle_count,
                        "pedestrian_count": pedestrian_count,
                        "stopped_count": stopped_count,
                        "level": level,
                    },
                }
            )

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        print(f"[DASHCAM] Stream error {session_id}: {exc}")
        import traceback

        traceback.print_exc()
    finally:
        _kill_procs(yt_proc, ffmpeg_proc)
        if cap is not None:
            cap.release()


def _kill_procs(*procs):
    """Safely kill one or more subprocess.Popen instances."""
    for proc in procs:
        if proc is None:
            continue
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass


def _launch_ytdlp_ffmpeg_pipeline(youtube_url: str, w: int, h: int):
    """Launch yt-dlp piped to ffmpeg for YouTube live streams.

    yt-dlp handles YouTube authentication/headers natively, avoiding 403
    errors on HLS segment downloads.  Returns (yt_proc, ffmpeg_proc).
    """
    import shutil

    yt_dlp_bin = shutil.which("yt-dlp") or "yt-dlp"

    yt_cmd = [
        yt_dlp_bin,
        "--no-warnings",
        "-q",
        "--extractor-args",
        "youtube:player_client=android",
        "-f",
        "best[height<=720]/best",
        "-o",
        "-",
        "--no-part",
        youtube_url,
    ]

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
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

    try:
        yt_proc = subprocess.Popen(
            yt_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=yt_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        # Allow yt_proc to receive SIGPIPE if ffmpeg exits
        yt_proc.stdout.close()
        print(f"[DASHCAM] yt-dlp→ffmpeg pipeline created ({w}x{h})")
        return yt_proc, ffmpeg_proc
    except Exception as exc:
        print(f"[DASHCAM] yt-dlp pipeline launch failed: {exc}")
        return None, None


def _launch_ffmpeg_direct(url: str, w: int, h: int):
    """Launch ffmpeg directly for non-YouTube streams (RTSP, HLS, etc.)."""
    is_hls = ".m3u8" in url.lower()
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-user_agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "-probesize",
        "150000",
        "-analyzeduration",
        "150000",
    ]
    if not is_hls:
        cmd += ["-fflags", "nobuffer", "-flags", "low_delay"]

    cmd += [
        "-i",
        url,
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
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        print(
            f"[DASHCAM] Direct ffmpeg pipe created ({w}x{h}) {'[HLS]' if is_hls else ''}"
        )
        return proc
    except Exception as exc:
        print(f"[DASHCAM] ffmpeg launch failed: {exc}")
        return None
