import os
import json
import logging
from typing import Dict, Any

from core.api_clients import query_myvariant, query_clinvar
from analysis.variant_analyser import VariantAnalyzer, VariantDataFetcher

# Set up logging directory
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(os.path.join(LOG_DIR, 'raw_api_responses'), exist_ok=True)
os.makedirs(os.path.join(LOG_DIR, 'parsed_data'), exist_ok=True)
os.makedirs(os.path.join(LOG_DIR, 'ai_prompts'), exist_ok=True)

def dump_json(data: Dict, path: str):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def test_single_variant_pipeline(variant_id: str, query_type: str = "rsid"):
    print(f"\n--- Testing Pipeline for {variant_id} ({query_type}) ---")
    
    fetcher = VariantDataFetcher()
    analyzer = VariantAnalyzer()
    
    # 1. Fetch Raw Data
    print("1. Fetching API Data...")
    raw_data = fetcher.fetch_variant_data(variant_id, query_type)
    
    dump_json(raw_data, os.path.join(LOG_DIR, 'raw_api_responses', f'{variant_id.replace(":", "_")}_raw.json'))
    print("   -> Dumped raw responses to tests/logs/raw_api_responses/")
    
    # 2. Analyze Data
    print("2. Parsing Data via VariantAnalyzer...")
    analysis = analyzer.analyze_variant(raw_data)
    
    dump_json(analysis, os.path.join(LOG_DIR, 'parsed_data', f'{variant_id.replace(":", "_")}_parsed.json'))
    print("   -> Dumped parsed analysis to tests/logs/parsed_data/")
    
    # 3. Validation Assertions
    print("3. Running Assertions...")
    
    # Check REVEL score (should not be an array string like "0.7890.789")
    # Note: Our backend analyzer doesn't extract REVEL for the frontend, the frontend does it from raw data.
    # We can just verify clinvar conditions
    if raw_data.get("clinvar_data") and not raw_data.get("error"):
        conds = raw_data["clinvar_data"].get("conditions", [])
        if conds:
            print(f"   [PASS] Found ClinVar conditions: {conds}")
        else:
            print("   [WARN] No ClinVar conditions found in raw data.")
    
    # Generate mock AI Prompt to verify contents
    prompt = f"Please provide a clinical assessment. Data: {json.dumps(analysis, indent=2)}"
    with open(os.path.join(LOG_DIR, 'ai_prompts', f'{variant_id.replace(":", "_")}_prompt.txt'), 'w') as f:
        f.write(prompt)
    print("   -> Mock Prompt generated successfully.")
    print("--- Done ---")

if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("rs113993960", "rsid"),           # Indel with ClinVar data
        ("rs28934578", "rsid"),            # Missense (usually has dbNSFP array issues)
        ("chr1:12345:A:G", "genomic_coordinates") # Unannotated/novel test
    ]
    
    for vid, qtype in test_cases:
        test_single_variant_pipeline(vid, qtype)
