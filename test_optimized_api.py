import json
from core.api_clients import (
    query_clinvar, 
    query_clingen, 
    query_myvariant, 
    query_vep, 
    API_LOGS, 
    clear_api_logs
)

def run_test_case(name: str, test_func):
    print("=" * 60)
    print(f" RUNNING TEST CASE: {name}")
    print("=" * 60)
    
    clear_api_logs()
    
    try:
        result = test_func()
        print("\n--- Final Parse Result ---")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"\nTest threw unexpected exception: {e}")
        
    print("\n--- API Intermediate Logging & Raw Payloads ---")
    for log in API_LOGS:
        print(f"[{log['timestamp']}] [{log['step']}] {log['message']}")
        if log['raw_payload']:
            # Pretty print a snippet of the raw payload
            raw_str = json.dumps(log['raw_payload'], indent=2)
            # Limit printed payload size to 400 characters to keep it clean
            if len(raw_str) > 400:
                print(f"Raw Payload (truncated):\n{raw_str[:400]}\n... [truncated {len(raw_str)-400} chars]")
            else:
                print(f"Raw Payload:\n{raw_str}")
        print("-" * 40)
    print("\n")

def test_valid_rsid():
    return query_clinvar(rsid="rs80359876")

def test_valid_gene():
    return query_clinvar(gene_symbol="BRCA2")

def test_invalid_rsid():
    return query_clinvar(rsid="rs999999999999999")

def test_bad_hgvs_clingen():
    return query_clingen("invalid_format_string")

def test_empty_params():
    return query_clinvar()

if __name__ == "__main__":
    print("STARTING COMPREHENSIVE OUTLIER AND BUG TESTING OF OPTIMIZED GENOMIC API CLIENT\n")
    
    # 1. Valid rsID
    run_test_case("Valid rsID (BRCA2 Pathogenic Variant rs80359876)", test_valid_rsid)
    
    # 2. Valid Gene symbol ClinVar search (outlier / fallback scenario)
    run_test_case("Valid Gene symbol search fallback (BRCA2)", test_valid_gene)
    
    # 3. Invalid rsID (Outlier: not found)
    run_test_case("Non-existent rsID search", test_invalid_rsid)
    
    # 4. Bad HGVS syntax (Outlier: API error/malformed input)
    run_test_case("Malformed HGVS input to ClinGen API", test_bad_hgvs_clingen)
    
    # 5. Empty inputs (Outlier: Empty parameter protection)
    run_test_case("No parameters passed to query_clinvar", test_empty_params)
