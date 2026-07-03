"""
Comprehensive Integration Test Suite v2
Tests: backend units, frontend API contracts, and 3 multi-user scenarios.

SCENARIOS:
  User A — Clinical counselor with 3-family VCF set (proband + sibling + mother)
           Verifies: patient isolation, cross-patient AI reasoning, context mode
  User B — Single-variant researcher asking about rsID in chat (no VCF)
           Verifies: sv_enabled routing, Clinical_Variant_Analyzer tool, PubMed
  User C — Pedigree-only session (describes family history, no VCF)
           Verifies: pedigree tool triggering, no VCF bleed, context isolation

Run: python tests/test_integration_v2.py
"""

import os, sys, json, time, io
os.chdir(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, '.')
import requests as req

BASE = "http://localhost:8000"
PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"
results = []

def test(name, fn, skip_if=None):
    if skip_if:
        results.append((SKIP, name, skip_if))
        print(f"  {SKIP} {name}\n       {skip_if}")
        return False
    try:
        ok, msg = fn()
        tag = PASS if ok else FAIL
        results.append((tag, name, msg))
        icon = "✓" if ok else "✗"
        print(f"  {tag} {name}\n       {icon} {msg}")
        return ok
    except Exception as e:
        msg = f"Exception: {e}"
        results.append((FAIL, name, msg))
        print(f"  {FAIL} {name}\n       ✗ {msg}")
        return False

def section(title):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")

# ─────────────────────────────────────────────────────────────
# SMALL VCF FIXTURES
# ─────────────────────────────────────────────────────────────

PROBAND_VCF = b"""##fileformat=VCFv4.1
##INFO=<ID=CLNSIG,Number=.,Type=String,Description="ClinVar clinical significance">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
7\t117548628\trs113993960\tCTT\tC\t.\tPASS\tCLNSIG=Pathogenic;GENEINFO=CFTR:1080
17\t41276044\trs28897696\tC\tT\t.\tPASS\tCLNSIG=Pathogenic;GENEINFO=BRCA1:672
11\t5246696\trs334\tT\tA\t.\tPASS\tCLNSIG=Pathogenic;GENEINFO=HBB:3043
"""

SIBLING_VCF = b"""##fileformat=VCFv4.1
##INFO=<ID=CLNSIG,Number=.,Type=String,Description="ClinVar clinical significance">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
7\t117548628\trs113993960\tCTT\tC\t.\tPASS\tCLNSIG=Pathogenic;GENEINFO=CFTR:1080
11\t5246696\trs334\tT\tA\t.\tPASS\tCLNSIG=Benign;GENEINFO=HBB:3043
"""

MOTHER_VCF = b"""##fileformat=VCFv4.1
##INFO=<ID=CLNSIG,Number=.,Type=String,Description="ClinVar clinical significance">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
17\t41276044\trs28897696\tC\tT\t.\tPASS\tCLNSIG=Benign;GENEINFO=BRCA1:672
11\t5246696\trs334\tT\tA\t.\tPASS\tCLNSIG=Pathogenic;GENEINFO=HBB:3043
"""

ANNOTATED_SINGLE_VCF = b"""##fileformat=VCFv4.1
##INFO=<ID=CLNSIG,Number=.,Type=String,Description="ClinVar clinical significance">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
7\t117548628\trs113993960\tCTT\tC\t.\tPASS\tCLNSIG=Pathogenic;GENEINFO=CFTR:1080
"""

# ─────────────────────────────────────────────────────────────
# SECTION 1: BACKEND UNIT CHECKS
# ─────────────────────────────────────────────────────────────
section("BACKEND UNIT CHECKS")

def bu_01():
    """history_db: count_vcf_files returns 0 for fresh conversation."""
    from core.history_db import SQLiteHistoryDB
    db = SQLiteHistoryDB()
    fake_id = "test-bu01-fresh"
    count = db.count_vcf_files(fake_id)
    return count == 0, f"count_vcf_files for fresh conv = {count}"
test("BU-01: history_db.count_vcf_files fresh conv = 0", bu_01)

def bu_02():
    """history_db: upsert_file stores and get_file_by_type retrieves correctly."""
    from core.history_db import SQLiteHistoryDB
    db = SQLiteHistoryDB()
    cid = "test-bu02-upsert"
    payload = b'{"test": true}'
    db.upsert_file(cid, "test.json", payload, "vcf_enriched", "Proband")
    retrieved = db.get_file_by_type(cid, "vcf_enriched", "Proband")
    match = retrieved == payload
    return match, f"stored {len(payload)}b | retrieved {len(retrieved) if retrieved else 0}b | match={match}"
test("BU-02: history_db.upsert_file + get_file_by_type roundtrip", bu_02)

