const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '') + '/api';

const api = {
  getConversations: async () => {
    const res = await fetch(`${API_BASE}/conversations`);
    return res.json();
  },
  
  createConversation: async (title) => {
    const res = await fetch(`${API_BASE}/conversations/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title })
    });
    return res.json();
  },
  
  deleteConversation: async (id) => {
    await fetch(`${API_BASE}/conversations/${id}`, { method: 'DELETE' });
  },
  
  renameConversation: async (id, title) => {
    await fetch(`${API_BASE}/conversations/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title })
    });
  },
  
  getMessages: async (id) => {
    const res = await fetch(`${API_BASE}/conversations/${id}/messages`);
    return res.json();
  },
  
  sendMessage: async (conversationId, userInput, aiEnabled, svEnabled, pedEnabled = false, systemContext = null) => {
    const res = await fetch(`${API_BASE}/chat/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: conversationId,
        user_input: userInput,
        ai_enabled: aiEnabled,
        sv_enabled: svEnabled,
        ped_enabled: pedEnabled,
        system_context: systemContext
      })
    });
    if (!res.ok) throw new Error("Failed to send message");
    return res.json();
  },
  
  uploadVcf: async (conversationId, file, patientLabel = '') => {
    const formData = new FormData();
    formData.append('conversation_id', conversationId);
    formData.append('patient_label', patientLabel);
    formData.append('file', file);
    
    const res = await fetch(`${API_BASE}/upload/`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || 'Failed to upload VCF');
    }
    return res.json();
  },

  
  getVariantDetails: async (variantId) => {
    const res = await fetch(`${API_BASE}/chat/variant/${variantId}`);
    if (!res.ok) throw new Error("Failed to fetch variant details");
    return res.json();
  }
};

export default api;
