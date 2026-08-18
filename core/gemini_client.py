"""
Shared Gemini client utilities: API key loading, model discovery, fallback generation,
and agent tool definitions with rich docstrings so the AI knows exactly how to use them.
"""
import os
import re
import warnings
import json
from typing import List, Optional, Tuple, Dict, Any

# Suppress google.generativeai deprecation FutureWarning (package still functional)
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")


# ── Genetics scope detection ──

GENETICS_KEYWORDS = [
    "variant", "mutation", "snp", "indel", "deletion", "insertion", "duplication",
    "rs", "hgvs", "clingen", "clinvar", "dbsnp", "gene", "chromosome", "allele",
    "genotype", "phenotype", "genome", "exon", "intron", "transcript", "protein",
    "amino acid", "nucleotide", "codon", "pathogenic", "benign", "vus", "significance",
    "inheritance", "hereditary", "carrier", "penetrance", "expressivity", "genetic counseling",
    "brca", "cf", "sickle cell", "hemophilia", "huntington", "duchenne", "frequency",
    "gnomad", "exac", "population", "consequence", "impact", "sift", "polyphen",
    "cadd", "revel", "vep", "annotation", "pedigree", "family history",
    "autosomal", "recessive", "dominant", "x-linked", "mitochondrial",
]

def is_genetics_related(query: str) -> bool:
    query_lower = query.lower()
    keyword_match = any(kw in query_lower for kw in GENETICS_KEYWORDS)
    hgvs_pattern = any(p in query_lower for p in ["nm_", "nc_", "ng_", "np_", "p.", "c.", "g."])
    rsid_pattern = "rs" in query_lower and any(c.isdigit() for c in query)
    return keyword_match or hgvs_pattern or rsid_pattern


def detect_rsid(text: str) -> Optional[str]:
    match = re.search(r'\brs\d+\b', text, re.IGNORECASE)
    return match.group(0) if match else None


def detect_hgvs(text: str) -> Optional[str]:
    match = re.search(r'\b(N[MCGP]_\d+\.\d+:[cpg]\.\d+\w+[>]\w+)\b', text, re.IGNORECASE)
    return match.group(0) if match else None


# ── Gemini API key loading ──

def load_gemini_api_key() -> Optional[str]:
    key_file_path = os.path.join("api_key", "gemini_key.txt")
    if os.path.exists(key_file_path):
        try:
            with open(key_file_path, "r") as f:
                lines = [l.strip() for l in f.readlines() if l.strip() and not l.strip().startswith("#")]
                if lines:
                    return lines[0]
        except Exception:
            pass
    return os.getenv("GEMINI_API_KEY")


def init_gemini():
    try:
        import google.generativeai as genai
        api_key = load_gemini_api_key()
        if api_key:
            genai.configure(api_key=api_key)
            return genai
    except ImportError:
        pass
    return None


# ── Model discovery & fallback ──

def discover_text_models(genai) -> List[str]:
    try:
        all_discovered = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name.split('/')[-1]
                all_discovered.append(name)
        exclude_keywords = ['embed', 'vision', 'audio', 'video', 'bidi', 'whisper', 'imagen', 'aqa', 'image', 'tts', 'robotics', 'computer-use']
        gemini_models = [
            m for m in all_discovered
            if 'gemini' in m.lower() and not any(kw in m.lower() for kw in exclude_keywords)
        ]
        gemini_models.sort(key=_model_rank, reverse=True)
        return gemini_models if gemini_models else _fallback_models()
    except Exception:
        return _fallback_models()


