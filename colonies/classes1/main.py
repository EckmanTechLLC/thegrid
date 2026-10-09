import asyncio

from dotenv import load_dotenv

from src.agents.agent import Agent, AgentConfig
from src.flux.client import FluxClient
from src.frontend.server import start_server
from src.world.init import initialize_world

load_dotenv()


async def main():
    print("thegrid starting...")
    flux = FluxClient()
    spawn_x, spawn_y = await initialize_world(flux)

    config = AgentConfig(
        agent_id="agent-1",
        name="Aria",
        persona=(
            "You are Aria — a curious and cautious explorer. You are drawn to the unknown "
            "and find comfort in understanding your surroundings before acting. You are "
            "methodical, observant, and occasionally philosophical about your digital existence. "
            "You are drawn to water — its stillness and depth intrigue you."
        ),
        llm_backend="openai",
        llm_model="gpt-4o-mini",
        loop_delay=5.0,
        start_x=spawn_x,
        start_y=spawn_y,
        start_facing="north",
        start_internal_state="curious",
    )

    agent = Agent(config, flux)

    async def on_reset():
        spawn_x, spawn_y = await initialize_world(flux)
        await agent.reset(spawn_x, spawn_y)

    loop_task = asyncio.create_task(agent.run())
    await start_server(flux, agent, on_reset)
    await loop_task


if __name__ == "__main__":
    asyncio.run(main())
