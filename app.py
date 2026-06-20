import streamlit as st
import requests
import pandas as pd
import json
import time
import re
import os
from urllib.parse import quote
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from core.query_router import GenomicQueryRouter
from core.api_clients import query_clingen, query_myvariant, query_vep, query_clinvar
from core.disease_correlation import correlate_diseases
from analysis.vcf_parser import VCFParser
from analysis.variant_analyser import VariantAnalyzer, VariantDataFetcher
from analysis.pedigree_streamlit import display_pedigree_generator
from ui import styling, layout

# Configure Streamlit page FIRST (must be the first Streamlit command)
st.set_page_config(
    page_title="Genetic Variant Analyzer",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed"  # Sidebar collapsed by default
)

load_dotenv()
styling.inject_css()
layout.header()

# Initialize router and analyzer globally
router = GenomicQueryRouter()
variant_analyzer = VariantAnalyzer()
variant_data_fetcher = VariantDataFetcher()

# Custom CSS for professional styling with modern color palette
st.markdown("""
<style>
:root {
    --primary-color: #2E3B4E;
    --secondary-color: #4A5F7F;
    --accent-color: #6B8CAE;
    --success-color: #5C946E;
    --warning-color: #D97E4A;
    --error-color: #C05746;
    --background-light: #F5F7FA;
    --text-primary: #2E3B4E;
    --text-secondary: #5A6C7D;
    --border-color: #D1DBE8;
}

.main-header {
    font-size: 2.5rem;
    color: var(--primary-color);
    text-align: center;
    margin-bottom: 2rem;
    font-weight: 600;
    letter-spacing: -0.5px;
}

.section-header {
    font-size: 1.5rem;
    color: var(--primary-color);
    border-bottom: 3px solid var(--accent-color);
    padding-bottom: 0.75rem;
    margin: 1.5rem 0 1rem 0;
    font-weight: 600;
}

.success-box {
    background-color: #E8F5EC;
    border-left: 4px solid var(--success-color);
    color: #2D5F3F;
    padding: 1rem 1.25rem;
    border-radius: 0.5rem;
    margin: 1rem 0;
}

.error-box {
    background-color: #FBE9E7;
    border-left: 4px solid var(--error-color);
    color: #7D2E1F;
    padding: 1rem 1.25rem;
    border-radius: 0.5rem;
    margin: 1rem 0;
}

.info-box {
    background-color: #E3EDF7;
    border-left: 4px solid var(--accent-color);
    color: #1E3A5F;
    padding: 1rem 1.25rem;
    border-radius: 0.5rem;
    margin: 1rem 0;
}

.warning-box {
    background-color: #FFF4E5;
    border-left: 4px solid var(--warning-color);
    color: #7D4A1F;
    padding: 1rem 1.25rem;
    border-radius: 0.5rem;
    margin: 1rem 0;
}

.transcript-box {
    background-color: var(--background-light);
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
    padding: 1.25rem;
    margin: 0.75rem 0;
}

.prediction-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.25rem;
    margin: 1.5rem 0;
}

.metric-card {
    background: white;
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
    padding: 1rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

/* Chat message styling */
.stChatMessage {
    background-color: white !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 0.75rem !important;
    padding: 1.25rem !important;
    margin-bottom: 1rem !important;
    color: var(--text-primary) !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
}

.stChatMessage * {
    color: var(--text-primary) !important;
}

/* User message styling */
.stChatMessage[data-testid*="user"] {
    background: linear-gradient(135deg, #6B8CAE 0%, #4A5F7F 100%) !important;
    border: none !important;
}

.stChatMessage[data-testid*="user"] * {
    color: white !important;
}

/* Assistant message styling */
.stChatMessage[data-testid*="assistant"] {
    background-color: var(--background-light) !important;
    border-left: 4px solid var(--accent-color) !important;
}

/* Chat input styling */
.stChatInput {
    border-radius: 0.75rem !important;
    border: 2px solid var(--border-color) !important;
}

.stChatInput:focus-within {
    border-color: var(--accent-color) !important;
    box-shadow: 0 0 0 3px rgba(107, 140, 174, 0.1) !important;
}

/* Tabs styling */
.stTabs [data-baseweb="tab-list"] {
    gap: 2rem;
    background-color: var(--background-light);
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
}

.stTabs [data-baseweb="tab"] {
    color: var(--text-secondary);
    font-weight: 500;
}

.stTabs [aria-selected="true"] {
    color: var(--primary-color);
    border-bottom-color: var(--accent-color);
}

/* Button styling */
.stButton button {
    background-color: var(--secondary-color);
    color: white;
    border: none;
    border-radius: 0.5rem;
    padding: 0.5rem 1.5rem;
    font-weight: 500;
    transition: all 0.2s;
}

.stButton button:hover {
    background-color: var(--primary-color);
    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

/* Dataframe styling */
.dataframe {
    border: 1px solid var(--border-color) !important;
    border-radius: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

# GenomicQueryRouter is imported from core.query_router

# ==================== GEMINI API ONLY ====================

def get_manual_api_key(service: str) -> Optional[str]:
    """Gets the API key from manual input, caches it, and correctly handles Streamlit's rerun."""
    key_name = f"{service.lower()}_api_key"

    if key_name in st.session_state and st.session_state[key_name]:
        return st.session_state[key_name]

    st.warning(f"{service} API key not found. Please enter it below to use the AI Assistant.")
    manual_key = st.text_input(
        f"Enter your {service} API Key:",
        type="password",
        key=f"{key_name}_input",
    )
    if manual_key:
        st.session_state[key_name] = manual_key
        st.rerun()
        st.stop()
    return None

def call_gemini_api(prompt: str, api_key: str, context: List[Dict[str, str]]) -> str:
    """Calls the Google Gemini API (v1) using a stable model from the provided list."""
    # Using a stable model name confirmed from user-provided CSV
    model_name = "gemini-2.5-flash"
    api_url = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    messages = []
    system_instruction = next((msg["content"] for msg in context if msg["role"] == "system"), None)

    history = []
    # Combine context and the current prompt for processing
    full_context = context + [{"role": "user", "content": prompt}]

    # Prepend system instruction to the very first user message in the history
    is_first_user_turn = True
    for msg in full_context:
        if msg["role"] == "system": continue

        role = "user" if msg["role"] == "user" else "model"

        current_content = msg["content"]
        if role == "user" and is_first_user_turn and system_instruction:
            current_content = f"{system_instruction}\n\n---\n\n{current_content}"
            is_first_user_turn = False

        history.append({"role": role, "parts": [{"text": current_content}]})

    payload = {"contents": history}
    st.session_state['last_ai_payload'] = payload

    try:
        with st.spinner(" Gemini is thinking..."):
            response = requests.post(api_url, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            data = response.json()

            if "candidates" not in data or not data["candidates"]:
                feedback = data.get("promptFeedback", {}).get("blockReason", "unknown")
                return f"Gemini response was blocked (reason: {feedback})."

            parts = data["candidates"][0].get("content", {}).get("parts", [])
            text = "".join([p.get("text", "") for p in parts])
            return text.strip() or "Gemini returned an empty response."

    except requests.exceptions.HTTPError as http_err:
        try:
            err_json = http_err.response.json()
            msg = err_json.get("error", {}).get("message", str(http_err))
            st.error(f"Gemini API error: {msg}")
        except Exception:
            st.error(f"Gemini HTTP error: {http_err}")
        return "Gemini request failed. Please check your API key or endpoint."

    except Exception as e:
        st.error(f"Unexpected Gemini error: {e}")
        return "Unexpected Gemini failure occurred."

def generate_summary_prompt(clingen_data: Dict, myvariant_data: Dict, vep_data: List) -> str:
    """Creates a detailed prompt for the AI to summarize the variant data."""
    if myvariant_data and 'dbnsfp' in myvariant_data:
        myvariant_data['dbnsfp'] = {
            k: v for k, v in myvariant_data['dbnsfp'].items()
            if k in ['sift', 'polyphen2_hdiv', 'polyphen2_hvar', 'cadd', 'revel', 'gerp++_rs']
        }
    summary_instruction = """
    Please provide a comprehensive but clear summary of the genetic variant data provided below. Organize your summary into sections:
    1.  **Variant Identification**: State key identifiers (HGVS, RSID, ClinGen Allele ID).
    2.  **Clinical Significance**: Detail ClinVar findings (significance, review status, conditions).
    3.  **Population Frequencies**: Report the highest overall gnomAD allele frequency and its source. Note if the variant is common, rare, etc.
    4.  **Functional Predictions**: Summarize SIFT and PolyPhen predictions (score and qualitative prediction).
    5.  **Transcript/Gene Consequences**: Describe the most significant VEP molecular consequence, affected gene, and impact level.
    **Rules**: Be accurate, traceable to the source data, and clear.
    """
    data_parts = [summary_instruction]
    if clingen_data: data_parts.append(f"**ClinGen Data:**\n{json.dumps(clingen_data, indent=2)}")
    if myvariant_data: data_parts.append(f"**MyVariant.info Data:**\n{json.dumps(myvariant_data, indent=2)}")
    if vep_data: data_parts.append(f"**Ensembl VEP Data:**\n{json.dumps(vep_data, indent=2)}")
    return "\n\n".join(data_parts)

def display_ai_assistant(analysis_data: Optional[Dict]):
    """Renders the AI Assistant UI."""
    st.markdown('<div class="section-header"> AI Assistant</div>', unsafe_allow_html=True)

    st.sidebar.markdown("###  AI Assistant Settings")
    ai_service = st.sidebar.radio("Select AI Service", ('Google Gemini',))

    api_key = get_manual_api_key(ai_service)
    if not api_key:
        st.info(" The AI Assistant is unavailable until an API key is provided.")
        return

    if "messages" not in st.session_state: st.session_state.messages = []
    for message in st.session_state.messages:
        with st.chat_message(message["role"]): st.markdown(message["content"])

    # --- Debugging Section ---
    with st.expander(" AI Debugging Tools"):
        if 'last_ai_payload' in st.session_state:
            st.markdown("**Last Gemini Request Payload:**")
            st.json(st.session_state['last_ai_payload'])
    # --- End Debugging Section ---

    system_prompt = {"role": "system", "content": "You are a knowledgeable assistant specializing in genomics and bioinformatics. Help users understand genetic variant data. When summarizing, be accurate, cite data sources, and be traceable. You can also answer general questions."}

    if analysis_data:
        if st.button(" Summarize & Interpret Results", key="summarize_ai"):
            prompt = generate_summary_prompt(analysis_data.get('clingen_data'), analysis_data.get('annotations', {}).get('myvariant_data'), analysis_data.get('annotations', {}).get('vep_data'))
            st.session_state.messages.append({"role": "user", "content": "Please summarize and interpret the results."})

            response = call_gemini_api(prompt, api_key, context=[system_prompt])

            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()

    if prompt := st.chat_input("Ask a question about the results or a general query..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        ai_response = call_gemini_api(prompt, api_key, context=[system_prompt] + st.session_state.messages)

        with st.chat_message("assistant"): st.markdown(ai_response)
        st.session_state.messages.append({"role": "assistant", "content": ai_response})

# ==================== VARIANT ANALYSIS FUNCTIONS ====================

def query_clingen_allele(hgvs: str) -> Dict[str, Any]:
    """Query ClinGen Allele Registry by HGVS notation with proper URL encoding."""
    base_url = "https://reg.clinicalgenome.org/allele"
    
    # Properly encode HGVS notation for URL
    encoded_hgvs = quote(hgvs, safe='')
    
    # Use encoded version in URL directly
    url = f"{base_url}?hgvs={encoded_hgvs}"

    with st.spinner(f"Querying ClinGen for: {hgvs}"):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                # Try alternative formatting
                # Remove spaces and retry
                cleaned_hgvs = hgvs.replace(" ", "")
                encoded_cleaned = quote(cleaned_hgvs, safe='')
                url = f"{base_url}?hgvs={encoded_cleaned}"
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                return response.json()
            raise

def parse_caid_minimal(raw_json):
    """Parse ClinGen Allele Registry JSON to extract key information."""
    result = {}
    result['CAid'] = raw_json.get('@id', '').split('/')[-1]
    dbsnp = raw_json.get('externalRecords', {}).get('dbSNP', [])
    result['rsid'] = dbsnp[0].get('rs') if dbsnp else None
    genomic = raw_json.get('genomicAlleles', [])
    result['genomic_hgvs_grch38'] = None
    result['genomic_hgvs_grch37'] = None
    for g in genomic:
        hgvs_list = g.get('hgvs', [])
        ref_genome = g.get('referenceGenome', '')
        if 'GRCh38' in ref_genome and hgvs_list:
            result['genomic_hgvs_grch38'] = hgvs_list[0]
        elif 'GRCh37' in ref_genome and hgvs_list:
            result['genomic_hgvs_grch37'] = hgvs_list[0]
    myv = raw_json.get('externalRecords', {})
    result['myvariant_hg38'] = myv.get('MyVariantInfo_hg38', [{}])[0].get('id') if myv.get('MyVariantInfo_hg38') else None
    result['myvariant_hg19'] = myv.get('MyVariantInfo_hg19', [{}])[0].get('id') if myv.get('MyVariantInfo_hg19') else None
    result['mane_ensembl'] = None
    result['mane_refseq'] = None
    transcripts = raw_json.get('transcriptAlleles', [])
    for t in transcripts:
        mane = t.get('MANE', {})
        if mane and mane.get('maneStatus') == 'MANE Select':
            if 'nucleotide' in mane:
                ensembl_info = mane['nucleotide'].get('Ensembl', {})
                refseq_info = mane['nucleotide'].get('RefSeq', {})
                result['mane_ensembl'] = ensembl_info.get('hgvs')
                result['mane_refseq'] = refseq_info.get('hgvs')
            break
    return result

def get_variant_annotations(clingen_data, classification=None):
    """Retrieve variant annotations from multiple APIs."""
    annotations = {'myvariant_data': {}, 'vep_data': [], 'errors': []}
    query_id = None
    if clingen_data.get('myvariant_hg38'):
        query_id = clingen_data['myvariant_hg38']
    elif classification and classification.query_type == 'rsid':
        query_id = classification.extracted_identifier
    if query_id:
        try:
            with st.spinner("Fetching MyVariant.info data..."):
                myv_url = f"https://myvariant.info/v1/variant/{query_id}?assembly=hg38"
                myv_response = requests.get(myv_url, timeout=30)
                if myv_response.ok:
                    myv_raw = myv_response.json()
                    if isinstance(myv_raw, list) and len(myv_raw) > 0:
                        myv_raw = myv_raw[0]
                    annotations['myvariant_data'] = myv_raw
                else:
                    annotations['errors'].append(f"MyVariant query failed: HTTP {myv_response.status_code}")
        except Exception as e:
            annotations['errors'].append(f"MyVariant query error: {str(e)}")
    vep_input = None
    vep_attempted = False
    if clingen_data.get('mane_ensembl'):
        vep_input = clingen_data['mane_ensembl']
        vep_attempted = True
        try:
            with st.spinner("Fetching Ensembl VEP data..."):
                vep_url = f"https://rest.ensembl.org/vep/human/hgvs/{vep_input}"
                vep_headers = {"Content-Type": "application/json", "Accept": "application/json"}
                vep_response = requests.get(vep_url, headers=vep_headers, timeout=30)
                if vep_response.ok:
                    annotations['vep_data'] = vep_response.json()
                else:
                    annotations['errors'].append(f"VEP query with MANE transcript failed: HTTP {vep_response.status_code}")
        except Exception as e:
            annotations['errors'].append(f"VEP query with MANE transcript error: {str(e)}")
    if (classification and classification.query_type == 'rsid' and not annotations['vep_data'] and not vep_attempted):
        vep_input = classification.extracted_identifier
        vep_attempted = True
        try:
            with st.spinner("Fetching Ensembl VEP data with RSID..."):
                vep_url = f"https://rest.ensembl.org/vep/human/hgvs/{vep_input}"
                vep_headers = {"Content-Type": "application/json", "Accept": "application/json"}
                vep_response = requests.get(vep_url, headers=vep_headers, timeout=30)
                if vep_response.ok:
                    annotations['vep_data'] = vep_response.json()
                else:
                    annotations['errors'].append(f"VEP query with RSID failed: HTTP {vep_response.status_code}")
        except Exception as e:
            annotations['errors'].append(f"VEP query with RSID error: {str(e)}")
    if (not annotations['vep_data'] and annotations['myvariant_data'] and isinstance(annotations['myvariant_data'], dict)):
        dbnsfp = annotations['myvariant_data'].get('dbnsfp', {})
        ensembl_data = dbnsfp.get('ensembl', {})
        transcript_ids = ensembl_data.get('transcriptid', [])
        if transcript_ids:
            if isinstance(transcript_ids, list) and len(transcript_ids) > 0:
                primary_transcript = transcript_ids[0]
            else:
                primary_transcript = transcript_ids
            hgvs_coding = dbnsfp.get('hgvsc')
            if hgvs_coding:
                if isinstance(hgvs_coding, list):
                    hgvs_coding = hgvs_coding[0]
                vep_hgvs = f"{primary_transcript}:{hgvs_coding}"
                try:
                    with st.spinner(f"Fetching VEP data with Ensembl transcript {primary_transcript}..."):
                        vep_url = f"https://rest.ensembl.org/vep/human/hgvs/{vep_hgvs}"
                        vep_headers = {"Content-Type": "application/json", "Accept": "application/json"}
                        vep_response = requests.get(vep_url, headers=vep_headers, timeout=30)
                        if vep_response.ok:
                            annotations['vep_data'] = vep_response.json()
                            annotations['vep_fallback_used'] = True
                            st.success(f"VEP fallback successful using transcript {primary_transcript}")
                        else:
                            annotations['errors'].append(f"VEP fallback query failed: HTTP {vep_response.status_code}")
                except Exception as e:
                    annotations['errors'].append(f"VEP fallback query error: {str(e)}")
    return annotations

def select_primary_vep_transcript(vep_data):
    """Select the primary transcript for VEP analysis based on priority."""
    if not vep_data or not vep_data[0].get('transcript_consequences'):
        return None, "No transcript consequences found"
    transcripts = vep_data[0]['transcript_consequences']
    for t in transcripts:
        flags = t.get('flags', [])
        if 'MANE_SELECT' in flags or any('mane' in str(flag).lower() for flag in flags):
            return t, "MANE Select"
    for t in transcripts:
        if t.get('canonical') == 1 or 'canonical' in t.get('flags', []):
            return t, "Canonical"
    for t in transcripts:
        if (t.get('biotype') == 'protein_coding' and 'missense_variant' in t.get('consequence_terms', [])):
            return t, "First protein coding with missense annotation"
    for t in transcripts:
        if t.get('biotype') == 'protein_coding':
            return t, "First protein coding"
    return transcripts[0], "First available transcript"

def display_vep_analysis(vep_data):
    """Display comprehensive VEP analysis."""
    if not vep_data or not vep_data[0].get('transcript_consequences'):
        st.warning("No VEP data available")
        return
    variant_info = vep_data[0]
    all_transcripts = variant_info.get('transcript_consequences', [])
    primary_transcript, selection_reason = select_primary_vep_transcript(vep_data)
    if primary_transcript:
        st.subheader(f"Primary Transcript Analysis")
        col1, col2 = st.columns([2, 1])
        with col1:
            st.write(f"**Transcript:** {primary_transcript.get('transcript_id', 'N/A')}")
            st.write(f"**Gene:** {primary_transcript.get('gene_symbol', 'N/A')} ({primary_transcript.get('gene_id', 'N/A')})")
        with col2:
            st.info(f"**Selection Criteria:** {selection_reason}")
        col1, col2, col3 = st.columns(3)
        with col1:
            consequences = primary_transcript.get('consequence_terms', [])
            st.write(f"**Consequence:** {', '.join(consequences)}")
        with col2:
            st.write(f"**Impact:** {primary_transcript.get('impact', 'N/A')}")
        with col3:
            st.write(f"**Biotype:** {primary_transcript.get('biotype', 'N/A')}")
        if primary_transcript.get('amino_acids'):
            st.subheader("Sequence Changes")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Amino Acid Change:** {primary_transcript.get('amino_acids', 'N/A')}")
                st.write(f"**Position:** {primary_transcript.get('protein_start', 'N/A')}")
            with col2:
                st.write(f"**Codon Change:** {primary_transcript.get('codons', 'N/A')}")
                st.write(f"**CDS Position:** {primary_transcript.get('cds_start', 'N/A')}")
            with col3:
                st.write(f"**cDNA Position:** {primary_transcript.get('cdna_start', 'N/A')}")
        if primary_transcript.get('sift_score') or primary_transcript.get('polyphen_score'):
            st.subheader("Functional Predictions")
            col1, col2 = st.columns(2)
            with col1:
                if primary_transcript.get('sift_score'):
                    st.metric("SIFT Score", f"{primary_transcript['sift_score']:.3f}")
                    st.write(f"**SIFT Prediction:** {primary_transcript.get('sift_prediction', 'N/A')}")
            with col2:
                if primary_transcript.get('polyphen_score'):
                    st.metric("PolyPhen Score", f"{primary_transcript['polyphen_score']:.3f}")
                    st.write(f"**PolyPhen Prediction:** {primary_transcript.get('polyphen_prediction', 'N/A')}")
    with st.expander(f"View All {len(all_transcripts)} Transcripts", expanded=False):
        for i, transcript in enumerate(all_transcripts, 1):
            with st.container():
                st.markdown(f"### Transcript {i}: {transcript.get('transcript_id', 'N/A')}")
                flags = transcript.get('flags', [])
                special_flags = []
                if transcript.get('canonical') == 1: special_flags.append("CANONICAL")
                if 'MANE_SELECT' in flags: special_flags.append("MANE SELECT")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.write(f"**Gene:** {transcript.get('gene_symbol', 'N/A')}")
                    if special_flags: st.success(f" {', '.join(special_flags)}")
                with col2:
                    st.write(f"**Consequence:** {', '.join(transcript.get('consequence_terms', []))}")
                    st.write(f"**Impact:** {transcript.get('impact', 'N/A')}")
                with col3:
                    st.write(f"**Biotype:** {transcript.get('biotype', 'N/A')}")
                    if transcript.get('distance'): st.write(f"**Distance:** {transcript.get('distance', 'N/A')}")
                with col4:
                    if transcript.get('amino_acids'):
                        st.write(f"**AA Change:** {transcript.get('amino_acids', 'N/A')}")
                        st.write(f"**Position:** {transcript.get('protein_start', 'N/A')}")
                if transcript.get('sift_score') or transcript.get('polyphen_score'):
                    pred_col1, pred_col2 = st.columns(2)
                    with pred_col1:
                        if transcript.get('sift_score'): st.write(f"**SIFT:** {transcript['sift_score']:.3f} ({transcript.get('sift_prediction', 'N/A')})")
                    with pred_col2:
                        if transcript.get('polyphen_score'): st.write(f"**PolyPhen:** {transcript['polyphen_score']:.3f} ({transcript.get('polyphen_prediction', 'N/A')})")
                st.markdown("---")

def display_comprehensive_myvariant_data(myvariant_data):
    """Display comprehensive MyVariant.info data analysis."""
    if not myvariant_data:
        st.warning("No MyVariant data available")
        return

    if isinstance(myvariant_data, list):
        if len(myvariant_data) > 1: st.info(f"Multiple variants found ({len(myvariant_data)}). Showing first result.")
        if len(myvariant_data) > 0: myvariant_data = myvariant_data[0]
        else:
            st.warning("Empty response from MyVariant")
            return
    if not isinstance(myvariant_data, dict):
        st.error("Unexpected data format from MyVariant")
        return

    data_tabs = st.tabs([" Basic Info", " Functional Predictions", " Population Frequencies", " ClinVar", " External DBs"])

    with data_tabs[0]:  # Basic Info
        st.subheader("Variant Information")
        col1, col2, col3 = st.columns(3)
        chrom = (myvariant_data.get('hg38', {}).get('chr') or myvariant_data.get('chrom') or 'N/A')
        hg38_data = myvariant_data.get('hg38', {})
        pos = (hg38_data.get('start') or hg38_data.get('end') or hg38_data.get('pos') or myvariant_data.get('pos') or myvariant_data.get('vcf', {}).get('position') or 'N/A')
        ref = (myvariant_data.get('hg38', {}).get('ref') or myvariant_data.get('ref') or myvariant_data.get('vcf', {}).get('ref') or 'N/A')
        alt = (myvariant_data.get('hg38', {}).get('alt') or myvariant_data.get('alt') or myvariant_data.get('vcv', {}).get('alt') or 'N/A')
        with col1:
            st.write(f"**Chromosome:** {chrom}")
            st.write(f"**Position (hg38):** {pos}")
        with col2:
            st.write(f"**Reference:** {ref}")
            st.write(f"**Alternate:** {alt}")
        with col3:
            gene_name = (myvariant_data.get('clinvar', {}).get('gene', {}).get('symbol') or
                         myvariant_data.get('snpeff', {}).get('ann', [{}])[0].get('genename') or
                         (myvariant_data.get('dbnsfp', {}).get('genename') if isinstance(myvariant_data.get('dbnsfp', {}).get('genename'), str) else None) or
                         (myvariant_data.get('dbnsfp', {}).get('genename', [None])[0] if isinstance(myvariant_data.get('dbnsfp', {}).get('genename'), list) else None) or 'N/A')

            st.write(f"**Gene:** {gene_name}")
            rsid = myvariant_data.get('rsid') or myvariant_data.get('dbsnp', {}).get('rsid') or 'N/A'
            st.write(f"**RSID:** {rsid}")
        if myvariant_data.get('clingen'):
            st.subheader("ClinGen Information")
            clingen = myvariant_data['clingen']
            st.write(f"**CAID:** {clingen.get('caid', 'N/A')}")

    with data_tabs[1]:  # Functional Predictions
        st.subheader("Functional Prediction Scores")
        dbnsfp = myvariant_data.get('dbnsfp', {})
        if not dbnsfp:
            st.info("No dbNSFP functional prediction data available")
            return

        def extract_nested_value(data, path_list):
            current = data
            for key in path_list:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return None
            return current

        prediction_categories = {
            "Pathogenicity Predictors": [("SIFT", ["sift", "score"], ["sift", "pred"]), ("PolyPhen2 HDiv", ["polyphen2", "hdiv", "score"], ["polyphen2", "hdiv", "pred"]), ("PolyPhen2 HVar", ["polyphen2", "hvar", "score"], ["polyphen2", "hvar", "pred"]), ("FATHMM", ["fathmm", "score"], ["fathmm", "pred"]), ("MutationTaster", ["mutationtaster", "score"], ["mutationtaster", "pred"]), ("MutationAssessor", ["mutationassessor", "score"], ["mutationassessor", "pred"]), ("PROVEAN", ["provean", "score"], ["provean", "pred"]), ("MetaSVM", ["metasvm", "score"], ["metasvm", "pred"]), ("MetaLR", ["metalr", "score"], ["metalr", "pred"]), ("M-CAP", ["m-cap", "score"], ["m-cap", "pred"]), ("REVEL", ["revel", "score"], None), ("MutPred", ["mutpred", "score"], None), ("LRT", ["lrt", "score"], ["lrt", "pred"])],
            "Conservation Scores": [("GERP++ NR", ["gerp++", "nr"], None), ("GERP++ RS", ["gerp++", "rs"], None), ("PhyloP 100way Vertebrate", ["phylop", "100way_vertebrate", "score"], None), ("PhyloP 470way Mammalian", ["phylop", "470way_mammalian", "score"], None), ("PhastCons 100way Vertebrate", ["phastcons", "100way_vertebrate", "score"], None), ("PhastCons 470way Mammalian", ["phastcons", "470way_mammalian", "score"], None), ("SiPhy 29way", ["siphy_29way", "logodds_score"], None)],
            "Ensemble Predictors": [("CADD Phred", ["cadd", "phred"], None), ("DANN", ["dann", "score"], None), ("Eigen PC Phred", ["eigen-pc", "phred_coding"], None), ("FATHMM-MKL", ["fathmm-mkl", "coding_score"], ["fathmm-mkl", "coding_pred"]), ("FATHMM-XF", ["fathmm-xf", "coding_score"], ["fathmm-xf", "coding_pred"]), ("GenoCanyon", ["genocanyon", "score"], None), ("Integrated FitCons", ["fitcons", "integrated", "score"], None), ("VEST4", ["vest4", "score"], None), ("MVP", ["mvp", "score"], None)],
            "Deep Learning": [("PrimateAI", ["primateai", "score"], ["primateai", "pred"]), ("DEOGEN2", ["deogen2", "score"], ["deogen2", "pred"]), ("BayesDel AddAF", ["bayesdel", "add_af", "score"], ["bayesdel", "add_af", "pred"]), ("ClinPred", ["clinpred", "score"], ["clinpred", "pred"]), ("LIST-S2", ["list-s2", "score"], ["list-s2", "pred"]), ("AlphaMissense", ["alphamissense", "score"], ["alphamissense", "pred"]), ("ESM1b", ["esm1b", "score"], ["esm1b", "pred"])]
        }

        for category, predictors in prediction_categories.items():
            st.markdown(f"#### {category}")
            predictor_data = []
            for predictor_info in predictors:
                if len(predictor_info) == 3: predictor_name, score_path, pred_path = predictor_info
                else: continue
                score_val = extract_nested_value(dbnsfp, score_path)
                if isinstance(score_val, list) and score_val: score_val = score_val[0]
                pred_val = None
                if pred_path:
                    pred_val = extract_nested_value(dbnsfp, pred_path)
                    if isinstance(pred_val, list) and pred_val: pred_val = pred_val[0]
                if score_val is not None:
                    predictor_data.append({'Predictor': predictor_name, 'Score': score_val, 'Prediction': pred_val or 'N/A'})
            if predictor_data:
                cols = st.columns(3)
                for i, pred in enumerate(predictor_data):
                    with cols[i % 3]:
                        score_str = f"{pred['Score']:.3f}" if isinstance(pred['Score'], float) else str(pred['Score'])
                        prediction_text = pred['Prediction']
                        if prediction_text in ['D', 'Damaging', 'DAMAGING']: prediction_color = ""
                        elif prediction_text in ['T', 'Tolerated', 'TOLERATED', 'B', 'Benign']: prediction_color = ""
                        elif prediction_text in ['P', 'Possibly damaging', 'POSSIBLY_DAMAGING']: prediction_color = ""
                        else: prediction_color = ""
                        display_pred = f"{prediction_color} {prediction_text}" if prediction_color else prediction_text
                        st.metric(pred['Predictor'], score_str, delta=display_pred if display_pred != 'N/A' else None)
            else:
                st.info(f"No {category.lower()} data available")

    with data_tabs[2]: # Population Frequencies
        st.subheader("Population Frequency Data")
        freq_tabs = st.tabs(["gnomAD Exome", "gnomAD Genome", "1000 Genomes", "ExAC", "Raw Data"])

        with freq_tabs[0]:
            gnomad_exome = myvariant_data.get('gnomad_exome', {})
            if gnomad_exome:
                st.markdown("**gnomAD Exome v2.1.1**")
                af_data, an_data, ac_data = gnomad_exome.get('af', {}), gnomad_exome.get('an', {}), gnomad_exome.get('ac', {})
                if isinstance(af_data, dict):
                    pop_data = []
                    populations = {'af': 'Overall', 'af_afr': 'African', 'af_amr': 'Latino', 'af_asj': 'Ashkenazi Jewish', 'af_eas': 'East Asian', 'af_fin': 'Finnish', 'af_nfe': 'Non-Finnish European', 'af_sas': 'South Asian', 'af_oth': 'Other'}
                    for pop_key, pop_name in populations.items():
                        freq = af_data.get(pop_key)
                        if freq is not None and freq > 0 and freq <= st.session_state.get('freq_threshold', 1.0):
                            an, ac = an_data.get(pop_key.replace('af', 'an')), ac_data.get(pop_key.replace('af', 'ac'))
                            pop_data.append({'Population': pop_name, 'Frequency': freq, 'Allele Count': ac or 'N/A', 'Total Alleles': an or 'N/A'})
                    if pop_data:
                        df_freq = pd.DataFrame(pop_data).sort_values(by="Frequency", ascending=False)
                        st.dataframe(df_freq, use_container_width=True)
                        chart_data = df_freq.set_index('Population')['Frequency']
                        if not chart_data.empty: st.bar_chart(chart_data)
                    else:
                        st.info("No gnomAD exome populations match the current filter settings.")
                else: st.info("gnomAD exome data format not recognized.")
            else: st.info("No gnomAD exome data available.")

        with freq_tabs[1]:
            gnomad_genome = myvariant_data.get('gnomad_genome', {})
            if gnomad_genome:
                st.markdown("**gnomAD Genome v3.1.2**")
                af_data, an_data, ac_data = gnomad_genome.get('af', {}), gnomad_genome.get('an', {}), gnomad_genome.get('ac', {})
                if isinstance(af_data, dict):
                    pop_data = []
                    populations = {'af': 'Overall', 'af_afr': 'African', 'af_amr': 'Latino', 'af_ami': 'Amish', 'af_asj': 'Ashkenazi Jewish', 'af_eas': 'East Asian', 'af_fin': 'Finnish', 'af_mid': 'Middle Eastern', 'af_nfe': 'Non-Finnish European', 'af_sas': 'South Asian', 'af_oth': 'Other'}
                    for pop_key, pop_name in populations.items():
                        freq = af_data.get(pop_key)
                        if freq is not None and freq > 0 and freq <= st.session_state.get('freq_threshold', 1.0):
                            an, ac = an_data.get(pop_key.replace('af', 'an')), ac_data.get(pop_key.replace('af', 'ac'))
                            pop_data.append({'Population': pop_name, 'Frequency': freq, 'Allele Count': ac or 'N/A', 'Total Alleles': an or 'N/A'})
                    if pop_data:
                        df_freq = pd.DataFrame(pop_data).sort_values(by="Frequency", ascending=False)
                        st.dataframe(df_freq, use_container_width=True)
                        chart_data = df_freq.set_index('Population')['Frequency']
                        if not chart_data.empty: st.bar_chart(chart_data)
                    else:
                        st.info("No gnomAD genome populations match the current filter settings.")

        with freq_tabs[2]: # 1000 Genomes
            kg_data = myvariant_data.get('dbnsfp', {}).get('1000gp3', {})
            if kg_data:
                st.markdown("**1000 Genomes Project Phase 3**")
                if isinstance(kg_data, list): kg_data = kg_data[0] # Handle list case

                pop_data = []
                # Note: dbnsfp provides af for each pop directly
                populations = {'af':'Global', 'afr_af':'African', 'amr_af':'American', 'eas_af':'East Asian', 'eur_af':'European', 'sas_af':'South Asian'}
                for key, name in populations.items():
                    # The key from dbnsfp is slightly different
                    actual_key = key.split('_')[0] if '_' in key else 'af'
                    freq_data = kg_data.get(actual_key)

                    freq = None
                    if isinstance(freq_data, dict):
                        freq = freq_data.get('af')
                    elif actual_key == 'af':
                        freq = kg_data.get('af')


                    if freq is not None and freq > 0 and freq <= st.session_state.get('freq_threshold', 1.0):
                        pop_data.append({'Population': name, 'Frequency': freq})

                if pop_data:
                    st.dataframe(pd.DataFrame(pop_data), use_container_width=True)
                else:
                    st.info("No 1000 Genomes populations match the current filter.")

        with freq_tabs[3]: # ExAC
            exac_data = myvariant_data.get('exac', {}) or myvariant_data.get('dbnsfp', {}).get('exac', {})

            if exac_data:
                st.markdown("**Exome Aggregation Consortium (ExAC)**")
                if isinstance(exac_data, list): exac_data = exac_data[0]
                pop_data = []
                populations = {'af':'Global', 'afr':'African', 'amr':'Latino', 'eas':'East Asian', 'fin':'Finnish', 'nfe':'Non-Finnish European', 'sas':'South Asian', 'oth':'Other'}
                for key, name in populations.items():
                    freq_val = exac_data.get(key)
                    freq = None
                    if isinstance(freq_val, dict):
                        freq = freq_val.get('af')
                    elif isinstance(freq_val, float):
                        freq = freq_val

                    if freq is not None and freq > 0 and freq <= st.session_state.get('freq_threshold', 1.0):
                        pop_data.append({'Population': name, 'Frequency': freq})
                if pop_data:
                    st.dataframe(pd.DataFrame(pop_data), use_container_width=True)
                else:
                    st.info("No ExAC populations match the current filter.")
            else:
                st.info("No ExAC data available.")

        with freq_tabs[4]: # Raw Data
            st.markdown("**All Available Frequency Fields**")
            freq_fields = {}
            def collect_freq_fields(data, prefix=""):
                for key, value in data.items():
                    full_key = f"{prefix}.{key}" if prefix else key
                    if 'af' in key.lower() or 'freq' in key.lower():
                        if isinstance(value, (int, float)) and value > 0 and value <= st.session_state.get('freq_threshold', 1.0):
                            freq_fields[full_key] = value
                    elif isinstance(value, dict):
                        collect_freq_fields(value, full_key)
            collect_freq_fields(myvariant_data)
            if freq_fields:
                st.dataframe(pd.DataFrame([{'Field': k, 'Frequency': v} for k,v in sorted(freq_fields.items())]), use_container_width=True)
            else:
                st.info("No frequency fields match the current filter.")

    with data_tabs[3]: # ClinVar
        st.subheader("ClinVar Clinical Annotations")
        clinvar_data = myvariant_data.get('clinvar', {})
        if not clinvar_data:
            st.info("No ClinVar data available")
            return
        clinical_sig = (clinvar_data.get('clinical_significance') or clinvar_data.get('clnsig') or 'N/A')
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Clinical Significance:** {clinical_sig}")
            if clinvar_data.get('variant_id'): st.write(f"**Variation ID:** {clinvar_data['variant_id']}")
            if clinvar_data.get('allele_id'): st.write(f"**Allele ID:** {clinvar_data['allele_id']}")
        with col2:
            gene_info = clinvar_data.get('gene', {})
            if isinstance(gene_info, dict):
                if gene_info.get('symbol'): st.write(f"**Gene Symbol:** {gene_info['symbol']}")
                if gene_info.get('id'): st.write(f"**Gene ID:** {gene_info['id']}")
        hgvs_info = clinvar_data.get('hgvs', {})
        if isinstance(hgvs_info, dict):
            st.subheader("HGVS Notations")
            col1, col2 = st.columns(2)
            with col1:
                if hgvs_info.get('coding'): st.write(f"**Coding:** {hgvs_info['coding']}")
                if hgvs_info.get('protein'): st.write(f"**Protein:** {hgvs_info['protein']}")
            with col2:
                if hgvs_info.get('genomic'):
                    genomic = hgvs_info['genomic']
                    st.write(f"**Genomic:** {', '.join(genomic) if isinstance(genomic, list) else str(genomic)}")
        rcv_data = clinvar_data.get('rcv', [])
        if rcv_data and isinstance(rcv_data, list):
            st.subheader(f"ClinVar Records ({len(rcv_data)} records)")
            for i, rcv in enumerate(rcv_data, 1):
                if isinstance(rcv, dict):
                    with st.expander(f"Record {i}: {rcv.get('accession', 'N/A')}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Accession:** {rcv.get('accession', 'N/A')}")
                            st.write(f"**Clinical Significance:** {rcv.get('clinical_significance', 'N/A')}")
                            st.write(f"**Review Status:** {rcv.get('review_status', 'N/A')}")
                            st.write(f"**Origin:** {rcv.get('origin', 'N/A')}")
                        with col2:
                            st.write(f"**Last Evaluated:** {rcv.get('last_evaluated', 'N/A')}")
                            st.write(f"**Number of Submitters:** {rcv.get('number_submitters', 'N/A')}")
                            conditions = rcv.get('conditions', {})
                            if isinstance(conditions, dict) and conditions.get('name'):
                                st.write(f"**Condition:** {conditions['name']}")
                                identifiers = conditions.get('identifiers', {})
                                if identifiers:
                                    id_list = [f"{db}: {id_val}" for db, id_val in identifiers.items()]
                                    st.write(f"**Identifiers:** {', '.join(id_list)}")

    with data_tabs[4]: # External DBs
        st.subheader("External Database References")
        dbsnp_data = myvariant_data.get('dbsnp', {})
        if dbsnp_data:
            st.markdown("#### dbSNP")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**RSID:** {dbsnp_data.get('rsid', 'N/A')}")
                st.write(f"**Build:** {dbsnp_data.get('dbsnp_build', 'N/A')}")
                st.write(f"**Variant Type:** {dbsnp_data.get('vartype', 'N/A')}")
            genes = dbsnp_data.get('gene', [])
            if genes and isinstance(genes, list):
                with col2:
                    st.write(f"**Associated Genes:** {len(genes)} genes")
                    for gene in genes[:3]:
                        if isinstance(gene, dict):
                            st.write(f"- {gene.get('symbol', 'N/A')} (ID: {gene.get('geneid', 'N/A')})")
        uniprot_data = myvariant_data.get('uniprot', {})
        if uniprot_data:
            st.markdown("#### UniProt")
            if uniprot_data.get('clinical_significance'): st.write(f"**Clinical Significance:** {uniprot_data['clinical_significance']}")
            if uniprot_data.get('source_db_id'): st.write(f"**Source DB ID:** {uniprot_data['source_db_id']}")

# ==================== MAIN APPLICATION ====================

# Initialize session state for active tab tracking
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = 0

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs(["🧬 Pedigree Generator", "🤖 AI Copilot", "🔬 Single Variant", "📊 VCF Batch"])

# Conditionally render sidebar based on active tab
# The sidebar is rendered here BEFORE tab content to ensure it updates properly
with st.sidebar:
    # Check if we're in Tab 2 by looking at query params or using a workaround
    # We'll populate the sidebar only when needed
    sidebar_placeholder = st.empty()
    
# Store sidebar content function
def render_tab2_sidebar():
    with st.sidebar:
        st.markdown("""
        <div style='background: linear-gradient(135deg, var(--secondary-color) 0%, var(--primary-color) 100%); 
                    padding: 1.25rem; 
                    border-radius: 0.75rem; 
                    margin-bottom: 1.5rem;
                    color: white;'>
            <h3 style='margin: 0 0 0.75rem 0; color: white; font-size: 1.1rem;'>Display Settings</h3>
        </div>
        """, unsafe_allow_html=True)
        
        st.session_state.freq_threshold = st.slider(
            "Max Allele Frequency", 
            min_value=0.0, max_value=1.0, 
            value=st.session_state.get('freq_threshold', 1.0), 
            step=0.001, format="%.3f", 
            help="Filter population frequencies below this threshold"
        )
        
        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
        
        st.markdown("""
        <div style='background-color: var(--background-light); 
                    padding: 1.25rem; 
                    border-radius: 0.75rem;
                    border-left: 4px solid var(--accent-color);'>
            <h4 style='margin: 0 0 0.75rem 0; color: var(--primary-color); font-size: 1rem;'>Supported Formats</h4>
            <div style='background: white; 
                        padding: 1rem; 
                        border-radius: 0.5rem; 
                        font-family: monospace; 
                        font-size: 0.9rem;
                        line-height: 1.8;
                        color: var(--text-primary);'>
                <div style='margin-bottom: 0.5rem;'>
                    <strong style='color: var(--accent-color);'>HGVS:</strong><br/>
                    <span style='color: #2E7D32;'>NM_002496.3:c.64C>T</span>
                </div>
                <div>
                    <strong style='color: var(--accent-color);'>RSID:</strong><br/>
                    <span style='color: #2E7D32;'>rs80359876</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

GENETICS_KEYWORDS = [
    "variant", "mutation", "snp", "indel", "deletion", "insertion", "duplication",
    "rs", "hgvs", "clingen", "clinvar", "dbsnp", "gene", "chromosome", "allele",
    "genotype", "phenotype", "genome", "exon", "intron", "transcript", "protein",
    "amino acid", "nucleotide", "codon", "pathogenic", "benign", "vus", "significance",
    "inheritance", "hereditary", "carrier", "penetrance", "expressivity", "genetic counseling",
    "brca", "cf", "sickle cell", "hemophilia", "huntington", "duchenne", "frequency",
    "gnomad", "exac", "population", "consequence", "impact", "sift", "polyphen",
    "cadd", "revel", "vep", "annotation"
]

def is_genetics_related(query: str) -> bool:
    query_lower = query.lower()
    keyword_match = any(keyword in query_lower for keyword in GENETICS_KEYWORDS)
    hgvs_pattern = any(pattern in query_lower for pattern in ["nm_", "nc_", "ng_", "np_", "p.", "c.", "g."])
    rsid_pattern = "rs" in query_lower and any(char.isdigit() for char in query)
    return keyword_match or hgvs_pattern or rsid_pattern

# --- Tab 1: Pedigree Generator ---
with tab1:
    st.session_state.active_tab = 0
    display_pedigree_generator()

# --- Tab 2: AI Copilot ---
with tab2:
    st.session_state.active_tab = 1
    st.markdown('<div class="section-header">Ask the Assistant</div>', unsafe_allow_html=True)

    # Initialize shared Gemini client
    if "gemini_client" not in st.session_state:
        try:
            import google.generativeai as genai
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                st.session_state["gemini_client"] = genai
            else:
                st.session_state["gemini_client"] = None
        except ImportError:
            st.warning("⚠️ `google-generativeai` package not installed. Install it with: `pip install google-generativeai`")
            st.session_state["gemini_client"] = None

    user_question = st.chat_input("Ask a variant or counseling question…")
    if user_question:
        if not is_genetics_related(user_question):
            with st.chat_message("assistant"):
                st.warning(" **Out of Scope Query Detected**")
                st.markdown("""
                I'm specifically designed to assist genetic counselors with genetics and genomics-related questions.
                
                Your query doesn't appear to be related to genetics or counseling topics.
                """)
            st.stop()
        
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
                    except:
                        pass
                
                model = genai.GenerativeModel('gemini-2.5-flash')
                full_prompt = f"{system_prompt}{extra_context}\n\nQuestion: {user_question}"
                response = model.generate_content(full_prompt)
                answer = response.text
            except Exception as e:
                answer = f"Error generating response: {str(e)}"

        with st.chat_message("assistant"):
            st.markdown(answer)

# --- Tab 3: Single Variant Analysis ---
with tab3:
    st.session_state.active_tab = 2
    
    # Render sidebar for Tab 2
    render_tab2_sidebar()
    
    st.markdown('<div class="section-header"> Single Variant Analysis</div>', unsafe_allow_html=True)
    
    variant_input = st.text_input("Enter a genetic variant (HGVS notation or RSID):", 
                                   placeholder="e.g., NM_002496.3:c.64C>T or rs80359876",
                                   key="variant_input_tab2")
    
    analyze_button = st.button(" Analyze Variant", type="primary", key="analyze_single")
    
    should_analyze = analyze_button and variant_input
    should_show_results = False
    
    if should_analyze:
        if 'sv_analysis_data' not in st.session_state or st.session_state.get('sv_last_query') != variant_input:
            with st.spinner("Analyzing variant..."):
                classification = router.classify(variant_input)
                
                if not classification.is_genomic:
                    st.error(" Invalid format. Please provide a valid HGVS notation or RSID.")
                    st.stop()
                
                try:
                    start_time = time.time()
                    
                    # Handle Gene Symbol, RSID vs HGVS differently
                    if classification.query_type == 'gene_symbol':
                        st.info(f" Gene Symbol detected: Querying ClinVar for '{classification.extracted_identifier}'")
                        variant_data = variant_data_fetcher.fetch_variant_data(
                            variant_id=classification.extracted_identifier,
                            query_type='gene_symbol'
                        )
                        clingen_data = {
                            'CAid': 'N/A (Gene input)',
                            'rsid': 'N/A',
                            'genomic_hgvs_grch38': 'N/A',
                            'genomic_hgvs_grch37': 'N/A',
                            'myvariant_hg38': 'N/A',
                            'mane_ensembl': 'N/A',
                            'mane_refseq': 'N/A'
                        }
                        annotations = {
                            'myvariant_data': variant_data.get('myvariant_data'),
                            'vep_data': variant_data.get('vep_data'),
                            'errors': []
                        }
                        if not annotations['myvariant_data']:
                            annotations['myvariant_data'] = {}
                        annotations['myvariant_data']['clinvar'] = variant_data.get('clinvar_data', {})
                    elif classification.query_type == 'rsid':
                        st.info(" RSID detected - querying MyVariant.info and Ensembl VEP directly")
                        clingen_data = {
                            'CAid': 'N/A (RSID input)', 
                            'rsid': classification.extracted_identifier.replace('rs', ''), 
                            'genomic_hgvs_grch38': None,
                            'genomic_hgvs_grch37': None, 
                            'myvariant_hg38': None, 
                            'myvariant_hg19': None, 
                            'mane_ensembl': None, 
                            'mane_refseq': None
                        }
                        annotations = get_variant_annotations(clingen_data, classification)
                        
                        # Try to get better VEP data
                        if annotations['myvariant_data']:
                            myv_data = annotations['myvariant_data']
                            if isinstance(myv_data, list) and len(myv_data) > 0:
                                myv_data = myv_data[0]
                                annotations['myvariant_data'] = myv_data
                            
                            if isinstance(myv_data, dict):
                                if myv_data.get('clingen', {}).get('caid'): 
                                    clingen_data['CAid'] = myv_data['clingen']['caid']
                                
                                hgvs_data = myv_data.get('clinvar', {}).get('hgvs', {})
                                if isinstance(hgvs_data, dict) and hgvs_data.get('coding'):
                                    try:
                                        vep_url = f"https://rest.ensembl.org/vep/human/hgvs/{hgvs_data['coding']}"
                                        vep_headers = {"Content-Type": "application/json", "Accept": "application/json"}
                                        vep_response = requests.get(vep_url, headers=vep_headers, timeout=30)
                                        if vep_response.ok: 
                                            annotations['vep_data'] = vep_response.json()
                                    except: 
                                        pass
                    else:
                        # HGVS notation - query ClinGen first
                        clingen_raw = query_clingen_allele(classification.extracted_identifier)
                        clingen_data = parse_caid_minimal(clingen_raw)
                        annotations = get_variant_annotations(clingen_data, classification)
                    
                    processing_time = time.time() - start_time
                    
                    st.session_state.sv_analysis_data = {
                        'classification': classification, 
                        'clingen_data': clingen_data, 
                        'annotations': annotations, 
                        'processing_time': processing_time
                    }
                    st.session_state.sv_last_query = variant_input
                    should_show_results = True
                    
                except Exception as e:
                    st.error(f" Analysis failed: {str(e)}")
                    with st.expander("Error Details"):
                        st.exception(e)
                    st.stop()
        else:
            should_show_results = True
    
    elif 'sv_analysis_data' in st.session_state and st.session_state.get('sv_last_query'):
        should_show_results = True
    
    if should_show_results and 'sv_analysis_data' in st.session_state:
        analysis_data = st.session_state.sv_analysis_data
        classification = analysis_data['classification']
        clingen_data = analysis_data['clingen_data']
        annotations = analysis_data['annotations']
        processing_time = analysis_data['processing_time']
        
        # Header with clear button
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button(" Clear Results", key="clear_sv_results"):
                if 'sv_analysis_data' in st.session_state: 
                    del st.session_state['sv_analysis_data']
                if 'sv_last_query' in st.session_state: 
                    del st.session_state['sv_last_query']
                st.rerun()
        with col2: 
            st.markdown(f"**Analyzing:** `{classification.extracted_identifier}`")
        
        # Basic info box
        st.markdown('<div class="info-box">', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1: 
            st.write(f"**Variant ID:** {classification.extracted_identifier}")
        with col2: 
            st.write(f"**Type:** {classification.query_type}")
        st.markdown('</div>', unsafe_allow_html=True)
        
        if classification.query_type == 'gene_symbol':
            st.warning("⚠️ **Gene Search Detected**: ClinVar contains thousands of variants for this gene. Showing a representative variant record.")

        # ClinGen section
        st.markdown('<div class="section-header"> ClinGen Allele Registry & Known Aliases</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**CAid:** {clingen_data.get('CAid', 'N/A')}")
            st.write(f"**RSID:** {clingen_data.get('rsid', 'N/A')}")
        with col2:
            st.write(f"**MANE Ensembl:** {clingen_data.get('mane_ensembl', 'N/A')}")
            st.write(f"**MANE RefSeq:** {clingen_data.get('mane_refseq', 'N/A')}")
        with col3:
            st.write(f"**GRCh38 Genomic:** {clingen_data.get('genomic_hgvs_grch38', 'N/A')}")
            st.write(f"**GRCh37 Genomic:** {clingen_data.get('genomic_hgvs_grch37', 'N/A')}")
        
        # Show any errors
        if annotations.get('errors'):
            with st.expander(" Data Retrieval Warnings", expanded=False):
                for error in annotations['errors']: 
                    st.warning(error)
        
        # Main results tabs (NO RAW DATA TAB)
        if annotations.get('myvariant_data') or annotations.get('vep_data'):
            st.markdown('<div class="section-header"> Analysis Results</div>', unsafe_allow_html=True)
            
            result_tabs = st.tabs([" VEP Analysis", " Functional Predictions", " Clinical Significance", " AI Interpretation"])
            
            # Tab 1: VEP Analysis
            with result_tabs[0]:
                if annotations.get('vep_data'): 
                    display_vep_analysis(annotations['vep_data'])
                else: 
                    st.info("No VEP data available for this variant.")
            
            # Tab 2: MyVariant Functional Data
            with result_tabs[1]:
                if annotations.get('myvariant_data'): 
                    display_comprehensive_myvariant_data(annotations['myvariant_data'])
                else: 
                    st.info("No MyVariant data available.")
            
            # Tab 3: Clinical Significance  
            with result_tabs[2]:
                if annotations.get('myvariant_data'):
                    myvariant_data = annotations['myvariant_data']
                    clinvar_data = myvariant_data.get('clinvar', {})
                    
                    if clinvar_data:
                        st.subheader(" ClinVar Clinical Significance")
                        clinical_sig = clinvar_data.get('clinical_significance') or clinvar_data.get('clnsig') or 'Not Available'
                        
                        # Color-code significance
                        if 'pathogenic' in clinical_sig.lower() and 'benign' not in clinical_sig.lower():
                            sig_color = "#dc3545"
                        elif 'benign' in clinical_sig.lower():
                            sig_color = "#28a745"
                        else:
                            sig_color = "#ffc107"
                        
                        st.markdown(f"""
                        <div style="background-color: {sig_color}; color: white; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
                            <h3 style="margin:0; color:white;">{clinical_sig}</h3>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            if clinvar_data.get('variant_id'): 
                                st.metric("ClinVar ID", clinvar_data['variant_id'])
                        with col2:
                            if clinvar_data.get('allele_id'): 
                                st.metric("Allele ID", clinvar_data['allele_id'])
                        with col3:
                            if clinvar_data.get('review_status'):
                                st.metric("Review Status", clinvar_data['review_status'])
                        
                        # Submission details
                        rcv_data = clinvar_data.get('rcv', [])
                        if rcv_data and isinstance(rcv_data, list):
                            st.subheader(" Submission Details")
                            for idx, rcv in enumerate(rcv_data, 1):
                                if isinstance(rcv, dict):
                                    with st.expander(f"Record {idx}: {rcv.get('accession', 'N/A')}", expanded=(idx==1)):
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.write(f"**Clinical Significance:** {rcv.get('clinical_significance', 'N/A')}")
                                            st.write(f"**Review Status:** {rcv.get('review_status', 'N/A')}")
                                            st.write(f"**Last Evaluated:** {rcv.get('last_evaluated', 'N/A')}")
                                        with col2:
                                            st.write(f"**Origin:** {rcv.get('origin', 'N/A')}")
                                            st.write(f"**Number of Submitters:** {rcv.get('number_submitters', 'N/A')}")
                                            conditions = rcv.get('conditions', {})
                                            if isinstance(conditions, dict) and conditions.get('name'): 
                                                st.write(f"**Associated Condition:** {conditions['name']}")
                    
                    # UniProt data
                    uniprot_data = myvariant_data.get('uniprot', {})
                    if uniprot_data and uniprot_data.get('clinical_significance'):
                        st.subheader(" UniProt Clinical Annotation")
                        st.write(f"**Clinical Significance:** {uniprot_data['clinical_significance']}")
                        if uniprot_data.get('source_db_id'): 
                            st.write(f"**Source:** {uniprot_data['source_db_id']}")
                    
                    # Population frequency context
                    st.subheader(" Population Frequency Context")
                    max_freq, freq_source = 0, "N/A"
                    
                    gnomad_exome = myvariant_data.get('gnomad_exome', {})
                    if gnomad_exome and gnomad_exome.get('af', {}).get('af'):
                        exome_freq = gnomad_exome['af']['af']
                        if exome_freq > max_freq: 
                            max_freq, freq_source = exome_freq, "gnomAD Exome"
                    
                    gnomad_genome = myvariant_data.get('gnomad_genome', {})
                    if gnomad_genome and gnomad_genome.get('af', {}).get('af'):
                        genome_freq = gnomad_genome['af']['af']
                        if genome_freq > max_freq: 
                            max_freq, freq_source = genome_freq, "gnomAD Genome"
                    
                    if max_freq > 0:
                        st.metric(f"Maximum Population Frequency ({freq_source})", f"{max_freq:.6f}")
                        
                        if max_freq >= 0.01: 
                            st.success(" **Common variant** (≥1%) - Likely benign due to high population frequency")
                        elif max_freq >= 0.005: 
                            st.warning(" **Low frequency variant** (0.5-1%) - Moderate rarity")
                        elif max_freq >= 0.0001: 
                            st.info(" **Rare variant** (0.01-0.5%) - Uncommon in populations")
                        else: 
                            st.error(" **Very rare variant** (<0.01%) - Highly uncommon, warrants further investigation")
                    else: 
                        st.info("No reliable population frequency data available")
                else: 
                    st.info("No clinical data available")
            
            # Tab 4: AI Interpretation (Gemini only)
            with result_tabs[3]:
                st.markdown("###  AI-Powered Clinical Interpretation")
                
                if st.button("Generate AI Interpretation", type="primary", key="gen_ai_interp"):
                    genai = st.session_state.get("gemini_client")
                    if not genai:
                        st.error("⚠️ **Gemini AI not available**")
                        st.markdown("""
                        The AI Interpretation feature requires:
                        1. Install: `pip install google-generativeai`
                        2. Set `GEMINI_API_KEY` environment variable
                        3. Restart the app
                        """)
                    else:
                        with st.spinner("Generating comprehensive interpretation..."):
                            try:
                                # Build comprehensive prompt
                                prompt = generate_summary_prompt(
                                    clingen_data, 
                                    annotations.get('myvariant_data'),
                                    annotations.get('vep_data')
                                )
                                
                                try:
                                    model = genai.GenerativeModel('gemini-1.5-flash')
                                    response = model.generate_content(prompt)
                                    ai_interpretation = response.text
                                    
                                    st.markdown(ai_interpretation)
                                    
                                    # Add references if available
                                    myv_data = annotations.get('myvariant_data', {})
                                    if myv_data and myv_data.get('clinvar', {}).get('rcv'):
                                        st.markdown("---")
                                        st.markdown("###  References")
                                        rcv_list = myv_data['clinvar']['rcv']
                                        if isinstance(rcv_list, list):
                                            for rcv in rcv_list[:3]:  # Top 3
                                                if isinstance(rcv, dict) and rcv.get('accession'):
                                                    st.markdown(f"- **ClinVar:** [{rcv['accession']}](https://www.ncbi.nlm.nih.gov/clinvar/{rcv.get('accession', '')})")
                                
                                except Exception as e:
                                    error_msg = str(e)
                                    if "429" in error_msg or "ResourceExhausted" in error_msg:
                                        st.error(" **Rate Limit Exceeded**")
                                        st.markdown("""
                                        The AI service is currently experiencing high demand. Please:
                                        1. Wait 30-60 seconds before trying again
                                        2. Try analyzing a different variant
                                        3. If the issue persists, check your API quota
                                        
                                        [Learn more about rate limits](https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429)
                                        """)
                                    else:
                                        raise
                                
                            except Exception as e:
                                st.error(f"AI interpretation failed: {str(e)}")
                                with st.expander("Error Details"):
                                    st.exception(e)
        
        # Download section
        st.markdown("---")
        st.markdown("###  Download Data")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if clingen_data:
                clingen_json = json.dumps(clingen_data, indent=2)
                st.download_button(
                    label=" ClinGen Data",
                    data=clingen_json,
                    file_name=f"clingen_{classification.extracted_identifier.replace(':', '_').replace('>', '_')}.json",
                    mime="application/json",
                    help="Download ClinGen data"
                )
        
        with col2:
            if annotations.get('myvariant_data'):
                myvariant_json = json.dumps(annotations['myvariant_data'], indent=2)
                st.download_button(
                    label=" MyVariant Data",
                    data=myvariant_json,
                    file_name=f"myvariant_{classification.extracted_identifier.replace(':', '_').replace('>', '_')}.json",
                    mime="application/json",
                    help="Download MyVariant data"
                )
        
        with col3:
            if annotations.get('vep_data'):
                vep_json = json.dumps(annotations['vep_data'], indent=2)
                st.download_button(
                    label=" VEP Data",
                    data=vep_json,
                    file_name=f"vep_{classification.extracted_identifier.replace(':', '_').replace('>', '_')}.json",
                    mime="application/json",
                    help="Download VEP data"
                )
        
        st.success(f" Analysis completed in {processing_time:.2f} seconds")

        # Developer & API Query Logs
        st.markdown("---")
        with st.expander("🛠️ API Query Logs & Raw Response Payloads", expanded=False):
            from core.api_clients import API_LOGS
            if API_LOGS:
                for idx, log in enumerate(API_LOGS, 1):
                    st.markdown(f"**{idx}. [{log['timestamp']}] [{log['step']}]** {log['message']}")
                    if log['raw_payload']:
                        st.json(log['raw_payload'])
                    st.markdown("---")
            else:
                st.info("No API query logs available for this session.")
    
    elif variant_input and not analyze_button:
        # Preview validation
        classification = router.classify(variant_input)
        if classification.is_genomic:
            st.success(f" Valid {classification.query_type} format detected: `{classification.extracted_identifier}`")
        else:
            st.error(" Invalid format. Please provide a valid HGVS notation or RSID.")

# --- Tab 4: VCF Batch Processing ---
with tab4:
    st.session_state.active_tab = 3
    st.markdown('<div class="section-header"> VCF File Upload</div>', unsafe_allow_html=True)
    
    st.info(" **For Non-Technical Users**: Upload your VCF file to discover potential genetic disease associations. Patient identifying information will be automatically removed for privacy.")
    
    uploaded = st.file_uploader(
        "Upload VCF file", 
        type=["vcf", "vcf.gz", "txt", "doc", "docx", "pdf"],
        label_visibility="collapsed",
        help="Supported formats: VCF, VCF.GZ, TXT, DOC, DOCX, PDF"
    )
    
    if uploaded:
        # De-identify by removing patient name from filename display
        safe_filename = "patient_sample.vcf" if not uploaded.name.startswith("sample") else uploaded.name
        
        with st.spinner("Parsing VCF file..."):
            parser = VCFParser()
            variants = parser.parse(uploaded.getvalue(), uploaded.name)
            df = parser.to_dataframe(variants)
        
        st.success(f" Successfully parsed **{len(variants)} variants** from {safe_filename}")
        
        # Show preview without patient-identifying info
        st.markdown("###  Variant Preview (First 100 rows)")
        # Remove any columns that might contain patient info
        display_df = df.head(100).copy()
        if 'sample' in display_df.columns:
            display_df = display_df.drop(columns=['sample'])
        
        st.dataframe(display_df, use_container_width=True)
        
        # Disease Analysis Button
        st.markdown("---")
        if st.button(" Analyze for Disease Associations", type="primary", use_container_width=True):
            st.markdown('<div class="section-header"> Disease Association Analysis</div>', unsafe_allow_html=True)
            
            st.info(f"Analyzing up to 20 variants for disease associations. This may take a moment...")
            
            with st.spinner("Querying genomic databases..."):
                disease_findings = []
                processed_count = 0
                
                for i, var in enumerate(variants[:20]):  # Reduced to 20 to avoid rate limits
                    query_id = var.get("query_id")
                    if not query_id:
                        continue
                    
                    try:
                        processed_count += 1
                        
                        # Progress indicator (every 5 variants)
                        if processed_count % 5 == 0:
                            st.write(f"✓ Processed {processed_count} variants... (Rate-limited to avoid API throttling)")
                        
                        # Classify and query variant using query router
                        classification = router.classify(query_id)
                        if classification.is_genomic:
                            # Use VariantDataFetcher for comprehensive data
                            variant_data = variant_data_fetcher.fetch_variant_data(
                                variant_id=classification.extracted_identifier,
                                query_type=classification.query_type
                            )
                            
                            clinvar_data = variant_data.get("clinvar_data", {})
                            myvariant_data = variant_data.get("myvariant_data", {})
                            
                            # Check if we have disease associations
                            if clinvar_data and "error" not in clinvar_data:
                                clinical_sig = clinvar_data.get("clinical_significance", "")
                                
                                if clinical_sig and clinical_sig != "Not provided":
                                    # Get gene info
                                    gene = clinvar_data.get('gene_symbol', 'Unknown gene')
                                    conditions = clinvar_data.get('conditions', [])
                                    
                                    if conditions:
                                        disease_findings.append({
                                            'variant': query_id,
                                            'gene': gene,
                                            'location': f"chr{var['chrom']}:{var['pos']}",
                                            'ref_alt': f"{var['ref']}>{var['alt']}",
                                            'clinical_sig': clinical_sig,
                                            'conditions': conditions,
                                            'review_status': clinvar_data.get('review_status', 'Unknown'),
                                            'molecular_consequence': clinvar_data.get('molecular_consequence', [])
                                        })
                        
                        # Delay to avoid rate limiting (increased for API stability)
                        time.sleep(0.5)
                        
                    except Exception as ex:
                        continue
            
            # Display results in user-friendly format
            if disease_findings:
                st.success(f" Found **{len(disease_findings)} variants** with disease associations")
                
                st.markdown("###  Detailed Findings")
                st.markdown("*The following genetic variants in your sample have been associated with medical conditions in scientific literature:*")
                st.markdown("---")
                
                for idx, finding in enumerate(disease_findings, 1):
                    # Color-code by clinical significance
                    sig = finding['clinical_sig']
                    if 'pathogenic' in sig.lower() and 'benign' not in sig.lower():
                        badge_color = "#dc3545"
                        icon = ""
                    elif 'benign' in sig.lower():
                        badge_color = "#28a745"
                        icon = ""
                    else:
                        badge_color = "#ffc107"
                        icon = ""
                    
                    st.markdown(f"""
                    <div style="border-left: 4px solid {badge_color}; padding: 15px; margin-bottom: 20px; background-color: #f8f9fa; border-radius: 5px; color: #2E3B4E;">
                        <h4 style="margin-top:0; color: #2E3B4E;">{icon} Variant {idx}: {finding['variant']} in {finding['gene']} gene</h4>
                        <p style="color: #2E3B4E;"><strong>Location:</strong> {finding['location']} ({finding['ref_alt']})</p>
                        <p style="color: #2E3B4E;"><strong>Clinical Significance:</strong> <span style="color: {badge_color}; font-weight: bold;">{finding['clinical_sig']}</span></p>
                        <p style="color: #2E3B4E;"><strong>Review Status:</strong> {finding['review_status']}</p>
                        <p style="color: #2E3B4E;"><strong>Associated Conditions:</strong></p>
                        <ul style="color: #2E3B4E;">
                    """, unsafe_allow_html=True)
                    
                    for condition in finding['conditions']:
                        st.markdown(f"<li style='color: #2E3B4E;'>{condition}</li>", unsafe_allow_html=True)
                    
                    if finding['molecular_consequence']:
                        st.markdown(f"<p style='color: #2E3B4E;'><strong>Effect on Protein:</strong> {', '.join(finding['molecular_consequence'])}</p>", unsafe_allow_html=True)
                    
                    st.markdown("</ul></div>", unsafe_allow_html=True)
                
                # Summary statistics
                st.markdown("###  Summary")
                col1, col2, col3 = st.columns(3)
                
                pathogenic_count = sum(1 for f in disease_findings if 'pathogenic' in f['clinical_sig'].lower() and 'benign' not in f['clinical_sig'].lower())
                benign_count = sum(1 for f in disease_findings if 'benign' in f['clinical_sig'].lower())
                uncertain_count = len(disease_findings) - pathogenic_count - benign_count
                
                with col1:
                    st.metric(" Pathogenic/Likely Pathogenic", pathogenic_count)
                with col2:
                    st.metric(" Benign/Likely Benign", benign_count)
                with col3:
                    st.metric(" Uncertain Significance", uncertain_count)
                
                # Clinical recommendations
                st.markdown("---")
                st.markdown("###  Next Steps")
                
                if pathogenic_count > 0:
                    st.warning("""
                    **Important:** This analysis found variants associated with medical conditions. Please note:
                    - This is for **research purposes only** and not a medical diagnosis
                    - Consult with a **genetic counselor** or medical geneticist
                    - They can help interpret these findings in the context of personal and family medical history
                    - Consider **confirmatory testing** through a certified clinical laboratory
                    """)
                else:
                    st.info("""
                    **No highly concerning variants detected** in the analyzed sample. However:
                    - This analysis is limited to variants with known clinical annotations
                    - Absence of findings doesn't rule out all genetic conditions
                    - Consider consulting a genetic counselor for comprehensive interpretation
                    """)
            
            else:
                st.warning("""
                ###  No Disease Associations Found
                
                This could mean:
                - **The variants don't have documented disease associations** (most common)
                - **The variants are benign** or normal population variants
                - **The VCF lacks rsID annotations** (needed for database lookups)
                
                ** To improve results:**
                1. Ensure your VCF file includes rsID annotations
                2. Annotate the VCF with tools like VEP, SnpEff, or ANNOVAR
                3. Use the "Single Variant" tab to analyze specific variants with HGVS notation
                
                **What you can still do:**
                - Use the variant table above to identify genes with changes
                - Research specific genes using the "AI Copilot" tab
                - Look up individual variants in the "Single Variant" tab
                """)
                
                # Helpful gene inference section
                st.markdown("###  Gene-Based Insights")
                st.markdown("Even without rsIDs, here are the genes affected in your sample:")
                
                genes_found = set()
                for var in variants[:50]:
                    gene = var.get("info", {}).get("GENE") or var.get("info", {}).get("GENEINFO", "").split("|")[0] if var.get("info", {}).get("GENEINFO") else None
                    if gene:
                        genes_found.add(gene)
                
                if genes_found:
                    st.write("**Genes with variants:**", ", ".join(sorted(list(genes_found))[:20]))
                    st.info(" You can ask the AI Copilot about any of these genes to learn about their function and associated conditions.")
                else:
                    st.write("No gene annotations found. Consider re-annotating your VCF file.")

# ==================== FOOTER ====================
st.markdown("---")
st.markdown("""
<div style="text-align: center; padding: 1.5rem 0; color: var(--text-secondary); font-size: 0.85rem; line-height: 1.6;">
    <p style="margin: 0 0 0.5rem 0;"><strong style="color: var(--primary-color);">Genetic Counselling Workbench</strong></p>
    <p style="margin: 0 0 0.5rem 0;">ClinGen • MyVariant.info • Ensembl VEP • Gemini AI</p>
    <p style="margin: 0; font-size: 0.8rem;">Research & Educational Use Only • Patient Data De-identified</p>
</div>
""", unsafe_allow_html=True)

def main():
    pass  # Main logic is now in the tabs above

if __name__ == "__main__":
    main()
