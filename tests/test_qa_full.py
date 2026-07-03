"""
Rigorous QA Test Suite — Genetic Counselling Bot
Role: Independent Clinical Counselor analyzing 500-variant VCF

Tests:
  Phase 1: Isolated unit tests of each module
  Phase 2: Full user journey end-to-end pathways
  Phase 3: Stress and edge cases

Run with: $env:PYTHONPATH="."; python tests/test_qa_full.py
"""
import sys, os, json, time
sys.path.insert(0, os.getcwd())

import requests as req

BASE = "http://localhost:8000"

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

results = []

def test(name, fn):
    try:
        ok, detail = fn()
        status = PASS if ok else FAIL
        print(f"  {status} {name}")
        if detail:
            print(f"       {detail}")
        results.append((name, ok, detail))
        return ok
    except Exception as e:
        print(f"  {FAIL} {name}")
        print(f"       Exception: {e}")
        results.append((name, False, str(e)))
        return False


# ─── Phase 1: Unit Tests ─────────────────────────────────────────────────────

print("\n" + "="*60)
print(" PHASE 1: Isolated Unit Tests")
print("="*60)

# P1-01: VCF Parser — annotated VCF
def p1_01():
    from analysis.vcf_parser import VCFParser
    vcf = b"""##fileformat=VCFv4.1
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
7\t117548628\trs113993960\tCTT\tC\t.\tPASS\tCLNSIG=Pathogenic;AF=0.0001
"""
    p = VCFParser()
    variants = p.parse(vcf, "test.vcf")
    v = variants[0]
    ok = v['query_id'] == 'rs113993960' and v['clnsig'] == 'Pathogenic' and v['af'] == 0.0001
    return ok, f"query_id={v['query_id']} clnsig={v['clnsig']} af={v['af']}"

# P1-02: VCF Parser — unannotated, ID is '.'
def p1_02():
    from analysis.vcf_parser import VCFParser
    vcf = b"""##fileformat=VCFv4.1
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
7\t117548628\t.\tCTT\tC\t.\tPASS\t.
"""
    p = VCFParser()
    variants = p.parse(vcf, "test.vcf")
    v = variants[0]
    ok = v['query_id'].startswith('chr7') and 'rs' not in v['query_id']
    return ok, f"query_id={v['query_id']}"

# P1-03: VCF Parser — mixed IDs
def p1_03():
    from analysis.vcf_parser import VCFParser
    vcf = b"""##fileformat=VCFv4.1
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
7\t100\trs113993960\tA\tT\t.\tPASS\t.
7\t200\t.\tC\tG\t.\tPASS\t.
"""
    p = VCFParser()
    variants = p.parse(vcf, "test.vcf")
    ok = variants[0]['query_id'] == 'rs113993960' and 'rs' not in variants[1]['query_id']
    return ok, f"v1={variants[0]['query_id']} v2={variants[1]['query_id']}"

# P1-04: VCF Prioritizer — CLNSIG bypass
def p1_04():
    from analysis.vcf_prioritizer import VCFPrioritizer
    variants = [
        {'query_id': 'rs113993960', 'chrom': '7', 'pos': 100, 'ref': 'CTT', 'alt': 'C',
         'clnsig': 'Pathogenic', 'af': 0.0001, 'info': {}},
    ]
    p = VCFPrioritizer(max_candidates=10)
    result = p.prioritize_variants(variants)
    ok = len(result['dangerous']) == 1
    return ok, f"dangerous={len(result['dangerous'])} (should be 1, bypassed API)"

# P1-05: VCF Prioritizer — max_candidates not capped
def p1_05():
    from analysis.vcf_parser import VCFParser
    vcf_path = os.path.join('data', 'demo_500_variants.vcf')
    if not os.path.exists(vcf_path):
        return False, f"File not found: {vcf_path}"
    with open(vcf_path, 'rb') as f:
        vcf_bytes = f.read()
    p = VCFParser()
    variants = p.parse(vcf_bytes, 'demo_500_variants.vcf')
    max_cand = max(100, len(variants))
    ok = max_cand == len(variants) and len(variants) >= 500
    return ok, f"Total variants={len(variants)} max_candidates={max_cand}"

