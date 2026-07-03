import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import api from './services/api';

function App() {
  const [conversations, setConversations] = useState([]);
  const [activeConversation, setActiveConversation] = useState(null);

  useEffect(() => {
    loadConversations();
  }, []);

  const loadConversations = async () => {
    try {
      const convs = await api.getConversations();
      setConversations(convs);
      
      if (convs.length > 0 && !activeConversation) {
        setActiveConversation(convs[0].id);
      } else if (convs.length === 0) {
        handleNewChat();
      }
    } catch (err) {
      console.error("Failed to load conversations", err);
    }
  };

  const handleNewChat = async () => {
    try {
      const newConv = await api.createConversation("New Conversation");
      setConversations(prev => [newConv, ...prev]);
      setActiveConversation(newConv.id);
    } catch (err) {
      console.error("Failed to create chat", err);
    }
  };

  const handleDeleteChat = async (id) => {
    try {
      await api.deleteConversation(id);
      setConversations(prev => prev.filter(c => c.id !== id));
      if (activeConversation === id) {
        const remaining = conversations.filter(c => c.id !== id);
        setActiveConversation(remaining.length > 0 ? remaining[0].id : null);
        if (remaining.length === 0) {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error("Failed to delete chat", err);
    }
  };

  const handleRenameChat = async (id, title) => {
    try {
      await api.renameConversation(id, title);
      setConversations(prev => prev.map(c => c.id === id ? { ...c, title } : c));
    } catch (err) {
      console.error("Failed to rename chat", err);
    }
  };

  return (
    <div className="app-container">
      <Sidebar 
        conversations={conversations}
        activeConversation={activeConversation}
        onSelect={setActiveConversation}
        onNewChat={handleNewChat}
        onDelete={handleDeleteChat}
        onRename={handleRenameChat}
      />
      <ChatArea 
        activeConversation={activeConversation}
        onChatUpdated={loadConversations}
      />
    </div>
  );
}

export default App;
