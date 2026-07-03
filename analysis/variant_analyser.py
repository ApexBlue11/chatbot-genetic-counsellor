import re
import json
import requests
import pandas as pd
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# Import existing project components
from core.query_router import GenomicQueryRouter, QueryClassification
from core.api_clients import query_myvariant, query_vep, query_clingen, query_clinvar
from core.disease_correlation import correlate_diseases

# ==================== VARIANT DATA FETCHING ====================

# ==================== VARIANT DATA FETCHING ====================

class VariantDataFetcher:
    def __init__(self):
        pass
    
    def fetch_variant_data(self, variant_id: str, query_type: str) -> Dict[str, Any]:
        """
        Fetch data for a specific variant based on its ID and type.
        
        Args:
            variant_id: The identifier for the variant (HGVS notation or rsID)
            query_type: The type of query (hgvs_transcript, hgvs_genomic, hgvs_protein, rsid)
            
        Returns:
            Dictionary containing variant data
        """
        result = {
            "myvariant_data": {},
            "vep_data": [],
            "clingen_data": {},
            "clinvar_data": {}
        }
        
        try:
            # Standardize genomic coordinates if provided
            formatted_hgvs_g = None
            if query_type == 'genomic_coordinates':
                parts = variant_id.split(':')
                if len(parts) == 4:
                    chrom, pos, ref, alt = parts[0], parts[1], parts[2], parts[3]
                    formatted_hgvs_g = f"{chrom}:g.{pos}{ref}>{alt}"
                else:
                    raise ValueError("Invalid genomic coordinates format. Expected 'chr:pos:ref:alt'.")

            # ── PHASE 1: Direct Queries for APIs that natively accept this input type ──
            if query_type == 'rsid':
                result["myvariant_data"] = query_myvariant(variant_id)
                result["clinvar_data"] = query_clinvar(rsid=variant_id)
                result["vep_data"] = query_vep(variant_id)
            elif query_type == 'genomic_coordinates':
                result["clingen_data"] = query_clingen(formatted_hgvs_g)
                result["myvariant_data"] = query_myvariant(formatted_hgvs_g)
                result["vep_data"] = query_vep(formatted_hgvs_g)
            elif query_type == 'gene_symbol':
                result["clinvar_data"] = query_clinvar(gene_symbol=variant_id)
            else: # HGVS (transcript, genomic, protein)
                result["clingen_data"] = query_clingen(variant_id)
                result["myvariant_data"] = query_myvariant(variant_id)
                if not query_type.startswith('hgvs_protein'):
                    result["vep_data"] = query_vep(variant_id)

            # ── PHASE 2: Multi-Source ID Resolution with OR Logic ──
            extracted_rsid = None
            if query_type == 'rsid':
                extracted_rsid = variant_id
            else:
                # 1. Try ClinGen dbSNP
                dbsnp_records = result["clingen_data"].get("externalRecords", {}).get("dbSNP", [])
                if dbsnp_records and dbsnp_records[0].get('rs'):
                    extracted_rsid = f"rs{dbsnp_records[0].get('rs')}"
                # 2. OR try MyVariant dbSNP
                elif result["myvariant_data"].get("dbsnp", {}).get("rsid"):
                    mv_rs = result["myvariant_data"]["dbsnp"]["rsid"]
                    extracted_rsid = mv_rs[0] if isinstance(mv_rs, list) else mv_rs
                    if not str(extracted_rsid).startswith('rs'):
                        extracted_rsid = f"rs{extracted_rsid}"
                # 3. OR try VEP colocated variants
                elif isinstance(result["vep_data"], list) and len(result["vep_data"]) > 0 and isinstance(result["vep_data"][0], dict):
                    colocated = result["vep_data"][0].get("colocated_variants", [])
                    for cv in colocated:
                        if cv.get("id", "").startswith("rs"):
                            extracted_rsid = cv["id"]
                            break

            # If ClinGen failed but MyVariant has a clingen.caid, rescue ClinGen data
            caid = result["myvariant_data"].get("clingen", {}).get("caid")
            if (not result["clingen_data"] or "error" in result["clingen_data"]) and caid:
                clingen_rescued = query_clingen(caid)
                if clingen_rescued and "error" not in clingen_rescued:
                    result["clingen_data"] = clingen_rescued
                    if not extracted_rsid:
                        dbsnp_records = clingen_rescued.get("externalRecords", {}).get("dbSNP", [])
                        if dbsnp_records and dbsnp_records[0].get('rs'):
                            extracted_rsid = f"rs{dbsnp_records[0].get('rs')}"

            # ── PHASE 3: Secondary Queries for unpopulated APIs using extracted IDs ──
            # Fill ClinVar if missing and extracted_rsid is found
            if not result["clinvar_data"] and extracted_rsid:
                result["clinvar_data"] = query_clinvar(rsid=extracted_rsid)

            # Fill VEP if missing and extracted_rsid is found
            if not result["vep_data"] and extracted_rsid:
                result["vep_data"] = query_vep(extracted_rsid)

            return result
        except Exception as e:
            return {"error": str(e)}

