import json
import sys
import os

# Add root directory to path
sys.path.insert(0, os.path.abspath("."))

from analysis.variant_analyser import VariantDataFetcher, VariantAnalyzer

def test_input_type(variant_id, query_type):
    print(f"\n==================================================")
    print(f" TESTING INPUT: '{variant_id}' | TYPE: '{query_type}'")
    print(f"==================================================")
    
    fetcher = VariantDataFetcher()
    analyzer = VariantAnalyzer()
    
    print("\n--- PHASE 1, 2, 3: Fetching Data via VariantDataFetcher ---")
    raw_data = fetcher.fetch_variant_data(variant_id, query_type)
    
    # Observe fetched APIs
    for api_key in ["clingen_data", "myvariant_data", "vep_data", "clinvar_data"]:
        val = raw_data.get(api_key)
        status = "POPULATED" if val and (not isinstance(val, dict) or "error" not in val) and val != [] else "EMPTY/ERROR"
        details = ""
        if isinstance(val, dict):
            if "error" in val:
                details = f"Error: {val['error']}"
            else:
                details = f"Keys count: {len(val.keys())}"
        elif isinstance(val, list):
            details = f"Items count: {len(val)}"
        print(f"  [{api_key}]: {status} ({details})")
        
    print("\n--- Running Analysis via VariantAnalyzer ---")
    analysis = analyzer.analyze_variant(raw_data)
    
    # Observe analysis output fields
    print("  [Pathogenicity]:", analysis.get("pathogenicity_prediction", {}).get("classification"), f"(Confidence: {analysis.get('pathogenicity_prediction', {}).get('confidence')})")
    print("  [Functional Impact]:", analysis.get("functional_impact", {}).get("protein_effect"))
    print("  [Clinical Relevance]:", analysis.get("clinical_relevance", {}).get("clinical_significance"))
    conditions = analysis.get("clinical_relevance", {}).get("associated_conditions", [])
    print("  [Associated Conditions]:", conditions[:3] if isinstance(conditions, list) else conditions)
    
    return raw_data, analysis

if __name__ == "__main__":
    test_cases = [
        ("rs113993960", "rsid"),
        ("NM_000492.3:c.1521_1523delCTT", "hgvs_transcript"),
        ("chr7:g.117559590_117559592del", "hgvs_genomic"),
    ]
    
    for vid, qtype in test_cases:
        test_input_type(vid, qtype)
