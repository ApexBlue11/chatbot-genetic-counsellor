const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '') + '/api';

/**
 * Every response was previously passed straight to res.json() without checking
 * res.ok, so a 500 resolved to an error body that callers treated as a real
 * record (a conversation with id: undefined), and a dead backend surfaced only
 * as a console message. Failures now throw with something worth showing.
 */
async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, options);
  } catch {
    throw new Error("Can't reach the VariantMind backend. Is it running on port 8000?");
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
};

export default api;
