import streamlit as st
import os
import json
from typing import Dict, Any, List, Optional
from core.history_db import SQLiteHistoryDB

def display_copilot(router, query_clinvar, query_clingen):
    st.session_state.active_tab = 1
    st.markdown('<div class="section-header">Ask the Assistant</div>', unsafe_allow_html=True)

    # Initialize swappable SQLite database
    if "history_db" not in st.session_state:
        st.session_state.history_db = SQLiteHistoryDB()
    
    db = st.session_state.history_db
    session_id = "default_streamlit_session"  # Can be mapped to real user session IDs in production

    # Visual feedback for attached papers
    if "selected_papers" in st.session_state and st.session_state.selected_papers:
        with st.container():
            st.markdown("##### 📎 Attached Literature Context")
            for pmid, paper in st.session_state.selected_papers.items():
                st.markdown(f"- 📄 **{paper.get('title')}** (PMID: {pmid})")
            st.write("")

    # Initialize shared Gemini client
    if "gemini_client" not in st.session_state:
        try:
            import google.generativeai as genai
            api_key = None
            key_file_path = os.path.join("api_key", "gemini_key.txt")
            if os.path.exists(key_file_path):
                try:
                    with open(key_file_path, "r") as f:
                        lines = [line.strip() for line in f.readlines() if line.strip() and not line.strip().startswith("#")]
                        if lines:
                            api_key = lines[0]
                except Exception:
                    pass
            if not api_key:
                api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                st.session_state["gemini_client"] = genai
            else:
                st.session_state["gemini_client"] = None
        except ImportError:
            st.warning("⚠️ `google-generativeai` package not installed. Install it with: `pip install google-generativeai`")
            st.session_state["gemini_client"] = None

    # Load session history from persistent SQLite DB if session_state is empty
    if "copilot_messages" not in st.session_state:
        db_messages = db.get_messages(session_id)
        if db_messages:
            st.session_state.copilot_messages = db_messages
        else:
            st.session_state.copilot_messages = []

    # Display chat history
    for message in st.session_state.copilot_messages:
        # Don't display internal system summaries to the counselor to keep UI clean
        if message["role"] == "system":
            continue
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Clear chat button
    if st.session_state.copilot_messages:
        if st.sidebar.button("🧹 Clear Chat History", key="clear_chat_db"):
            db.clear_session(session_id)
            st.session_state.copilot_messages = []
            st.rerun()

    user_question = st.chat_input("Ask a variant or counseling question…")
    if user_question:
        # Check scope
        from app import is_genetics_related
        if not is_genetics_related(user_question):
            with st.chat_message("assistant"):
                st.warning(" **Out of Scope Query Detected**")
                st.markdown("""
                I'm specifically designed to assist genetic counselors with genetics and genomics-related questions.
                
                Your query doesn't appear to be related to genetics or counseling topics.
                """)
            st.stop()
        
        # Save user question to state and database
        st.session_state.copilot_messages.append({"role": "user", "content": user_question})
        db.save_message(session_id, "user", user_question)
        
        with st.chat_message("user"):
            st.markdown(user_question)

        # Classify the question
        classification = router.classify(user_question)

        genai = st.session_state.get("gemini_client")
        if not genai:
            with st.chat_message("assistant"):
                st.error("⚠️ **Gemini AI not available**")
            st.stop()
            
        with st.spinner("Generating response…"):
            try:
                system_prompt = (
                    "You are a genomics-savvy assistant for genetic counselors. "
                    "Use clinical evidence to answer questions clearly. "
                    "Provide concise, professional guidance."
                )
                
                extra_context = ""
                if classification.is_genomic:
                    clinvar_data = {}
                    try:
                        if classification.query_type == "rsid":
                            clinvar_data = query_clinvar(rsid=classification.extracted_identifier)
                        else:
                            if not classification.extracted_identifier.startswith("NP_"):
                                clingen_raw = query_clingen(classification.extracted_identifier)
                                dbsnp_records = clingen_raw.get("externalRecords", {}).get("dbSNP", [])
                                if dbsnp_records:
                                    rsid = f"rs{dbsnp_records[0].get('rs')}"
                                    clinvar_data = query_clinvar(rsid=rsid)
                        
                        if clinvar_data and "error" not in clinvar_data:
                            extra_context = f"\n\nLive variant context: {json.dumps(clinvar_data)}"
                    except Exception:
                        pass
                
                # Check for selected papers to inject into AI Copilot context
                if 'selected_papers' in st.session_state and st.session_state.selected_papers:
                    papers_context = []
                    for pmid, paper in st.session_state.selected_papers.items():
                        papers_context.append(f"- Title: {paper.get('title')} (PMID: {pmid}, Authors: {paper.get('authors')}, Journal: {paper.get('journal')}, Date: {paper.get('pubdate')})")
                    papers_str = "\n".join(papers_context)
                    extra_context += f"\n\nUser-Selected Relevant Literature:\n{papers_str}"

                # COMPRESSION / SUMMARIZATION THRESHOLD LOGIC
                # If message history grows too long, summarize older messages to save free tokens
                messages_to_send = list(st.session_state.copilot_messages)
                if len(messages_to_send) > 6:
                    st.info("🔄 Optimizing conversation context (compressing older history to save tokens)...")
                    
                    # Call Gemini to compress the first 4 turns
                    compress_model = genai.GenerativeModel('gemini-1.5-flash')
                    turns_to_compress = messages_to_send[:4]
                    formatted_turns = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in turns_to_compress])
                    
                    compress_prompt = (
                        "Summarize this earlier conversation between a genetic counselor and a genomic AI assistant. "
                        "Keep it extremely concise, focusing only on the molecular and clinical conclusions: \n\n"
                        f"{formatted_turns}"
                    )
                    
                    try:
                        compress_resp = compress_model.generate_content(compress_prompt)
                        summary_text = compress_resp.text.strip()
                        
                        # Create system summary message
                        summary_msg = {
                            "role": "system", 
                            "content": f"Summary of earlier conversation: {summary_text}"
                        }
                        
                        # Re-write local session history to replace compressed turns with the summary message
                        messages_to_send = [summary_msg] + messages_to_send[4:]
                        
                        # Persist compressed history to DB
                        db.clear_session(session_id)
                        for msg in messages_to_send:
                            db.save_message(session_id, msg["role"], msg["content"])
                            
                        # Update session state messages
                        st.session_state.copilot_messages = list(messages_to_send)
                    except Exception as ex:
                        # Fallback: slide the window without crashing
                        messages_to_send = messages_to_send[2:]

                model = genai.GenerativeModel('gemini-2.5-flash')
                
                # Format turn list into model content
                model_contents = []
                # First, construct the initial system/instruction guidelines
                model_contents.append({"role": "user", "parts": [{"text": f"{system_prompt}{extra_context}"}]})
                model_contents.append({"role": "model", "parts": [{"text": "Understood. I will act as a genomics-savvy assistant using the provided context."}]})
                
                # Append history turns
                for msg in messages_to_send:
                    # Map system role or regular turns to API roles
                    role = "model" if msg["role"] == "assistant" else "user"
                    model_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

                response = model.generate_content(model_contents)
                answer = response.text
                
            except Exception as e:
                answer = f"Error generating response: {str(e)}"

        # Save assistant answer to state and database
        st.session_state.copilot_messages.append({"role": "assistant", "content": answer})
        db.save_message(session_id, "assistant", answer)
        
        with st.chat_message("assistant"):
            st.markdown(answer)
        st.rerun()
