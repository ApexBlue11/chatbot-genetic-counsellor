from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from core.history_db import SQLiteHistoryDB
from core.session import require_session, verify_owns
from core.query_router import GenomicQueryRouter
from core.gemini_client import (
    init_gemini, detect_rsid, detect_hgvs,
    generate_with_fallback, generate_with_agent, set_current_conv_id
)
from analysis.variant_analyser import VariantAnalyzer, VariantDataFetcher
from analysis.vcf_prioritizer import PREDICTOR_GUIDE
import json

router = APIRouter()
db = SQLiteHistoryDB()
router_genomic = GenomicQueryRouter()
fetcher = VariantDataFetcher()
analyzer = VariantAnalyzer()


class ChatRequest(BaseModel):
    model_config = {"populate_by_name": True}
    conversation_id: str
    message: str = ""
    user_input: str = ""   # legacy alias
    ai_enabled: bool = True
    sv_enabled: bool = True
    ped_enabled: bool = False
    system_context: Optional[str] = None

    def get_user_input(self) -> str:
        return self.message or self.user_input


@router.post("/")
def send_message(req: ChatRequest, session_id: str = Depends(require_session)):
    # The conversation id arrives in the body, so it must be checked against
    # the caller's session before any history is read or written.
    verify_owns(db, req.conversation_id, session_id)
    conversation_id = req.conversation_id
    user_input = req.get_user_input()

    if not user_input.strip():
        raise HTTPException(status_code=400, detail="Empty input")

    db.save_message(conversation_id, "user", user_input)

    # Auto-title on first user message
    convs = db.list_conversations(session_id)
    for c in convs:
        if c["id"] == conversation_id and c["title"] == "New Conversation":
            title = user_input[:40].strip()
            if len(user_input) > 40:
                title += "…"
            db.rename_conversation(conversation_id, title)
            break

    if not (req.ai_enabled or req.ped_enabled):
        msg = "AI is disabled. Enable AI in settings to converse with the assistant."
        db.save_message(conversation_id, "assistant", msg)
        return {"response": msg, "metadata": {}}

    # ── sv_enabled: route single-variant queries through the deep analysis path ──
    #
    # Only for requests that are *only* about the variant. This fast path
    # bypasses the agent loop entirely, so it has no pedigree tool and no
    # PubMed access; taking it for a composite question ("draw the pedigree,
    # look up this variant, find literature, then reason about it") silently
    # dropped every other tool and left the model answering from memory.
    if req.sv_enabled and req.ai_enabled and not req.ped_enabled:
        rsid = detect_rsid(user_input)
        hgvs = detect_hgvs(user_input)
        if (rsid or hgvs) and not _needs_agent(user_input):
            variant_id = rsid or hgvs
            return handle_single_variant(variant_id, user_input, conversation_id, req.ai_enabled)

    return handle_ai_chat(user_input, conversation_id, req.ped_enabled, req.system_context)


# Cues that a request needs more than a single-variant lookup, and so must go
# to the agent loop where the pedigree, literature and VCF tools live.
_AGENT_CUES = (
    "pedigree", "family history", "family tree", "draw the", "proband",
    "literature", "pubmed", "paper", "publication", "cite", "citation",
    "study", "studies", "recommend", "counsel", "risk of", "carrier risk",
    "sibling", "brother", "sister", "parents", "pregnan", "inherit",
)


def _needs_agent(text: str) -> bool:
    """True when the request asks for anything beyond one variant lookup."""
    lowered = text.lower()
    return any(cue in lowered for cue in _AGENT_CUES)


# ── Context builders ──

