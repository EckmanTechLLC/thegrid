from pathlib import Path
from typing import Callable, Awaitable

from aiohttp import web

from src.agents.agent import Agent
from src.flux.client import FluxClient

STATIC_DIR = Path(__file__).parent / "static"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET",
    "Access-Control-Allow-Headers": "Content-Type",
}


async def _index(request):
    return web.FileResponse(STATIC_DIR / "index.html")


async def start_server(flux: FluxClient, agent: Agent, on_reset: Callable[[], Awaitable[None]]) -> None:
    async def _reset_options(request):
        return web.Response(headers=CORS_HEADERS)

    async def _reset(request):
        await flux.delete_all_entities("world")
        await flux.delete_all_entities("agent")
        await on_reset()
        return web.json_response({"status": "ok"}, headers=CORS_HEADERS)

    async def _agent_start(request):
        data = await request.json()
        model = data.get("model", "gpt-4o-mini")
        await agent.start_with_model(model)
        return web.json_response({"status": "started", "model": model}, headers=CORS_HEADERS)

    async def _agent_stop(request):
        agent.stop()
        return web.json_response({"status": "stopped"}, headers=CORS_HEADERS)

    async def _agent_status(request):
        return web.json_response({
            "running": agent._running.is_set(),
            "model": agent.config.llm_model,
        }, headers=CORS_HEADERS)

    async def _agent_start_options(request):
        return web.Response(headers=CORS_HEADERS)

    async def _agent_stop_options(request):
        return web.Response(headers=CORS_HEADERS)

    app = web.Application()
    app.router.add_get("/", _index)
    app.router.add_post("/reset", _reset)
    app.router.add_route("OPTIONS", "/reset", _reset_options)
    app.router.add_post("/agent/start", _agent_start)
    app.router.add_route("OPTIONS", "/agent/start", _agent_start_options)
    app.router.add_post("/agent/stop", _agent_stop)
    app.router.add_route("OPTIONS", "/agent/stop", _agent_stop_options)
    app.router.add_get("/agent/status", _agent_status)
    app.router.add_static("/", path=STATIC_DIR, name="static")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=8083)
    await site.start()
    print("Frontend running at http://0.0.0.0:8083")
