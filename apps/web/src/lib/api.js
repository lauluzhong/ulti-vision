import { env } from '$env/dynamic/public';

const API_BASE = (env.PUBLIC_API_BASE_URL || '/api').replace(/\/$/, '');

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

async function parseResponse(response) {
  const isJson = response.headers.get('content-type')?.includes('application/json');
  const payload = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const message =
      typeof payload === 'string'
        ? payload
        : payload?.detail || payload?.message || `Request failed with ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

async function request(path, init = {}) {
  const response = await fetch(apiUrl(path), init);
  return parseResponse(response);
}

export async function submitLocalGame({ upload, gameId, fps = 1 }) {
  const form = new FormData();
  form.append('upload', upload);
  form.append('fps', String(fps));
  if (gameId) {
    form.append('game_id', gameId);
  }
  return request('/ingest', {
    method: 'POST',
    body: form
  });
}

export async function submitRemoteGame({ url, ackRights, callerId, gameId, fps = 1 }) {
  const form = new FormData();
  form.append('url', url);
  form.append('ack_rights', ackRights ? 'true' : 'false');
  form.append('caller_id', callerId || 'web');
  form.append('fps', String(fps));
  if (gameId) {
    form.append('game_id', gameId);
  }
  return request('/ingest', {
    method: 'POST',
    body: form
  });
}

export async function fetchJobStatus(gameId) {
  return request(`/jobs/${gameId}`);
}

export async function fetchGameEvents(gameId) {
  return request(`/games/${gameId}/events`);
}

export async function fetchGamePoints(gameId) {
  return request(`/games/${gameId}/points`);
}

export function gameVideoUrl(gameId) {
  return apiUrl(`/games/${gameId}/video`);
}

export async function submitCorrection(gameId, payload) {
  return request(`/games/${gameId}/corrections`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
}

export async function updatePointBoundaries(gameId, payload) {
  return request(`/games/${gameId}/points`, {
    method: 'PUT',
    headers: {
      'content-type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
}
