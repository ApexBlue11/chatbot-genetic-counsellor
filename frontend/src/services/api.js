const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '') + '/api';

/**
 * Anonymous per-browser session id.
 *
 * The backend has no accounts and the demo is one shared link over one
 * database, so without this every visitor saw and could delete every other
 * visitor's conversations and uploaded VCFs. Kept in localStorage so a reload
 * does not orphan your own chats.
 */
const SESSION_KEY = 'vm_session_id';

export function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = (crypto.randomUUID?.() ?? `s-${Date.now()}-${Math.random().toString(36).slice(2)}`)
      .replace(/[^A-Za-z0-9_-]/g, '');
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

function withSession(options = {}) {
  return { ...options, headers: { ...(options.headers || {}), 'X-Session-Id': getSessionId() } };
}

/**
 * Every response was previously passed straight to res.json() without checking
 * res.ok, so a 500 resolved to an error body that callers treated as a real
 * record (a conversation with id: undefined), and a dead backend surfaced only
 * as a console message. Failures now throw with something worth showing.
 */
async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, withSession(options));
  } catch {
    throw new Error(
      'Cannot reach the VariantMind backend. It may still be waking up — this can take up to a minute on a free host.'
    );
  }

  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body.detail || body.message || '';
    } catch {
      detail = await res.text().catch(() => '');
    }
    throw new Error(detail || `Request failed (HTTP ${res.status})`);
  }

  if (res.status === 204) return null;
  return res.json().catch(() => null);
}

const api = {
  getConversations: () => request('/conversations/'),

  createConversation: async (title) => {
    const conv = await request('/conversations/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    if (!conv || !conv.id) {
      throw new Error('The backend did not return a conversation id.');
    }
    return conv;
  },

  deleteConversation: (id) => request(`/conversations/${id}`, { method: 'DELETE' }),

  renameConversation: (id, title) =>
    request(`/conversations/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    }),

  getMessages: (id) => request(`/conversations/${id}/messages`),

  sendMessage: (conversationId, userInput, aiEnabled, svEnabled, pedEnabled = false, systemContext = null) =>
    request('/chat/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: conversationId,
        user_input: userInput,
        ai_enabled: aiEnabled,
        sv_enabled: svEnabled,
        ped_enabled: pedEnabled,
        system_context: systemContext,
      }),
    }),

  uploadVcf: (conversationId, file, patientLabel = '') => {
    const formData = new FormData();
    formData.append('conversation_id', conversationId);
    formData.append('patient_label', patientLabel);
    formData.append('file', file);
    return request('/upload/', { method: 'POST', body: formData });
  },

  getVariantDetails: (variantId) => request(`/chat/variant/${variantId}`),

  /**
   * Health probe used by the connection indicator.
   *
   * Free hosts idle their containers, so the first request after a quiet spell
   * can take the better part of a minute. Resolves to true/false rather than
   * throwing, since callers only poll it.
   */
  ping: async (timeoutMs = 8000) => {
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), timeoutMs);
    try {
      const res = await fetch(`${API_BASE}/health`, { signal: abort.signal });
      return res.ok;
    } catch {
      return false;
    } finally {
      clearTimeout(timer);
    }
  },
};

export default api;
