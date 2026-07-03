"""
Main chat interface: unified view replacing the old 4-tab layout.
Handles text input, VCF uploads, single variant analysis, AI interpretation,
and extended clinical thinking — all within a chat conversation.
"""
import streamlit as st
import json
import re
from typing import Optional

from core.history_db import SQLiteHistoryDB
from core.query_router import GenomicQueryRouter
from core.gemini_client import (
    init_gemini, is_genetics_related, detect_rsid, detect_hgvs,
    generate_with_fallback, generate_with_agent, load_gemini_api_key,
)
from core.api_clients import query_pubmed
from analysis.variant_analyser import VariantAnalyzer, VariantDataFetcher
from analysis.vcf_parser import VCFParser
from analysis.vcf_prioritizer import VCFPrioritizer
from ui.components import render_priority_tabs, render_thinking_block
from analysis.pedigree_streamlit import display_pedigree_generator
from analysis.pedigree_generator import PedigreeGenerator


def _get_db() -> SQLiteHistoryDB:
    if "history_db" not in st.session_state:
        st.session_state.history_db = SQLiteHistoryDB()
    return st.session_state.history_db


def _render_pedigree_result(meta: dict):
    """Re-render a saved pedigree chart from metadata."""
    pedigree_data = meta.get("pedigree_data")
    if pedigree_data:
        try:
            generator = PedigreeGenerator(api_key=load_gemini_api_key())
            image = generator.generate_image(pedigree_data)
            st.image(image, use_container_width=True)
            
            # Download button
            png_bytes = generator.generate_png_bytes(pedigree_data)
            st.download_button(
                "📥 Download Pedigree PNG",
                data=png_bytes,
                file_name="pedigree_tree.png",
                mime="image/png",
                key=f"dl_ped_{hash(json.dumps(pedigree_data))}"
            )
        except Exception as e:
            st.error(f"Error rendering pedigree: {e}")


def display_chat(conversation_id: str):
    """Render the main chat interface for the given conversation."""
    db = _get_db()
    router = GenomicQueryRouter()
    fetcher = VariantDataFetcher()
    analyzer = VariantAnalyzer()

    if st.session_state.get("show_pedigree", False):
        col_chat, col_pedigree = st.columns([1, 1])
        with col_chat:
            _render_chat_column(conversation_id, db, router, fetcher, analyzer)
        with col_pedigree:
            if st.button("❌ Close Pedigree Panel", use_container_width=True):
                st.session_state.show_pedigree = False
                st.rerun()
            display_pedigree_generator()
    else:
        _render_chat_column(conversation_id, db, router, fetcher, analyzer)


def _render_chat_column(conversation_id: str, db, router, fetcher, analyzer):
    """Helper to render the chat feed and input box."""
    # ── Load messages from DB on first render ──
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = db.get_messages(conversation_id)

    # ── Render chat history ──
    for msg in st.session_state.chat_messages:
        if msg["role"] == "system":
            continue
        with st.chat_message(msg["role"]):
            content = msg["content"]
            meta = msg.get("metadata", {})

            has_custom_render = False
            if meta:
                if meta.get("type") == "variant_analysis":
                    _render_variant_result(meta)
                    has_custom_render = True
                elif meta.get("type") == "vcf_analysis":
                    _render_vcf_result(meta)
                    has_custom_render = True
                elif meta.get("type") == "pedigree_chart":
                    _render_pedigree_result(meta)
                    has_custom_render = True

            if not has_custom_render or content:
                st.markdown(content)

    # ── Bottom Input Area ──
    # Create an empty container to push things to the bottom
    st.write("")
    
    # Use pills for mode selection right above chat input
    sv_disabled = st.session_state.get("vcf_active", False)
    modes = ["AI Copilot"]
    if not sv_disabled:
        modes.append("Single Variant")
        
    selected_modes = st.pills(
        "Analysis Modes", 
        options=modes, 
        selection_mode="multi", 
        default=st.session_state.get("selected_modes", modes),
        label_visibility="collapsed"
    )
    st.session_state.selected_modes = selected_modes
    
    ai_enabled = "AI Copilot" in selected_modes
    sv_enabled = "Single Variant" in selected_modes and not sv_disabled

    # ── Chat input with file attach ──
    prompt = st.chat_input("Ask a question, type a variant ID, or describe patient symptoms…", accept_file=True)

    if prompt:
        user_input = prompt.text if hasattr(prompt, 'text') else str(prompt)
        # Check if files were attached in the prompt object (Streamlit 1.35+)
        uploaded_file = None
        if hasattr(prompt, 'files') and prompt.files:
            uploaded_file = prompt.files[0]
            
        _handle_user_input(
            user_input=user_input,
            uploaded_file=uploaded_file,
            conversation_id=conversation_id,
            db=db,
            router=router,
            fetcher=fetcher,
            analyzer=analyzer,
            ai_enabled=ai_enabled,
            sv_enabled=sv_enabled,
        )


