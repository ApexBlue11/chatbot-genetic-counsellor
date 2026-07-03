import streamlit as st
import pandas as pd
import requests
import json
import time
from urllib.parse import quote
from typing import Dict, Any, List, Optional
from core.api_clients import query_clingen, query_myvariant, query_vep, query_clinvar, query_pubmed

# Amino acid mapping dictionary
AMINO_ACIDS_MAP = {
    'ALA': 'Ala', 'ARG': 'Arg', 'ASN': 'Asn', 'ASP': 'Asp', 'CYS': 'Cys',
    'GLU': 'Glu', 'GLN': 'Gln', 'GLY': 'Gly', 'HIS': 'His', 'ILE': 'Ile',
    'LEU': 'Leu', 'LYS': 'Lys', 'MET': 'Met', 'PHE': 'Phe', 'PRO': 'Pro',
    'SER': 'Ser', 'THR': 'Thr', 'TRP': 'Trp', 'TYR': 'Tyr', 'VAL': 'Val',
    'A': 'Ala', 'R': 'Arg', 'N': 'Asn', 'D': 'Asp', 'C': 'Cys',
    'E': 'Glu', 'Q': 'Gln', 'G': 'Gly', 'H': 'His', 'I': 'Ile',
    'L': 'Leu', 'K': 'Lys', 'M': 'Met', 'F': 'Phe', 'P': 'Pro',
    'S': 'Ser', 'T': 'Thr', 'W': 'Trp', 'Y': 'Tyr', 'V': 'Val',
    'X': 'Term', '*': 'Term'
}

def format_amino_acids(aa_str: str) -> str:
    if '/' in aa_str:
        parts = aa_str.split('/')
        if len(parts) == 2:
            ref_aa = AMINO_ACIDS_MAP.get(parts[0].upper(), parts[0])
            alt_aa = AMINO_ACIDS_MAP.get(parts[1].upper(), parts[1])
            return f"{aa_str} ({ref_aa} → {alt_aa})"
    return aa_str

def clean_ui_label(label: str) -> str:
    if not label:
        return 'N/A'
    return label.replace('_', ' ').title()

def get_variant_annotations(clingen_data, classification=None):
    """Retrieve variant annotations from multiple APIs using core clients."""
    annotations = {'myvariant_data': {}, 'vep_data': [], 'pubmed_data': [], 'errors': []}
    
    myvariant_query_id = clingen_data.get('myvariant_hg38')
    if not myvariant_query_id and classification and classification.query_type == 'rsid':
        myvariant_query_id = classification.extracted_identifier
        
    if myvariant_query_id:
        with st.spinner("Fetching MyVariant.info data..."):
            myv_raw = query_myvariant(myvariant_query_id)
            if "error" in myv_raw:
                annotations['errors'].append(myv_raw["error"])
            else:
                annotations['myvariant_data'] = myv_raw
                
    vep_data = None
    if clingen_data.get('mane_ensembl'):
        with st.spinner("Fetching Ensembl VEP data..."):
            vep_data = query_vep(clingen_data['mane_ensembl'])
            
    if (not vep_data or "error" in vep_data) and classification and classification.query_type == 'rsid':
        with st.spinner("Fetching Ensembl VEP data with RSID..."):
            vep_data = query_vep(classification.extracted_identifier)
            
    if (not vep_data or "error" in vep_data) and annotations['myvariant_data']:
        dbnsfp = annotations['myvariant_data'].get('dbnsfp', {})
        ensembl_data = dbnsfp.get('ensembl', {})
        transcript_ids = ensembl_data.get('transcriptid', [])
        if transcript_ids:
            primary_transcript = transcript_ids[0] if isinstance(transcript_ids, list) else transcript_ids
            hgvs_coding = dbnsfp.get('hgvsc')
            if hgvs_coding:
                hgvs_coding = hgvs_coding[0] if isinstance(hgvs_coding, list) else hgvs_coding
                vep_hgvs = f"{primary_transcript}:{hgvs_coding}"
                with st.spinner(f"Fetching VEP data with Ensembl transcript {primary_transcript}..."):
                    vep_data = query_vep(vep_hgvs)
                    if vep_data and "error" not in vep_data:
                        annotations['vep_fallback_used'] = True
                        st.success(f"VEP fallback successful using transcript {primary_transcript}")

    if vep_data and "error" not in vep_data:
        annotations['vep_data'] = vep_data
    elif vep_data and "error" in vep_data:
        annotations['errors'].append(vep_data["error"])
        
    pubmed_query = None
    if classification:
        pubmed_query = classification.extracted_identifier
    elif clingen_data.get('rsid') and clingen_data['rsid'] != 'N/A':
        pubmed_query = f"rs{clingen_data['rsid']}"
    elif clingen_data.get('genomic_hgvs_grch38'):
        pubmed_query = clingen_data['genomic_hgvs_grch38']
        
    if pubmed_query:
        with st.spinner("Fetching PubMed literature..."):
            annotations['pubmed_data'] = query_pubmed(pubmed_query)
            
    return annotations