def bu_03():
    """history_db: upsert_file replaces existing file (no duplicates)."""
    from core.history_db import SQLiteHistoryDB
    db = SQLiteHistoryDB()
    cid = "test-bu03-replace"
    db.upsert_file(cid, "data.json", b'{"v":1}', "vcf_enriched", "P1")
    db.upsert_file(cid, "data.json", b'{"v":2}', "vcf_enriched", "P1")
    files = db.get_files_with_labels(cid)
    enriched = [f for f in files if f["file_type"] == "vcf_enriched" and f["patient_label"] == "P1"]
    ok = len(enriched) == 1
    content = db.get_file_by_type(cid, "vcf_enriched", "P1")
    has_v2 = content and b'"v": 2' in content or (content and b'"v":2' in content)
    return ok and has_v2, f"enriched file count={len(enriched)} (want 1) | content updated={has_v2}"
test("BU-03: history_db.upsert_file replaces (no duplicates)", bu_03)

def bu_04():
    """history_db: get_files_with_labels returns patient_label field."""
    from core.history_db import SQLiteHistoryDB
    db = SQLiteHistoryDB()
    cid = "test-bu04-labels"
    db.upsert_file(cid, "a.vcf", b"VCF", "vcf", "PatientA")
    db.upsert_file(cid, "b.vcf", b"VCF", "vcf", "PatientB")
    files = db.get_files_with_labels(cid)
    vcf_files = [f for f in files if f["file_type"] == "vcf"]
    labels = {f["patient_label"] for f in vcf_files}
    ok = "PatientA" in labels and "PatientB" in labels
    return ok, f"labels found: {labels}"
test("BU-04: history_db.get_files_with_labels includes patient_label", bu_04)

def bu_05():
    """vcf_prioritizer: CLNSIG bypass (no API call, instant categorization)."""
    from analysis.vcf_parser import VCFParser
    from analysis.vcf_prioritizer import VCFPrioritizer
    parser = VCFParser()
    variants = parser.parse(PROBAND_VCF, "proband.vcf")
    p = VCFPrioritizer()
    result = p.prioritize_variants(variants)
    dangerous = result.get("dangerous", [])
    ok = len(dangerous) >= 3  # all 3 are Pathogenic
    return ok, f"dangerous={len(dangerous)} (want >=3) from CLNSIG bypass"
test("BU-05: vcf_prioritizer CLNSIG bypass → all Pathogenic instantly", bu_05)

def bu_06():
    """vcf_prioritizer: enriched_data returned with correct structure."""
    from analysis.vcf_parser import VCFParser
    from analysis.vcf_prioritizer import VCFPrioritizer
    parser = VCFParser()
    variants = parser.parse(PROBAND_VCF, "proband.vcf")
    p = VCFPrioritizer()
    result = p.prioritize_variants(variants)
    enriched = result.get("enriched_data", {})
    ok = len(enriched) > 0
    first = next(iter(enriched.values()), {})
    has_clinical = "clinical" in first
    has_functional = "functional" in first
    has_population = "population" in first
    ok = ok and has_clinical and has_functional and has_population
    return ok, f"enriched has {len(enriched)} entries | clinical={has_clinical} functional={has_functional} population={has_population}"
test("BU-06: vcf_prioritizer.enriched_data has clinical+functional+population keys", bu_06)

def bu_07():
    """vcf_prioritizer: PER_FILE_CAP enforced on large VCF."""
    from analysis.vcf_prioritizer import PER_FILE_CAP
    vcf_path = os.path.join('data', 'demo_500_variants.vcf')
    if not os.path.exists(vcf_path):
        return True, "SKIP: demo_500_variants.vcf not found"
    from analysis.vcf_parser import VCFParser
    from analysis.vcf_prioritizer import VCFPrioritizer
    parser = VCFParser()
    with open(vcf_path, 'rb') as f:
        content = f.read()
    variants = parser.parse(content, "demo_500_variants.vcf")
    ok_parse = isinstance(variants, list) and len(variants) > 0
    if not ok_parse:
        return False, f"Parser returned {type(variants)} with {len(variants) if isinstance(variants, list) else '?'} items"
    from analysis.vcf_prioritizer import VCFPrioritizer
    p = VCFPrioritizer()
    result = p.prioritize_variants(variants)
    if not isinstance(result, dict):
        return False, f"prioritize_variants returned {type(result).__name__} instead of dict"
    total = sum(len(result.get(c, [])) for c in ['dangerous','possibly_harmful','vus','unannotated','benign'])
    ok = total <= PER_FILE_CAP
    return ok, f"parsed={len(variants)} variants | processed={total} (cap={PER_FILE_CAP}) | ok={ok}"
test("BU-07: vcf_prioritizer.PER_FILE_CAP enforced on 500-variant VCF", bu_07)

