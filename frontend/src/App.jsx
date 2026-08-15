import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import RuixenMoonChat from './components/ui/ruixen-moon-chat';
import AILoader from './components/ui/ai-loader';
import WelcomePage from './components/ui/welcome-page';
import api from './services/api';
import useBackendStatus from './hooks/useBackendStatus';

function App() {
  const [conversations, setConversations] = useState([]);
  const [activeConversation, setActiveConversation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const backend = useBackendStatus();
  const [currentView, setCurrentView] = useState(() => {
    // The launch choice belongs to the tab, not to the browser forever. Storing
    // it in localStorage meant that clicking "Launch workspace" once hid the
    // intro page permanently, on every future visit.
    localStorage.removeItem('vm_view');
    return sessionStorage.getItem('vm_view') || 'welcome';
  });

  useEffect(() => {
    loadConversations();
  }, []);

  // The first load usually lands while the demo backend is still asleep, so
  // retry once it answers rather than leaving the user on an empty sidebar.
  useEffect(() => {
    if (backend.isOnline) loadConversations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backend.isOnline]);

  const DEFAULT_TITLE = "New Conversation";

  const loadConversations = async () => {
    try {
      const convs = await api.getConversations();
      setConversations(convs);
      setError(null);

      if (convs.length > 0 && !activeConversation) {
        setActiveConversation(convs[0].id);
      } else if (convs.length === 0) {
        handleNewChat();
      }
    } catch (err) {
      console.error("Failed to load conversations", err);
      // While the server is still waking the status indicator already explains
      // what is happening; a red banner on top of it is just noise.
      if (backend.status === 'offline') setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleNewChat = async () => {
    // An untouched chat keeps the default title (it is renamed on first
    // message), so reuse it instead of stacking up more empty rows.
    const spare = conversations.find(c => c.title === DEFAULT_TITLE);
    if (spare) {
      setActiveConversation(spare.id);
      setError(null);
      return;
    }

    if (!backend.isOnline) {
      setError('The analysis server is still waking up. This can take up to a minute — the dot in the sidebar turns green when it is ready.');
      return;
    }

    setBusy(true);
    try {
      const newConv = await api.createConversation(DEFAULT_TITLE);
      setConversations(prev => [newConv, ...prev]);
      setActiveConversation(newConv.id);
      setError(null);
    } catch (err) {
      console.error("Failed to create chat", err);
      setError(`Could not start a new conversation. ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteChat = async (id) => {
    try {
      await api.deleteConversation(id);
      const remaining = conversations.filter(c => c.id !== id);
      setConversations(remaining);
      setError(null);
      if (activeConversation === id) {
        setActiveConversation(remaining.length > 0 ? remaining[0].id : null);
        if (remaining.length === 0) {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error("Failed to delete chat", err);
      setError(`Could not delete that conversation. ${err.message}`);
    }
  };

  const handleRenameChat = async (id, title) => {
    const previous = conversations;
    setConversations(prev => prev.map(c => c.id === id ? { ...c, title } : c));
    try {
      await api.renameConversation(id, title);
      setError(null);
    } catch (err) {
      console.error("Failed to rename chat", err);
      setConversations(previous);            // roll the optimistic update back
      setError(`Could not rename that conversation. ${err.message}`);
    }
  };

  const handleLaunchWorkspace = () => {
    setCurrentView('chat');
    sessionStorage.setItem('vm_view', 'chat');
  };

  const handleGoHome = () => {
    setCurrentView('welcome');
    sessionStorage.setItem('vm_view', 'welcome');
  };

  if (loading) {
    return <AILoader text="VariantMind" />;
  }

  if (currentView === 'welcome') {
    return <WelcomePage onLaunch={handleLaunchWorkspace} backend={backend} />;
  }

  return (
    <div className="app-container animate-fade-in">
      <Sidebar
        conversations={conversations}
        activeConversation={activeConversation}
        onSelect={setActiveConversation}
        onNewChat={handleNewChat}
        onDelete={handleDeleteChat}
        onRename={handleRenameChat}
        onGoHome={handleGoHome}
        busy={busy}
        backend={backend}
      />
      <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
        {error && (
          <div className="app-error-banner" role="alert">
            <span>{error}</span>
            <button onClick={() => { setError(null); loadConversations(); }}>Retry</button>
            <button onClick={() => setError(null)} aria-label="Dismiss">×</button>
          </div>
        )}
        <RuixenMoonChat
          activeConversation={activeConversation}
          onChatUpdated={loadConversations}
        />
      </div>
    </div>
  );
}

export default App;
