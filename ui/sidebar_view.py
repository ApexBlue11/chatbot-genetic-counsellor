"""
Sidebar: conversation list, new/rename/delete, pedigree tool link, settings.
"""
import streamlit as st
import time
from core.history_db import SQLiteHistoryDB


def _get_db() -> SQLiteHistoryDB:
    if "history_db" not in st.session_state:
        st.session_state.history_db = SQLiteHistoryDB()
    return st.session_state.history_db


def render_sidebar():
    """Render the full sidebar. Returns the active conversation_id."""
    db = _get_db()

    with st.sidebar:
        # ── Header ──
        st.markdown(
            "<h2 style='margin-top:-1rem; font-size:1.4rem; font-weight:600;'>Clinical Variant Copilot</h2>",
            unsafe_allow_html=True,
        )

        # ── New Conversation ──
        if st.button("＋ New Conversation", use_container_width=True, type="primary"):
            conv_id = db.create_conversation("New Conversation")
            st.session_state.active_conversation = conv_id
            st.session_state.pop("chat_messages", None)
            st.session_state.pop("vcf_active", None)
            st.session_state.pop("prioritized_variants", None)
            st.rerun()

        st.divider()

        # ── Conversation list ──
        conversations = db.list_conversations()

        if not conversations:
            st.caption("No conversations yet.")
        else:
            # Ensure we have an active conversation
            if "active_conversation" not in st.session_state:
                st.session_state.active_conversation = conversations[0]["id"]

            for conv in conversations:
                cid = conv["id"]
                is_active = cid == st.session_state.get("active_conversation")
                ts = time.strftime("%b %d", time.localtime(conv["updated_at"]))

                col_btn, col_del = st.columns([5, 1])
                with col_btn:
                    label = f"{'▸ ' if is_active else ''}{conv['title']}"
                    if st.button(label, key=f"conv_{cid}", use_container_width=True):
                        st.session_state.active_conversation = cid
                        st.session_state.pop("chat_messages", None)
                        st.session_state.pop("vcf_active", None)
                        st.session_state.pop("prioritized_variants", None)
                        st.rerun()
                with col_del:
                    if st.button("🗑", key=f"del_{cid}", help="Delete conversation"):
                        db.delete_conversation(cid)
                        if is_active:
                            st.session_state.pop("active_conversation", None)
                            st.session_state.pop("chat_messages", None)
                        st.rerun()

        # ── Rename active conversation ──
        if "active_conversation" in st.session_state:
            active_conv = st.session_state.active_conversation
            convs_map = {c["id"]: c for c in conversations}
            current_title = convs_map.get(active_conv, {}).get("title", "")
            st.markdown("<div style='font-size:0.85rem; font-weight:600; color:#94A3B8; margin-top:0.8rem; margin-bottom:0.4rem;'>RENAME ACTIVE CHAT</div>", unsafe_allow_html=True)
            new_title = st.text_input(
                "Rename active conversation",
                value=current_title,
                key="rename_input",
                label_visibility="collapsed",
                placeholder="Rename active chat...",
            )
            if new_title and new_title != current_title:
                db.rename_conversation(active_conv, new_title)
                st.rerun()
                
        st.divider()

        # ── Tools ──
        st.markdown("<div style='font-size:0.85rem; font-weight:600; color:#94A3B8; margin-bottom:0.5rem;'>TOOLS</div>", unsafe_allow_html=True)
        if st.button("🧬 Pedigree Generator", use_container_width=True):
            st.session_state.show_pedigree = not st.session_state.get("show_pedigree", False)
            st.rerun()

        st.divider()

        # ── Supported formats ──
        with st.expander("📋 Supported Formats", expanded=False):
            st.markdown("""
            **Single Variant** (type in chat):
            - `rs1801133` (rsID)
            - `NM_005957.5:c.665C>T` (HGVS)

            **Batch Analysis** (attach file):
            - `.vcf` / `.vcf.gz` files
            """)

    # Ensure active conversation exists
    if "active_conversation" not in st.session_state:
        conv_id = db.create_conversation("New Conversation")
        st.session_state.active_conversation = conv_id

    return st.session_state.active_conversation