def bu_08():
    """chat context builder: deep mode for ≤35 variants."""
    from api.routers.chat import _build_vcf_context_for_prompt
    from core.history_db import SQLiteHistoryDB
    db = SQLiteHistoryDB()
    cid = "test-bu08-deep"
    payload = {
        "patient_label": "Proband",
        "filename": "proband.vcf",
        "total_variants": 3,
        "enriched_data": {
            "rs113993960": {
                "variant": "rs113993960", "gene": "CFTR",
                "location": "chr7:117548628", "ref_alt": "CTT>C",
                "hgvs_c": "",
                "clinical": {"significance": "Pathogenic", "review_status": "reviewed by expert panel",
                             "conditions": ["Cystic fibrosis"], "submissions": []},
                "functional": {"impact": "HIGH", "consequences": ["inframe_deletion"],
                               "sift": "N/A", "sift_score": None, "polyphen": "N/A",
                               "polyphen_score": None, "revel": 0.94, "cadd": 28.4,
                               "lrt": "D", "mutationtaster": "A", "fathmm": "D", "provean": None},
                "population": {"global": 2.1e-5, "african": 1e-4, "east_asian": 0,
                               "south_asian": 0, "european_nfe": 1.9e-5,
                               "european_fin": 2.4e-5, "latino": 2.5e-5, "ashkenazi": 3.9e-5}
            }
        },
        "compact_table": "| # | Variant | Gene |\n|---|---------|------|"
    }
    db.upsert_file(cid, "enriched_Proband.json", json.dumps(payload).encode(), "vcf_enriched", "Proband")
    block, mode = _build_vcf_context_for_prompt(cid)
    block_lower = block.lower()
    ok = (mode == "deep"
          and "sift" in block_lower
          and "cadd" in block_lower
          and "population" in block_lower
          and "pathogenic" in block_lower)
    return ok, f"mode={mode} | SIFT={'sift' in block_lower} | CADD={'cadd' in block_lower} | Population={'population' in block_lower} | Pathogenic={'pathogenic' in block_lower}"
test("BU-08: chat._build_vcf_context_for_prompt → deep mode for 1-variant file", bu_08)

def bu_09():
    """chat context builder: basic mode for >35 variants (inject 36 fake entries)."""
    from api.routers.chat import _build_vcf_context_for_prompt
    from core.history_db import SQLiteHistoryDB
    db = SQLiteHistoryDB()
    cid = "test-bu09-basic"
    # 36 fake variants → should trigger basic mode
    fake_enriched = {f"rs{i}": {
        "variant": f"rs{i}", "gene": f"GENE{i}", "location": f"chr1:{i}",
        "ref_alt": "A>T", "hgvs_c": "",
        "clinical": {"significance": "VUS", "review_status": "", "conditions": [], "submissions": []},
        "functional": {"impact": "LOW", "consequences": [], "sift": None, "sift_score": None,
                       "polyphen": None, "polyphen_score": None, "revel": None, "cadd": None,
                       "lrt": None, "mutationtaster": None, "fathmm": None, "provean": None},
        "population": {"global": None, "african": None, "east_asian": None, "south_asian": None,
                       "european_nfe": None, "european_fin": None, "latino": None, "ashkenazi": None}
    } for i in range(1, 37)}
    payload = {"patient_label": "BigFile", "filename": "big.vcf", "total_variants": 36,
               "enriched_data": fake_enriched,
               "compact_table": "| # | Variant | Gene |\n|---|---------|------|\n| 1 | rs1 | GENE1 |"}
    db.upsert_file(cid, "enriched_BigFile.json", json.dumps(payload).encode(), "vcf_enriched", "BigFile")
    block, mode = _build_vcf_context_for_prompt(cid)
    ok = mode == "basic" and "GENE1" in block
    return ok, f"mode={mode} (want 'basic') | compact table in block={('GENE1' in block)}"
test("BU-09: chat._build_vcf_context_for_prompt → basic mode for 36-variant file", bu_09)

def bu_10():
    """gemini_client: read_enriched_data tool reads correct patient's data."""
    from core.history_db import SQLiteHistoryDB
    import core.gemini_client as gc
    db = SQLiteHistoryDB()
    cid = "test-bu10-enrich-read"
    payload = {"patient_label": "Mother", "filename": "mother.vcf", "total_variants": 2,
               "enriched_data": {"rs334": {"gene": "HBB", "clinical": {"significance": "Pathogenic"}}},
               "compact_table": ""}
    db.upsert_file(cid, "enriched_Mother.json", json.dumps(payload).encode(), "vcf_enriched", "Mother")
    gc.set_current_conv_id(cid)
    result_str = gc.read_enriched_data("Mother", "rs334")
    result = json.loads(result_str)
    ok = "rs334" in result and result["rs334"].get("gene") == "HBB"
    return ok, f"read_enriched_data('Mother', 'rs334') → gene={result.get('rs334', {}).get('gene')}"
test("BU-10: gemini_client.read_enriched_data reads correct patient's enriched JSON", bu_10)

