import asyncio
import json
import threading
import time
import urllib.parse
import uuid
from typing import Dict, Optional

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.responses import StreamingResponse

router = APIRouter()


class MjpegHttpReader:
    """Reads frames from ESP32-style MJPEG HTTP streams (multipart/x-mixed-replace).
    Drop-in replacement for cv2.VideoCapture — same read()/isOpened()/release() API."""

    def __init__(self, url, timeout=10):
        self._url = url
        self._resp = None
        self._buf = b""
        self._opened = False
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            self._resp = urllib.request.urlopen(req, timeout=timeout)
            self._opened = True
        except Exception as e:
            print(f"[LIVECAM] MJPEG HTTP reader failed to connect: {e}")

    def isOpened(self):
        return self._opened

    def read(self):
        if not self._opened:
            return False, None
        try:
            while True:
                chunk = self._resp.read(8192)
                if not chunk:
                    self._opened = False
                    return False, None
                self._buf += chunk
                # ponytail: find JPEG SOI (0xFFD8) and EOI (0xFFD9) markers directly
                start = self._buf.find(b"\xff\xd8")
                if start < 0:
                    self._buf = self._buf[-2:]
                    continue
                end = self._buf.find(b"\xff\xd9", start + 2)
                if end < 0:
                    continue
                jpeg = self._buf[start:end + 2]
                self._buf = self._buf[end + 2:]
                frame = cv2.imdecode(
                    np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR
                )
                if frame is not None:
                    return True, frame
        except Exception:
            self._opened = False
            return False, None

    def release(self):
        self._opened = False
        if self._resp:
            try:
                self._resp.close()
            except Exception:
                pass

    def get(self, prop_id):
        return 0


def _open_video_capture(url):
    """Try OpenCV VideoCapture, fall back to manual MJPEG reader for ESP32 streams."""
    # ESP32 MJPEG streams: use singleton proxy (avoids single-client contention)
    if url.startswith("http") and "10.194." in url or "esp32" in url.lower():
        proxy = Esp32StreamProxy.get_instance(url)
        print(f"[LIVECAM] Using ESP32 singleton proxy for {url}")
        return proxy

    cap = cv2.VideoCapture(url)
    if cap.isOpened():
        return cap
    cap.release()
    print(f"[LIVECAM] OpenCV failed, trying MJPEG HTTP reader for {url}")
    reader = MjpegHttpReader(url)
    return reader


class Esp32StreamProxy:
    """Singleton: one connection to ESP32, shares frames with all consumers.
    Implements cv2.VideoCapture interface so livecam session can use it directly."""

    _instances: Dict[str, "Esp32StreamProxy"] = {}
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, url: str) -> "Esp32StreamProxy":
        with cls._lock:
            if url not in cls._instances:
                cls._instances[url] = cls(url)
            inst = cls._instances[url]
            if not inst._running:
                inst._start()
            return inst

    def __init__(self, url: str):
        self.url = url
        self.latest_jpeg: Optional[bytes] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._got_first_frame = False

    def _start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[ESP32 PROXY] Started reader for {self.url}")

    def _loop(self):
        import socket
        parsed = urllib.parse.urlparse(self.url)
        host, port = parsed.hostname, parsed.port or 80

        while self._running:
            try:
                sock = socket.create_connection((host, port), timeout=30)
                sock.settimeout(60)
                sock.sendall(
                    f"GET {parsed.path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: ESP32Proxy\r\nConnection: keep-alive\r\n\r\n".encode()
                )
                hdr = b""
                while b"\r\n\r\n" not in hdr:
                    b = sock.recv(1)
                    if not b:
                        raise ConnectionError("closed during headers")
                    hdr += b
                print(f"[ESP32 PROXY] Connected to {self.url}")

                buf = b""
                no_data_count = 0
                while self._running:
                    try:
                        chunk = sock.recv(32768)
                    except socket.timeout:
                        no_data_count += 1
                        if no_data_count > 3:
                            print("[ESP32 PROXY] No data for 3min, reconnecting...")
                            break
                        continue
                    if not chunk:
                        break
                    no_data_count = 0
                    buf += chunk
                    while True:
                        start = buf.find(b"\xff\xd8")
                        if start < 0:
                            if len(buf) > 2:
                                buf = buf[-2:]
                            break
                        end = buf.find(b"\xff\xd9", start + 2)
                        if end < 0:
                            break
                        self.latest_jpeg = buf[start:end + 2]
                        if not self._got_first_frame:
                            self._got_first_frame = True
                            print(f"[ESP32 PROXY] First frame: {len(self.latest_jpeg)}B")
                        buf = buf[end + 2:]
                sock.close()
            except Exception as e:
                print(f"[ESP32 PROXY] Error: {e}, retrying in 3s...")
            time.sleep(3)

    # cv2.VideoCapture-compatible interface
    def isOpened(self):
        return self._running

    def read(self):
        jpeg = self.latest_jpeg
        if jpeg is None and not self._got_first_frame:
            # ponytail: block up to 20s waiting for ESP32's first frame
            for _ in range(200):
                time.sleep(0.1)
                jpeg = self.latest_jpeg
                if jpeg is not None:
                    break
        if jpeg is None:
            time.sleep(0.1)
            return False, None
        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        time.sleep(0.05)
        return frame is not None, frame

    def release(self):
        pass

    def get(self, prop_id):
        return 0