def select_primary_vep_transcript(vep_data, target_transcript_id=None):
    if not vep_data or not vep_data[0].get('transcript_consequences'):
        return None, "No transcript consequences found"
    transcripts = vep_data[0]['transcript_consequences']
    
    if target_transcript_id:
        clean_target = target_transcript_id.split('.')[0].split(':')[0].strip()
        for t in transcripts:
            if t.get('transcript_id', '').split('.')[0].strip() == clean_target:
                return t, f"Matched target MANE transcript ({clean_target})"
                
    for t in transcripts:
        flags = t.get('flags', [])
        if 'MANE_SELECT' in flags or any('mane' in str(flag).lower() for flag in flags):
            return t, "MANE Select"
    for t in transcripts:
        if t.get('canonical') == 1 or 'canonical' in t.get('flags', []):
            return t, "Canonical Flagged"
    for t in transcripts:
        if (t.get('biotype') == 'protein_coding' and 'missense_variant' in t.get('consequence_terms', [])):
            return t, "First protein coding with missense annotation"
    for t in transcripts:
        if t.get('biotype') == 'protein_coding':
            return t, "First protein coding"
    return transcripts[0], "First available transcript"

def display_vep_analysis(vep_data, target_transcript_id=None):
    if not vep_data or not isinstance(vep_data, list) or not vep_data[0].get('transcript_consequences'):
        st.warning("No VEP data available")
        return
    variant_info = vep_data[0]
    all_transcripts = variant_info.get('transcript_consequences', [])
    primary_transcript, selection_reason = select_primary_vep_transcript(vep_data, target_transcript_id)
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
            st.write(f"**Consequence:** {', '.join(clean_ui_label(c) for c in consequences)}")
        with col2:
            st.write(f"**Impact:** {clean_ui_label(primary_transcript.get('impact', 'N/A'))}")
        with col3:
            st.write(f"**Biotype:** {clean_ui_label(primary_transcript.get('biotype', 'N/A'))}")
        if primary_transcript.get('amino_acids'):
            st.subheader("Sequence Changes")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Amino Acid Change:** {format_amino_acids(primary_transcript.get('amino_acids', 'N/A'))}")
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
                if primary_transcript.get('sift_score') is not None:
                    st.metric("SIFT Score", f"{primary_transcript['sift_score']:.3f}")
                    st.write(f"**SIFT Prediction:** {clean_ui_label(primary_transcript.get('sift_prediction', 'N/A'))}")
                    st.caption("ℹ️ **SIFT Scale**: 0.0 (deleterious) to 1.0 (tolerated). Threshold: ≤ 0.05 is Deleterious.")
            with col2:
                if primary_transcript.get('polyphen_score') is not None:
                    st.metric("PolyPhen Score", f"{primary_transcript['polyphen_score']:.3f}")
                    st.write(f"**PolyPhen Prediction:** {clean_ui_label(primary_transcript.get('polyphen_prediction', 'N/A'))}")
                    st.caption("ℹ️ **PolyPhen-2 Scale**: 0.0 (benign) to 1.0 (damaging). Thresholds: 0.0–0.446 Benign, 0.447–0.908 Possibly Damaging, 0.909–1.0 Probably Damaging.")
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
                    st.write(f"**Consequence:** {', '.join(clean_ui_label(c) for c in transcript.get('consequence_terms', []))}")
                    st.write(f"**Impact:** {clean_ui_label(transcript.get('impact', 'N/A'))}")
                with col3:
                    st.write(f"**Biotype:** {clean_ui_label(transcript.get('biotype', 'N/A'))}")
                    if transcript.get('distance'): st.write(f"**Distance:** {transcript.get('distance', 'N/A')}")
                with col4:
                    if transcript.get('amino_acids'):
                        st.write(f"**AA Change:** {format_amino_acids(transcript.get('amino_acids', 'N/A'))}")
                        st.write(f"**Position:** {transcript.get('protein_start', 'N/A')}")
                if transcript.get('sift_score') or transcript.get('polyphen_score'):
                    pred_col1, pred_col2 = st.columns(2)
                    with pred_col1:
                        if transcript.get('sift_score') is not None: st.write(f"**SIFT:** {transcript['sift_score']:.3f} ({clean_ui_label(transcript.get('sift_prediction', 'N/A'))})")
                    with pred_col2:
                        if transcript.get('polyphen_score') is not None: st.write(f"**PolyPhen:** {transcript['polyphen_score']:.3f} ({clean_ui_label(transcript.get('polyphen_prediction', 'N/A'))})")
                st.markdown("---")