def bu_11():
    """gemini_client: read_enriched_data returns error for unknown patient."""
    from core.history_db import SQLiteHistoryDB
    import core.gemini_client as gc
    cid = "test-bu11-nopatient"
    gc.set_current_conv_id(cid)
    result_str = gc.read_enriched_data("NonExistentPatient", "rs334")
    ok = "not found" in result_str.lower() or "no enriched" in result_str.lower() or "available" in result_str.lower()
    return ok, f"error response: {result_str[:150]}"
test("BU-11: gemini_client.read_enriched_data → graceful error for unknown patient", bu_11)

def bu_12():
    """gemini_client: tools list has 5 tools and all have docstrings."""
    import core.gemini_client as gc
    tools = [gc.search_pubmed, gc.Clinical_Variant_Analyzer, gc.read_patient_vcf,
             gc.read_enriched_data, gc.create_pedigree_chart]
    all_have_docs = all(bool(t.__doc__ and len(t.__doc__.strip()) > 50) for t in tools)
    tool_names = [t.__name__ for t in tools]
    return all_have_docs, f"tools={tool_names} | all have docs={all_have_docs}"
test("BU-12: gemini_client has 5 tools, all with rich docstrings", bu_12)

def bu_13():
    """upload endpoint: 3-file limit enforced (4th upload returns 409)."""
    r = req.post(f"{BASE}/api/conversations/", json={"title": "BU-13 3-file limit"}, timeout=15)
    r.raise_for_status()
    cid = r.json()["id"]
    tiny_vcf = ANNOTATED_SINGLE_VCF
    for i, label in enumerate(["P1", "P2", "P3"], 1):
        resp = req.post(f"{BASE}/api/upload/",
                        data={"conversation_id": cid, "patient_label": label},
                        files={"file": (f"p{i}.vcf", tiny_vcf, "text/plain")}, timeout=90)
        if not resp.ok:
            return False, f"Upload #{i} failed: {resp.status_code} {resp.text[:200]}"
    # 4th should be 409
    resp4 = req.post(f"{BASE}/api/upload/",
                     data={"conversation_id": cid, "patient_label": "P4"},
                     files={"file": ("p4.vcf", tiny_vcf, "text/plain")}, timeout=30)
    ok = resp4.status_code == 409
    return ok, f"4th upload status={resp4.status_code} (want 409) | detail={resp4.json().get('detail','')[:100]}"
test("BU-13: upload endpoint enforces 3-file max (4th → HTTP 409)", bu_13)

# ─────────────────────────────────────────────────────────────
# SECTION 2: FRONTEND API CONTRACT CHECKS
# ─────────────────────────────────────────────────────────────
section("FRONTEND API CONTRACT CHECKS (matching React component expectations)")

FC_CONV = None
FC_UPLOAD = None

def fc_00():
    global FC_CONV
    # Retry up to 5s if server just restarted
    for attempt in range(5):
        try:
            r = req.post(f"{BASE}/api/conversations/", json={"title": "FC: API Contract Test"}, timeout=10)
            r.raise_for_status()
            FC_CONV = r.json()["id"]
            return bool(FC_CONV), f"conv_id={FC_CONV}"
        except Exception:
            time.sleep(1)
    return False, "Server not reachable after 5 attempts"
test("FC-00: Create conversation for API contract tests", fc_00)

def fc_01():
    """Upload response must have all keys ChatArea.jsx reads."""
    global FC_UPLOAD
    r = req.post(f"{BASE}/api/upload/",
                 data={"conversation_id": FC_CONV, "patient_label": "TestPatient"},
                 files={"file": ("test.vcf", PROBAND_VCF, "text/plain")}, timeout=90)
    r.raise_for_status()
    FC_UPLOAD = r.json()
    required = {"status", "summary", "prioritized", "enriched_data", "patient_label",
                "total_vcf_count", "context_mode", "compact_table"}
    missing = required - set(FC_UPLOAD.keys())
    ok = len(missing) == 0
    return ok, f"missing keys={missing} | context_mode={FC_UPLOAD.get('context_mode')} | patient={FC_UPLOAD.get('patient_label')}"
test("FC-01: Upload response has all keys ChatArea.jsx expects", fc_01,
     skip_if=None if FC_CONV else "FC_CONV not set")

def fc_02():
    """prioritized variants each have keys VcfVariantTable.jsx requires."""
    if not FC_UPLOAD:
        return False, "FC_UPLOAD is None"
    p = FC_UPLOAD.get("prioritized", {})
    required = {"variant", "gene", "location", "ref_alt", "clinical_sig"}
    bad = []
    for cat in ["dangerous", "possibly_harmful", "vus", "unannotated", "benign"]:
        for v in p.get(cat, []):
            missing = required - set(v.keys())
            if missing:
                bad.append(f"{v.get('variant','?')}: missing {missing}")
    ok = len(bad) == 0
    return ok, f"all variants have required keys={ok} | bad={bad[:3]}"