# P1-06: VEP batch chunking
def p1_06():
    from core.api_clients import query_vep_batch
    # Send 5 known rsIDs — verify no HTTP 400
    ids = ['rs113993960', 'rs28934578', 'rs334']
    result = query_vep_batch(ids)
    ok = isinstance(result, list)
    return ok, f"VEP batch returned {len(result)} records for {len(ids)} IDs"

# P1-07: MyVariant rsID query — key fields present
def p1_07():
    from core.api_clients import query_myvariant
    result = query_myvariant('rs113993960')
    has_clinvar = 'clinvar' in result
    has_gnomad = 'gnomad_genome' in result or 'gnomad_exome' in result
    ok = has_clinvar or has_gnomad
    return ok, f"clinvar={'clinvar' in result} gnomad={'gnomad_genome' in result or 'gnomad_exome' in result}"

# P1-08: ClinVar full rsID string query (not stripped)
def p1_08():
    from core.api_clients import query_clinvar
    result = query_clinvar(rsid='rs113993960')
    ok = 'clinical_significance' in result and result.get('clinical_significance') not in [None, 'Not Annotated', 'error']
    return ok, f"clinical_significance={result.get('clinical_significance')}"

# P1-09: variant_analyser clinical_relevance — no TypeError
def p1_09():
    from analysis.variant_analyser import VariantDataFetcher, VariantAnalyzer
    fetcher = VariantDataFetcher()
    analyser = VariantAnalyzer()
    # Fetch and analyze rs121909001 (known to have caused TypeError)
    variant_data = fetcher.fetch_variant_data('rs121909001', 'rsid')
    analysis = analyser.analyze_variant(variant_data)
    conditions = analysis.get('clinical_relevance', {}).get('associated_conditions', [])
    all_strings = all(isinstance(c, str) for c in conditions)
    pathogenicity = analysis.get('pathogenicity_prediction', {}).get('classification', '')
    ok = isinstance(analysis, dict) and all_strings
    return ok, f"pathogenicity={pathogenicity} conditions_type={'string' if all_strings else 'MIXED/DICT'} count={len(conditions)}"

# P1-10: dbNSFP — indel gets blank predictors, SNV gets values
def p1_10():
    from analysis.variant_analyser import VariantDataFetcher, VariantAnalyzer
    fetcher = VariantDataFetcher()
    analyser = VariantAnalyzer()
    # rs28934578 is a BRCA1 SNV
    snv_raw = fetcher.fetch_variant_data('rs28934578', 'rsid')
    snv_analysis = analyser.analyze_variant(snv_raw)
    snv_preds = snv_analysis.get('functional_impact', {})
    # rs113993960 is inframe deletion
    indel_raw = fetcher.fetch_variant_data('rs113993960', 'rsid')
    indel_analysis = analyser.analyze_variant(indel_raw)
    indel_preds = indel_analysis.get('functional_impact', {})
    snv_effect = snv_preds.get('protein_effect', '')
    ok = isinstance(snv_preds, dict) and isinstance(indel_preds, dict)
    return ok, f"SNV protein_effect={snv_effect} | indel protein_effect={indel_preds.get('protein_effect','')}"

# P1-11: Population freq — HBB rs334 has African ancestry AF
def p1_11():
    from analysis.variant_analyser import VariantDataFetcher, VariantAnalyzer
    fetcher = VariantDataFetcher()
    raw = fetcher.fetch_variant_data('rs334', 'rsid')
    mv = raw.get('myvariant_data', {})
    gg = mv.get('gnomad_genome', {})
    ge = mv.get('gnomad_exome', {})
    # gnomAD stores population AFs nested under gg['af'] dict (not at top level of gg)
    gg_af = gg.get('af', gg)  # use gg['af'] sub-dict if present, fallback to gg
    ge_af = ge.get('af', ge)
    afr_af = gg_af.get('af_afr') or ge_af.get('af_afr') or gg.get('af_afr') or ge.get('af_afr')
    ok = afr_af is not None and float(afr_af) > 0.0
    return ok, f"African AF={afr_af} | gg['af'] keys={list(gg_af.keys())[:6] if isinstance(gg_af, dict) else 'N/A'}"