def _build_deep_context(enriched_payload: dict, patient_label: str) -> str:
    """Build a rich, fully-annotated context block for a single patient's VCF (deep mode)."""
    enriched = enriched_payload.get("enriched_data", {})
    total = len(enriched)
    lines = [f"=== PATIENT VCF: {patient_label} ({total} variant{'s' if total != 1 else ''}) ==="]

    for i, (vid, rec) in enumerate(enriched.items(), 1):
        lines.append(f"\n--- VARIANT {i}: {vid} | {rec.get('gene','?')} | {rec.get('location','')} | {rec.get('ref_alt','')} ---")
        if rec.get("hgvs_c"):
            lines.append(f"HGVS (coding): {rec['hgvs_c']}")

        clin = rec.get("clinical", {})
        lines.append(f"Clinical Significance: {clin.get('significance','N/A').upper()} ({clin.get('review_status','') or 'no review status'})")
        if clin.get("conditions"):
            lines.append(f"Associated Conditions: {', '.join(clin['conditions'])}")

        subs = clin.get("submissions", [])
        if subs:
            lines.append(f"ClinVar Submissions ({len(subs)}):")
            for s in subs:
                lines.append(f"  [{s.get('accession','')}] {s.get('significance','')} | {s.get('condition','')} | Evaluated: {s.get('last_evaluated','N/A')}")

        func = rec.get("functional", {})
        lines.append(f"Functional Impact: {func.get('impact','?')} | {', '.join(func.get('consequences',[]) or ['N/A'])}")
        lines.append("Functional Predictors:")

        def _fmt(label, val, score, guide):
            score_str = f" (score: {score})" if score not in (None, "", "None") else ""
            val_str = val if val not in (None, "", "None") else "N/A"
            return f"  {label}: {val_str}{score_str}  [{guide}]"

        lines.append(_fmt("SIFT", func.get("sift"), func.get("sift_score"),
                          "Scale 0–1, <0.05=deleterious — BEST for missense"))
        lines.append(_fmt("PolyPhen-2 HDIV", func.get("polyphen"), func.get("polyphen_score"),
                          "Scale 0–1, >0.85=probably damaging"))
        if func.get("revel") not in (None, "", "None"):
            lines.append(f"  REVEL: {func['revel']}  [Scale 0–1, >0.75=likely pathogenic — MOST RELIABLE ensemble]")
        if func.get("cadd") not in (None, "", "None"):
            lines.append(f"  CADD (Phred): {func['cadd']}  [>20=top 1%, >30=top 0.1% most deleterious — works for ALL variant types]")
        for pred_key, pred_label in [("lrt","LRT"), ("mutationtaster","MutationTaster"), ("fathmm","FATHMM"), ("provean","PROVEAN")]:
            v = func.get(pred_key)
            if v not in (None, "", "None"):
                lines.append(f"  {pred_label}: {v}")

        pop = rec.get("population", {})
        def _af(v):
            if v is None:
                return "N/A"
            try:
                return f"{float(v):.2e}"
            except Exception:
                return str(v)
        lines.append(
            f"Population Frequencies (gnomAD):\n"
            f"  Global: {_af(pop.get('global'))} | African: {_af(pop.get('african'))} | "
            f"East Asian: {_af(pop.get('east_asian'))} | South Asian: {_af(pop.get('south_asian'))}\n"
            f"  European (Non-Finnish): {_af(pop.get('european_nfe'))} | "
            f"European (Finnish): {_af(pop.get('european_fin'))}\n"
            f"  Latino: {_af(pop.get('latino'))} | Ashkenazi Jewish: {_af(pop.get('ashkenazi'))}"
        )

    return "\n".join(lines)


def _build_vcf_context_for_prompt(conversation_id: str) -> tuple[str, str]:
    """
    Load all enriched VCF files for this conversation and build the appropriate context.
    Returns (context_block, context_mode).
    """
    files = db.get_files_with_labels(conversation_id)
    enriched_files = [f for f in files if f["file_type"] == "vcf_enriched"]
    if not enriched_files:
        return "", "none"

    # Count total variants to decide mode
    total_variants = 0
    payloads = {}
    for f in enriched_files:
        raw = db.get_file_by_type(conversation_id, "vcf_enriched", f["patient_label"])
        if raw:
            payload = json.loads(raw.decode("utf-8"))
            payloads[f["patient_label"]] = payload
            total_variants += len(payload.get("enriched_data", {}))

    from analysis.vcf_prioritizer import DEEP_CONTEXT_LIMIT
    context_mode = "deep" if total_variants <= DEEP_CONTEXT_LIMIT else "basic"

    blocks = []
    if context_mode == "deep":
        for label, payload in payloads.items():
            blocks.append(_build_deep_context(payload, label))
        blocks.append(f"\n{PREDICTOR_GUIDE}")
    else:
        # Basic mode: compact table per patient
        for label, payload in payloads.items():
            table = payload.get("compact_table", "")
            blocks.append(f"=== PATIENT: {label} ===\n{table}")

    return "\n\n".join(blocks), context_mode


# ── Main AI chat handler ──

