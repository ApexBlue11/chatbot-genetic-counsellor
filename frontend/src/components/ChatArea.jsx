import { useState, useEffect, useRef } from 'react';
import { Send, Paperclip, Loader2, Bot, Sparkles, Activity, GitBranch, UserCircle, X } from 'lucide-react';
import MessageBubble from './MessageBubble';
import api from '../services/api';

const MAX_VCF_FILES = 3;

function ChatArea({ activeConversation, onChatUpdated }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [attachedFile, setAttachedFile] = useState(null);
  const [patientLabel, setPatientLabel] = useState('');
  const [vcfCount, setVcfCount] = useState(0);
  const [uploadError, setUploadError] = useState('');

  // Toggles
  const [aiEnabled, setAiEnabled] = useState(true);
  const [svEnabled, setSvEnabled] = useState(true);
  const [pedEnabled, setPedEnabled] = useState(false);

  const endOfMessagesRef = useRef(null);
  const currentConvRef = useRef(activeConversation);

  useEffect(() => {
    currentConvRef.current = activeConversation;
    if (activeConversation) {
      loadMessages(activeConversation);
      setVcfCount(0);
      setUploadError('');
    } else {
      setMessages([]);
    }
  }, [activeConversation]);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadMessages = async (id) => {
    try {
      const msgs = await api.getMessages(id);
      setMessages(msgs);
      // Infer VCF count from existing messages
      const uploadCount = msgs.filter(m => m.role === 'user' && m.content?.startsWith('📎 Uploaded')).length;
      setVcfCount(uploadCount);
    } catch (err) {
      console.error('Failed to load messages', err);
    }
  };

  const handleSend = async () => {
    if ((!input.trim() && !attachedFile) || !activeConversation) return;

    const userMsg = input.trim() || `Please analyze: ${attachedFile?.name}`;
    const reqConv = activeConversation;
    const fileToSend = attachedFile;
    const labelToSend = patientLabel.trim() || `Patient-${vcfCount + 1}`;

    setInput('');
    setAttachedFile(null);
    setPatientLabel('');
    setUploadError('');
    setLoading(true);

    try {
      if (fileToSend) {
        // Show user message immediately
        setMessages(prev => [...prev, {
          role: 'user',
          content: `📎 Uploaded \`${fileToSend.name}\` (Patient: **${labelToSend}**)\n\n${userMsg}`
        }]);

        let uploadRes;
        try {
          uploadRes = await api.uploadVcf(reqConv, fileToSend, labelToSend);
        } catch (uploadErr) {
          // Show error message (e.g. 409 max files reached)
          setUploadError(uploadErr.message || 'Upload failed');
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: `⚠️ **Upload failed:** ${uploadErr.message}`
          }]);
          return;
        }

        if (currentConvRef.current !== reqConv) return;

        setVcfCount(uploadRes.total_vcf_count || vcfCount + 1);

        const summaryMsg = {
          role: 'assistant',
          content: uploadRes.summary,
          metadata: { type: 'vcf_analysis', ...uploadRes }
        };
        setMessages(prev => [...prev, summaryMsg]);

        // ── Build system_context from upload response ──
        // Backend already stores enriched JSON and will build the context itself.
        // We pass a lightweight trigger so the AI knows a VCF was just uploaded.
        const contextMode = uploadRes.context_mode || 'basic';
        const systemContext = contextMode === 'deep'
          ? `[VCF uploaded for patient '${labelToSend}'. Deep context mode: full annotations loaded server-side.]`
          : `[VCF uploaded for patient '${labelToSend}'. Basic context mode: ${uploadRes.summary}. Use read_enriched_data tool to drill into specific variants.]`;

        if (aiEnabled) {
          const res = await api.sendMessage(reqConv, userMsg, true, svEnabled, pedEnabled, systemContext);
          if (currentConvRef.current !== reqConv) return;
          setMessages(prev => [...prev, { role: 'assistant', content: res.response, metadata: res.metadata }]);
        }
      } else {
        setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
        if (aiEnabled) {
          const res = await api.sendMessage(reqConv, userMsg, true, svEnabled, pedEnabled, null);
          if (currentConvRef.current !== reqConv) return;
          setMessages(prev => [...prev, { role: 'assistant', content: res.response, metadata: res.metadata }]);
        }
      }
      onChatUpdated();
    } catch (err) {
      console.error(err);
      if (currentConvRef.current !== reqConv) return;
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message || 'Connection failed'}` }]);
    } finally {
      if (currentConvRef.current === reqConv) setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setAttachedFile(file);
    setUploadError('');
    e.target.value = null;
  };

  const filesRemaining = MAX_VCF_FILES - vcfCount;
  const atFileLimit = filesRemaining <= 0;

  if (!activeConversation) {
    return (
      <div className="chat-area" style={{ alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>
        No active conversation
      </div>
    );
  }

  return (
    <div className="chat-area">
      <div className="messages-container">
        {messages.filter(m => m.role !== 'system').map((msg, idx) => (
          <MessageBubble key={idx} message={msg} />
        ))}
        {loading && (
          <div className="message">
            <div className="message-avatar avatar-assistant"><Bot size={18} /></div>
            <div className="message-content" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)' }}>
              <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> Thinking...
            </div>
          </div>
        )}
        <div ref={endOfMessagesRef} />
      </div>

      <div className="input-container">
        {/* Patient label + file badge row */}
        {(attachedFile || uploadError) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.4rem 0.75rem', background: 'var(--bg-body)', borderRadius: '8px 8px 0 0', borderBottom: '1px solid var(--border-color)', flexWrap: 'wrap' }}>
            {attachedFile && (
              <>
                <span style={{ background: 'var(--primary)', color: 'white', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  📎 {attachedFile.name}
                  <button onClick={() => setAttachedFile(null)} style={{ background: 'transparent', border: 'none', color: 'white', cursor: 'pointer', padding: 0, lineHeight: 1 }}>
                    <X size={12} />
                  </button>
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <UserCircle size={14} style={{ color: 'var(--text-secondary)' }} />
                  <input
                    type="text"
                    placeholder={`Patient label (e.g. Proband, Sibling-1)`}
                    value={patientLabel}
                    onChange={e => setPatientLabel(e.target.value)}
                    style={{
                      border: '1px solid var(--border-color)', borderRadius: '6px',
                      padding: '2px 8px', fontSize: '0.78rem', background: 'var(--bg-surface)',
                      color: 'var(--text-primary)', outline: 'none', width: '200px'
                    }}
                  />
                </div>
              </>
            )}
            {uploadError && (
              <span style={{ color: '#EF4444', fontSize: '0.78rem' }}>⚠️ {uploadError}</span>
            )}
          </div>
        )}

        <div className="input-box">
          <textarea
            className="input-textarea"
            placeholder="Ask a question, type a variant ID, or attach a VCF file..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={loading}
          />
          <div className="input-actions">
            <div className="action-toggles">
              {/* VCF upload with file count badge */}
              <label
                className={`upload-btn ${atFileLimit ? 'disabled' : ''}`}
                title={atFileLimit ? 'Max 3 VCF files per conversation' : `Attach VCF file (${filesRemaining} of ${MAX_VCF_FILES} remaining)`}
                style={{ position: 'relative', opacity: atFileLimit ? 0.5 : 1, cursor: atFileLimit ? 'not-allowed' : 'pointer' }}
              >
                <Paperclip size={18} />
                {vcfCount > 0 && (
                  <span style={{
                    position: 'absolute', top: '-6px', right: '-6px',
                    background: vcfCount >= MAX_VCF_FILES ? '#EF4444' : 'var(--primary)',
                    color: 'white', borderRadius: '50%', width: '14px', height: '14px',
                    fontSize: '0.6rem', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700
                  }}>
                    {vcfCount}/{MAX_VCF_FILES}
                  </span>
                )}
                <input type="file" accept=".vcf,.vcf.gz,.txt" onChange={handleFileUpload} disabled={loading || atFileLimit} style={{ display: 'none' }} />
              </label>

              <button className={`toggle-pill ${aiEnabled ? 'active' : ''}`} onClick={() => setAiEnabled(!aiEnabled)} title="Toggle AI Copilot">
                <Sparkles size={14} /> AI Copilot
              </button>
              <button className={`toggle-pill ${svEnabled ? 'active' : ''}`} onClick={() => setSvEnabled(!svEnabled)} title="Toggle Single Variant Search">
                <Activity size={14} /> Single Variant
              </button>
              <button className={`toggle-pill ${pedEnabled ? 'active' : ''}`} onClick={() => setPedEnabled(!pedEnabled)} title="Toggle Pedigree Generator">
                <GitBranch size={14} /> Pedigree Tool
              </button>
            </div>
            <button className="send-btn" onClick={handleSend} disabled={(!input.trim() && !attachedFile) || loading}>
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>

      <div style={{ textAlign: 'center', padding: '0.5rem', fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
        VariantMind is an AI assistant. Results must be interpreted within clinical context and confirmed by a board-certified genetic counselor before clinical decisions are made.
      </div>
    </div>
  );
}

export default ChatArea;