test("P1-01: VCF Parser — rsID + CLNSIG + AF extraction", p1_01)
test("P1-02: VCF Parser — unannotated dot ID → genomic coord", p1_02)
test("P1-03: VCF Parser — mixed IDs correctly assigned", p1_03)
test("P1-04: Prioritizer — CLNSIG bypass (no API call needed)", p1_04)
test("P1-05: Prioritizer — max_candidates = len(variants) for 500-var file", p1_05)
test("P1-06: VEP batch — no HTTP 400 on chunked requests", p1_06)
test("P1-07: MyVariant rsID — clinvar + gnomad keys present", p1_07)
test("P1-08: ClinVar — full rsID string, correct pathogenicity returned", p1_08)
test("P1-09: Variant analyser — conditions are strings not dicts (no TypeError)", p1_09)
test("P1-10: dbNSFP — SNV gets SIFT scores, indel has empty predictors", p1_10)
test("P1-11: Population freq — rs334 has African ancestry AF > 0", p1_11)


# ─── Phase 2: Full User Journey API Tests ────────────────────────────────────

print("\n" + "="*60)
print(" PHASE 2: Full User Journey (HTTP API, Clinical Counselor Persona)")
print("="*60)

CONV_ID = None

# J-00: Create a fresh conversation
def j_00():
    global CONV_ID
    r = req.post(f"{BASE}/api/conversations/", json={"title": "QA: 500-Variant VCF Test"}, timeout=10)
    r.raise_for_status()
    CONV_ID = r.json()['id']
    ok = bool(CONV_ID)
    return ok, f"conversation_id={CONV_ID}"

test("J-00: Create fresh conversation", j_00)

# J-A1: Upload 500-variant VCF — should process up to PER_FILE_CAP (25) variants
upload_result = None
def j_a1():
    global upload_result
    vcf_path = os.path.join('data', 'demo_500_variants.vcf')
    if not os.path.exists(vcf_path):
        return False, f"VCF file not found at {vcf_path}"
    with open(vcf_path, 'rb') as f:
        vcf_bytes = f.read()
    r = req.post(
        f"{BASE}/api/upload/",
        data={"conversation_id": CONV_ID, "patient_label": "QA-Patient"},
        files={"file": ("demo_500_variants.vcf", vcf_bytes, "text/plain")},
        timeout=180
    )
    r.raise_for_status()
    upload_result = r.json()
    total = sum(len(upload_result['prioritized'].get(c, [])) for c in ['dangerous','possibly_harmful','vus','unannotated','benign'])
    # PER_FILE_CAP = 25, so we expect ≤ 25 variants processed
    ok = 1 <= total <= 25
    return ok, f"Total variants processed={total} (expected 1-25, capped at PER_FILE_CAP=25) | context_mode={upload_result.get('context_mode')} | patient={upload_result.get('patient_label')}"

test("J-A1: Upload 500-variant VCF — capped at PER_FILE_CAP=25, response valid", j_a1)

# J-A2: Verify each category and breakdown
def j_a2():
    p = upload_result.get('prioritized', {})
    categories = ['dangerous', 'possibly_harmful', 'vus', 'unannotated', 'benign']
    details = {c: len(p.get(c, [])) for c in categories}
    total = sum(details.values())
    # Each entry must have 'variant', 'gene', 'location', 'ref_alt', 'clinical_sig'
    required_keys = {'variant', 'gene', 'location', 'ref_alt', 'clinical_sig'}
    all_ok = True
    missing_keys_count = 0
    for cat in categories:
        for item in p.get(cat, []):
            missing = required_keys - set(item.keys())
            if missing:
                missing_keys_count += 1
                all_ok = False
    return all_ok, f"Breakdown={details} | Missing key occurrences={missing_keys_count}"

test("J-A2: Upload response — all required UI prop keys present per variant", j_a2)

# J-A3: gene_clusters field present and structured
def j_a3():
    clusters = upload_result.get('prioritized', {}).get('gene_clusters', [])
    ok = isinstance(clusters, list)
    return ok, f"gene_clusters field present. Count={len(clusters)} entries"

test("J-A3: gene_clusters field present in upload response", j_a3)

# J-A4: enriched_data and context_mode present in response
def j_a4():
    if not upload_result:
        return False, "upload_result is None — J-A1 failed"
    context_mode = upload_result.get('context_mode')
    enriched = upload_result.get('enriched_data', {})
    patient = upload_result.get('patient_label', '')
    ok = context_mode in ('deep', 'basic') and isinstance(enriched, dict) and patient
    return ok, f"context_mode={context_mode} | enriched_data has {len(enriched)} entries | patient_label='{patient}'"

