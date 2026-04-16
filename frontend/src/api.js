const BASE = '/api';

export async function fetchCompanies() {
  const res = await fetch(`${BASE}/companies`);
  return res.json();
}

export async function fetchUsers(companyId) {
  const res = await fetch(`${BASE}/companies/${companyId}/users`);
  return res.json();
}

export async function searchSync(companyId, userId, query) {
  const res = await fetch(`${BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company_id: companyId, user_id: userId, query }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Search failed');
  }
  return res.json();
}

/**
 * Stream search results via SSE.
 * Calls onEvent({ type, ...data }) for each event.
 * Returns an AbortController to cancel the stream.
 */
export function searchStream(companyId, userId, query, onEvent) {
  const controller = new AbortController();

  fetch(`${BASE}/search/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company_id: companyId, user_id: userId, query }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const err = await res.json();
        onEvent({ type: 'error', text: err.detail || 'Search failed' });
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onEvent(data);
            } catch {
              // skip malformed lines
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onEvent({ type: 'error', text: err.message });
      }
    });

  return controller;
}