def _handle_user_input(
    user_input: str,
    uploaded_file,
    conversation_id: str,
    db: SQLiteHistoryDB,
    router: GenomicQueryRouter,
    fetcher: VariantDataFetcher,
    analyzer: VariantAnalyzer,
    ai_enabled: bool,
    sv_enabled: bool,
):
    """Process user input: detect variant IDs, handle VCF uploads, call AI."""

    # ── VCF file attached ──
    if uploaded_file:
        st.session_state.vcf_active = True
        _handle_vcf_upload(
            uploaded_file=uploaded_file,
            user_input=user_input,
            conversation_id=conversation_id,
            db=db,
            ai_enabled=ai_enabled,
        )
        return

    if not user_input.strip():
        return

    # Save user message
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.chat_messages.append({"role": "user", "content": user_input})
    db.save_message(conversation_id, "user", user_input)

    # Auto-title on first message
    _auto_title_conversation(conversation_id, user_input, db)

    # Reset VCF active flag for text-only messages
    st.session_state.vcf_active = False

    # ── Detect variant identifiers in text ──
    rsid = detect_rsid(user_input)
    hgvs = detect_hgvs(user_input)
    variant_id = rsid or hgvs

    if variant_id and sv_enabled:
        _handle_single_variant(
            variant_id=variant_id,
            user_input=user_input,
            conversation_id=conversation_id,
            db=db,
            router=router,
            fetcher=fetcher,
            analyzer=analyzer,
            ai_enabled=ai_enabled,
        )
    elif ai_enabled:
        _handle_ai_chat(
            user_input=user_input,
            conversation_id=conversation_id,
            db=db,
        )
    else:
        # Neither variant detected nor AI enabled
        with st.chat_message("assistant"):
            st.info("No variant ID detected and AI is disabled. Enable AI or type a variant ID (e.g. rs1801133).")