def display_comprehensive_myvariant_data(myvariant_data):
    if not myvariant_data:
        st.warning("No MyVariant data available")
        return

    if isinstance(myvariant_data, list):
        best_record = myvariant_data[0]
        best_score = -1
        for r in myvariant_data:
            if not isinstance(r, dict): continue
            score = 0
            if 'clinvar' in r: score += 10
            if 'gnomad_genome' in r or 'gnomad_exome' in r: score += 5
            if 'dbnsfp' in r: score += 3
            if 'uniprot' in r: score += 2
            score += len(r.keys()) * 0.1
            if score > best_score:
                best_score = score
                best_record = r
        myvariant_data = best_record
    if not isinstance(myvariant_data, dict):
        st.error("Unexpected data format from MyVariant")
        return

    data_tabs = st.tabs([" Basic Info", " Pathogenicity Predictors", " Population Frequencies", " ClinVar", " External DBs"])

    with data_tabs[0]:
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

            gene_name = (
                myvariant_data.get('clinvar', {}).get('gene', {}).get('symbol') or
                snpeff_gene or
                dbnsfp_gene_str or
                'N/A'
            )
            st.write(f"**Gene:** {gene_name}")
            rsid = myvariant_data.get('rsid') or myvariant_data.get('dbsnp', {}).get('rsid') or 'N/A'
            st.write(f"**RSID:** {rsid}")
        if myvariant_data.get('clingen'):
            st.subheader("ClinGen Information")
            clingen = myvariant_data['clingen']
            st.write(f"**CAID:** {clingen.get('caid', 'N/A')}")

    with data_tabs[1]:
        st.subheader("Functional Prediction Scores")
        dbnsfp = myvariant_data.get('dbnsfp', {})
        if not dbnsfp:
            st.info("No dbNSFP functional prediction data available")
        else:
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
                    predictor_name, score_path, pred_path = predictor_info
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
                            st.metric(pred['Predictor'], score_str, delta=pred['Prediction'] if pred['Prediction'] != 'N/A' else None)
                else:
                    st.info(f"No {category.lower()} data available")

            st.markdown("---")
            with st.expander("📖 View Official Pathogenicity & Conservation Scores Guide", expanded=False):
                st.markdown(r"""
                ### Official Pathogenicity & Conservation Scores Guide
                Below are the official scales and clinical interpretation thresholds (from dbNSFP guidelines):
                
                | Category | Predictor | Official Scale Range | Pathogenicity / Conservation Threshold |
                | :--- | :--- | :--- | :--- |
                | **Pathogenicity** | **SIFT** | `0.0` (deleterious) to `1.0` (tolerated) | Score $\le$ 0.05 is Deleterious |
                | | **PolyPhen-2 (HDiv / HVar)** | `0.0` (benign) to `1.0` (damaging) | HDiv: $\ge$ 0.957 Probably, $\ge$ 0.453 Possibly Damaging. <br>HVar: $\ge$ 0.909 Probably, $\ge$ 0.447 Possibly Damaging. |
                | | **FATHMM** | `-15.0` to `15.0` | Score $\le$ -1.5 is Damaging |
                | | **MutationTaster** | `0.0` to `1.0` | A: Automatic Disease Causing, D: Disease Causing, N: Polymorphism |
                | | **MutationAssessor** | `-5.5` to `5.9` | Score > 1.9 is Medium/High functional impact |
                | | **PROVEAN** | `-14.0` to `14.0` | Score $\le$ -2.5 is Damaging |
                | | **MetaSVM / MetaLR** | `0.0` to `1.0` | Score $\ge$ 0.5 is Damaging |
                | | **REVEL** | `0.0` to `1.0` | Score $\ge$ 0.85 is strongly pathogenic |
                | | **CADD Phred** | `1.0` to `99.0` | Score $\ge$ 20 is top 1% deleterious, $\ge$ 30 is top 0.1% |
                | | **GERP++ RS** | `-12.3` to `6.17` | Score > 2 indicates evolutionary constraint (conserved) |
                """)

    with data_tabs[2]:
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
                        st.info("No gnomAD exome populations match filter.")
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

        with freq_tabs[2]:
            kg_data = myvariant_data.get('dbnsfp', {}).get('1000gp3', {})
            if kg_data:
                st.markdown("**1000 Genomes Project Phase 3**")
                if isinstance(kg_data, list): kg_data = kg_data[0]
                pop_data = []
                populations = {'af':'Global', 'afr_af':'African', 'amr_af':'American', 'eas_af':'East Asian', 'eur_af':'European', 'sas_af':'South Asian'}
                for key, name in populations.items():
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

        with freq_tabs[3]:
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
                if pop_data: st.dataframe(pd.DataFrame(pop_data), use_container_width=True)

        with freq_tabs[4]:
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

    with data_tabs[3]:
        st.subheader("ClinVar Clinical Annotations")
        clinvar_data = myvariant_data.get('clinvar', {})
        if clinvar_data:
            clinical_sig = clinvar_data.get('clinical_significance') or clinvar_data.get('clnsig')
            if not clinical_sig and isinstance(clinvar_data.get('rcv'), list) and clinvar_data['rcv']:
                sig_list = []
                for rcv in clinvar_data['rcv']:
                    if isinstance(rcv, dict) and rcv.get('clinical_significance'):
                        sig_list.append(rcv['clinical_significance'])
                if sig_list: clinical_sig = "; ".join(list(set(sig_list)))
            if not clinical_sig: clinical_sig = 'N/A'
                
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Clinical Significance:** {clinical_sig}")
                if clinvar_data.get('variant_id'): st.write(f"**Variation ID:** {clinvar_data['variant_id']}")
                if clinvar_data.get('allele_id'): st.write(f"**Allele ID:** {clinvar_data['allele_id']}")
            with col2:
                gene_info = clinvar_data.get('gene', {})
                if isinstance(gene_info, dict):
                    if gene_info.get('symbol'): st.write(f"**Gene Symbol:** {gene_info['symbol']}")
            
            hgvs_info = clinvar_data.get('hgvs', {})
            if isinstance(hgvs_info, dict):
                st.subheader("HGVS Notations")
                col1, col2 = st.columns(2)
                with col1:
                    if hgvs_info.get('coding'): st.write(f"**Coding:** {hgvs_info['coding']}")
                with col2:
                    if hgvs_info.get('genomic'):
                        genomic = hgvs_info['genomic']
                        st.write(f"**Genomic:** {', '.join(genomic) if isinstance(genomic, list) else str(genomic)}")

    with data_tabs[4]:
        st.subheader("External Database References")
        dbsnp_data = myvariant_data.get('dbsnp', {})
        if dbsnp_data:
            st.markdown("#### dbSNP")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**RSID:** {dbsnp_data.get('rsid', 'N/A')}")
                st.write(f"**Variant Type:** {dbsnp_data.get('vartype', 'N/A')}")
        uniprot_data = myvariant_data.get('uniprot', {})
        if uniprot_data:
            st.markdown("#### UniProt Reference")
            if isinstance(uniprot_data, dict):
                if uniprot_data.get('clinical_significance'): st.write(f"**Clinical Significance:** {uniprot_data['clinical_significance']}")
                if uniprot_data.get('swiss_prot_ac'):
                    st.write(f"**SwissProt Accession:** [{uniprot_data['swiss_prot_ac']}](https://www.uniprot.org/uniprotkb/{uniprot_data['swiss_prot_ac']})")

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