def _model_rank(name: str) -> tuple:
    """Rank a model by capability, for choosing which to try first.

    These names were previously sorted reverse-alphabetically, which is not a
    capability order at all: "gemini-flash-lite-latest" sorts above
    "gemini-flash-latest" (because "li" > "la") and above every "gemini-3.x"
    (because "f" > "3"). The lite model therefore won the ranking and answered
    complex requests — and lite models are markedly worse at multi-step tool
    calling, so the agent would skip its tools and answer from memory while
    still presenting the result as a database lookup.

    Ordered by: tier (pro > flash > lite), then version, then stable > preview.
    """
    n = name.lower()

    if 'lite' in n:
        tier = 1
    elif 'pro' in n:
        tier = 3
    elif 'flash' in n:
        tier = 2
    else:
        tier = 0

    version_match = re.search(r'(\d+(?:\.\d+)?)', n)
    version = float(version_match.group(1)) if version_match else 0.0
    # "latest" aliases carry no number but track the current release.
    if 'latest' in n and version == 0.0:
        version = 99.0

    stable = 0 if any(k in n for k in ('preview', 'exp', 'experimental')) else 1
    return (tier, stable, version)


def _fallback_models() -> List[str]:
    return ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']


def generate_with_fallback(genai, prompt: str, on_status=None) -> Tuple[str, str]:
    models = discover_text_models(genai)
    last_error = None
    for model_name in models:
        try:
            if on_status:
                on_status(f"Querying `{model_name}`...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text, model_name
        except Exception as e:
            last_error = str(e)
            if on_status:
                if "429" in last_error or "quota" in last_error.lower():
                    on_status(f"⚠️ `{model_name}` rate-limited. Trying next model...")
                else:
                    on_status(f"⚠️ `{model_name}` error. Trying next model...")
            continue
    raise RuntimeError(f"All models exhausted. Last error: {last_error}")


# ═══════════════════════════════════════════════════════════════
#  AGENT TOOLS
#  Each docstring IS the tool schema the AI reads — write it
#  clearly so the AI knows exactly when and how to call each tool.
# ═══════════════════════════════════════════════════════════════

def search_pubmed(query_term: str) -> str:
    """
    Search PubMed biomedical literature database for research papers, clinical studies, case reports,
    and population studies related to genes, variants, conditions, or inheritance patterns.

    YOU SHOULD CALL THIS TOOL PROACTIVELY whenever you are:
    - Discussing a specific variant or gene with clinical significance
    - Assessing pathogenicity and want to cite supporting evidence
    - Looking for population frequency data from published studies
    - Checking if a variant has been reported in disease cohorts
    - Researching a condition mentioned by the counselor

    Formulate your own search query — do NOT use a hardcoded format. Good examples:
      - "CFTR F508del cystic fibrosis pathogenicity"
      - "rs113993960 functional impact lung disease"
      - "HBB sickle cell trait heterozygous clinical management"
      - "BRCA2 missense variant Ashkenazi Jewish population frequency"

    Returns up to 5 recent papers with titles, journals, and links.
    """
    from core.api_clients import query_pubmed
    try:
        papers = query_pubmed(query_term)
        if not papers:
            return f"No PubMed literature found for query: '{query_term}'"
        res = []
        for i, p in enumerate(papers, 1):
            res.append(
                f"{i}. Title: {p['title']}\n"
                f"   Journal: {p['journal']} ({p['pubdate']})\n"
                f"   Authors: {p['authors']}\n"
                f"   Link: {p['link']}"
            )
        return "\n\n".join(res)
    except Exception as e:
        return f"Error searching PubMed: {str(e)}"


def Clinical_Variant_Analyzer(variant_id: str) -> str:
    """
    Perform a deep single-variant analysis by querying ClinVar, Ensembl VEP, dbNSFP, and
    MyVariant.info for a specific genetic variant.

    Use this tool when:
    - The counselor asks about a specific variant by rsID (e.g. rs334) or HGVS notation
      (e.g. NM_000518.5:c.20A>T)
    - You need up-to-date pathogenicity, functional predictors, or population frequencies
      for a single variant that is NOT already covered in the uploaded context
    - A variant from the VCF context table needs detailed analysis beyond what the context
      already provides (prefer read_enriched_data first — it's faster and doesn't need API calls)

    variant_id: rsID (e.g. 'rs334') or HGVS notation (e.g. 'NM_000518.5:c.20A>T')

    Returns: pathogenicity classification, confidence, protein effect, clinical significance,
             associated conditions, all population frequencies, dbNSFP predictor scores.
    """
    from core.query_router import GenomicQueryRouter
    from analysis.variant_analyser import VariantDataFetcher, VariantAnalyzer

    try:
        router = GenomicQueryRouter()
        fetcher = VariantDataFetcher()
        analyzer = VariantAnalyzer()

        classification = router.classify(variant_id)
        variant_data = fetcher.fetch_variant_data(
            variant_id=classification.extracted_identifier,
            query_type=classification.query_type
        )
        analysis = analyzer.analyze_variant(variant_data)

        frequencies = analysis.get("population_frequency") or {}
        predictors = analysis.get("functional_impact", {}).get("predictor_scores") or {}

        payload = {
            "variant": variant_id,
            "classification": classification.query_type,
            "pathogenicity": analysis["pathogenicity_prediction"]["classification"],
            "confidence": analysis["pathogenicity_prediction"]["confidence"],
            "protein_effect": analysis["functional_impact"]["protein_effect"],
            "clinical_significance": analysis.get("clinical_relevance", {}).get("clinical_significance", "N/A"),
            "associated_conditions": analysis.get("clinical_relevance", {}).get("associated_conditions", []),
            "population_frequency": frequencies,
            "predictor_scores": predictors,
        }

        # Say plainly what came back empty. Silence was being read as "not
        # mentioned" rather than "not retrieved", and the model filled the gap
        # from memory while still attributing it to this tool — a recalled
        # gnomAD frequency printed under a database heading is exactly the
        # failure this product claims to avoid.
        missing = [name for name, value in (
            ("gnomAD/population frequency", frequencies),
            ("functional predictor scores", predictors),
            ("associated conditions", payload["associated_conditions"]),
        ) if not value]
        if missing:
            payload["data_not_retrieved"] = missing
            payload["reporting_instruction"] = (
                "The fields listed in data_not_retrieved were NOT returned by any "
                "database for this variant. Do not supply them from prior knowledge. "
                "State that the lookup did not return them, and if you mention such a "
                "figure anyway, label it explicitly as general knowledge rather than "
                "as a retrieved result."
            )

        return json.dumps(payload, indent=2)
    except Exception as e:
        return f"Error analyzing variant {variant_id}: {str(e)}"


def read_patient_vcf(patient_label: str, start_row: int, end_row: int) -> str:
    """
    Read a range of raw variant rows from an uploaded VCF file, identified by the patient's label.

    Patient labels were assigned when the VCF was uploaded (e.g. 'Proband', 'Sibling-1', 'Mother').
    If you are unsure of the label, pass an empty string "" to read the most recent VCF file.

    Use this tool when:
    - The counselor refers to specific row numbers (e.g. '#12', 'variant row 7')
    - You want to see the raw genomic coordinates of unannotated/novel variants
    - You need the REF/ALT alleles, chromosomal position, or VCF INFO fields for a specific region
    - You want to inspect a range of variants for a specific patient without loading all of them

    patient_label: e.g. 'Proband', 'Sibling-1', or '' for the most recent file
    start_row: 1-indexed row number to start reading from
    end_row: 1-indexed row number to stop reading at (inclusive)

    Returns: raw variant rows with chrom, pos, ref, alt, gene (if annotated in VCF INFO).
    """
    from core.history_db import SQLiteHistoryDB
    from analysis.vcf_parser import VCFParser
    try:
        _db = SQLiteHistoryDB()
        conv_id = _CURRENT_CONV_ID
        if not conv_id:
            return "Error: No active conversation context."

        files = _db.get_files_with_labels(conv_id)
        vcf_file_meta = None
        for f in reversed(files):
            if f["file_type"] == "vcf":
                if not patient_label or f["patient_label"].lower() == patient_label.lower():
                    vcf_file_meta = f
                    break

        if not vcf_file_meta:
            labels = [f["patient_label"] for f in files if f["file_type"] == "vcf"]
            return f"No VCF file found for patient '{patient_label}'. Available labels: {labels}"

        raw = _db.get_file_bytes(vcf_file_meta["id"])
        if not raw:
            return "VCF file data not found."

        parser = VCFParser()
        variants = parser.parse(raw, vcf_file_meta["filename"])

        total = len(variants)
        subset = variants[max(0, start_row - 1):min(total, end_row)]
        formatted = []
        for idx, v in enumerate(subset, start=max(1, start_row)):
            formatted.append(
                f"Row #{idx}: ID={v.get('variant_id')} | "
                f"{v.get('chrom')}:{v.get('pos')} {v.get('ref')}>{v.get('alt')} | "
                f"Gene={v.get('info', {}).get('SYMBOL', 'N/A')}"
            )
        return json.dumps({
            "patient": vcf_file_meta["patient_label"],
            "filename": vcf_file_meta["filename"],
            "total_rows": total,
            "range": f"{start_row}-{end_row}",
            "rows": formatted
        }, indent=2)
    except Exception as e:
        return f"Error reading VCF rows: {str(e)}"


def read_enriched_data(patient_label: str, variant_ids: str) -> str:
    """
    Read the full enriched annotation record for one or more specific variants from the
    pre-computed enrichment file stored for a patient. This is FASTER than Clinical_Variant_Analyzer
    because it reads cached data — no new API calls needed.

    The enriched record contains:
    - Clinical: ClinVar significance, review status, ALL ClinVar submissions (up to 20),
                associated conditions for each submission
    - Functional: VEP impact, consequence terms, SIFT (score + prediction), PolyPhen-2 HDIV
                  (score + prediction), REVEL ensemble score, CADD Phred score,
                  LRT, MutationTaster, FATHMM, PROVEAN predictions
    - Population (gnomAD): Global AF, African, East Asian, South Asian,
                           European Non-Finnish, European Finnish, Latino, Ashkenazi Jewish

    YOU SHOULD CALL THIS TOOL PROACTIVELY when:
    - You want to compare population frequencies across ethnic groups for a variant
    - You need specific predictor scores (REVEL, CADD) to assess pathogenicity
    - You want to review all ClinVar submissions for a variant, not just the summary
    - You are in basic context mode and need full details on a variant from the compact table

    patient_label: e.g. 'Proband', 'Sibling-1', or '' for the most recent enrichment file
    variant_ids: comma-separated list of variant IDs, e.g. 'rs334,rs113993960,chr7:g.12345A>T'

    Returns: full enriched annotation records as JSON.
    """
    from core.history_db import SQLiteHistoryDB
    try:
        _db = SQLiteHistoryDB()
        conv_id = _CURRENT_CONV_ID
        if not conv_id:
            return "Error: No active conversation context."

        enriched_bytes = _db.get_file_by_type(conv_id, "vcf_enriched", patient_label or None)
        if not enriched_bytes:
            files = _db.get_files_with_labels(conv_id)
            labels = [f["patient_label"] for f in files if f["file_type"] == "vcf_enriched"]
            return f"No enriched data found for patient '{patient_label}'. Available: {labels}"

        payload = json.loads(enriched_bytes.decode("utf-8"))
        enriched = payload.get("enriched_data", {})

        ids = [v.strip() for v in variant_ids.split(",") if v.strip()]
        results = {}
        for vid in ids:
            if vid in enriched:
                results[vid] = enriched[vid]
            else:
                # Try case-insensitive match
                match = next((k for k in enriched if k.lower() == vid.lower()), None)
                results[vid] = enriched[match] if match else {"error": f"Variant '{vid}' not found in enriched data for patient '{patient_label}'"}
        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error reading enriched data: {str(e)}"


# Module-level pedigree storage, so the SVG never has to travel back through the
# LLM's context window.
_LAST_PEDIGREE_SVG: Optional[str] = None


def create_pedigree_chart(individuals: list, relationships: list) -> dict:
    """
    Generate and draw a medical pedigree chart from structured family tree data.

    Use this tool when the user describes a family history or requests a pedigree chart.
    You must translate the described family members and their connections into the structured lists.

    individuals: List of dicts representing family members. Each dict must contain:
      - id: Unique short string identifier (e.g. "proband", "father", "mother", "sister1")
      - name: Display name
      - gender: Gender string, must be one of: "male", "female", "unknown"
      - status: Disease status, must be one of: "affected", "carrier", "unaffected", "unknown"
      - deceased: Boolean flag (true if deceased, false otherwise)
      
    relationships: List of dicts representing connections. Each dict must contain:
      - type: Relationship type, one of: "marriage", "parent-child", "sibling"
      - person1: String ID of the first person
      - person2: String ID of the second person
    """
    from analysis.pedigree_generator import PedigreeGenerator
    from analysis.pedigree_logging import PedigreeTrace
    global _LAST_PEDIGREE_SVG

    trace = PedigreeTrace("tool-call")
    try:
        generator = PedigreeGenerator(api_key=load_gemini_api_key())

        # Normalize protobuf RepeatedComposite objects to standard Python lists of dicts
        python_individuals = []
        for ind in individuals:
            if hasattr(ind, "to_dict"):
                python_individuals.append(ind.to_dict())
            elif hasattr(ind, "items"):
                python_individuals.append(dict(ind.items()))
            else:
                try:
                    python_individuals.append(dict(ind))
                except Exception:
                    d = {}
                    for field in ["id", "name", "gender", "status", "deceased", "generation", "conditions", "age"]:
                        if hasattr(ind, field):
                            d[field] = getattr(ind, field)
                    python_individuals.append(d)

        python_relationships = []
        for rel in relationships:
            if hasattr(rel, "to_dict"):
                python_relationships.append(rel.to_dict())
            elif hasattr(rel, "items"):
                python_relationships.append(dict(rel.items()))
            else:
                try:
                    python_relationships.append(dict(rel))
                except Exception:
                    d = {}
                    for field in ["type", "person1", "person2"]:
                        if hasattr(rel, field):
                            d[field] = getattr(rel, field)
                    python_relationships.append(d)

        pedigree_data = {
            "individuals": python_individuals,
            "relationships": python_relationships,
        }
        trace.dump_artifact("tool_input.json", pedigree_data)

        # Generation levels, ordering and routing are all computed inside the
        # layout engine — the model only supplies who exists and how they relate.
        layout = generator.build_layout(pedigree_data, trace)
        _LAST_PEDIGREE_SVG = generator.generate_svg(pedigree_data, trace=trace)

        pedigree_data["generations"] = [
            {"generation": gen, "individuals": members}
            for gen, members in sorted(layout.generations.items())
        ]

        summary = trace.finish()
        return {
            "status": "success",
            "message": (f"Pedigree rendered with {len(layout.nodes)} individuals across "
                        f"{len(layout.generations)} generations. The chart is shown in the UI."),
            "pedigree_data": pedigree_data,
            "warnings": summary.get("warnings", [])[:5],
            "_INTERNAL_MARKER_PEDIGREE": True,
        }
    except Exception as e:
        trace.error("tool", f"Pedigree generation failed: {e}")
        trace.finish()
        return {"status": "error", "message": f"Error creating pedigree chart: {str(e)}"}


# Module-level conversation ID — set by handle_ai_chat before each call
# so tools can look up the right patient files without the AI needing to pass conv_id
_CURRENT_CONV_ID: Optional[str] = None

def set_current_conv_id(conv_id: str):
    global _CURRENT_CONV_ID
    _CURRENT_CONV_ID = conv_id


# ── Agent Loop ──

def generate_with_agent(genai, prompt: str, on_status=None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Query Gemini with all registered tools available for autonomous calling.
    Returns (response_text, model_used, metadata).
    """
    models = discover_text_models(genai)
    last_error = None
    
    global _LAST_PEDIGREE_SVG
    _LAST_PEDIGREE_SVG = None

    tools = [
        search_pubmed,
        Clinical_Variant_Analyzer,
        read_patient_vcf,
        read_enriched_data,
        create_pedigree_chart,
    ]

    for model_name in models:
        try:
            if on_status:
                on_status(f"Running agent on `{model_name}`...")

            model = genai.GenerativeModel(model_name=model_name, tools=tools)
            chat = model.start_chat(enable_automatic_function_calling=True)
            response = chat.send_message(prompt)

            metadata = None
            for msg in chat.history:
                parts = getattr(msg, "parts", None) or []
                for part in parts:
                    func_resp = getattr(part, "function_response", None)
                    if func_resp and getattr(func_resp, "name", None) == "create_pedigree_chart":
                        try:
                            resp = getattr(func_resp, "response", None)
                            if resp is None:
                                continue
                            resp_dict = {}
                            
                            # Try multiple conversion styles
                            if hasattr(resp, "items"):
                                try:
                                    resp_dict = dict(resp.items())
                                except Exception:
                                    pass
                            
                            if not resp_dict:
                                if isinstance(resp, dict):
                                    resp_dict = resp
                                elif hasattr(resp, "to_dict"):
                                    resp_dict = resp.to_dict()
                                elif hasattr(type(resp), "to_dict"):
                                    resp_dict = type(resp).to_dict(resp)
                                else:
                                    # Fallback attribute checking
                                    for key in ["pedigree_data", "image_base64", "status", "message", "result"]:
                                        if hasattr(resp, key):
                                            resp_dict[key] = getattr(resp, key)
                                
                            # Unpack 'result' string if wrapped by protobuf MapComposite
                            if "result" in resp_dict and isinstance(resp_dict["result"], str):
                                try:
                                    resp_dict = json.loads(resp_dict["result"])
                                except Exception:
                                    pass

                            # Recursively convert any MapComposite/protobuf objects to raw Python structures
                            def to_dict_clean(val):
                                if hasattr(val, "items"):
                                    return {k: to_dict_clean(v) for k, v in val.items()}
                                elif isinstance(val, (list, tuple)) or (hasattr(val, "__iter__") and not isinstance(val, (str, bytes))):
                                    return [to_dict_clean(x) for x in val]
                                return val

                            from analysis.pedigree_generator import log_pedigree_step
                            if "pedigree_data" in resp_dict or resp_dict.get("status") == "success" or resp_dict.get("_INTERNAL_MARKER_PEDIGREE"):
                                metadata = {
                                    "type": "pedigree_chart",
                                    "pedigree_data": to_dict_clean(resp_dict.get("pedigree_data", {})),
                                    "svg": _LAST_PEDIGREE_SVG,
                                }
                                log_pedigree_step("PEDIGREE_METADATA_EXTRACT", "Successfully extracted pedigree chart metadata", {
                                    "has_svg": bool(metadata["svg"]),
                                    "svg_bytes": len(metadata["svg"] or ""),
                                    "individuals_count": len(metadata["pedigree_data"].get("individuals", []))
                                })
                        except Exception as ex:
                            from analysis.pedigree_generator import log_pedigree_step
                            log_pedigree_step("PEDIGREE_METADATA_ERROR", "Failed to convert function response to metadata dict", {"error": str(ex)})
                            pass

            return response.text, model_name, metadata

        except Exception as e:
            last_error = str(e)
            if on_status:
                on_status(f"⚠️ `{model_name}` agent error. Trying next model...")
            continue

    raise RuntimeError(f"All agent models exhausted. Last error: {last_error}")
