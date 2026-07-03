import streamlit as st
import time
import os
import re
import json
from typing import Dict, Any, List
from analysis.vcf_prioritizer import VCFPrioritizer
from core.api_clients import query_pubmed

def display_vcf_batch_processing(router, variant_data_fetcher, VCFParser):
    st.session_state.active_tab = 3
    st.markdown('<div class="section-header">🧬 VCF File Upload & Prioritization</div>', unsafe_allow_html=True)
    
    st.info("💡 **Clinical Workflow**: Upload a patient's VCF file. The system will de-identify the sample, perform batch annotations, and prioritize variants by pathogenicity. You can then input the patient's symptoms to perform an AI-driven clinical correlation with Extended Thinking.")
    
    uploaded = st.file_uploader(
        "Upload VCF file", 
        type=["vcf", "vcf.gz", "txt"],
        label_visibility="collapsed"
    )
    
    if uploaded:
        # De-identify filename
        safe_filename = "patient_sample.vcf" if not uploaded.name.startswith("sample") else uploaded.name
        
        # Initialize prioritized variants session state
        if "prioritized_variants" not in st.session_state or st.session_state.get("uploaded_file_name") != uploaded.name:
            with st.spinner("Parsing and prioritizing VCF variants..."):
                parser = VCFParser()
                try:
                    variants = parser.parse(uploaded.getvalue(), uploaded.name)
                    # Run prioritization pipeline
                    prioritizer = VCFPrioritizer(frequency_threshold=0.01, max_candidates=100)
                    prioritized = prioritizer.prioritize_variants(variants)
                    
                    st.session_state.prioritized_variants = prioritized
                    st.session_state.raw_variants_count = len(variants)
                    st.session_state.uploaded_file_name = uploaded.name
                except Exception as e:
                    st.error(f"Error parsing VCF: {str(e)}")
                    st.stop()
        
        prioritized = st.session_state.prioritized_variants
        raw_count = st.session_state.raw_variants_count
        
        st.success(f" Successfully processed VCF sample with **{raw_count} variants** (de-identified as `{safe_filename}`).")
        
        # Display Prioritized Variant Tabs
        st.markdown("### 📊 Prioritized Variants")
        
        tab_danger, tab_possible, tab_vus, tab_benign = st.tabs([
            f"🔴 Dangerous / Harmful ({len(prioritized['dangerous'])})",
            f"🟡 Possibly Harmful ({len(prioritized['possibly_harmful'])})",
            f"🔵 Uncertain Significance (VUS) ({len(prioritized['vus'])})",
            f"🟢 Benign / Common ({len(prioritized['benign'])})"
        ])
        
        def render_variant_table(var_list: List[Dict[str, Any]]):
            if not var_list:
                st.info("No variants found in this category.")
                return
            
            # Format display records
            display_records = []
            for v in var_list:
                display_records.append({
                    "Variant ID": v.get("variant", "N/A"),
                    "Gene": v.get("gene", "N/A"),
                    "Location": v.get("location", "N/A"),
                    "Change": v.get("ref_alt", "N/A"),
                    "Clinical Significance": v.get("clinical_sig", "N/A"),
                    "Allele Freq": f"{v['af']:.5f}" if v.get("af") is not None else "N/A"
                })
            st.dataframe(display_records, use_container_width=True)

        with tab_danger:
            st.markdown("##### 🚨 Pathogenic and High-Impact Variants")
            st.write("These variants are clinical targets with high-severity molecular consequences or established clinical significance.")
            render_variant_table(prioritized["dangerous"])
            
        with tab_possible:
            st.markdown("##### ⚠️ Likely Deleterious & Conflicting Variants")
            st.write("These variants show signs of functional damage (e.g. SIFT Deleterious/PolyPhen Damaging) or conflicting clinical reports.")
            render_variant_table(prioritized["possibly_harmful"])
            
        with tab_vus:
            st.markdown("##### 🔍 Variants of Uncertain Significance (VUS)")
            st.write("These variants lack sufficient clinical evidence and should be correlated against symptoms.")
            render_variant_table(prioritized["vus"])
            
        with tab_benign:
            st.markdown("##### ✅ Benign & Common Polymorphisms")
            st.write("Common population polymorphisms or variants classified as benign.")
            render_variant_table(prioritized["benign"])
            
        # AI Clinical Symptom Correlation Section
        st.markdown("---")
        st.markdown("### 🧠 AI Clinical Correlation & Extended Thinking")
        st.write("Input patient symptoms and medical history. The AI will extract key genes, search literature, analyze pathways, and run an **Extended Thinking** reasoning model to identify compound heterozygous or synergistic effects.")
        
        patient_symptoms = st.text_area(
            "Patient Symptoms & Clinical Notes",
            placeholder="Example: Patient is a 4-year-old child presenting with bilateral sensorineural hearing loss, motor developmental delays, and vestibular dysfunction. Family history includes a cousin with early onset deafness.",
            height=120
        )
        
        # Configure Gemini API
        if "gemini_client" not in st.session_state:
            try:
                import google.generativeai as genai
                api_key = None
                key_file_path = os.path.join("api_key", "gemini_key.txt")
                if os.path.exists(key_file_path):
                    with open(key_file_path, "r") as f:
                        lines = [line.strip() for line in f.readlines() if line.strip() and not line.strip().startswith("#")]
                        if lines:
                            api_key = lines[0]
                if not api_key:
                    api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                    st.session_state["gemini_client"] = genai
                else:
                    st.session_state["gemini_client"] = None
            except ImportError:
                st.session_state["gemini_client"] = None
                
        if st.button("🔍 Run Clinical Correlation & Extended Thinking", type="primary", use_container_width=True):
            if not patient_symptoms.strip():
                st.warning("Please provide patient symptoms or clinical notes before running the analysis.")
                st.stop()
                
            genai = st.session_state.get("gemini_client")
            if not genai:
                st.error("Gemini API key is not configured. Please paste your key in `api_key/gemini_key.txt` or set `GEMINI_API_KEY` environmental variable.")
                st.stop()
                
            with st.spinner("Analyzing candidate genes and searching medical literature..."):
                # Collect candidate genes from dangerous, possibly harmful, and VUS lists
                candidate_genes = set()
                all_candidates = prioritized["dangerous"] + prioritized["possibly_harmful"] + prioritized["vus"]
                for c in all_candidates:
                    if c.get("gene") and c.get("gene") != "N/A":
                        candidate_genes.add(c.get("gene"))
                
                # Fetch PubMed literature
                pubmed_context = ""
                if candidate_genes:
                    gene_query = " OR ".join(candidate_genes)
                    # Extract a few key medical keywords from symptoms (e.g. hearing, deafness, motor, developmental)
                    keywords = [word for word in re.findall(r'\b\w{5,}\b', patient_symptoms.lower()) 
                                if word not in ["patient", "presenting", "history", "clinical", "symptoms", "family", "disease"]]
                    keyword_query = " OR ".join(keywords[:4]) if keywords else ""
                    
                    search_term = f"({gene_query})"
                    if keyword_query:
                        search_term += f" AND ({keyword_query})"
                        
                    papers = query_pubmed(search_term)
                    if not papers and keyword_query:
                        # Fallback query with genes only
                        papers = query_pubmed(gene_query)
                        
                    if papers:
                        papers_list = []
                        for idx, p in enumerate(papers, 1):
                            papers_list.append(f"{idx}. Title: {p.get('title')}\n   Journal: {p.get('journal')} ({p.get('pubdate')})\n   PMID: {p.get('pmid')}\n   Link: {p.get('link')}")
                        pubmed_context = "\n\n".join(papers_list)
                    else:
                        pubmed_context = "No direct literature papers resolved for this variant-symptom query."
                else:
                    pubmed_context = "No candidate genes found for automated literature lookup."
                
                # Construct Extended Thinking Prompt
                prompt = f"""
You are a senior clinical genetics expert. A genetic counselor has uploaded a patient's VCF file and provided the following clinical symptoms and history:

[Patient Symptoms & History]
{patient_symptoms}

[Prioritized Genetic Variants from VCF]
- Dangerous/Harmful:
{json.dumps(prioritized["dangerous"][:15], indent=2)}

- Possibly Harmful:
{json.dumps(prioritized["possibly_harmful"][:15], indent=2)}

- Variants of Uncertain Significance (VUS):
{json.dumps(prioritized["vus"][:20], indent=2)}

- Benign / Tolerated:
{json.dumps(prioritized["benign"][:10], indent=2)}

[Relevant Scientific Literature Context]
{pubmed_context}

First, you must perform a detailed, multi-step clinical reasoning process. Write your thoughts step-by-step inside a `<clinical_thinking>` block. In your reasoning:
1. Cross-reference the patient's symptoms with the genes in the variant lists.
2. Evaluate individual variants for pathogenicity.
3. Specifically investigate whether any combinations of variants (such as compound heterozygous variants in a single gene, or variants in interacting genes/pathways) could explain the symptoms synergistically, even if the individual variants are classified as VUS or Benign.
4. Formulate diagnostic hypotheses and recommend follow-up clinical testing or literature checks.

After closing the `</clinical_thinking>` block, output your final, patient-deidentified Clinical Interpretation Report. The report must contain:
1. **Clinical Interpretation Summary**: Key genetic findings relating to symptoms.
2. **Prioritized Variant Breakdown**: Explaining the role of key candidate variants.
3. **Synergy & Pathway Interactions**: Any compound heterozygous or oligogenic synergy findings.
4. **Clinical Recommendations**: Clear, actionable next steps for the genetic counselor.
"""
            
            with st.spinner("Processing clinical extended thinking... (Cross-referencing databases and predicting pathway interactions)"):
                try:
                    # Dynamically discover all Gemini text generation models and sort descending (newer first)
                    model_list = []
                    try:
                        all_discovered = []
                        for m in genai.list_models():
                            if 'generateContent' in m.supported_generation_methods:
                                name = m.name.split('/')[-1]
                                all_discovered.append(name)
                        
                        # Exclude non-text/embedding/media models
                        exclude_keywords = ['embed', 'vision', 'audio', 'video', 'bidi', 'whisper', 'imagen', 'aqa']
                        gemini_models = [
                            m for m in all_discovered 
                            if 'gemini' in m.lower() and not any(kw in m.lower() for kw in exclude_keywords)
                        ]
                        # Sort reverse-alphabetical (which puts higher/newer numbers first, e.g. gemini-2.5 before gemini-1.5)
                        gemini_models.sort(reverse=True)
                        model_list = gemini_models if gemini_models else ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']
                    except Exception:
                        model_list = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']

                    response_text = None
                    last_error = None
                    selected_model_name = None
                    
                    for model_name in model_list:
                        try:
                            st.info(f"Querying clinical insights using `{model_name}`...")
                            model = genai.GenerativeModel(model_name)
                            response = model.generate_content(prompt)
                            response_text = response.text
                            selected_model_name = model_name
                            break
                        except Exception as e:
                            last_error = str(e)
                            if "429" in last_error or "quota" in last_error.lower():
                                st.warning(f"⚠️ Model `{model_name}` rate limit hit (429). Retrying with another model...")
                                continue
                            else:
                                st.warning(f"⚠️ Model `{model_name}` error: {last_error}. Retrying with another model...")
                                continue

                    if not response_text:
                        st.error(f"Error generating clinical deduction: All available models returned errors. Last error: {last_error}")
                        st.stop()
                    
                    # Parse out thinking block
                    thinking_content = ""
                    report_content = response_text
                    
                    thinking_match = re.search(r'<clinical_thinking>(.*?)</clinical_thinking>', response_text, re.DOTALL)
                    if thinking_match:
                        thinking_content = thinking_match.group(1).strip()
                        report_content = response_text.replace(thinking_match.group(0), "").strip()
                        
                    # Display Results
                    st.success(f"✅ Analysis completed successfully using `{selected_model_name}`!")
                    
                    if thinking_content:
                        with st.expander("🧑‍⚕️ Clinical Reasoning & Extended Thinking (click to expand)", expanded=False):
                            st.markdown(thinking_content)
                            
                    st.markdown("### 📋 Clinical Interpretation Report")
                    st.markdown(report_content)
                    
                except Exception as ex:
                    st.error(f"Error generating clinical deduction: {str(ex)}")