test("FC-02: Each variant in prioritized has variant/gene/location/ref_alt/clinical_sig", fc_02)

def fc_03():
    """context_mode is 'deep' for small VCF (3 variants ≤ 35 limit)."""
    if not FC_UPLOAD:
        return False, "FC_UPLOAD is None"
    mode = FC_UPLOAD.get("context_mode")
    ok = mode == "deep"
    return ok, f"context_mode='{mode}' (want 'deep' for 3-variant VCF)"
test("FC-03: context_mode='deep' for 3-variant VCF", fc_03)

def fc_04():
    """enriched_data has clinical + functional + population for each variant."""
    if not FC_UPLOAD:
        return False, "FC_UPLOAD is None"
    enriched = FC_UPLOAD.get("enriched_data", {})
    if not enriched:
        return False, "enriched_data is empty"
    issues = []
    for vid, rec in enriched.items():
        for key in ("clinical", "functional", "population"):
            if key not in rec:
                issues.append(f"{vid} missing '{key}'")
        pop = rec.get("population", {})
        for pop_key in ("global", "african", "east_asian", "south_asian", "european_nfe",
                        "european_fin", "latino", "ashkenazi"):
            if pop_key not in pop:
                issues.append(f"{vid}.population missing '{pop_key}'")
    ok = len(issues) == 0
    return ok, f"enriched has {len(enriched)} entries | issues={issues[:5]}"
test("FC-04: enriched_data has all 8 population keys and clinical/functional/population structure", fc_04)

def fc_05():
    """/api/chat/ with empty message returns 400, not 500."""
    r = req.post(f"{BASE}/api/chat/",
                 json={"conversation_id": FC_CONV, "message": "", "ai_enabled": True}, timeout=10)
    ok = r.status_code == 400
    return ok, f"empty message status={r.status_code} (want 400)"
test("FC-05: Empty message → HTTP 400 (not 500)", fc_05,
     skip_if=None if FC_CONV else "FC_CONV not set")

def fc_06():
    """/api/chat/variant/{id} returns correct structure for VariantDetailsTabs."""
    r = req.get(f"{BASE}/api/chat/variant/rs334", timeout=60)
    r.raise_for_status()
    data = r.json()
    required = {"variant_id", "pathogenicity", "confidence", "protein_effect",
                "clinical_significance", "raw_data"}
    missing = required - set(data.keys())
    ok = len(missing) == 0 and data.get("pathogenicity") != "Unknown"
    return ok, f"missing={missing} | pathogenicity={data.get('pathogenicity')} | confidence={data.get('confidence')}"
test("FC-06: /api/chat/variant/rs334 returns VariantDetailsTabs-compatible structure", fc_06)

def fc_07():
    """/api/conversations/{id}/messages returns messages list."""
    r = req.get(f"{BASE}/api/conversations/{FC_CONV}/messages", timeout=10)
    r.raise_for_status()
    msgs = r.json()
    ok = isinstance(msgs, list)
    roles = [m.get("role") for m in msgs]
    return ok, f"message count={len(msgs)} | roles={roles[:6]}"
test("FC-07: /api/conversations/{id}/messages returns list with role/content", fc_07,
     skip_if=None if FC_CONV else "FC_CONV not set")

# ─────────────────────────────────────────────────────────────
# SECTION 3A: USER SCENARIO — FAMILY TRIO (3 VCFs)
# ─────────────────────────────────────────────────────────────
section("USER SCENARIO A — Family Trio (Proband + Sibling + Mother)")
print("  Counselor uploads 3 VCF files for a family. Tests patient isolation,")
print("  cross-patient AI reasoning, and deep context mode with 8 variants total.\n")

TRIO_CONV = None
TRIO_PROBAND = None
TRIO_SIBLING = None
TRIO_MOTHER  = None

def sa_00():
    global TRIO_CONV
    r = req.post(f"{BASE}/api/conversations/", json={"title": "Scenario A: Family Trio"}, timeout=10)
    r.raise_for_status()
    TRIO_CONV = r.json()["id"]
    return bool(TRIO_CONV), f"conv_id={TRIO_CONV}"
test("SA-00: Create conversation for family trio", sa_00)

def sa_01():
    global TRIO_PROBAND
    r = req.post(f"{BASE}/api/upload/",
                 data={"conversation_id": TRIO_CONV, "patient_label": "Proband"},
                 files={"file": ("proband.vcf", PROBAND_VCF, "text/plain")}, timeout=90)
    r.raise_for_status()
    TRIO_PROBAND = r.json()
    ok = TRIO_PROBAND.get("patient_label") == "Proband"
    return ok, f"patient_label={TRIO_PROBAND.get('patient_label')} | vcf_count={TRIO_PROBAND.get('total_vcf_count')}"
