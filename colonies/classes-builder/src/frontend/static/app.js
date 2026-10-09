// Flux runs on the same host that serves this page, on port 3000.
const FLUX_HOST = window.location.hostname;
const FLUX_HTTP = `http://${FLUX_HOST}:3000`;
const FLUX_WS = `ws://${FLUX_HOST}:3000/api/ws`;
const TILE_SIZE = 24;

const TERRAIN_COLOURS = {
  floor: '#d4d4d4',
  wall: '#374151',
  water: '#3b82f6',
  forest: '#16a34a',
};

// State
const tiles = {};   // tiles[x][y] = {terrain_type, passable}
const objects = {}; // objects[object_id] = {type, x, y, interactable, opened}
const agents = {};  // agents[agent_id] = {name, x, y, facing}
const lastActions = {}; // agents[agent_id] = last seen last_action value

const canvas = document.getElementById('map');
const ctx = canvas.getContext('2d');
const feed = document.getElementById('feed');

// ── Helpers ──────────────────────────────────────────────────────────────────

function terrainColour(type) {
  return TERRAIN_COLOURS[type] || '#9ca3af';
}

function worldBounds() {
  let maxX = 0;
  let maxY = 0;
  for (const x in tiles) {
    if (+x > maxX) maxX = +x;
    for (const y in tiles[x]) {
      if (+y > maxY) maxY = +y;
    }
  }
  return { width: maxX + 1, height: maxY + 1 };
}

// ── Rendering ─────────────────────────────────────────────────────────────────

function renderMap() {
  const { width, height } = worldBounds();
  canvas.width = width * TILE_SIZE;
  canvas.height = height * TILE_SIZE;

  // Tiles
  for (const x in tiles) {
    for (const y in tiles[x]) {
      const tile = tiles[x][y];
      ctx.fillStyle = terrainColour(tile.terrain_type);
      ctx.fillRect(+x * TILE_SIZE, +y * TILE_SIZE, TILE_SIZE, TILE_SIZE);
    }
  }

  // Objects
  for (const id in objects) {
    const obj = objects[id];
    const cx = obj.x * TILE_SIZE + TILE_SIZE / 2;
    const cy = obj.y * TILE_SIZE + TILE_SIZE / 2;

    if (obj.type === 'chest') {
      ctx.fillStyle = '#92400e';
      ctx.strokeStyle = '#92400e';
      ctx.lineWidth = 1.5;
      if (obj.opened) {
        ctx.strokeRect(cx - 4, cy - 4, 8, 8);
      } else {
        ctx.fillRect(cx - 4, cy - 4, 8, 8);
      }
    } else if (obj.type === 'rock') {
      ctx.fillStyle = '#6b7280';
      ctx.beginPath();
      ctx.arc(cx, cy, 5, 0, Math.PI * 2);
      ctx.fill();
    } else if (obj.type === 'tree') {
      ctx.fillStyle = '#15803d';
      ctx.beginPath();
      ctx.arc(cx, cy, 5, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Agents
  for (const id in agents) {
    const agent = agents[id];
    const cx = agent.x * TILE_SIZE + TILE_SIZE / 2;
    const cy = agent.y * TILE_SIZE + TILE_SIZE / 2;

    // Body
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(cx, cy, 10, 0, Math.PI * 2);
    ctx.fill();

    // Direction indicator
    const dirs = {
      north: [0, -1],
      south: [0, 1],
      east:  [1, 0],
      west:  [-1, 0],
    };
    const dir = dirs[agent.facing] || [0, -1];
    ctx.strokeStyle = '#111827';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + dir[0] * 10, cy + dir[1] * 10);
    ctx.stroke();

    // Name label
    ctx.fillStyle = '#e5e7eb';
    ctx.font = '9px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(agent.name || id, cx, cy + 22);
  }
}

// ── Activity Feed ─────────────────────────────────────────────────────────────

function addFeedEntry(agent, props) {
  const action = props.last_action || '';
  const feedback = props.last_feedback || '';
  const reasoning = props.last_reasoning || '';
  const name = props.name || agent;

  const now = new Date();
  const time = now.toTimeString().slice(0, 8);

  const entry = document.createElement('div');
  entry.className = 'feed-entry';
  entry.innerHTML =
    `<span class="feed-agent">[${name}]</span> <span class="feed-action">${escapeHtml(action)}</span>` +
    (reasoning ? `<span class="feed-reasoning">${escapeHtml(reasoning)}</span>` : '') +
    `<span class="feed-feedback">${escapeHtml(feedback)}</span>` +
    `<span class="feed-time">── ${time} ──</span>`;

  feed.prepend(entry);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── State Parsing ─────────────────────────────────────────────────────────────

function parseTileId(entityId) {
  // world/tile/{x}/{y}
  const parts = entityId.split('/');
  if (parts.length >= 4) {
    return { x: +parts[2], y: +parts[3] };
  }
  return null;
}

function parseObjectId(entityId) {
  // world/object/{object_id}
  const parts = entityId.split('/');
  if (parts.length >= 3) {
    return parts.slice(2).join('/');
  }
  return null;
}

function parseAgentId(entityId) {
  // agent/{agent_id}  (not agent/.../action)
  const parts = entityId.split('/');
  if (parts.length === 2) {
    return parts[1];
  }
  return null;
}

// ── Initial Load ──────────────────────────────────────────────────────────────

async function loadInitialState() {
  const res = await fetch(`${FLUX_HTTP}/api/state/entities`);
  const entities = await res.json();

  for (const entity of entities) {
    const id = entity.id;
    const props = entity.properties || {};

    if (id.startsWith('world/tile/')) {
      const pos = parseTileId(id);
      if (pos) {
        if (!tiles[pos.x]) tiles[pos.x] = {};
        tiles[pos.x][pos.y] = {
          terrain_type: props.terrain_type || 'floor',
          passable: props.passable !== false,
        };
      }
    } else if (id.startsWith('world/object/')) {
      const objId = parseObjectId(id);
      if (objId) {
        objects[objId] = {
          type: props.type || '',
          x: props.x || 0,
          y: props.y || 0,
          interactable: props.interactable !== false,
          opened: props.opened === true,
        };
      }
    } else if (id.startsWith('agent/') && !id.endsWith('/action')) {
      const agentId = parseAgentId(id);
      if (agentId) {
        agents[agentId] = {
          name: props.name || agentId,
          x: props.x || 0,
          y: props.y || 0,
          facing: props.facing || 'north',
        };
        lastActions[agentId] = props.last_action || '';
      }
    }
  }

  renderMap();
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

function connectWebSocket() {
  const ws = new WebSocket(FLUX_WS);

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'subscribe', entity_id: '*' }));
  };

  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }

    if (msg.type === 'entity_deleted') {
      const id = msg.entity_id;
      if (id.startsWith('world/tile/')) {
        const pos = parseTileId(id);
        if (pos && tiles[pos.x]) delete tiles[pos.x][pos.y];
        renderMap();
      } else if (id.startsWith('world/object/')) {
        const objId = parseObjectId(id);
        if (objId) delete objects[objId];
        renderMap();
      } else if (id.startsWith('agent/') && !id.endsWith('/action')) {
        const agentId = parseAgentId(id);
        if (agentId) delete agents[agentId];
        renderMap();
      }
      return;
    }

    if (msg.type !== 'state_update') return;

    const id = msg.entity_id;
    const prop = msg.property;
    const value = msg.value;

    if (id.startsWith('world/tile/')) {
      const pos = parseTileId(id);
      if (pos) {
        if (!tiles[pos.x]) tiles[pos.x] = {};
        if (!tiles[pos.x][pos.y]) tiles[pos.x][pos.y] = { terrain_type: 'floor', passable: true };
        tiles[pos.x][pos.y][prop] = value;
        renderMap();
      }
    } else if (id.startsWith('world/object/')) {
      const objId = parseObjectId(id);
      if (objId) {
        if (!objects[objId]) objects[objId] = { type: '', x: 0, y: 0, interactable: true, opened: false };
        objects[objId][prop] = (prop === 'x' || prop === 'y') ? +value : value;
        renderMap();
      }
    } else if (id.startsWith('agent/') && !id.endsWith('/action')) {
      const agentId = parseAgentId(id);
      if (agentId) {
        if (!agents[agentId]) agents[agentId] = { name: agentId, x: 0, y: 0, facing: 'north' };
        agents[agentId][prop] = (prop === 'x' || prop === 'y') ? +value : value;

        // Re-fetch full agent props for feed entry if last_action changed
        if (prop === 'last_action' && value && value !== lastActions[agentId]) {
          lastActions[agentId] = value;
          fetch(`${FLUX_HTTP}/api/state/entities/${encodeURIComponent(id)}`)
            .then(r => r.json())
            .then(entity => {
              addFeedEntry(agentId, entity.properties || {});
            })
            .catch(() => {
              addFeedEntry(agentId, agents[agentId]);
            });
        }

        renderMap();
      }
    }
  };

  ws.onclose = () => {
    setTimeout(connectWebSocket, 5000);
  };

  ws.onerror = () => {
    ws.close();
  };
}