def _handle_single_variant(
    variant_id, user_input, conversation_id, db, router, fetcher, analyzer, ai_enabled
):
    """Run single variant analysis and optionally AI interpretation."""
    with st.chat_message("assistant"):
        with st.spinner(f"Analyzing variant `{variant_id}`..."):
            classification = router.classify(variant_id)
            variant_data = fetcher.fetch_variant_data(
                variant_id=classification.extracted_identifier,
                query_type=classification.query_type,
            )
            analysis = analyzer.analyze_variant(variant_data)

        # Display results
        st.markdown(f"### 🔬 Analysis: `{variant_id}`")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Pathogenicity", analysis["pathogenicity_prediction"]["classification"])
        with col2:
            st.metric("Confidence", analysis["pathogenicity_prediction"]["confidence"])
        with col3:
            st.metric("Protein Effect", analysis["functional_impact"]["protein_effect"].replace("_", " ").title())

        clin_sig = analysis.get("clinical_relevance", {}).get("clinical_significance", "N/A")
        st.markdown(f"**Clinical Significance:** {clin_sig}")

        # PubMed search for single variant
        pubmed_context = "No literature found."
        papers = []
        
        # Determine gene
        clinvar_data = variant_data.get("clinvar_data", {})
        myvariant_data = variant_data.get("myvariant_data", {})
        gene = "Unknown"
        if clinvar_data and isinstance(clinvar_data, dict) and clinvar_data.get("gene_symbol"):
            gene = clinvar_data.get("gene_symbol")
        elif myvariant_data and isinstance(myvariant_data, dict):
            snpeff_ann = myvariant_data.get('snpeff', {}).get('ann', [])
            snpeff_gene = None
            if isinstance(snpeff_ann, list) and snpeff_ann:
                snpeff_gene = snpeff_ann[0].get('genename') if isinstance(snpeff_ann[0], dict) else None
            elif isinstance(snpeff_ann, dict):
                snpeff_gene = snpeff_ann.get('genename')

            dbnsfp_gene = myvariant_data.get('dbnsfp', {}).get('genename')
            dbnsfp_gene_str = None
            if isinstance(dbnsfp_gene, str):
                dbnsfp_gene_str = dbnsfp_gene
            elif isinstance(dbnsfp_gene, list) and dbnsfp_gene:
                dbnsfp_gene_str = dbnsfp_gene[0]

            gene_candidates = [
                myvariant_data.get('clinvar', {}).get('gene', {}).get('symbol'),
                snpeff_gene,
                dbnsfp_gene_str
            ]
            for candidate in gene_candidates:
                if candidate:
                    gene = candidate
                    break
        
        search_query = f"{variant_id}"
        if gene and gene != "Unknown":
            search_query = f"{gene} AND {variant_id}"
            
        with st.spinner("Searching literature..."):
            papers = query_pubmed(search_query)
            if not papers and gene and gene != "Unknown":
                papers = query_pubmed(variant_id)
            if not papers and gene and gene != "Unknown":
                papers = query_pubmed(gene)
                
            if papers:
                lines = []
                for i, p in enumerate(papers, 1):
                    lines.append(f"{i}. [{p.get('title')}]({p.get('link')}) ({p.get('journal')}, {p.get('pubdate')})")
                pubmed_context = "\n".join(lines)

        if papers:
            with st.expander("📚 Literature References", expanded=False):
                for p in papers:
                    st.markdown(f"- **[{p.get('title')}]({p.get('link')})**\n  *Journal:* {p.get('journal')} ({p.get('pubdate')}) | *Authors:* {p.get('authors')}")

        # Store analysis metadata
        meta = {
            "type": "variant_analysis",
            "variant_id": variant_id,
            "pathogenicity": analysis["pathogenicity_prediction"]["classification"],
            "confidence": analysis["pathogenicity_prediction"]["confidence"],
            "protein_effect": analysis["functional_impact"]["protein_effect"],
            "clinical_significance": clin_sig,
            "literature": papers
        }

        summary = (
            f"Variant `{variant_id}`: {meta['pathogenicity']} "
            f"({meta['confidence']}), {meta['protein_effect'].replace('_', ' ')}"
        )

        # AI interpretation
        if ai_enabled:
            genai = init_gemini()
            if genai:
                with st.spinner("Generating AI interpretation..."):
                    prompt = _build_variant_prompt(variant_id, variant_data, analysis, user_input, pubmed_context)
                    try:
                        response_text, model_used = generate_with_fallback(genai, prompt)
                        report = render_thinking_block(response_text)
                        st.markdown("### 📋 AI Interpretation")
                        st.markdown(report)
                        st.caption(f"Model: {model_used}")
                        summary += f"\n\nAI Interpretation:\n{report[:500]}..."
                    except RuntimeError as e:
                        st.error(f"AI interpretation failed: {e}")

        st.session_state.chat_messages.append({
            "role": "assistant", "content": summary, "metadata": meta,
        })
        db.save_message(conversation_id, "assistant", summary, metadata=meta)


