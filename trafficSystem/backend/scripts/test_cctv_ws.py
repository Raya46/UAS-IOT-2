import asyncio
import json
import websockets

async def test():
    uri = "ws://localhost:8000/ws/livecam"
    async with websockets.connect(uri) as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(msg)
        print("Connected:", data.get("type"), data.get("session_id"))

        # Send config for CCTV stream
        await ws.send(json.dumps({
            "type": "config",
            "mode": "stream",
            "stream_url": "https://cctv.balitower.co.id/Bendungan-Hilir-003-700014_1/embed.html",
            "jpeg_quality": 80,
            "resize_width": 960,
            "source_label": "bendungan_hilir_3",
        }))

        frame_count = 0
        for i in range(20):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                if isinstance(msg, bytes):
                    frame_count += 1
                    print("Frame %d: %d bytes" % (frame_count, len(msg)))
                else:
                    data = json.loads(msg)
                    dtype = data.get("type", "?")
                    fps = data.get("fps", 0)
                    dets = len(data.get("detections", []))
                    traffic = data.get("traffic", {})
                    print("JSON: type=%s fps=%s detections=%d traffic=%s" % (dtype, fps, dets, traffic))
            except asyncio.TimeoutError:
                print("Timeout waiting for message %d" % i)
                break

        print("Total frames received: %d" % frame_count)
        await ws.send(json.dumps({"type": "stop"}))

asyncio.run(test())