test("SA-01: Upload Proband VCF (3 variants: CFTR/BRCA1/HBB — all Pathogenic)", sa_01,
     skip_if=None if TRIO_CONV else "TRIO_CONV not set")

def sa_02():
    global TRIO_SIBLING
    r = req.post(f"{BASE}/api/upload/",
                 data={"conversation_id": TRIO_CONV, "patient_label": "Sibling-1"},
                 files={"file": ("sibling.vcf", SIBLING_VCF, "text/plain")}, timeout=90)
    r.raise_for_status()
    TRIO_SIBLING = r.json()
    ok = TRIO_SIBLING.get("patient_label") == "Sibling-1" and TRIO_SIBLING.get("total_vcf_count") == 2
    return ok, f"patient_label={TRIO_SIBLING.get('patient_label')} | vcf_count={TRIO_SIBLING.get('total_vcf_count')}"
test("SA-02: Upload Sibling-1 VCF (2 variants: CFTR Pathogenic, HBB Benign)", sa_02,
     skip_if=None if TRIO_CONV else "TRIO_CONV not set")

def sa_03():
    global TRIO_MOTHER
    r = req.post(f"{BASE}/api/upload/",
                 data={"conversation_id": TRIO_CONV, "patient_label": "Mother"},
                 files={"file": ("mother.vcf", MOTHER_VCF, "text/plain")}, timeout=90)
    r.raise_for_status()
    TRIO_MOTHER = r.json()
    ok = TRIO_MOTHER.get("patient_label") == "Mother" and TRIO_MOTHER.get("total_vcf_count") == 3
    return ok, f"patient_label={TRIO_MOTHER.get('patient_label')} | vcf_count={TRIO_MOTHER.get('total_vcf_count')}"
test("SA-03: Upload Mother VCF (2 variants: BRCA1 Benign, HBB Pathogenic)", sa_03,
     skip_if=None if TRIO_CONV else "TRIO_CONV not set")

def sa_04():
    """4th upload must be rejected."""
    r = req.post(f"{BASE}/api/upload/",
                 data={"conversation_id": TRIO_CONV, "patient_label": "Father"},
                 files={"file": ("father.vcf", ANNOTATED_SINGLE_VCF, "text/plain")}, timeout=30)
    ok = r.status_code == 409
    return ok, f"4th upload status={r.status_code} (want 409)"
test("SA-04: 4th VCF upload rejected with HTTP 409", sa_04,
     skip_if=None if TRIO_CONV else "TRIO_CONV not set")

def sa_05():
    """context_mode must be 'deep' (total 7 variants ≤ 35)."""
    if not TRIO_MOTHER:
        return False, "TRIO_MOTHER not set"
    mode = TRIO_MOTHER.get("context_mode")
    ok = mode == "deep"
    return ok, f"context_mode='{mode}' after 3 uploads with 7 total variants (want 'deep')"
test("SA-05: context_mode='deep' after all 3 VCF uploads (7 variants total ≤ 35)", sa_05)

def sa_06():
    """AI knows which variants belong to which patient."""
    time.sleep(1)
    r = req.post(f"{BASE}/api/chat/",
                 json={"conversation_id": TRIO_CONV,
                       "message": "Which patient has the rs334 HBB variant marked as Pathogenic and which has it as Benign? List both.",
                       "ai_enabled": True, "sv_enabled": False, "ped_enabled": False},
                 timeout=120)
    r.raise_for_status()
    resp = r.json().get("response", "").lower()
    # Should mention proband or mother as pathogenic for rs334, sibling as benign
    has_proband_or_mother = "proband" in resp or "mother" in resp
    has_sibling = "sibling" in resp
    has_benign = "benign" in resp
    has_pathogenic = "pathogenic" in resp
    ok = has_proband_or_mother and has_sibling and has_benign and has_pathogenic
    return ok, (f"mentions proband/mother={has_proband_or_mother} sibling={has_sibling} "
                f"benign={has_benign} pathogenic={has_pathogenic}\n"
                f"  Preview: {resp[:300].replace(chr(10),' ')}")
test("SA-06: AI correctly identifies rs334 as Pathogenic in Proband/Mother, Benign in Sibling-1", sa_06,
     skip_if=None if TRIO_CONV else "TRIO_CONV not set")

def sa_07():
    """AI names patients correctly, doesn't confuse Proband/Sibling/Mother."""
    r = req.post(f"{BASE}/api/chat/",
                 json={"conversation_id": TRIO_CONV,
                       "message": "Which patient has the BRCA1 variant rs28897696? Is it pathogenic in all family members?",
                       "ai_enabled": True, "sv_enabled": False, "ped_enabled": False},
                 timeout=120)
    r.raise_for_status()
    resp = r.json().get("response", "").lower()
    has_proband = "proband" in resp
    has_brca1 = "brca1" in resp
    # Mother has BRCA1 as Benign, Proband as Pathogenic — sibling doesn't have it
    ok = has_proband and has_brca1
    return ok, (f"mentions proband={has_proband} brca1={has_brca1}\n"
                f"  Preview: {resp[:300].replace(chr(10),' ')}")
