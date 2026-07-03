import { useState } from 'react';
import { MessageSquare, Plus, Trash2, Edit2, Check, X } from 'lucide-react';

function Sidebar({ conversations, activeConversation, onSelect, onNewChat, onDelete, onRename }) {
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
        <div className="sidebar-title">VariantMind</div>
        <button className="new-chat-btn" onClick={onNewChat}>
          <Plus size={18} /> New Conversation
        </button>
      </div>
      
      <div className="conversation-list">
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
                <button className="action-btn" onClick={saveEdit}><Check size={14} /></button>
                <button className="action-btn" onClick={cancelEdit}><X size={14} /></button>
              </div>
            ) : (
              <>
                <div className="conversation-title">
                  <MessageSquare size={14} style={{ display: 'inline', marginRight: '0.5rem', verticalAlign: 'middle' }} />
                  {conv.title}
                </div>
                <div className="conversation-actions">
                  <button className="action-btn" onClick={(e) => startEdit(e, conv)}>
                    <Edit2 size={14} />
                  </button>
                  <button className="action-btn" onClick={(e) => {
                    e.stopPropagation();
                    onDelete(conv.id);
                  }}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default Sidebar;
