import asyncio
import dataclasses
import json
from dataclasses import dataclass

from src.actions.processor import process_action
from src.agents.llm import LLMError, call_llm
from src.agents.prompts import build_system_prompt
from src.flux.client import FluxClient
from src.perception.models import AgentState
from src.perception.translator import build_perception


@dataclass
class AgentConfig:
    agent_id: str
    name: str
    persona: str
    llm_backend: str
    llm_model: str
    loop_delay: float
    start_x: int
    start_y: int
    start_facing: str
    start_internal_state: str


class Agent:
    def __init__(self, config: AgentConfig, flux: FluxClient):
        self.config = config
        self.flux = flux
        self.x = config.start_x
        self.y = config.start_y
        self.facing = config.start_facing
        self.internal_state = config.start_internal_state
        self.last_action = ""
        self.last_feedback = ""
        self.last_reasoning = ""
        self.history: list[dict] = []
        self._running = asyncio.Event()
        # _running is NOT set — Aria starts paused

    async def start_with_model(self, model: str) -> None:
        self.config = dataclasses.replace(self.config, llm_model=model)
        await self._publish_state()
        self._running.set()

    def stop(self) -> None:
        self._running.clear()

    async def reset(self, spawn_x: int, spawn_y: int) -> None:
        self._running.clear()
        self.x = spawn_x
        self.y = spawn_y
        self.facing = self.config.start_facing
        self.internal_state = self.config.start_internal_state
        self.last_action = ""
        self.last_feedback = ""
        self.last_reasoning = ""
        self.history = []
        await self._publish_state()
        # do NOT set _running — user must click Start

    async def run(self) -> None:
        config = self.config
        while True:
            await self._running.wait()  # blocks if paused
            # 1. Build AgentState
            agent_state = AgentState(
                agent_id=config.agent_id,
                x=self.x,
                y=self.y,
                facing=self.facing,
                internal_state=self.internal_state,
                last_action=self.last_action,
                last_feedback=self.last_feedback,
            )

            # 2. Build perception
            try:
                perception = await build_perception(agent_state, self.flux)
            except Exception as e:
                print(f"[{config.name}] Perception error: {e}")
                await asyncio.sleep(config.loop_delay)
                continue

            # 3 & 4. Build system prompt and call LLM
            system_prompt = build_system_prompt(self.config)
            try:
                response = await call_llm(
                    system_prompt,
                    perception.description,
                    self.config.llm_backend,
                    self.config.llm_model,
                    history=self.history,
                )
            except LLMError as e:
                print(f"[{config.name}] LLM error: {e}")
                self.last_feedback = "I couldn't decide what to do"
                await self._publish_state()
                await asyncio.sleep(config.loop_delay)
                continue

            # 5. Append to rolling history (assistant messages only)
            self.history.append({"role": "assistant", "content": response})
            self.history = self.history[-10:]

            # 6. Parse action
            action = self._parse_action(response)

            # 7. Handle parse failure
            if action is None:
                self.last_feedback = "I couldn't decide what to do"
                await self._publish_state()
                await asyncio.sleep(config.loop_delay)
                continue

            # 8. Publish action event to Flux
            properties = dict(action)
            properties["agent_id"] = config.agent_id
            properties["perception"] = perception.description
            await self.flux.publish_event(
                stream="agent.actions",
                source=config.agent_id,
                entity_id=f"agent/{config.agent_id}/action",
                properties=properties,
            )

            # 9. Store reasoning
            self.last_reasoning = action.get("reasoning", "")

            # 10. Process action and get real feedback
            summary = _action_summary(action)
            feedback, new_x, new_y, new_facing, new_internal_state = await process_action(
                action, config.agent_id, self.x, self.y, self.facing, self.flux
            )
            self.last_action = summary
            self.last_feedback = feedback
            self.x = new_x
            self.y = new_y
            self.facing = new_facing
            if new_internal_state is not None:
                self.internal_state = new_internal_state

            # 11. Publish updated agent state
            await self._publish_state()

            # 12. Print
            print(f"[{config.name}] {summary}")

            # 13. Sleep
            await asyncio.sleep(config.loop_delay)

    async def _publish_state(self) -> None:
        await self.flux.publish_event(
            stream="agent.state",
            source=self.config.agent_id,
            entity_id=f"agent/{self.config.agent_id}",
            properties={
                "name": self.config.name,
                "x": self.x,
                "y": self.y,
                "facing": self.facing,
                "internal_state": self.internal_state,
                "last_action": self.last_action,
                "last_feedback": self.last_feedback,
                "last_reasoning": self.last_reasoning,
            },
        )

    def _parse_action(self, response: str) -> dict | None:
        try:
            data = json.loads(response.strip())
        except (json.JSONDecodeError, ValueError):
            print(f"[{self.config.name}] Invalid action response: {response}")
            return None

        action = data.get("action")
        if action not in ("move", "turn", "interact", "wait"):
            print(f"[{self.config.name}] Invalid action response: {response}")
            return None

        if action in ("move", "turn"):
            direction = data.get("direction")
            if direction not in ("north", "south", "east", "west"):
                print(f"[{self.config.name}] Invalid action response: {response}")
                return None

        if action == "interact":
            if "object_id" not in data:
                print(f"[{self.config.name}] Invalid action response: {response}")
                return None

        return data


def _action_summary(action: dict) -> str:
    a = action.get("action")
    if a == "move":
        return f"move {action.get('direction', '')}"
    elif a == "turn":
        return f"turn {action.get('direction', '')}"
    elif a == "interact":
        return f"interact {action.get('object_id', '')}"
    return "wait"
