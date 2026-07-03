import sys
import os
import json
from fastapi.testclient import TestClient

# Add project root to path
sys.path.insert(0, os.path.abspath("."))

from api.main import app

client = TestClient(app)

def test_pathway_a_upload_scale():
    print("\n==================================================")
    print(" PATHWAY A: Testing 500-Variant VCF Upload Scale")
    print("==================================================")
    
    vcf_path = "demo_500_variants.vcf"
    if not os.path.exists(vcf_path):
        from tests.generate_large_vcf import generate_large_vcf
        generate_large_vcf(vcf_path, 500)
        
    conv_id = "test_e2e_session_500"
    with open(vcf_path, "rb") as f:
        response = client.post("/api/upload/", data={"conversation_id": conv_id}, files={"file": ("demo_500_variants.vcf", f, "text/plain")})
        
    assert response.status_code == 200, f"Upload failed: {response.text}"
    data = response.json()
    assert data["status"] == "success"
    
    prioritized = data.get("prioritized", {})
    categories = ["dangerous", "possibly_harmful", "vus", "unannotated", "benign"]
    
    total_found = 0
    for cat in categories:
        items = prioritized.get(cat, [])
        total_found += len(items)
        print(f"  [Category '{cat}']: {len(items)} variants")
        if items:
            # Validate React Table prop schema for each variant
            sample = items[0]
            assert "variant" in sample, "Missing 'variant' key for VcfVariantTable row"
            assert "gene" in sample, "Missing 'gene' key"
            assert "location" in sample, "Missing 'location' key"
            assert "ref_alt" in sample, "Missing 'ref_alt' key"
            
    print(f"  Total Prioritized Variants Parsed: {total_found}")
    assert total_found == 500, f"Expected 500 variants, found {total_found}"
    print("  [PASS] Pathway A Verified Successfully!")

def test_pathway_b_row_expansion_contract():
    print("\n==================================================")
    print(" PATHWAY B: Testing Interactive Row Expansion Contract")
    print("==================================================")
    
    variants_to_test = ["rs113993960", "rs28934578", "rs334", "rs121909001"]
    for vid in variants_to_test:
        response = client.get(f"/api/chat/variant/{vid}")
        assert response.status_code == 200, f"Variant details failed for {vid}: {response.text}"
        details = response.json()
        
        # Deep prop inspection matching VariantDetailsTabs.jsx requirements
        assert "variant_id" in details, "Missing variant_id"
        assert "pathogenicity" in details, "Missing pathogenicity"
        assert "confidence" in details, "Missing confidence"
        assert "protein_effect" in details, "Missing protein_effect"
        assert "raw_data" in details, "Missing raw_data payload"
        
        # Verify JSON serializability of raw_data and analysis fields
        try:
            json.dumps(details)
        except TypeError as e:
            assert False, f"JSON serialization failed for variant {vid}: {str(e)}"
            
        print(f"  [Variant {vid}]: Pathogenicity='{details['pathogenicity']}' | JSON Serializability: VALID")
        
    print("  [PASS] Pathway B Verified Successfully!")

def test_pathway_c_agent_chat_and_tools():
    print("\n==================================================")
    print(" PATHWAY C: Testing Conversational Agent & Intent Tools")
    print("==================================================")
    
    conv_id = "test_agent_session_1"
    
    # Send message referencing row number
    req_payload = {
        "conversation_id": conv_id,
        "user_input": "Let's examine row #1 and row #2 from our uploaded file.",
        "ai_enabled": True,
        "sv_enabled": False,
        "ped_enabled": False
    }
    
    response = client.post("/api/chat/", json=req_payload)
    assert response.status_code == 200, f"Chat failed: {response.text}"
    chat_res = response.json()
    assert "response" in chat_res
    print("  [Agent Chat Response Received]:", chat_res["response"][:120].replace("\n", " ") + "...")
    print("  [PASS] Pathway C Verified Successfully!")

if __name__ == "__main__":
    test_pathway_a_upload_scale()
    test_pathway_b_row_expansion_contract()
    test_pathway_c_agent_chat_and_tools()