def _handle_vcf_upload(uploaded_file, user_input, conversation_id, db, ai_enabled):
    """Parse VCF, run prioritization, optionally run AI clinical correlation."""
    file_bytes = uploaded_file.getvalue()

    # Save file to DB
    db.save_file(conversation_id, uploaded_file.name, file_bytes, "vcf")

    # Save user message
    display_text = user_input if user_input else f"📎 Uploaded `{uploaded_file.name}`"
    with st.chat_message("user"):
        st.markdown(display_text)
    st.session_state.chat_messages.append({"role": "user", "content": display_text})
    db.save_message(conversation_id, "user", display_text)

    _auto_title_conversation(conversation_id, f"VCF: {uploaded_file.name}", db)

    with st.chat_message("assistant"):
        with st.spinner("Parsing and prioritizing VCF variants..."):
            parser = VCFParser()
            try:
                variants = parser.parse(file_bytes, uploaded_file.name)
            except Exception as e:
                st.error(f"Error parsing VCF: {e}")
                return

            prioritizer = VCFPrioritizer(max_candidates=100)
            prioritized = prioritizer.prioritize_variants(variants)

        st.markdown(f"### 📊 VCF Analysis — {len(variants)} variants")
        render_priority_tabs(prioritized)

        # AI clinical correlation if enabled and user provided symptoms
        if ai_enabled and user_input and user_input.strip():
            _run_clinical_correlation(prioritized, user_input, conversation_id, db)
        elif ai_enabled:
            st.info("💡 To run AI clinical correlation, type patient symptoms alongside the VCF upload.")

        # Save summary
        summary = (
            f"VCF: {len(variants)} variants — "
            f"🔴 {len(prioritized['dangerous'])} dangerous, "
            f"🟡 {len(prioritized['possibly_harmful'])} possibly harmful, "
            f"🔵 {len(prioritized['vus'])} VUS, "
            f"🟢 {len(prioritized['benign'])} benign"
        )
        meta = {"type": "vcf_analysis", "total": len(variants), "summary": summary}
        st.session_state.chat_messages.append({"role": "assistant", "content": summary, "metadata": meta})
        db.save_message(conversation_id, "assistant", summary, metadata=meta)


def _run_clinical_correlation(prioritized, patient_symptoms, conversation_id, db):
    """Run PubMed lookup + Gemini extended thinking for clinical correlation."""
    genai = init_gemini()
    if not genai:
        st.error("Gemini API key not configured.")
        return

    with st.spinner("Searching literature and running clinical extended thinking..."):
        # Collect candidate genes
        candidate_genes = set()
        for cat in ["dangerous", "possibly_harmful", "vus"]:
            for v in prioritized.get(cat, []):
                g = v.get("gene", "")
                if g and g not in ("Unknown", "N/A"):
                    candidate_genes.add(g)

        # PubMed search
        pubmed_context = "No literature found."
        if candidate_genes:
            gene_query = " OR ".join(list(candidate_genes)[:8])
            papers = query_pubmed(gene_query)
            if papers:
                lines = []
                for i, p in enumerate(papers, 1):
                    lines.append(f"{i}. {p.get('title')} ({p.get('journal')}, {p.get('pubdate')})")
                pubmed_context = "\n".join(lines)

        prompt = f"""You are a senior clinical genetics expert. A genetic counselor uploaded a patient VCF and provided symptoms.

[Patient Symptoms & History]
{patient_symptoms}

[Prioritized Variants]
Dangerous: {json.dumps(prioritized['dangerous'][:10], indent=1)}
Possibly Harmful: {json.dumps(prioritized['possibly_harmful'][:10], indent=1)}
VUS: {json.dumps(prioritized['vus'][:15], indent=1)}

[Literature]
{pubmed_context}

Write detailed reasoning inside <clinical_thinking> tags, then a clean Clinical Interpretation Report covering:
1. Clinical Interpretation Summary
2. Prioritized Variant Breakdown
3. Synergy & Pathway Interactions
4. Clinical Recommendations"""

        try:
            response_text, model_used = generate_with_fallback(genai, prompt)
            report = render_thinking_block(response_text)
            st.markdown("### 📋 Clinical Interpretation Report")
            st.markdown(report)
            st.caption(f"Model: {model_used}")
        except RuntimeError as e:
            st.error(f"Clinical correlation failed: {e}")