def generate_summary_prompt(clingen_data: Dict, myvariant_data: Dict, vep_data: List) -> str:
    if myvariant_data and isinstance(myvariant_data, dict) and 'dbnsfp' in myvariant_data and isinstance(myvariant_data['dbnsfp'], dict):
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
    
    if 'selected_papers' in st.session_state and st.session_state.selected_papers:
        papers_context = []
        for pmid, paper in st.session_state.selected_papers.items():
            papers_context.append(f"- Title: {paper.get('title')}\n  Authors: {paper.get('authors')}\n  Journal: {paper.get('journal')}\n  Date: {paper.get('pubdate')}\n  Link: {paper.get('link')}")
        papers_str = "\n".join(papers_context)
        data_parts.append(f"**User-Selected Relevant Literature Context:**\n{papers_str}\nInclude details or citations from these articles in your final summary where relevant.")
        
    return "\n\n".join(data_parts)

def parse_caid_minimal(raw_json):
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
            result['mane_ensembl'] = t.get('ensemblTranscript', {}).get('id')
            result['mane_refseq'] = t.get('refSeqTranscript', {}).get('id')
    return result

def display_single_variant_analysis(router, variant_data_fetcher):
    st.session_state.active_tab = 2
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
                        st.info(" 🔍 RSID detected - querying ClinGen Allele Registry by rsID to resolve MANE and coordinate aliases...")
                        rs_num = classification.extracted_identifier.replace('rs', '')
                        clingen_data = None
                        try:
                            clingen_search_url = f"https://reg.clinicalgenome.org/alleles?dbSNP.rs={rs_num}"
                            headers = {"Accept": "application/json"}
                            search_resp = requests.get(clingen_search_url, headers=headers, timeout=15)
                            if search_resp.ok:
                                urls = search_resp.json()
                                if isinstance(urls, list) and urls:
                                    if isinstance(urls[0], dict):
                                        clingen_raw = urls[0]
                                        clingen_data = parse_caid_minimal(clingen_raw)
                                        st.success(" ✅ Successfully resolved RSID aliases from ClinGen Allele Registry!")
                                    else:
                                        allele_url = urls[0]
                                        allele_resp = requests.get(allele_url, headers=headers, timeout=15)
                                        if allele_resp.ok:
                                            clingen_raw = allele_resp.json()
                                            clingen_data = parse_caid_minimal(clingen_raw)
                                            st.success(" ✅ Successfully resolved RSID aliases from ClinGen Allele Registry!")
                        except Exception as e:
                            st.warning(f"Could not resolve RSID via ClinGen Allele Registry: {str(e)}")

                        if not clingen_data:
                            clingen_data = {
                                'CAid': 'N/A (RSID input)', 
                                'rsid': rs_num, 
                                'genomic_hgvs_grch38': None,
                                'genomic_hgvs_grch37': None, 
                                'myvariant_hg38': None, 
                                'myvariant_hg19': None, 
                                'mane_ensembl': None, 
                                'mane_refseq': None
                            }
                        
                        annotations = get_variant_annotations(clingen_data, classification)
                        
                        if not annotations.get('vep_data') and annotations['myvariant_data']:
                            myv_data = annotations['myvariant_data']
                            if isinstance(myv_data, list) and len(myv_data) > 0:
                                best_record = myv_data[0]
                                best_score = -1
                                for r in myv_data:
                                    if not isinstance(r, dict): continue
                                    score = 0
                                    if 'clinvar' in r: score += 10
                                    if 'gnomad_genome' in r or 'gnomad_exome' in r: score += 5
                                    if 'dbnsfp' in r: score += 3
                                    if 'uniprot' in r: score += 2
                                    score += len(r.keys()) * 0.1
                                    if score > best_score:
                                        best_score = score
                                        best_record = r
                                myv_data = best_record
                                annotations['myvariant_data'] = myv_data
                            
                            if isinstance(myv_data, dict):
                                if myv_data.get('clingen', {}).get('caid') and clingen_data['CAid'].startswith('N/A'): 
                                    clingen_data['CAid'] = myv_data['clingen']['caid']
                                
                                hgvs_data = myv_data.get('clinvar', {}).get('hgvs', {})
                                if isinstance(hgvs_data, dict) and hgvs_data.get('coding'):
                                    try:
                                        vep_data = query_vep(hgvs_data['coding'])
                                        if vep_data and "error" not in vep_data:
                                            annotations['vep_data'] = vep_data
                                    except Exception: 
                                        pass
                    else:
                        base_url = "https://reg.clinicalgenome.org/allele"
                        encoded_hgvs = quote(classification.extracted_identifier, safe='')
                        url = f"{base_url}?hgvs={encoded_hgvs}"
                        clingen_raw = {}
                        try:
                            response = requests.get(url, timeout=30)
                            response.raise_for_status()
                            clingen_raw = response.json()
                        except Exception:
                            cleaned_hgvs = classification.extracted_identifier.replace(" ", "")
                            encoded_cleaned = quote(cleaned_hgvs, safe='')
                            url = f"{base_url}?hgvs={encoded_cleaned}"
                            response = requests.get(url, timeout=30)
                            response.raise_for_status()
                            clingen_raw = response.json()

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
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button(" Clear Results", key="clear_sv_results"):
                if 'sv_analysis_data' in st.session_state: del st.session_state['sv_analysis_data']
                if 'sv_last_query' in st.session_state: del st.session_state['sv_last_query']
                st.rerun()
        with col2: 
            st.markdown(f"**Analyzing:** `{classification.extracted_identifier}`")
            
        st.markdown('<div class="info-box">', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1: st.write(f"**Variant ID:** {classification.extracted_identifier}")
        with col2: st.write(f"**Type:** {classification.query_type}")
        st.markdown('</div>', unsafe_allow_html=True)
        
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
            
        if annotations.get('myvariant_data') or annotations.get('vep_data'):
            st.markdown('<div class="section-header"> Analysis Results</div>', unsafe_allow_html=True)
            result_tabs = st.tabs([" VEP Analysis", " Functional Predictions", " Clinical Significance", " Literature", " AI Interpretation"])
            
            with result_tabs[0]:
                if annotations.get('vep_data'): display_vep_analysis(annotations['vep_data'], clingen_data.get('mane_ensembl'))
                else: st.info("No VEP data available for this variant.")
            with result_tabs[1]:
                if annotations.get('myvariant_data'): display_comprehensive_myvariant_data(annotations['myvariant_data'])
                else: st.info("No MyVariant data available.")
            with result_tabs[2]:
                if annotations.get('myvariant_data'):
                    myvariant_data = annotations['myvariant_data']
                    clinvar_data = myvariant_data.get('clinvar', {})
                    if clinvar_data:
                        st.subheader(" ClinVar Clinical Significance")
                        clinical_sig = clinvar_data.get('clinical_significance') or clinvar_data.get('clnsig')
                        if not clinical_sig and isinstance(clinvar_data.get('rcv'), list) and clinvar_data['rcv']:
                            sig_list = [rcv['clinical_significance'] for rcv in clinvar_data['rcv'] if isinstance(rcv, dict) and rcv.get('clinical_significance')]
                            if sig_list: clinical_sig = "; ".join(list(set(sig_list)))
                        if not clinical_sig: clinical_sig = 'Not Available'
                        
                        sig_color = "#dc3545" if 'pathogenic' in clinical_sig.lower() and 'benign' not in clinical_sig.lower() else ("#28a745" if 'benign' in clinical_sig.lower() else "#ffc107")
                        st.markdown(f'<div style="background-color: {sig_color}; color: white; padding: 15px; border-radius: 10px; margin-bottom: 20px;"><h3 style="margin:0; color:white;">{clinical_sig}</h3></div>', unsafe_allow_html=True)
            
            with result_tabs[3]:
                st.subheader(" PubMed Search Results & Literature")
                scholar_query = classification.extracted_identifier
                scholar_url = f"https://scholar.google.com/scholar?q={quote(scholar_query)}"
                st.markdown(f"[🔍 Search '{scholar_query}' on Google Scholar]({scholar_url})")
                st.write("")
                pubmed_papers = annotations.get('pubmed_data', [])
                if pubmed_papers:
                    if "selected_papers" not in st.session_state: st.session_state.selected_papers = {}
                    st.markdown("**Check the box next to any article to inject its details directly into the AI Copilot and AI Interpretation context:**")
                    for paper in pubmed_papers:
                        pmid = paper.get('pmid')
                        is_selected = pmid in st.session_state.selected_papers
                        col1, col2 = st.columns([0.05, 0.95])
                        with col1:
                            checked = st.checkbox("", value=is_selected, key=f"paper_{pmid}")
                            if checked != is_selected:
                                if checked: st.session_state.selected_papers[pmid] = paper
                                else: st.session_state.selected_papers.pop(pmid, None)
                                st.rerun()
                        with col2:
                            st.markdown(f"**[{paper.get('title')}]({paper.get('link')})**")
                            st.caption(f"PMID: {pmid} | Authors: {paper.get('authors')} | Journal: {paper.get('journal')} | Date: {paper.get('pubdate')}")
                            st.write("")
                else: st.info("No PubMed results found or available for this query.")
                
            with result_tabs[4]:
                st.markdown("###  AI-Powered Clinical Interpretation")
                if st.button("Generate AI Interpretation", type="primary", key="gen_ai_interp"):
                    genai = st.session_state.get("gemini_client")
                    if not genai: st.error("⚠️ **Gemini AI not available**")
                    else:
                        with st.spinner("Generating comprehensive interpretation..."):
                            try:
                                prompt = generate_summary_prompt(clingen_data, annotations.get('myvariant_data'), annotations.get('vep_data'))
                                model = genai.GenerativeModel('gemini-1.5-flash')
                                response = model.generate_content(prompt)
                                st.markdown(response.text)
                            except Exception as e:
                                st.error(f"AI interpretation failed: {str(e)}")
