# Session 001 — Phase 1 Implementation

**Date:** 2026-03-11
**Status:** Phase 1 functionally complete, two bugs remaining

---

## What Was Built

- `src/flux/client.py` — async Flux HTTP + WebSocket wrapper (`publish_event`, `get_entity`, `get_all_entities`, `delete_entity`). URL-encodes entity IDs with slashes.
- `src/world/map.py` — procedural 20x20 grid, terrain types: floor/wall/water/forest, seeded RNG. `find_spawn_point()` finds clear tile near center (radius 2).
- `src/world/objects.py` — places rock×5, tree×5, chest×3 on passable non-border tiles
- `src/world/init.py` — publishes world to Flux on startup, returns `(spawn_x, spawn_y)`
- `src/perception/translator.py` — reads Flux state, builds natural language description relative to agent facing. Interactable objects show ID, non-interactable show `(not interactable)`.
- `src/perception/models.py` — `AgentState`, `PerceptionResult` dataclasses
- `src/agents/llm.py` — Ollama + OpenAI backends, `LLMError` exception
- `src/agents/prompts.py` — system prompt builder with persona + JSON action format
- `src/agents/agent.py` — `AgentConfig`, `Agent` class, full async loop, graceful error handling
- `src/actions/processor.py` — validates move/interact/wait, applies outcomes to Flux
- `src/frontend/server.py` — aiohttp on 0.0.0.0:8083, serves static files, `POST /reset` endpoint
- `src/frontend/static/` — index.html, app.js, style.css — 2D canvas map + activity feed
- `docker-compose.yml` — thegrid's own Flux instance (port 3000), isolated from dev Flux
- `main.py` — wires everything together, safe spawn, reset closure

---

## Key Decisions Made

- Flux used as world state engine — no SQLite, no custom persistence
- Flux stream names must use dots not hyphens (`agent.state` not `agent-state`)
- Flux entity IDs with `/` must be URL-encoded when used in HTTP path (`quote(id, safe="")`)
- Agent keeps local state (x, y, facing) — Flux is broadcast layer, not source of truth for running agent
- Non-interactable objects in perception description show `(not interactable)` with no ID — prevents LLM from attempting to interact
- Safe spawn: find tile near center where all tiles within radius 2 are passable
- Frontend served by aiohttp from thegrid — no separate web server needed
- Flux WebSocket `state_update` messages arrive one property at a time — JS fetches full entity on `last_action` change to get coherent feed entry
- Reset button clears Flux, reinitializes world, resets Aria to new spawn point

---

## Known Bugs / Open Issues

1. **Map not updating** — Aria's position does not move on the canvas despite correct x/y in Flux. Suspected JS issue — object x/y cast fix was applied but not verified. Console.log added for diagnosis.

2. **Aria fixates on distant chest** — sees chest in perception, tries `interact` every cycle instead of moving toward it first. System prompt gives no guidance on multi-step goals. Needs prompt improvement.

3. **Reset endpoint is slow** — deletes 400+ entities one-by-one. Should use Flux batch delete API (`POST /api/state/entities/delete` with prefix filter).

---

## Infrastructure Notes

- Dev server: <DEV_VM_IP>
- Flux runs via `docker compose up -d` in `<PROJECT_DIR>`
- thegrid started via `source venv/bin/activate && python main.py`
- Frontend accessible at `http://<DEV_VM_IP>:8083` from Windows browser
- Flux API at `http://localhost:3000`, UI at `http://localhost:8082` (not running for thegrid)
- OpenAI (`gpt-4o-mini`) used for Aria — Ollama not available yet
- Never use bare `python` — always use venv

---

## Next Steps / Open Discussion

- Fix map canvas position update bug
- Fix Aria fixation / system prompt improvement
- Fix reset endpoint to use batch delete
- Discuss: stuck detection (Aria trapped by walls despite safe spawn)
- Discuss: Aria's internal state changes (bored, curious, etc.) — not yet dynamic
- Discuss: world size — 20x20 may be too small, objects too sparse
- Discuss: agent loop delay — 5s feels slow for observation, consider 3s