def _handle_ai_chat(user_input, conversation_id, db):
    """Handle plain AI chat (no variant detected)."""
    genai = init_gemini()
    if not genai:
        with st.chat_message("assistant"):
            st.error("Gemini API key not configured. Place your key in `api_key/gemini_key.txt`.")
        return

    # Build context from history
    history = st.session_state.chat_messages[-10:]  # Last 10 messages for context
    context_parts = [
        "You are a genetics and genomics expert assistant for genetic counselors. "
        "Answer questions about variants, genes, inheritance patterns, and clinical genetics. "
        "You have tools to search PubMed literature, analyze genetic variants, and build pedigree charts. "
        "If a user asks to create/generate a pedigree chart, draw/build a family tree, or similar, use the create_pedigree_chart tool."
    ]
    for msg in history:
        role = msg["role"].upper()
        context_parts.append(f"{role}: {msg['content']}")
    context_parts.append(f"USER: {user_input}")

    prompt = "\n\n".join(context_parts)

    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        def on_status(text):
            status_placeholder.info(text)
            
        try:
            response_text, model_used, metadata = generate_with_agent(genai, prompt, on_status=on_status)
            status_placeholder.empty()
            
            if metadata and metadata.get("type") == "pedigree_chart":
                _render_pedigree_result(metadata)
                
            st.markdown(response_text)
            st.caption(f"Model: {model_used}")

            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": response_text,
                "metadata": metadata
            })
            db.save_message(conversation_id, "assistant", response_text, metadata=metadata)
        except RuntimeError as e:
            status_placeholder.empty()
            st.error(f"AI error: {e}")


# ── Helper renderers for saved messages ──

def _render_variant_result(meta: dict):
    """Re-render a saved variant analysis result from metadata."""
    vid = meta.get("variant_id", "?")
    st.markdown(f"### 🔬 Analysis: `{vid}`")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Pathogenicity", meta.get("pathogenicity", "N/A"))
    with col2:
        st.metric("Confidence", meta.get("confidence", "N/A"))
    with col3:
        effect = meta.get("protein_effect", "N/A").replace("_", " ").title()
        st.metric("Protein Effect", effect)
    st.markdown(f"**Clinical Significance:** {meta.get('clinical_significance', 'N/A')}")
    
    papers = meta.get("literature", [])
    if papers:
        with st.expander("📚 Literature References", expanded=False):
            for p in papers:
                st.markdown(f"- **[{p.get('title')}]({p.get('link')})**\n  *Journal:* {p.get('journal')} ({p.get('pubdate')}) | *Authors:* {p.get('authors')}")


def _render_vcf_result(meta: dict):
    """Re-render a saved VCF analysis summary."""
    st.markdown(f"### 📊 VCF Summary")
    st.markdown(meta.get("summary", "No summary available."))


def _auto_title_conversation(conversation_id: str, text: str, db: SQLiteHistoryDB):
    """Auto-set conversation title from first message if still 'New Conversation'."""
    convs = db.list_conversations()
    for c in convs:
        if c["id"] == conversation_id and c["title"] == "New Conversation":
            # Truncate to first 40 chars
            title = text[:40].strip()
            if len(text) > 40:
                title += "…"
            db.rename_conversation(conversation_id, title)
            break


def _build_variant_prompt(variant_id, variant_data, analysis, user_input, pubmed_context=None):
    """Build a detailed prompt for AI variant interpretation."""
    prompt = f"""You are a clinical genetics expert. Interpret the following variant analysis for a genetic counselor.

User's question: {user_input}
Variant: {variant_id}
Pathogenicity: {analysis['pathogenicity_prediction']['classification']} ({analysis['pathogenicity_prediction']['confidence']})
Protein Effect: {analysis['functional_impact']['protein_effect']}
Clinical Significance: {analysis.get('clinical_relevance', {}).get('clinical_significance', 'N/A')}
"""
    if pubmed_context and pubmed_context != "No literature found.":
        prompt += f"\n[Literature]\n{pubmed_context}\n"

    prompt += f"""
Raw data summary:
- MyVariant: {json.dumps(variant_data.get('myvariant_data', {}), indent=1)[:2000]}
- ClinVar: {json.dumps(variant_data.get('clinvar_data', {}), indent=1)[:1000]}

Write your reasoning inside <clinical_thinking> tags, then provide a clean interpretation report."""
    return prompt
