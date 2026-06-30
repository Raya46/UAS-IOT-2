"""Test ESP32 camera stream via WebSocket dashcam endpoint."""
import asyncio
import json
import sys
import websockets

ESP32_URL = sys.argv[1] if len(sys.argv) > 1 else "http://esp32cam.local/stream"
WS_URL = "ws://localhost:8000/ws/dashcam"


async def main():
    async with websockets.connect(WS_URL) as ws:
        connected = json.loads(await ws.recv())
        print(f"Connected: {connected}")

        await ws.send(json.dumps({"esp32_url": ESP32_URL}))
        resolved = json.loads(await ws.recv())
        print(f"Resolved: {resolved}")

        frame_count = 0
        while True:
            msg = await ws.recv()
            if isinstance(msg, bytes):
                frame_count += 1
                print(f"\rFrame {frame_count} ({len(msg)} bytes)", end="", flush=True)
            else:
                data = json.loads(msg)
                if data.get("type") == "frame_result":
                    t = data.get("traffic", {})
                    print(f" | vehicles={t.get('vehicle_count',0)} pedestrians={t.get('pedestrian_count',0)} fps={data.get('fps',0)}")
                elif data.get("type") == "error":
                    print(f"\nError: {data['message']}")
                    break


if __name__ == "__main__":
    print(f"Connecting to ESP32 at {ESP32_URL} via {WS_URL}")
    asyncio.run(main())
