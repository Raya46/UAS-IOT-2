import asyncio
import json
import websockets

async def test():
    uri = "ws://localhost:8000/ws/dashcam"
    async with websockets.connect(uri) as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=10)
        data = json.loads(msg)
        print("Connected:", data.get("type"), data.get("session_id"))

        # Send config to start YouTube stream
        await ws.send(json.dumps({
            "youtube_id": "swJ1-ejSm1Q"
        }))

        # Wait for resolving/resolved messages
        for _ in range(5):
            msg = await asyncio.wait_for(ws.recv(), timeout=15)
            data = json.loads(msg)
            print("Server response:", data)
            if data.get("type") == "resolved":
                break

        # Receive frames and analysis
        frame_count = 0
        for i in range(10):
            try:
                # Expect frame bytes first
                msg = await asyncio.wait_for(ws.recv(), timeout=20)
                if isinstance(msg, bytes):
                    frame_count += 1
                    print(f"Frame {frame_count}: {len(msg)} bytes")
                    
                    # Expect JSON metadata next
                    metadata_msg = await asyncio.wait_for(ws.recv(), timeout=10)
                    data = json.loads(metadata_msg)
                    fps = data.get("fps", 0)
                    vehicles = len(data.get("vehicles", []))
                    pedestrians = len(data.get("pedestrians", []))
                    traffic_light = data.get("traffic_light_color", "unknown")
                    print(f"Metadata: fps={fps} vehicles={vehicles} pedestrians={pedestrians} traffic_light={traffic_light}")
                else:
                    data = json.loads(msg)
                    print("Unexpected JSON:", data.get("type"))
            except asyncio.TimeoutError:
                print("Timeout waiting for message", i)
                break

        print("Total frames received:", frame_count)
        await ws.send(json.dumps({"type": "stop"}))

asyncio.run(test())
