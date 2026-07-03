import streamlit as st

# ── Page config (must be first Streamlit call) ──
st.set_page_config(
    page_title="Genetic Counselling Workbench",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom styling ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
    --primary: #2E3B4E;
    --accent: #6B8CAE;
    --success: #5C946E;
    --warning: #D97E4A;
    --error: #C05746;
    --bg-light: #F5F7FA;
    --text-secondary: #5A6C7D;
}

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Clean chat appearance */
.stChatMessage { border-radius: 12px; }
[data-testid="stSidebar"] { 
    background-color: #1E293B; 
    color: #F8FAFC; 
}
[data-testid="stSidebar"] [data-testid="stButton"] button {
    text-align: left;
    font-size: 0.85rem;
    border-radius: 8px;
    padding: 0.4rem 0.6rem;
    background-color: #334155;
    color: #F8FAFC;
    border: none;
}
[data-testid="stSidebar"] [data-testid="stButton"] button:hover {
    background-color: #475569;
}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] span {
    color: #E2E8F0 !important;
}

/* Toggle pills */
.stToggle label { font-size: 0.85rem; font-weight: 500; }

/* Compact header */
h1 { font-size: 1.6rem !important; margin-bottom: 0.5rem !important; }
</style>
""", unsafe_allow_html=True)

# ── Render sidebar (returns active conversation_id) ──
from ui.sidebar_view import render_sidebar
conversation_id = render_sidebar()

# ── Render main chat ──
from ui.chat_view import display_chat
display_chat(conversation_id)