@router.get("/esp32-stream")
async def esp32_stream_proxy_endpoint():
    """Proxy ESP32 MJPEG stream — backend maintains the single connection."""
    from app.routers.cameras import LOCAL_CAMERAS
    esp32_url = next(
        (c.stream_url for c in LOCAL_CAMERAS if c.id.startswith("esp32")), None
    )
    if not esp32_url:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "No ESP32 camera configured"}, status_code=404)

    proxy = Esp32StreamProxy.get_instance(esp32_url)

    async def generate():
        boundary = b"\r\n--frame\r\n"
        header_tpl = b"Content-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n"
        last = None
        while proxy._running:
            jpeg = proxy.latest_jpeg
            if jpeg is not None and jpeg is not last:
                last = jpeg
                yield boundary + (header_tpl % len(jpeg)) + jpeg
            await asyncio.sleep(0.066)  # ~15 FPS

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace;boundary=frame",
        headers={"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"},
    )


_LiveCamSession = None


def _get_livecam_session_class():
    global _LiveCamSession
    if _LiveCamSession is None:
        from app.livecam_session import LiveCamSession

        _LiveCamSession = LiveCamSession
    return _LiveCamSession


def _resolve_cctv_stream_url(url: str) -> str:
    if url.startswith("/api/uploads/"):
        import os
        filename = url.split("/")[-1]
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        local_path = os.path.join(backend_dir, "data", "uploads", urllib.parse.unquote(filename))
        print(f"[LIVECAM] Resolved local upload {url} -> {local_path}")
        return local_path

    if "/embed.html" not in url:
        return url

    # Strip embed.html → construct index.m3u8 directly
    # Pattern: https://host/STREAMNAME/embed.html → https://host/STREAMNAME/index.m3u8
    index_url = url.replace("/embed.html", "/index.m3u8").replace(
        "/embed", "/index.m3u8"
    )
    print(f"[LIVECAM] Resolved {url} -> {index_url}")
    return index_url


active_livecam_sessions: Dict[str, object] = {}


@router.websocket("/ws/livecam")
async def livecam_websocket(websocket: WebSocket):
    await websocket.accept()
    session_id = str(uuid.uuid4())[:8]
    session = None
    stream_task = None

    try:
        SessionClass = _get_livecam_session_class()
        session = SessionClass(session_id)
        active_livecam_sessions[session_id] = session

        await websocket.send_json(
            {
                "type": "connected",
                "session_id": session_id,
                "message": "Send a config message, then start sending frames (browser mode) or wait for stream.",
            }
        )

        mode = "browser"
        stream_url = None

        while True:
            if mode == "stream" and stream_task is not None:
                try:
                    msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.05)
                    if msg.get("type") == "config":
                        session.update_settings(msg)
                    elif msg.get("type") == "stop":
                        break
                except asyncio.TimeoutError:
                    pass
                if stream_task.done():
                    try:
                        stream_task.result()
                    except Exception as exc:
                        print(f"[LIVECAM] Stream task finished with exception: {exc}")
                    break
                await asyncio.sleep(0.01)
                continue

            message = await websocket.receive()

            if "text" in message:
                try:
                    data = json.loads(message["text"])
                except Exception:
                    continue

                if data.get("type") == "config":
                    session.update_settings(data)
                    new_mode = data.get("mode", mode)
                    new_url = data.get("stream_url")

                    if new_mode == "stream" and new_url:
                        mode = "stream"
                        stream_url = _resolve_cctv_stream_url(new_url)
                        stream_task = asyncio.create_task(
                            _stream_pull_loop(
                                websocket, session, stream_url, session_id
                            )
                        )
                        await websocket.send_json(
                            {"type": "stream_started", "stream_url": stream_url}
                        )
                    continue

                if data.get("type") == "stop":
                    break
                continue

            if "bytes" in message:
                jpeg_data = message["bytes"]
                result = await asyncio.to_thread(session.process_frame, jpeg_data)

                if result.get("dropped"):
                    await websocket.send_json({"type": "dropped"})
                    continue
                if result.get("error"):
                    await websocket.send_json(
                        {"type": "error", "message": result["error"]}
                    )
                    continue

                await websocket.send_bytes(result["frame_bytes"])
                await websocket.send_json(
                    {"type": "frame_result", **result["metadata"]}
                )

    except WebSocketDisconnect:
        print(f"[LIVECAM] Client disconnected: {session_id}")
    except Exception as exc:
        print(f"[LIVECAM] Session error {session_id}: {exc}")
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
        if session is not None:
            session.stop()
        active_livecam_sessions.pop(session_id, None)