// ── Agent Controls ───────────────────────────────────────────────────────────

async function loadAgentStatus() {
  try {
    const res = await fetch('/agent/status');
    const data = await res.json();
    updateStartStopButton(data.running);
    document.getElementById('model-select').value = data.model;
  } catch {
    updateStartStopButton(false);
  }
}

function updateStartStopButton(running) {
  const btn = document.getElementById('start-stop-btn');
  btn.dataset.running = running ? 'true' : 'false';
  btn.textContent = running ? 'Stop Aria' : 'Start Aria';
}

document.getElementById('start-stop-btn').addEventListener('click', async () => {
  const btn = document.getElementById('start-stop-btn');
  const isRunning = btn.dataset.running === 'true';
  btn.disabled = true;
  if (isRunning) {
    await fetch('/agent/stop', { method: 'POST' });
    updateStartStopButton(false);
  } else {
    const model = document.getElementById('model-select').value;
    await fetch('/agent/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    });
    updateStartStopButton(true);
  }
  btn.disabled = false;
});

// ── Reset ────────────────────────────────────────────────────────────────────

document.getElementById('reset-btn').addEventListener('click', async () => {
  const btn = document.getElementById('reset-btn');
  btn.disabled = true;
  btn.textContent = 'Resetting...';
  try {
    await fetch('/reset', { method: 'POST' });
    // Clear local state
    for (const k in tiles) delete tiles[k];
    for (const k in objects) delete objects[k];
    for (const k in agents) delete agents[k];
    for (const k in lastActions) delete lastActions[k];
    feed.innerHTML = '';
    // Reload fresh state from Flux
    await loadInitialState();
    updateStartStopButton(false);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Reset World';
  }
});

// ── Boot ──────────────────────────────────────────────────────────────────────

loadInitialState().then(async () => {
  await loadAgentStatus();
  connectWebSocket();
});