def handle_ai_chat(user_input, conversation_id, ped_enabled=False, system_context=None):
    genai = init_gemini()
    if not genai:
        raise HTTPException(status_code=500, detail="Gemini API not configured")

    # Set conversation ID so tool functions can load patient files
    set_current_conv_id(conversation_id)

    history = db.get_messages(conversation_id)[-10:]

    # Build file manifest for AI awareness
    files = db.get_files_with_labels(conversation_id)
    patient_vcfs = [(f["patient_label"], f["filename"]) for f in files if f["file_type"] == "vcf"]
    enriched_files = [(f["patient_label"], f["filename"]) for f in files if f["file_type"] == "vcf_enriched"]

    file_manifest = ""
    if patient_vcfs:
        vcf_lines = ", ".join([f"'{label}' ({fname})" for label, fname in patient_vcfs])
        enriched_lines = ", ".join([f"'{label}'" for label, _ in enriched_files])
        file_manifest = (
            f"\n\nACTIVE WORKSPACE FILES:"
            f"\n  Original VCF files: {vcf_lines}"
            f"\n  Enriched annotation files (pre-computed, no API calls needed): {enriched_lines}"
            f"\n  Conversation ID (for tool calls): '{conversation_id}'"
        )

    # Build VCF context (deep or basic)
    vcf_context_block, context_mode = _build_vcf_context_for_prompt(conversation_id)

    # ── System prompt ──
    system_parts = [
        "You are a professional genetics and genomics expert assistant for genetic counselors. "
        "You help analyse variants, interpret pathogenicity, research literature, and support "
        "clinical decision-making. You are NOT a replacement for clinical judgment.",

        "TOOLS AVAILABLE TO YOU — USE THEM PROACTIVELY:"
        "\n  • search_pubmed(query_term): Search PubMed for literature. YOU SHOULD SEARCH for every "
        "clinically significant variant you discuss. Formulate your own query based on the clinical context."
        "\n  • Clinical_Variant_Analyzer(variant_id): Deep single-variant analysis (calls live APIs). "
        "Use for new variants not in the uploaded context."
        "\n  • read_patient_vcf(patient_label, start_row, end_row): Read raw VCF rows by patient label. "
        "Use when a counselor references specific row numbers."
        "\n  • read_enriched_data(patient_label, variant_ids): Read full pre-computed annotation records "
        "(all predictors, all ClinVar submissions, all population frequencies). "
        "PREFER THIS over Clinical_Variant_Analyzer when variants are from uploaded VCF files — it's instant."
        "\n  • create_pedigree_chart(description): Draw a medical pedigree from a family description.",
    ]

    if file_manifest:
        system_parts.append(file_manifest)

    if vcf_context_block:
        if context_mode == "deep":
            system_parts.append(
                "COMPLETE VARIANT CONTEXT (deep mode — all variants with full annotations):\n"
                + vcf_context_block
            )
            system_parts.append(
                "INSTRUCTIONS FOR DEEP CONTEXT:\n"
                "• You have FULL annotation data for all variants above — use it directly.\n"
                "• Do NOT call Clinical_Variant_Analyzer for these variants (data already here).\n"
                "• DO call read_enriched_data if you need to re-read or compare specific records.\n"
                "• DO call search_pubmed for any variant with Pathogenic/Likely Pathogenic/VUS significance.\n"
                "• After your analysis, present findings clearly to the counselor — flag gene clusters, "
                "compare population frequencies across ethnicities, and highlight any conflicting submissions."
            )
        else:
            system_parts.append(
                "VARIANT CONTEXT SUMMARY (basic mode — use tools to drill into specific variants):\n"
                + vcf_context_block
            )
            system_parts.append(
                "INSTRUCTIONS FOR BASIC CONTEXT:\n"
                "• The table above shows ALL variants. Use it to identify which variants to investigate.\n"
                "• When you want full details for a variant, call read_enriched_data(patient_label, variant_ids).\n"
                "• This returns all predictors, all ClinVar submissions, and all population frequencies instantly.\n"
                "• After reading enriched data, call search_pubmed to find supporting literature.\n"
                "• Prioritise investigating Pathogenic/HIGH impact variants first, then VUS."
            )
    elif system_context:
        # Fallback: use system_context passed from frontend (legacy path)
        system_parts.append(f"UPLOAD CONTEXT:\n{system_context}")

    if ped_enabled:
        system_parts.append(
            "CRITICAL: The Pedigree Tool is ON. If the user describes any family history, "
            "MUST call create_pedigree_chart immediately."
        )

    system_parts.append(
        "CRITICAL RESPONSE RULES:\n"
        "1. ALWAYS wrap your step-by-step clinical reasoning in:\n"
        "   <details><summary>Clinical Thinking Process</summary>\n"
        "   ... reasoning ...\n"
        "   </details>\n"
        "   Then present your final answer clearly after the closing tag.\n"
        "2. NEVER hallucinate literature — only cite papers returned by search_pubmed.\n"
        "3. When summarising multiple variants, output a Markdown table: Variant ID | Gene | "
        "Protein Effect | Pathogenicity | Associated Conditions.\n"
        "4. Reference specific databases (ClinVar, gnomAD, dbNSFP) when stating facts.\n"
        "5. If predictors conflict, state the conflict explicitly and explain which is more reliable."
    )

    # Conversation history
    for msg in history:
        if msg["role"] == "system":
            continue
        system_parts.append(f"{msg['role'].upper()}: {msg['content']}")

    if not history or history[-1]["content"] != user_input:
        system_parts.append(f"USER: {user_input}")

    prompt = "\n\n".join(system_parts)

    try:
        response_text, model_used, metadata = generate_with_agent(genai, prompt)
        
        import re
        # Strip any markdown image references containing base64 data URIs
        response_text = re.sub(r'!\[.*?\]\(data:image/.*?;base64,.*?\)', '', response_text)
        response_text = re.sub(r'\n{3,}', '\n\n', response_text).strip()

        full_response = response_text
        if metadata and metadata.get("type") == "pedigree_chart":
            full_response += "\n\n*[Pedigree chart generated]*"
        db.save_message(conversation_id, "assistant", full_response, metadata=metadata)
        return {"response": full_response, "metadata": metadata}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Single Variant Handler ──

