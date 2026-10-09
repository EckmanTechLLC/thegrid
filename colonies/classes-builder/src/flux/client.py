import json
import os
import time
from urllib.parse import quote

import httpx
import websockets
from dotenv import load_dotenv

load_dotenv()


class FluxClient:
    def __init__(self):
        flux_url = os.getenv("FLUX_URL", "http://localhost:3000")
        self.base_url = flux_url.rstrip("/")
        self.ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")

    async def publish_event(self, stream: str, source: str, entity_id: str, properties: dict) -> dict:
        """POST /api/events — publish a single event to Flux."""
        payload = {
            "stream": stream,
            "source": source,
            "timestamp": int(time.time() * 1000),
            "payload": {
                "entity_id": entity_id,
                "properties": properties,
            },
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/api/events", json=payload)
            response.raise_for_status()
            return response.json()

    async def get_entity(self, entity_id: str) -> dict:
        """GET /api/state/entities/:id — get a specific entity by ID."""
        encoded = quote(entity_id, safe="")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/state/entities/{encoded}")
            response.raise_for_status()
            return response.json()

    async def get_all_entities(self, prefix: str | None = None) -> list:
        """GET /api/state/entities — list all entities, optionally filtered by prefix."""
        params = {}
        if prefix:
            params["prefix"] = prefix
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/state/entities", params=params)
            response.raise_for_status()
            return response.json()

    async def delete_entity(self, entity_id: str) -> dict:
        """DELETE /api/state/entities/:id — delete an entity from Flux."""
        encoded = quote(entity_id, safe="")
        async with httpx.AsyncClient() as client:
            response = await client.delete(f"{self.base_url}/api/state/entities/{encoded}")
            response.raise_for_status()
            return response.json()

    async def delete_all_entities(self, prefix: str) -> None:
        """POST /api/state/entities/delete — batch delete all entities with prefix."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/state/entities/delete",
                json={"prefix": prefix},
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                pass  # Ignore errors (e.g. no entities found for prefix)

    async def subscribe(self, entity_ids: list[str], on_update) -> None:
        """WebSocket subscription — calls on_update(message) for each state_update message."""
        uri = f"{self.ws_url}/api/ws"
        async with websockets.connect(uri) as ws:
            for entity_id in entity_ids:
                await ws.send(json.dumps({"type": "subscribe", "entity_id": entity_id}))
            async for raw in ws:
                message = json.loads(raw)
                if message.get("type") == "state_update":
                    await on_update(message)