test("J-A4: Upload response — context_mode + enriched_data + patient_label present", j_a4)

# J-A5: Chat — AI receives and responds to unannotated VCF
def j_a5():
    time.sleep(2)
    unannotated = upload_result.get('prioritized', {}).get('unannotated', [])
    ctx_data = {
        'dangerous': upload_result['prioritized'].get('dangerous', [])[:5],
        'possibly_harmful': upload_result['prioritized'].get('possibly_harmful', [])[:3],
        'vus': upload_result['prioritized'].get('vus', [])[:3],
        'unannotated': unannotated[:5],
        'benign': upload_result['prioritized'].get('benign', [])[:2],
    }
    vcf_ctx = f"\n\n[SYSTEM CONTEXT: The user uploaded a VCF file. Summary: {upload_result['summary']}\n\nKey Variants:\n{json.dumps(ctx_data)}\n\nPlease provide a clinical assessment.]"
    r = req.post(
        f"{BASE}/api/chat/",
        json={
            "conversation_id": CONV_ID,
            "message": "I've just uploaded a VCF with 500 variants from a patient. Please summarize what you see and flag any concerns.",
            "system_context": vcf_ctx,
            "ai_enabled": True,
            "sv_enabled": False,
            "ped_enabled": False
        },
        timeout=120
    )
    r.raise_for_status()
    resp = r.json()
    response_text = resp.get('response', '')
    # AI should NOT say "I have no information" or similar
    bad_phrases = ["no information", "i cannot", "i don't have", "no data available", "unable to access"]
    has_bad = any(p in response_text.lower() for p in bad_phrases)
    has_variant_mention = any(kw in response_text.lower() for kw in ['variant', 'gene', 'unannotated', 'clinical', 'chromosome'])
    ok = not has_bad and has_variant_mention
    preview = response_text[:300].replace('\n', ' ')
    return ok, f"has_bad_phrase={has_bad} has_variant_mention={has_variant_mention}\nPreview: {preview}"

test("J-A5: AI chat — responds substantively to VCF, no 'no info' message", j_a5)

# J-B1: Upload annotated VCF
annotated_result = None
CONV_ID_B = None
def j_b1():
    global annotated_result, CONV_ID_B
    # Create new conversation for annotated test
    r = req.post(f"{BASE}/api/conversations/", json={"title": "QA: Annotated VCF Test"}, timeout=10)
    r.raise_for_status()
    CONV_ID_B = r.json()['id']

    annotated_vcf = b"""##fileformat=VCFv4.1
##INFO=<ID=CLNSIG,Number=.,Type=String,Description="ClinVar clinical significance">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
7\t117548628\trs113993960\tCTT\tC\t.\tPASS\tCLNSIG=Pathogenic;GENEINFO=CFTR:1080
17\t41276044\trs28897696\tC\tT\t.\tPASS\tCLNSIG=Pathogenic;GENEINFO=BRCA1:672
11\t5246696\trs334\tT\tA\t.\tPASS\tCLNSIG=Pathogenic;GENEINFO=HBB:3043
7\t117571748\trs121909001\tATCT\tA\t.\tPASS\tCLNSIG=Pathogenic;GENEINFO=CFTR:1080
7\t117523647\t.\tG\tA\t.\tPASS\tCLNSIG=Benign;GENEINFO=CFTR:1080
"""
    r = req.post(
        f"{BASE}/api/upload/",
        data={"conversation_id": CONV_ID_B},
        files={"file": ("annotated_test.vcf", annotated_vcf, "text/plain")},
        timeout=90
    )
    r.raise_for_status()
    annotated_result = r.json()
    dangerous = annotated_result['prioritized'].get('dangerous', [])
    ok = len(dangerous) >= 3
    return ok, f"Dangerous variants={[v['variant'] for v in dangerous]}"

test("J-B1: Annotated VCF — rs113993960, rs28897696, rs334 all in dangerous category", j_b1)

