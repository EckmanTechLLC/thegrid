# ADR-001 — Core Architecture

**Date:** 2026-03-11
**Status:** Accepted
**Project:** thegrid

---

## Context

thegrid is a virtual spatial environment where AI agents exist as native digital entities. Agents perceive the world through structured language descriptions and interact through defined actions. The system serves as an observation and experimentation sandbox — not a training platform.

The design philosophy rejects human sensory simulation. Agents are not given vision, graphics, or raw sensor data. They receive structured state descriptions and act through validated action requests.

---

## Decision

Build thegrid as a Python backend with a browser-based frontend. Use Flux (projects/flux) as the world state engine — an existing event-sourced, persistent state platform with built-in WebSocket subscriptions.

Flux runs as a separate Docker Compose service. thegrid's Python backend is a client to Flux — publishing events and reading state via Flux's HTTP and WebSocket APIs.

---

## System Components

### Flux — World State Engine
Flux is the authoritative, persistent store for all world state. It is event-sourced: state is derived from immutable events, not stored directly. This means the full history of everything that happened in the world is preserved by default.

thegrid uses Flux to store:
- World layout and terrain (as Flux entities)
- Object positions and properties
- Agent positions, capabilities, and internal state
- Every action and its outcome (event history = activity feed)

Flux provides out of the box:
- Persistence (survives restarts, replays from event history)
- Real-time WebSocket subscriptions for any entity
- Event replay and time-travel debugging
- Multiple simultaneous observers of the same state

Flux runs at `http://localhost:3000` (Docker Compose, separate from thegrid).

### World Engine (Python)
Responsible for world rules and consistency. Does not store state — reads from and writes to Flux. Responsibilities:
- Validate agent actions against world rules
- Publish action outcome events to Flux
- Enforce traversal and interaction constraints
- Manage world initialization and layout

### Agent Loop (Python)
Each agent runs on its own async loop (real-time, not turn-based). The loop follows:

```
perceive → reason → act → receive feedback → repeat
```

Agents are configurable to use either local Ollama models or OpenAI/Anthropic APIs. The LLM backend is set per agent at configuration time.

The agent loop reads world state from Flux (via HTTP or WebSocket subscription) to build its perception input. It publishes its actions as events to Flux.

### Agent Observation of Other Agents
Because all agent state lives in Flux, any agent can subscribe to another agent's Flux entity. This means agents can natively observe what other agents are doing — their position, current action, internal state — and factor that into their own reasoning. This is not a special feature; it falls out naturally from the Flux model.

### Agent Internal State
Internal state is first-class in the data model. Agents carry emotional/motivational state (e.g. curious, bored, uncertain, goal-directed) stored as properties on the agent's Flux entity. This state influences the perception description the agent receives and the context passed to the LLM. It is not bolted on later — it is modeled from the start.

### Perception Translator (Python)
Converts Flux world state into a structured natural language description for the agent. Output is relative to the agent's position and facing direction. Includes:
- Nearby objects with relative distance and direction
- Traversal possibilities and interaction constraints
- Agent's own current state and capabilities
- Recent action feedback
- Current internal/emotional state
- Observations of nearby agents (their state, recent actions)

Agents never receive absolute world coordinates or global state.

### Action Processor (Python)
Receives the agent's chosen action, validates it against world rules and agent capabilities, publishes the outcome as a Flux event, and returns structured feedback. Agents do not directly mutate state — they propose actions, the world engine decides outcomes.

### Frontend
Browser-based. Subscribes directly to Flux WebSocket for real-time updates. Two panels:
- **2D Map View** — spatial representation of the world, agent positions, and objects. Canvas or SVG. Human observation only — agents never see this.
- **Activity Feed** — live log of each agent's perception summaries, reasoning, actions taken, and feedback received. Driven by Flux event history and real-time subscriptions.

The frontend is a pure observer. It reads from Flux — it never writes.

---

## Data Flow

```
Agent Loop (Python)
       ↓
Perception Translator ← reads Flux state (HTTP/WebSocket)
       ↓
Agent (LLM — Ollama or API)
       ↓
Action Processor → validates → publishes event to Flux
                                        ↓
                               Flux derives new state
                                        ↓
                    WebSocket subscribers notified:
                         - Other agent loops
                         - Frontend (Map + Activity Feed)
```

---

## Key Design Principles

**AI-native interaction** — Agents receive structured descriptions, not graphics or raw sensor data.

**Relative perception** — All spatial information is relative to the agent. No absolute coordinates exposed to agents.

**Capability-driven actions** — Agents can only perform actions their capability set allows. The action processor enforces this.

**Action validation** — Agents propose actions. The world engine decides outcomes. Agents cannot directly mutate state.

**Internal state as first-class** — Emotional/motivational state is modeled from day one and feeds into perception descriptions.

**Agent observability** — Agents can observe other agents natively via Flux subscriptions. No special inter-agent communication layer needed.

**Event-sourced world** — Every action, state change, and outcome is an immutable event in Flux. Full world history is preserved. The activity feed is just event history rendered for humans.

**Observation focus** — The system is designed for watching agents behave, not for training them.

---

## Future Expansion Areas

These are out of scope for Phase 1 but the architecture should not block them:

- Multiple simultaneous agents
- Agent memory (persistent across sessions)
- Goal systems
- Inventory and resource management
- Agent collaboration or competition
- Agent-proposed tools or capability expansion
- Self-modification within controlled boundaries

---

## Technology Summary

| Component | Choice | Reason |
|---|---|---|
| World state + persistence | Flux (existing) | Event-sourced, WebSocket, persistent, zero rebuild |
| Backend language | Python | Best LLM ecosystem, fast iteration |
| Agent framework | Python async | Per-agent real-time loops |
| LLM backends | Ollama + OpenAI/Anthropic | Configurable per agent |
| Frontend | HTML/JS (Canvas or SVG) | Simple, no build toolchain required |
| Realtime transport | Flux WebSocket | Already provided by Flux |
| Flux deployment | Docker Compose (separate) | Independent, easy to spin up |

---

## Infrastructure

- Dev VM: <DEV_VM_IP>
- Flux API: `http://localhost:3000` (Docker Compose)
- Flux UI: `http://localhost:8082`
- thegrid backend: Python process (port TBD)
- thegrid frontend: served by Python backend (port TBD)

---

## Project Structure

```
thegrid/
├── CLAUDE.md
├── docs/
│   ├── decisions/
│   └── sessions/
├── .odin/
│   ├── tasks/
│   └── sessions/
└── src/
    ├── world/          ← World engine, rules, initialization
    ├── agents/         ← Agent loop, internal state, LLM interface
    ├── perception/     ← Perception translator (Flux state → description)
    ├── actions/        ← Action processor (validate → publish to Flux)
    ├── flux/           ← Flux client (HTTP + WebSocket wrapper)
    └── frontend/       ← HTML/JS map + activity feed
```