def handle_single_variant(variant_id, user_input, conversation_id, ai_enabled):
    classification = router_genomic.classify(variant_id)
    variant_data = fetcher.fetch_variant_data(
        variant_id=classification.extracted_identifier,
        query_type=classification.query_type,
    )
    analysis = analyzer.analyze_variant(variant_data)
    clin_sig = analysis.get("clinical_relevance", {}).get("clinical_significance", "N/A")

    # Gene resolution
    gene = "Unknown"
    clinvar_data = variant_data.get("clinvar_data", {})
    myvariant_data = variant_data.get("myvariant_data", {})
    if clinvar_data and isinstance(clinvar_data, dict) and clinvar_data.get("gene_symbol"):
        gene = clinvar_data["gene_symbol"]
    elif myvariant_data and isinstance(myvariant_data, dict):
        for candidate in [
            myvariant_data.get("clinvar", {}).get("gene", {}).get("symbol"),
            (myvariant_data.get("dbnsfp", {}).get("genename") or [None])[0]
            if isinstance(myvariant_data.get("dbnsfp", {}).get("genename"), list)
            else myvariant_data.get("dbnsfp", {}).get("genename"),
        ]:
            if candidate:
                gene = candidate
                break

    meta = {
        "type": "variant_analysis",
        "variant_id": variant_id,
        "pathogenicity": analysis["pathogenicity_prediction"]["classification"],
        "confidence": analysis["pathogenicity_prediction"]["confidence"],
        "protein_effect": analysis["functional_impact"]["protein_effect"],
        "clinical_significance": clin_sig,
        "raw_data": variant_data,
    }
    summary = (
        f"Variant `{variant_id}`: {meta['pathogenicity']} "
        f"({meta['confidence']}), {meta['protein_effect'].replace('_', ' ')}"
    )

    if ai_enabled:
        genai = init_gemini()
        if genai:
            set_current_conv_id(conversation_id)
            prompt = _build_variant_prompt(variant_id, gene, variant_data, analysis, user_input)
            try:
                response_text, model_used = generate_with_fallback(genai, prompt)
                summary += f"\n\n### 📋 AI Interpretation\n{response_text}\n\n*Model: {model_used}*"
            except Exception:
                pass

    db.save_message(conversation_id, "assistant", summary, metadata=meta)
    return {"response": summary, "metadata": meta}


@router.get("/variant/{variant_id}")
def get_variant_details(variant_id: str):
    classification = router_genomic.classify(variant_id)
    variant_data = fetcher.fetch_variant_data(
        variant_id=classification.extracted_identifier,
        query_type=classification.query_type,
    )
    analysis = analyzer.analyze_variant(variant_data)
    clin_sig = analysis.get("clinical_relevance", {}).get("clinical_significance", "N/A")
    return {
        "variant_id": variant_id,
        "pathogenicity": analysis["pathogenicity_prediction"]["classification"],
        "confidence": analysis["pathogenicity_prediction"]["confidence"],
        "protein_effect": analysis["functional_impact"]["protein_effect"],
        "clinical_significance": clin_sig,
        "raw_data": variant_data,
    }


def _build_variant_prompt(variant_id, gene, variant_data, analysis, user_input):
    prompt = f"""You are a clinical genetics expert. Interpret the following variant for a genetic counselor.
Use Unicode symbols (Δ, α, β) instead of LaTeX. Do NOT format as a letter.

User question: {user_input}
Variant: {variant_id} | Gene: {gene}
Pathogenicity: {analysis['pathogenicity_prediction']['classification']} ({analysis['pathogenicity_prediction']['confidence']})
Protein Effect: {analysis['functional_impact']['protein_effect']}
Clinical Significance: {analysis.get('clinical_relevance', {}).get('clinical_significance', 'N/A')}

Raw data summary:
- MyVariant: {json.dumps(variant_data.get('myvariant_data', {}), indent=1)[:2000]}
- ClinVar: {json.dumps(variant_data.get('clinvar_data', {}), indent=1)[:1000]}

Wrap your reasoning in:
<details><summary>Clinical Thinking Process</summary>
... reasoning ...
</details>
Then provide a clear clinical interpretation."""
    return prompt