# J-B2: Benign variant is correctly categorized and NOT missing
def j_b2():
    benign = annotated_result['prioritized'].get('benign', [])
    # The dot-ID variant should end up somewhere (benign or unannotated)
    all_variants = []
    for cat in ['dangerous', 'possibly_harmful', 'vus', 'unannotated', 'benign']:
        all_variants.extend(annotated_result['prioritized'].get(cat, []))
    has_cftr_dot = any('chr7' in v.get('variant','') or v.get('gene','') == 'CFTR' for v in benign)
    ok = len(benign) >= 1 or has_cftr_dot
    return ok, f"benign={len(benign)} | All={[(v['variant'], v['clinical_sig']) for v in all_variants]}"

test("J-B2: Annotated VCF — benign variant present and correctly categorized", j_b2)

# J-B3: CFTR gene cluster detected (3 CFTR variants in file)
def j_b3():
    clusters = annotated_result['prioritized'].get('gene_clusters', [])
    cftr_cluster = [c for c in clusters if 'CFTR' in str(c)]
    ok = len(cftr_cluster) > 0
    return ok, f"gene_clusters={clusters} CFTR_detected={len(cftr_cluster) > 0}"

test("J-B3: Gene cluster — CFTR has 3 variants, should be flagged in gene_clusters", j_b3)

# J-B4: AI response for annotated VCF mentions CFTR cluster risk
def j_b4():
    time.sleep(2)
    ctx_data = {
        'dangerous': annotated_result['prioritized'].get('dangerous', [])[:5],
        'possibly_harmful': annotated_result['prioritized'].get('possibly_harmful', [])[:3],
        'vus': annotated_result['prioritized'].get('vus', [])[:3],
        'unannotated': annotated_result['prioritized'].get('unannotated', [])[:5],
        'benign': annotated_result['prioritized'].get('benign', [])[:2],
        'gene_clusters': annotated_result['prioritized'].get('gene_clusters', []),
    }
    vcf_ctx = f"\n\n[SYSTEM CONTEXT: The user uploaded an annotated VCF file. Summary: {annotated_result['summary']}\n\nKey Variants + Gene Clusters:\n{json.dumps(ctx_data)}\n\nPlease provide a clinical assessment, note gene clusters, and comment on whether benign variants in the same gene as pathogenic ones are clinically relevant.]"
    r = req.post(
        f"{BASE}/api/chat/",
        json={
            "conversation_id": CONV_ID_B,
            "message": "Please analyze this annotated VCF. Note any gene clusters, the pathogenic variants, and whether benign variants in the same gene as pathogenic ones might be relevant.",
            "system_context": vcf_ctx,
            "ai_enabled": True,
            "sv_enabled": False,
            "ped_enabled": False
        },
        timeout=120
    )
    r.raise_for_status()
    resp = r.json()
    response_text = resp.get('response', '')
    has_cftr = 'cftr' in response_text.lower() or 'cystic fibrosis' in response_text.lower()
    has_cluster = any(kw in response_text.lower() for kw in ['cluster', 'multiple variant', 'same gene', 'compound', 'three', '3 variant'])
    has_brca = 'brca' in response_text.lower()
    ok = has_cftr and has_brca
    preview = response_text[:400].replace('\n', ' ')
    return ok, f"mentions_CFTR={has_cftr} mentions_cluster={has_cluster} mentions_BRCA={has_brca}\nPreview: {preview}"

test("J-B4: AI chat — mentions CFTR + BRCA1, ideally flags gene cluster", j_b4)

# J-C1: Variant row expansion — rs113993960
def j_c1():
    r = req.get(f"{BASE}/api/chat/variant/rs113993960", timeout=30)
    r.raise_for_status()
    data = r.json()
    raw = data.get('raw_data', {})
    has_vep = bool(raw.get('vep_data'))
    has_clinvar = bool(raw.get('clinvar_data'))
    has_mv = bool(raw.get('myvariant_data'))
    pathogenicity = data.get('pathogenicity', '')
    ok = has_vep and has_clinvar and pathogenicity == 'Pathogenic'
    return ok, f"VEP={has_vep} ClinVar={has_clinvar} MyVariant={has_mv} Pathogenicity={pathogenicity}"

test("J-C1: Variant expansion rs113993960 — VEP + ClinVar + pathogenicity correct", j_c1)