# ==================== VARIANT ANALYSIS ====================

class VariantAnalyzer:
    def __init__(self, api_key=None):
        self.api_key = api_key
    
    def analyze_variant(self, variant_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze variant data to provide interpretations and recommendations.
        
        Args:
            variant_data: Dictionary containing variant data from multiple sources
            
        Returns:
            Dictionary containing analysis results
        """
        # Extract data from different sources
        myvariant_data = variant_data.get("myvariant_data", {})
        vep_data = variant_data.get("vep_data", [])
        clinvar_data = variant_data.get("clinvar_data", {})
        clingen_data = variant_data.get("clingen_data", {})
        
        # Analyze pathogenicity
        pathogenicity = self._predict_pathogenicity(myvariant_data, vep_data, clinvar_data)
        
        # Analyze functional impact
        functional_impact = self._predict_functional_impact(myvariant_data, vep_data)
        
        # Assess clinical relevance
        clinical_relevance = self._assess_clinical_relevance(myvariant_data, clinvar_data, vep_data, clingen_data)
        
        # Find literature references
        literature_references = self._find_literature_references(myvariant_data, clinvar_data)
        
        return {
            "pathogenicity_prediction": pathogenicity,
            "functional_impact": functional_impact,
            "clinical_relevance": clinical_relevance,
            "literature_references": literature_references
        }
    
    def _predict_pathogenicity(self, myvariant_data: Dict[str, Any], vep_data: List[Dict[str, Any]], 
                              clinvar_data: Dict[str, Any]) -> Dict[str, Any]:
        """Predict the pathogenicity of a variant."""
        # Default values
        classification = "Variant of Uncertain Significance"
        confidence = "Low"
        evidence = []
        score = 0.5
        
        # Check ClinVar from MyVariant first (highest specificity to variant)
        mv_clinvar = myvariant_data.get('clinvar')
        found_clinvar = False
        
        if mv_clinvar and 'rcv' in mv_clinvar:
            rcvs = mv_clinvar['rcv']
            if not isinstance(rcvs, list):
                rcvs = [rcvs]
                
            # Try to find a pathogenic classification first
            for rcv in rcvs:
                if 'pathogenic' in str(rcv.get('clinical_significance', '')).lower():
                    classification = "Pathogenic"
                    break
                    
            if classification == "Variant of Uncertain Significance":
                # Take the first one if no pathogenic found
                classification = str(rcvs[0].get('clinical_significance', 'Uncertain'))
                
            confidence = "High (ClinVar)"
            evidence.append("ClinVar database")
            found_clinvar = True
            
        # Fallback to direct ClinVar E-utils data
        elif clinvar_data and "error" not in clinvar_data and clinvar_data.get("clinical_significance"):
            classification = clinvar_data.get('clinical_significance', 'Uncertain')
            confidence = "High (ClinVar)"
            evidence.append("ClinVar database")
            found_clinvar = True
            
        if found_clinvar:
            # Map classification to score
            if "pathogenic" in classification.lower():
                score = 0.9 if "likely" in classification.lower() else 1.0
            elif "benign" in classification.lower():
                score = 0.1 if "likely" in classification.lower() else 0.0
            else:
                score = 0.5
        
        # Check functional predictions from MyVariant if no ClinVar
        elif myvariant_data:
            pathogenic_criteria = 0
            benign_criteria = 0
            
            # Check SIFT and PolyPhen predictions
            dbnsfp = myvariant_data.get('dbnsfp', {})
            if dbnsfp:
                # SIFT: < 0.05 is damaging
                sift_score = None
                sift_data = dbnsfp.get('sift')
                if sift_data:
                    if isinstance(sift_data, dict):
                        sift_score = sift_data.get('score')
                    elif isinstance(sift_data, list) and len(sift_data) > 0:
                        sift_score = sift_data[0] if isinstance(sift_data[0], (int, float)) else None
                
                if sift_score is not None and sift_score < 0.05:
                    pathogenic_criteria += 1
                    evidence.append("SIFT damaging prediction")
                elif sift_score is not None and sift_score > 0.05:
                    benign_criteria += 1
                
                # PolyPhen: > 0.85 is probably damaging
                polyphen_score = None
                polyphen_data = dbnsfp.get('polyphen2')
                if polyphen_data:
                    if isinstance(polyphen_data, dict):
                        polyphen_score = polyphen_data.get('hdiv', {}).get('score') or polyphen_data.get('hvar', {}).get('score')
                    elif isinstance(polyphen_data, list) and len(polyphen_data) > 0:
                        polyphen_score = polyphen_data[0] if isinstance(polyphen_data[0], (int, float)) else None
                
                if polyphen_score is not None and polyphen_score > 0.85:
                    pathogenic_criteria += 1
                    evidence.append("PolyPhen probably damaging prediction")
                elif polyphen_score is not None and polyphen_score < 0.15:
                    benign_criteria += 1
            
            # Check VEP consequences
            if isinstance(vep_data, list) and len(vep_data) > 0 and isinstance(vep_data[0], dict) and 'error' not in vep_data[0]:
                transcript_consequences = vep_data[0].get('transcript_consequences', [])
                if transcript_consequences:
                    # Find the most severe impact
                    impacts = []
                    consequences = []
                    for transcript in transcript_consequences:
                        if isinstance(transcript, dict):
                            impact = transcript.get('impact', '').upper()
                            if impact:
                                impacts.append(impact)
                            cons_terms = transcript.get('consequence_terms', [])
                            if isinstance(cons_terms, list):
                                consequences.extend(cons_terms)
                    
                    # Check for high impact consequences
                    high_impact_terms = ['frameshift_variant', 'stop_gained', 'stop_lost', 
                                        'splice_donor_variant', 'splice_acceptor_variant', 'start_lost']
                    if any(term in consequences for term in high_impact_terms) or 'HIGH' in impacts:
                        pathogenic_criteria += 1
                        evidence.append("High impact variant consequence")
                    elif 'MODERATE' in impacts or 'missense_variant' in consequences:
                        evidence.append("Moderate impact (missense) variant")
                    elif 'LOW' in impacts or 'synonymous_variant' in consequences:
                        benign_criteria += 1
                        evidence.append("Low impact (synonymous) variant")
            
            # Determine classification based on criteria
            if pathogenic_criteria >= 2:
                classification = "Likely Pathogenic"
                confidence = "Medium"
                score = 0.8
            elif pathogenic_criteria == 1 and benign_criteria == 0:
                classification = "Possibly Pathogenic"
                confidence = "Low"
                score = 0.7
            elif benign_criteria >= 2:
                classification = "Likely Benign"
                confidence = "Medium"
                score = 0.2
            elif benign_criteria == 1 and pathogenic_criteria == 0:
                classification = "Possibly Benign"
                confidence = "Low"
                score = 0.3
        
        return {
            "score": score,
            "classification": classification,
            "confidence": confidence,
            "evidence": evidence
        }
    
    def _predict_functional_impact(self, myvariant_data: Dict[str, Any], vep_data: Any) -> Dict[str, Any]:
        """Predict the functional impact of a variant."""
        # Default values with specific missing data context
        protein_effect = "Unknown (no data available from VEP)"
        domain_affected = "Unknown (no data available from VEP)"
        structural_impact = "Unknown (no data available from VEP)"
        evolutionary_conservation = "Unknown (no conservation score available from MyVariant)"
        
        # Extract from VEP data
        if isinstance(vep_data, list) and len(vep_data) > 0 and isinstance(vep_data[0], dict) and 'error' not in vep_data[0]:
            variant_info = vep_data[0]
            transcripts = variant_info.get('transcript_consequences', [])
            
            if transcripts:
                # Find canonical or first protein-coding transcript
                primary_transcript = None
                for t in transcripts:
                    if t.get('canonical') == 1:
                        primary_transcript = t
                        break
                
                if not primary_transcript:
                    for t in transcripts:
                        if t.get('biotype') == 'protein_coding':
                            primary_transcript = t
                            break
                
                if not primary_transcript and transcripts:
                    primary_transcript = transcripts[0]
                
                if primary_transcript:
                    # Get protein effect
                    consequences = primary_transcript.get('consequence_terms', [])
                    if consequences:
                        protein_effect = consequences[0]
                    
                    # Get domain information if available
                    domains = primary_transcript.get('domains', [])
                    if domains:
                        domain_names = [d.get('db') + ":" + d.get('name') for d in domains if d.get('db') and d.get('name')]
                        if domain_names:
                            domain_affected = ", ".join(domain_names)
                    
                    # Get structural impact from SIFT/PolyPhen
                    sift = primary_transcript.get('sift_prediction')
                    polyphen = primary_transcript.get('polyphen_prediction')
                    
                    if sift and polyphen:
                        if 'deleterious' in sift.lower() and 'damaging' in polyphen.lower():
                            structural_impact = "High"
                        elif 'deleterious' in sift.lower() or 'damaging' in polyphen.lower():
                            structural_impact = "Moderate"
                        else:
                            structural_impact = "Low"
                    elif sift:
                        structural_impact = "Moderate" if 'deleterious' in sift.lower() else "Low"
                    elif polyphen:
                        structural_impact = "Moderate" if 'damaging' in polyphen.lower() else "Low"
        
        # Check MyVariant for conservation data
        if myvariant_data and 'dbnsfp' in myvariant_data:
            dbnsfp = myvariant_data['dbnsfp']
            
            # Check conservation scores
            phylop = dbnsfp.get('phylop100way_vertebrate')
            if phylop:
                score = phylop
                if isinstance(score, list) and score:
                    score = score[0]
                
                if isinstance(score, (int, float)):
                    if score > 1.5:
                        evolutionary_conservation = "High"
                    elif score > 0.5:
                        evolutionary_conservation = "Medium"
                    else:
                        evolutionary_conservation = "Low"
            else:
                evolutionary_conservation = "Unknown (no phylop score in MyVariant dbnsfp data)"
        else:
            evolutionary_conservation = "Unknown (no dbnsfp data available from MyVariant)"
        
        return {
            "protein_effect": protein_effect,
            "domain_affected": domain_affected,
            "structural_impact": structural_impact,
            "evolutionary_conservation": evolutionary_conservation
        }
    
    def _assess_clinical_relevance(self, myvariant_data: Dict[str, Any], clinvar_data: Dict[str, Any], vep_data: List[Dict[str, Any]], clingen_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess the clinical relevance of a variant."""
        # Default values
        associated_conditions = []
        clinical_significance = "Unknown"
        actionability = "Unknown"
        guidelines = "Consult with a genetic counselor for interpretation"

        # Use correlate_diseases to get disease associations
        disease_matches = correlate_diseases(myvariant_data, vep_data, clingen_data)

        for match in disease_matches:
            associated_conditions.append(match.disease_name)
            # Prioritize clinical significance from ClinVar RCV if available
            if match.clinical_significance != "Not specified" and match.clinical_significance != "Inferred":
                clinical_significance = match.clinical_significance

        # Check ClinVar data first
        if clinvar_data and "error" not in clinvar_data:
            if clinvar_data.get("conditions"):
                associated_conditions = clinvar_data.get("conditions", [])
            
            if clinvar_data.get("clinical_significance"):
                clinical_significance = clinvar_data.get("clinical_significance")
            
            # Determine actionability based on clinical significance
            if "pathogenic" in clinical_significance.lower():
                actionability = "High"
                guidelines = "Recommend genetic counseling and clinical management"
            elif "benign" in clinical_significance.lower():
                actionability = "Low"
                guidelines = "No specific clinical action indicated"
            else:
                actionability = "Medium"
                guidelines = "Consider genetic counseling for further evaluation"
        
        # Check MyVariant data if ClinVar data is not available
        elif myvariant_data:
            # Check for ClinVar data within MyVariant
            if 'clinvar' in myvariant_data:
                clinvar = myvariant_data['clinvar']
                
                # Get conditions safely
                if clinvar.get('rcv'):
                    rcv_list = clinvar['rcv'] if isinstance(clinvar['rcv'], list) else [clinvar['rcv']]
                    for rcv in rcv_list:
                        if isinstance(rcv, dict) and rcv.get('conditions'):
                            cond = rcv['conditions']
                            if isinstance(cond, dict):
                                name = cond.get('name') or cond.get('synonyms')
                                if name: associated_conditions.append(name if isinstance(name, str) else str(name))
                            elif isinstance(cond, list):
                                for c in cond:
                                    if isinstance(c, dict) and c.get('name'):
                                        associated_conditions.append(str(c['name']))
                                    elif isinstance(c, str):
                                        associated_conditions.append(c)
                            elif isinstance(cond, str):
                                associated_conditions.append(cond)
                
                # Get clinical significance
                if clinvar.get('clinical_significance'):
                    clinical_significance = clinvar['clinical_significance']
                    
                    # Determine actionability based on clinical significance
                    if "pathogenic" in str(clinical_significance).lower():
                        actionability = "High"
                        guidelines = "Recommend genetic counseling and clinical management"
                    elif "benign" in str(clinical_significance).lower():
                        actionability = "Low"
                        guidelines = "No specific clinical action indicated"
                    else:
                        actionability = "Medium"
                        guidelines = "Consider genetic counseling for further evaluation"
        
        # Remove duplicates safely
        clean_conditions = []
        for cond in associated_conditions:
            cond_str = str(cond['name']) if isinstance(cond, dict) and 'name' in cond else str(cond)
            if cond_str not in clean_conditions:
                clean_conditions.append(cond_str)
        associated_conditions = clean_conditions
        
        return {
            "associated_conditions": associated_conditions,
            "clinical_significance": clinical_significance,
            "actionability": actionability,
            "guidelines": guidelines
        }
    
    def _find_literature_references(self, myvariant_data: Dict[str, Any], clinvar_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Find literature references for a variant."""
        references = []

        # Check for PubMed references in MyVariant data
        if myvariant_data and 'clinvar' in myvariant_data:
            clinvar = myvariant_data['clinvar']

            if clinvar.get('citations'):
                citations = clinvar['citations']

                if isinstance(citations, list):
                    for citation in citations[:5]:  # Limit to 5 references
                        if citation.get('id') and citation.get('type') == 'PubMed':
                            # We don't have full citation details, so create a placeholder
                            references.append({
                                "title": f"PubMed ID: {citation['id']}",
                                "authors": "See PubMed",
                                "journal": "See PubMed",
                                "year": "N/A",
                                "doi": f"https://pubmed.ncbi.nlm.nih.gov/{citation['id']}/"
                            })

        # Check for PubMed references in ClinVar data
        if clinvar_data and clinvar_data.get("uid"):
            # ClinVar data from query_clinvar provides a UID which can be used to search PubMed
            # For simplicity, we'll just create a link to the ClinVar entry itself
            # A more advanced implementation would query PubMed with the UID or title
            clinvar_uid = clinvar_data["uid"]
            clinvar_title = clinvar_data.get("title", f"ClinVar Entry {clinvar_uid}")
            references.append({
                "title": clinvar_title,
                "authors": "ClinVar",
                "journal": "ClinVar",
                "year": "N/A",
                "doi": f"https://www.ncbi.nlm.nih.gov/clinvar/{clinvar_uid}/"
            })

        # If no references found, provide a generic message
        if not references:
            references.append({
                "title": "No specific literature references found",
                "authors": "N/A",
                "journal": "N/A",
                "year": "N/A",
                "doi": "N/A"
            })
        return references

    def generate_report(self, query: str, variant_data: Dict[str, Any], analysis_results: Dict[str, Any]) -> str:
        """
        Generate a comprehensive report for the variant.
        
        Args:
            query: The original query string
            variant_data: Dictionary containing variant data
            analysis_results: Dictionary containing analysis results
            
        Returns:
            String containing the formatted report
        """
        # Extract basic variant information
        myvariant_data = variant_data.get("myvariant_data", {})
        vep_data = variant_data.get("vep_data", [])
        clinvar_data = variant_data.get("clinvar_data", {})
        clingen_data = variant_data.get("clingen_data", {})
        
        # Get variant identifier
        identifier = query
        
        # Get gene information
        gene = "Unknown"
        if clinvar_data and clinvar_data.get("gene_symbol"):
            gene = clinvar_data.get("gene_symbol")
        elif myvariant_data:
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
        
        # Get location information
        chrom = "Unknown"
        pos = "Unknown"
        ref = "Unknown"
        alt = "Unknown"
        
        if myvariant_data:
            chrom = (myvariant_data.get('hg38', {}).get('chr') or 
                    myvariant_data.get('chrom') or 'Unknown')
            
            hg38_data = myvariant_data.get('hg38', {})
            pos = (hg38_data.get('start') or 
                  hg38_data.get('end') or 
                  hg38_data.get('pos') or 
                  myvariant_data.get('pos') or 'Unknown')
            
            ref = (myvariant_data.get('hg38', {}).get('ref') or 
                  myvariant_data.get('ref') or 'Unknown')
            
            alt = (myvariant_data.get('hg38', {}).get('alt') or 
                  myvariant_data.get('alt') or 'Unknown')
        
        # Get consequence information
        consequence = "Unknown"
        if vep_data and len(vep_data) > 0:
            variant_info = vep_data[0]
            transcripts = variant_info.get('transcript_consequences', [])
            
            if transcripts and len(transcripts) > 0:
                consequences = transcripts[0].get('consequence_terms', [])
                if consequences:
                    consequence = ", ".join(consequences)
        
        # Generate the report
        report = f"""
# Genetic Variant Analysis Report

## Query
Original query: {query}

## Variant Information
- Identifier: {identifier}
- Gene: {gene}
- Chromosome: {chrom}
- Position: {pos}
- Reference: {ref}
- Alternate: {alt}
- Consequence: {consequence}

## Pathogenicity Assessment
- Classification: {analysis_results['pathogenicity_prediction']['classification']}
- Confidence: {analysis_results['pathogenicity_prediction']['confidence']}
- Evidence: {', '.join(analysis_results['pathogenicity_prediction']['evidence']) if analysis_results['pathogenicity_prediction']['evidence'] else 'No specific evidence available'}

## Functional Impact
- Protein Effect: {analysis_results['functional_impact']['protein_effect']}
- Domain Affected: {analysis_results['functional_impact']['domain_affected']}
- Structural Impact: {analysis_results['functional_impact']['structural_impact']}
- Evolutionary Conservation: {analysis_results['functional_impact']['evolutionary_conservation']}

## Clinical Relevance
- Associated Conditions: {', '.join(analysis_results['clinical_relevance']['associated_conditions']) if analysis_results['clinical_relevance']['associated_conditions'] else 'None reported'}
- Clinical Significance: {analysis_results['clinical_relevance']['clinical_significance']}
- Actionability: {analysis_results['clinical_relevance']['actionability']}
- Guidelines: {analysis_results['clinical_relevance']['guidelines']}

## Literature References
{self._format_references(analysis_results['literature_references'])}
"""
        return report
    
    def _format_references(self, references: List[Dict[str, str]]) -> str:
        """Format literature references for the report."""
        if not references:
            return "No references found."
        
        formatted = ""
        for i, ref in enumerate(references, 1):
            formatted += f"{i}. {ref['authors']} ({ref['year']}). {ref['title']}. {ref['journal']}. DOI: {ref['doi']}\n"
        
        return formatted

# ==================== MAIN INTEGRATION CLASS ====================

class GeneticVariantAnalyzer:
    def __init__(self, openai_api_key=None, variant_api_key=None):
        self.query_router = GenomicQueryRouter()
        self.data_fetcher = VariantDataFetcher(api_key=variant_api_key)
        self.analyzer = VariantAnalyzer(openai_api_key=openai_api_key)
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """
        Process a user query about genetic variants.
        
        Args:
            query: The user input string
            
        Returns:
            Dictionary containing the processing results
        """
        # Step 1: Classify the query
        classification = self.query_router.classify_query(query)
        
        # If not a genomic query, return early
        if not classification.is_genomic:
            return {
                "is_genomic": False,
                "message": "This does not appear to be a genomic query."
            }
        
        # Step 2: Fetch variant data
        variant_data = self.data_fetcher.fetch_variant_data(
            classification.extracted_identifier,
            classification.query_type
        )
        
        # Step 3: Analyze the variant
        analysis_results = self.analyzer.analyze_variant(variant_data)
        
        # Step 4: Generate a report
        report = self.analyzer.generate_report(query, variant_data, analysis_results)
        
        # Return the complete results
        return {
            "is_genomic": True,
            "query_type": classification.query_type,
            "extracted_identifier": classification.extracted_identifier,
            "variant_data": variant_data,
            "analysis_results": analysis_results,
            "report": report
        }

# ==================== USAGE EXAMPLE ====================

def example_usage():
    """Example of how to use the GeneticVariantAnalyzer class."""
    # Initialize the analyzer
    analyzer = GeneticVariantAnalyzer(
        openai_api_key="your_openai_api_key",
        variant_api_key="your_variant_api_key"
    )
    
    # Process a query
    query = "What can you tell me about NM_000546.5:c.215C>G?"
    results = analyzer.process_query(query)
    
    # Check if it's a genomic query
    if results["is_genomic"]:
        print(f"Query type: {results['query_type']}")
        print(f"Identifier: {results['extracted_identifier']}")
        print("\nReport:")
        print(results["report"])
    else:
        print(results["message"])

if __name__ == "__main__":
    example_usage()