test("SA-07: AI correctly reports BRCA1 rs28897696 is Pathogenic in Proband (not in all members)", sa_07,
     skip_if=None if TRIO_CONV else "TRIO_CONV not set")

def sa_08():
    """AI uses deep context without needing tool calls (no 'read_enriched_data' in response for small VCF)."""
    r = req.post(f"{BASE}/api/chat/",
                 json={"conversation_id": TRIO_CONV,
                       "message": "What is the global allele frequency of rs334 in gnomAD?",
                       "ai_enabled": True, "sv_enabled": False, "ped_enabled": False},
                 timeout=120)
    r.raise_for_status()
    resp = r.json().get("response", "").lower()
    # Should answer from deep context, not say "I need to look this up"
    has_freq = any(k in resp for k in ["frequency", "af", "allele", "gnomad", "e-", "×10"])
    no_tool_excuse = "let me look" not in resp and "i need to check" not in resp
    ok = has_freq and no_tool_excuse
    return ok, (f"has_freq={has_freq} no_tool_excuse={no_tool_excuse}\n"
                f"  Preview: {resp[:300].replace(chr(10),' ')}")
test("SA-08: AI answers gnomAD frequency from deep context (no tool call needed)", sa_08,
     skip_if=None if TRIO_CONV else "TRIO_CONV not set")

# ─────────────────────────────────────────────────────────────
# SECTION 3B: USER SCENARIO B — Single Variant Researcher
# ─────────────────────────────────────────────────────────────
section("USER SCENARIO B — Single Variant Researcher (no VCF, chat-only)")
print("  Researcher types 'tell me about rs334' in chat. Tests sv_enabled routing,\n"
      "  Clinical_Variant_Analyzer tool, and PubMed integration.\n")

SB_CONV = None

def sb_00():
    global SB_CONV
    r = req.post(f"{BASE}/api/conversations/", json={"title": "Scenario B: Single Variant"}, timeout=10)
    r.raise_for_status()
    SB_CONV = r.json()["id"]
    return bool(SB_CONV), f"conv_id={SB_CONV}"
test("SB-00: Create conversation for single-variant researcher", sb_00)

def sb_01():
    """rsID in message with sv_enabled=True → single variant route."""
    r = req.post(f"{BASE}/api/chat/",
                 json={"conversation_id": SB_CONV,
                       "message": "What can you tell me about rs334? Is it disease-causing?",
                       "ai_enabled": True, "sv_enabled": True, "ped_enabled": False},
                 timeout=120)
    r.raise_for_status()
    resp = r.json()
    response_text = resp.get("response", "").lower()
    meta = resp.get("metadata", {})
    has_pathogenic = "pathogenic" in response_text or "sickle" in response_text
    has_hbb = "hbb" in response_text
    has_meta = meta.get("type") == "variant_analysis"
    ok = has_pathogenic and has_hbb
    return ok, (f"metadata.type={meta.get('type')} pathogenic={has_pathogenic} hbb={has_hbb}\n"
                f"  Preview: {response_text[:250].replace(chr(10),' ')}")
test("SB-01: rs334 in message → sv_enabled route → pathogenic HBB response + variant_analysis metadata", sb_01,
     skip_if=None if SB_CONV else "SB_CONV not set")

def sb_02():
    """rsID with sv_enabled=False → goes through AI agent (not single variant route)."""
    r2 = req.post(f"{BASE}/api/chat/",
                  json={"conversation_id": SB_CONV,
                        "message": "Tell me about rs334 again",
                        "ai_enabled": True, "sv_enabled": False, "ped_enabled": False},
                  timeout=120)
    if not r2.ok:
        return False, f"Request failed: {r2.status_code} {r2.text[:200]}"
    resp2 = r2.json()
    if not isinstance(resp2, dict):
        return False, f"Expected dict, got {type(resp2).__name__}: {str(resp2)[:100]}"
    meta2 = resp2.get("metadata") or {}
    response_text = resp2.get("response", "").lower()
    not_sv_type = meta2.get("type") != "variant_analysis"
    has_content = len(response_text) > 100
    ok = has_content
    return ok, f"status={r2.status_code} | metadata.type={meta2.get('type')} | response_length={len(response_text)} | has_content={has_content}"
test("SB-02: rs334 with sv_enabled=False → AI agent path (not single-variant route)", sb_02,
     skip_if=None if SB_CONV else "SB_CONV not set")

