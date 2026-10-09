from dataclasses import dataclass


@dataclass
class AgentState:
    agent_id: str
    x: int
    y: int
    facing: str          # "north" | "south" | "east" | "west"
    internal_state: str  # e.g. "curious", "bored"
    last_action: str
    last_feedback: str


@dataclass
class PerceptionResult:
    agent_id: str
    description: str     # full natural language description
    raw: dict            # structured data used to build the description (for debugging)