async def _stream_pull_loop(
    websocket: WebSocket, session, stream_url: str, session_id: str
):
    import subprocess as _subprocess

    is_hls = ".m3u8" in stream_url.lower()
    print(
        f"[LIVECAM] Starting stream pull from {stream_url} (session {session_id}) {'[HLS]' if is_hls else ''}"
    )

    cap = None
    ffmpeg_proc = None
    ffmpeg_width = 0
    ffmpeg_height = 0
    reconnect_attempts = 0
    max_reconnect = 10

    _ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    _ref = "Referer: https://cctv.balitower.co.id/"

    def _launch_ffmpeg(url: str, ua: str, ref: str, is_hls: bool = False):
        w, h = 960, 540
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-user_agent",
            ua,
            "-headers",
            ref,
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
            proc = _subprocess.Popen(
                cmd, stdout=_subprocess.PIPE, stderr=_subprocess.DEVNULL
            )
            print(
                f"[LIVECAM] Direct ffmpeg pipe created ({w}x{h}) {'[HLS mode]' if is_hls else ''}"
            )
            return proc, w, h
        except Exception as exc:
            print(f"[LIVECAM] Direct ffmpeg launch failed: {exc}")
        return None, 0, 0

    def _try_ffmpeg(url: str) -> bool:
        nonlocal ffmpeg_proc, ffmpeg_width, ffmpeg_height
        if ffmpeg_proc is not None:
            try:
                ffmpeg_proc.kill()
                ffmpeg_proc.wait()
            except Exception:
                pass
        ffmpeg_proc, ffmpeg_width, ffmpeg_height = _launch_ffmpeg(
            url, _ua, _ref, is_hls
        )
        if ffmpeg_proc is not None:
            import time as _time
            _time.sleep(0.5)
            if ffmpeg_proc.poll() is not None:
                try:
                    ffmpeg_proc.kill()
                except Exception:
                    pass
                ffmpeg_proc = None
        return ffmpeg_proc is not None

    if is_hls:
        ffmpeg_proc, ffmpeg_width, ffmpeg_height = await asyncio.to_thread(
            _launch_ffmpeg, stream_url, _ua, _ref, True
        )
        if ffmpeg_proc is not None:
            await asyncio.sleep(2.0)
            if ffmpeg_proc.poll() is not None:
                stderr_log = ""
                if ffmpeg_proc.stderr:
                    try:
                        raw_stderr = ffmpeg_proc.stderr.read(500)
                        stderr_log = raw_stderr.decode("utf-8", errors="replace")
                    except Exception:
                        pass
                print(f"[LIVECAM] ffmpeg exited immediately: {stderr_log}. Falling back to OpenCV.")
                try:
                    ffmpeg_proc.kill()
                except Exception:
                    pass
                ffmpeg_proc = None
        if ffmpeg_proc is None:
            print("[LIVECAM] ffmpeg pipe failed, falling back to OpenCV for HLS")
            cap = _open_video_capture(stream_url)
    else:
        cap = _open_video_capture(stream_url)

    try:
        while True:
            frame = None

            if ffmpeg_proc is not None:
                if ffmpeg_proc.poll() is not None:
                    stderr_log = ""
                    if ffmpeg_proc.stderr and ffmpeg_proc.returncode != 0:
                        raw_stderr = await asyncio.to_thread(
                            ffmpeg_proc.stderr.read, 500
                        )
                        stderr_log = raw_stderr.decode("utf-8", errors="replace")
                    print(
                        f"[LIVECAM] ffmpeg exited (code={ffmpeg_proc.returncode}): {stderr_log}"
                    )
                    if reconnect_attempts < max_reconnect:
                        reconnect_attempts += 1
                        print(
                            f"[LIVECAM] ffmpeg reconnecting ({reconnect_attempts}/{max_reconnect})..."
                        )
                        await asyncio.sleep(2)
                        if _try_ffmpeg(stream_url):
                            continue
                    await websocket.send_json(
                        {"type": "error", "message": "Stream ended."}
                    )
                    break

                frame_size = ffmpeg_width * ffmpeg_height * 3
                try:
                    raw = await asyncio.wait_for(
                        asyncio.to_thread(ffmpeg_proc.stdout.read, frame_size),
                        timeout=30.0,
                    )
                except asyncio.TimeoutError:
                    print(
                        f"[LIVECAM] ffmpeg frame read timed out for session {session_id}"
                    )
                    if reconnect_attempts < max_reconnect:
                        reconnect_attempts += 1
                        await asyncio.sleep(2)
                        ffmpeg_proc.kill()
                        if _try_ffmpeg(stream_url):
                            continue
                    await websocket.send_json(
                        {"type": "error", "message": "Stream timed out."}
                    )
                    break

                if len(raw) < frame_size:
                    print(
                        f"[LIVECAM] ffmpeg short read ({len(raw)} < {frame_size}), reconnecting..."
                    )
                    if reconnect_attempts < max_reconnect:
                        reconnect_attempts += 1
                        await asyncio.sleep(2)
                        ffmpeg_proc.kill()
                        if _try_ffmpeg(stream_url):
                            continue
                    await websocket.send_json(
                        {"type": "error", "message": "Stream ended or read failed."}
                    )
                    break

                frame = (
                    np.frombuffer(raw, dtype=np.uint8)
                    .reshape((ffmpeg_height, ffmpeg_width, 3))
                    .copy()
                )

                # Drain stale frames that accumulated while processing previous frame
                # This prevents pipe buffer overflow when YOLO inference is slow
                try:
                    while True:
                        stale = await asyncio.wait_for(
                            asyncio.to_thread(ffmpeg_proc.stdout.read, frame_size),
                            timeout=0.001,
                        )
                        if len(stale) < frame_size:
                            break
                        frame = (
                            np.frombuffer(stale, dtype=np.uint8)
                            .reshape((ffmpeg_height, ffmpeg_width, 3))
                            .copy()
                        )
                except asyncio.TimeoutError:
                    pass
            else:
                if cap is None or not cap.isOpened():
                    print(f"[LIVECAM] OpenCV capture not opened for {session_id}")
                    if reconnect_attempts < max_reconnect:
                        reconnect_attempts += 1
                        await asyncio.sleep(2)
                        cap = _open_video_capture(stream_url)
                        continue
                    await websocket.send_json(
                        {"type": "error", "message": "Stream ended."}
                    )
                    break

                ok, frame = cap.read()
                if not ok:
                    if reconnect_attempts < max_reconnect:
                        reconnect_attempts += 1
                        print(
                            f"[LIVECAM] OpenCV read failed, reconnecting ({reconnect_attempts}/{max_reconnect})..."
                        )
                        await asyncio.sleep(2)
                        cap.release()
                        cap = _open_video_capture(stream_url)
                        continue
                    print(f"[LIVECAM] OpenCV stream ended for session {session_id}")
                    await websocket.send_json(
                        {"type": "error", "message": "Stream ended."}
                    )
                    break

            reconnect_attempts = 0
            result = await asyncio.to_thread(session.process_raw_frame, frame)

            if result.get("dropped"):
                continue
            if result.get("error"):
                await websocket.send_json({"type": "error", "message": result["error"]})
                continue

            await websocket.send_bytes(result["frame_bytes"])
            await websocket.send_json({"type": "frame_result", **result["metadata"]})

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        print(f"[LIVECAM] Stream pull error {session_id}: {exc}")
        import traceback

        traceback.print_exc()
    finally:
        if ffmpeg_proc is not None:
            try:
                ffmpeg_proc.kill()
                ffmpeg_proc.wait(timeout=5)
            except Exception:
                pass
        if cap is not None:
            cap.release()
        print(f"[LIVECAM] Stream pull ended for session {session_id}")