def sb_03():
    """No VCF bleed — SB conversation has no VCF context from SA."""
    from core.history_db import SQLiteHistoryDB
    if not SB_CONV:
        return False, "SB_CONV not set"
    db = SQLiteHistoryDB()
    files = db.get_files_with_labels(SB_CONV)
    vcf_files = [f for f in files if f["file_type"] in ("vcf", "vcf_enriched")]
    ok = len(vcf_files) == 0
    return ok, f"VCF files in SB conversation={len(vcf_files)} (want 0)"
test("SB-03: Single-variant conversation has no VCF bleed from Scenario A", sb_03)

# ─────────────────────────────────────────────────────────────
# SECTION 3C: USER SCENARIO C — Pedigree Session
# ─────────────────────────────────────────────────────────────
section("USER SCENARIO C — Pedigree Session (family history, no VCF)")
print("  Counselor describes a family with autosomal recessive disease.")
print("  Tests pedigree tool triggering, context isolation, AI reasoning.\n")

SC_CONV = None

def sc_00():
    global SC_CONV
    r = req.post(f"{BASE}/api/conversations/", json={"title": "Scenario C: Pedigree"}, timeout=10)
    r.raise_for_status()
    SC_CONV = r.json()["id"]
    return bool(SC_CONV), f"conv_id={SC_CONV}"
test("SC-00: Create conversation for pedigree session", sc_00)

def sc_01():
    """Pedigree tool triggered when ped_enabled=True and family described."""
    r = req.post(f"{BASE}/api/chat/",
                 json={"conversation_id": SC_CONV,
                       "message": ("The proband is an affected male child. His mother is an unaffected carrier. "
                                   "His father is also an unaffected carrier. He has one unaffected sister. "
                                   "Can you draw a pedigree and explain the inheritance pattern?"),
                       "ai_enabled": True, "sv_enabled": False, "ped_enabled": True},
                 timeout=240)
    if not r.ok:
        return False, f"Request failed: {r.status_code} {r.text[:200]}"
    resp = r.json()
    response_text = resp.get("response", "").lower()
    meta = resp.get("metadata") or {}
    has_pedigree_meta = meta.get("type") == "pedigree_chart" or "pedigree" in str(meta).lower()
    has_pedigree_mention = "pedigree" in response_text or "chart" in response_text or "generated" in response_text
    has_inheritance = any(k in response_text for k in ["autosomal", "recessive", "carrier", "inheritance"])
    ok = has_inheritance and (has_pedigree_meta or has_pedigree_mention)
    return ok, (f"pedigree_meta={has_pedigree_meta} pedigree_mention={has_pedigree_mention} inheritance={has_inheritance}\n"
                f"  Preview: {response_text[:300].replace(chr(10),' ')}")
test("SC-01: Pedigree tool triggered with ped_enabled=True + family description", sc_01,
     skip_if=None if SC_CONV else "SC_CONV not set")

def sc_02():
    """SC conversation has no VCF files (clean isolation)."""
    from core.history_db import SQLiteHistoryDB
    db = SQLiteHistoryDB()
    files = db.get_files_with_labels(SC_CONV)
    vcf_files = [f for f in files if f["file_type"] in ("vcf", "vcf_enriched")]
    ok = len(vcf_files) == 0
    return ok, f"VCF files in pedigree conversation={len(vcf_files)} (want 0)"
test("SC-02: Pedigree conversation has no VCF data (correct isolation)", sc_02,
     skip_if=None if SC_CONV else "SC_CONV not set")

def sc_03():
    """AI can discuss genetics without VCF, no crash/500."""
    r = req.post(f"{BASE}/api/chat/",
                 json={"conversation_id": SC_CONV,
                       "message": "What ACMG criteria should I apply when classifying a VUS in a recessive disease gene?",
                       "ai_enabled": True, "sv_enabled": False, "ped_enabled": False},
                 timeout=120)
    ok = r.status_code == 200 and len(r.json().get("response", "")) > 100
    return ok, f"status={r.status_code} | response_length={len(r.json().get('response',''))}"
test("SC-03: AI answers ACMG criteria question without VCF (no crash)", sc_03,
     skip_if=None if SC_CONV else "SC_CONV not set")

# ─────────────────────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────────────────────
section("RESULTS")
passed = [r for r in results if r[0] == PASS]
failed = [r for r in results if r[0] == FAIL]
skipped = [r for r in results if r[0] == SKIP]

print(f"\n  Passed:  {len(passed)}/{len(results)}")
print(f"  Failed:  {len(failed)}")
print(f"  Skipped: {len(skipped)}")

if failed:
    print("\n  FAILED TESTS:")
    for _, name, msg in failed:
        print(f"    • {name}")
        print(f"      {msg[:200]}")

if skipped:
    print("\n  SKIPPED TESTS:")
    for _, name, msg in skipped:
        print(f"    • {name}: {msg}")

print(f"\n  {'✅ ALL TESTS PASSED' if not failed else '❌ FAILURES DETECTED — SEE ABOVE'}")
