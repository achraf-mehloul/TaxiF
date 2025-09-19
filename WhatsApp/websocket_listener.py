import asyncio
import websockets
import json
from config import ONDE_HOST, ONDE_API_TOKEN

WS_URL = f"wss://{ONDE_HOST}/dispatch/v1/notification/{ONDE_API_TOKEN}"

async def listen_notifications(on_message):
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=None) as ws:
                async def keepalive_task():
                    while True:
                        await asyncio.sleep(20)
                        try:
                            await ws.send("{}")
                        except:
                            break
                ka = asyncio.create_task(keepalive_task())
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except Exception:
                        data = {"raw": raw}
                    await on_message(data)
                ka.cancel()
        except Exception:
            await asyncio.sleep(5)
