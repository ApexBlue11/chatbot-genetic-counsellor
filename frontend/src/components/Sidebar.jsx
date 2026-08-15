import { useState } from 'react';
import { MessageSquare, Plus, Trash2, Edit2, Check, X, Dna } from 'lucide-react';
import ConnectionStatus from './ConnectionStatus';

function Sidebar({ conversations, activeConversation, onSelect, onNewChat, onDelete, onRename, onGoHome, busy = false, backend }) {
  const [editingId, setEditingId] = useState(null);
  const [editTitle, setEditTitle] = useState('');

  const startEdit = (e, conv) => {
    e.stopPropagation();
    setEditingId(conv.id);
    setEditTitle(conv.title);
  };

  const saveEdit = (e) => {
    e.stopPropagation();
    if (editTitle.trim()) {
      onRename(editingId, editTitle.trim());
    }
    setEditingId(null);
  };

  const cancelEdit = (e) => {
    e.stopPropagation();
    setEditingId(null);
  };

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        {/* Same mark as the chat header, so the two sides of the app agree. */}
        <button className="sidebar-brand" onClick={onGoHome} title="Back to the overview">
          <span className="sidebar-brand-mark">
            <Dna size={16} />
          </span>
          <span>
            <span className="sidebar-brand-name">VariantMind</span>
            <span className="sidebar-brand-sub">Back to overview</span>
          </span>
        </button>

        <button
          className="new-chat-btn"
          onClick={onNewChat}
          disabled={busy || (backend && !backend.isOnline)}
          title={backend && !backend.isOnline ? 'Waiting for the analysis server to wake up' : undefined}
        >
          <Plus size={16} /> {busy ? 'Starting…' : 'New Conversation'}
        </button>
      </div>

      <div className="sidebar-section-label">Recent</div>

      <div className="conversation-list">
        {conversations.length === 0 && (
          <div className="sidebar-empty">
            No conversations yet.
            <br />
            Start one to begin analysing variants.
          </div>
        )}

        {conversations.map((conv) => (
          <div
            key={conv.id}
            className={`conversation-item ${activeConversation === conv.id ? 'active' : ''}`}
            onClick={() => onSelect(conv.id)}
          >
            {editingId === conv.id ? (
              <div style={{ display: 'flex', width: '100%', gap: '0.25rem' }}>
                <input
                  autoFocus
                  className="conversation-title-input"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') saveEdit(e);
                    if (e.key === 'Escape') cancelEdit(e);
                  }}
                />
                <button className="action-btn" onClick={saveEdit} aria-label="Save title">
                  <Check size={14} />
                </button>
                <button className="action-btn" onClick={cancelEdit} aria-label="Cancel">
                  <X size={14} />
                </button>
              </div>
            ) : (
              <>
                <MessageSquare size={14} className="conversation-icon" />
                <div className="conversation-title">{conv.title}</div>
                <div className="conversation-actions">
                  <button
                    className="action-btn"
                    onClick={(e) => startEdit(e, conv)}
                    aria-label="Rename conversation"
                  >
                    <Edit2 size={13} />
                  </button>
                  <button
                    className="action-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(conv.id);
                    }}
                    aria-label="Delete conversation"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>

      <div className="sidebar-footer">
        <span>{conversations.length} conversation{conversations.length === 1 ? '' : 's'}</span>
        {backend ? (
          <ConnectionStatus status={backend.status} onRetry={backend.retry} />
        ) : (
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <span className="sidebar-footer-dot" />
            Research use
          </span>
        )}
      </div>
    </div>
  );
}

export default Sidebar;