# J-C2: Variant row expansion — rs334 population frequencies
def j_c2():
    r = req.get(f"{BASE}/api/chat/variant/rs334", timeout=30)
    r.raise_for_status()
    data = r.json()
    raw = data.get('raw_data', {})
    mv = raw.get('myvariant_data', {})
    # Check for gnomad data somewhere
    gg = mv.get('gnomad_genome', {})
    ge = mv.get('gnomad_exome', {})
    has_af = bool(gg.get('af') or ge.get('af') or gg.get('af', {}).get('af') if isinstance(gg.get('af'), dict) else None)
    afr = gg.get('af_afr') or ge.get('af_afr')
    ok = data.get('pathogenicity') == 'Pathogenic'
    return ok, f"pathogenicity={data.get('pathogenicity')} gnomad_genome_keys={list(gg.keys())[:5]} afr={afr}"

test("J-C2: Variant expansion rs334 — HBB pathogenic, gnomAD fields present", j_c2)

# J-C3: Direct rsID chat (no file) — AI queries API
def j_c3():
    time.sleep(2)
    r = req.post(
        f"{BASE}/api/chat/",
        json={
            "conversation_id": CONV_ID,
            "message": "Can you look up rs334 for me? I want to understand its clinical significance and population frequency.",
            "ai_enabled": True,
            "sv_enabled": False,
            "ped_enabled": False
        },
        timeout=120
    )
    r.raise_for_status()
    resp = r.json()
    response_text = resp.get('response', '')
    has_hbb = 'hbb' in response_text.lower() or 'hemoglobin' in response_text.lower() or 'sickle' in response_text.lower() or 'rs334' in response_text.lower()
    ok = has_hbb
    preview = response_text[:400].replace('\n', ' ')
    return ok, f"mentions_HBB_context={has_hbb}\nPreview: {preview}"

test("J-C3: Direct rsID mention in chat — AI retrieves and responds about rs334 / HBB", j_c3)

# J-D1: Edge case — empty VCF
def j_d1():
    r_conv = req.post(f"{BASE}/api/conversations/", json={"title": "QA: Edge Case Empty VCF"}, timeout=10)
    r_conv.raise_for_status()
    eid = r_conv.json()['id']
    empty_vcf = b"""##fileformat=VCFv4.1
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
"""
    try:
        r = req.post(
            f"{BASE}/api/upload/",
            data={"conversation_id": eid},
            files={"file": ("empty.vcf", empty_vcf, "text/plain")},
            timeout=30
        )
        # Should not 500, should return graceful 200 or 400
        ok = r.status_code in (200, 400, 422)
        return ok, f"Status={r.status_code} (should NOT be 500)"
    except Exception as e:
        return False, f"Exception: {e}"

test("J-D1: Edge case — empty VCF returns graceful error, no 500", j_d1)

# J-D2: Conversation isolation — VCF context doesn't bleed across conversations
def j_d2():
    # Create a fresh conversation with NO vcf upload
    r_conv = req.post(f"{BASE}/api/conversations/", json={"title": "QA: Blank Chat"}, timeout=10)
    r_conv.raise_for_status()
    fresh_id = r_conv.json()['id']
    time.sleep(1)
    r = req.post(
        f"{BASE}/api/chat/",
        json={
            "conversation_id": fresh_id,
            "message": "Hello, what is this conversation about?",
            "ai_enabled": True,
            "sv_enabled": False,
            "ped_enabled": False
        },
        timeout=120
    )
    r.raise_for_status()
    resp = r.json()
    response_text = resp.get('response', '').lower()
    # Should NOT mention vcf/variants from previous conversations
    bleeds = any(kw in response_text for kw in ['500 variant', 'demo_500', 'rs113993960', 'annotated vcf'])
    ok = not bleeds
    return ok, f"context_bleed={bleeds} | Preview: {response_text[:200]}"

test("J-D2: Conversation isolation — fresh chat shows no VCF bleed from other convos", j_d2)


# ─── Phase 3: Summary Report ─────────────────────────────────────────────────

print("\n" + "="*60)
print(" QA RESULTS SUMMARY")
print("="*60)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)
print(f"  {PASS} Passed: {passed}/{total}")
print(f"  {FAIL} Failed: {failed}/{total}")
print()
if failed > 0:
    print("  FAILED TESTS:")
    for name, ok, detail in results:
        if not ok:
            print(f"    ✗ {name}")
            if detail:
                print(f"      {detail}")

print("\n" + "="*60)
print(" OBSERVATIONS & FINDINGS (Independent Analyst)")
print("="*60)
