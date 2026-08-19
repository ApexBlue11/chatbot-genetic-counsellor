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
from core.api_clients import fetch_pubmed_by_ids, pubmed_ids_from_vep, query_pubmed
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
    thinking_enabled: bool = False
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
            return handle_single_variant(
                variant_id, user_input, conversation_id, req.ai_enabled, req.thinking_enabled
            )

    return handle_ai_chat(
        user_input, conversation_id, req.ped_enabled, req.system_context, req.thinking_enabled
    )


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

def handle_ai_chat(user_input, conversation_id, ped_enabled=False, system_context=None,
                   thinking_enabled=False):
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
        "CITATIONS: every reference to published literature must carry the PMID "
        "returned by search_pubmed, written as a markdown link "
        "([PMID: 12345678](https://pubmed.ncbi.nlm.nih.gov/12345678/)). Cite only "
        "papers that tool actually returned; if you did not call it, say so rather "
        "than citing from memory.\n"
        "RETRIEVED VS RECALLED: name the database each fact came from. If a tool "
        "lists a field under data_not_retrieved, do not supply that number from "
        "prior knowledge without labelling it as general knowledge rather than a lookup."
    )

    # Rule 1 is the half of Thinking mode the counselor can see: on, they get the
    # reasoning to audit; off, they get the finding without the deliberation.
    if thinking_enabled:
        reasoning_rule = (
            "1. Reason the case through step by step BEFORE concluding, and show that "
            "work wrapped in:\n"
            "   <details><summary>Clinical Thinking Process</summary>\n"
            "   ... reasoning ...\n"
            "   </details>\n"
            "   Weigh the evidence explicitly: which predictors agree, which conflict, "
            "what the population frequency implies, and what would change your call. "
            "Then present your final answer clearly after the closing tag.\n"
        )
    else:
        reasoning_rule = (
            "1. Answer directly. Do NOT emit a "
            "<details>Clinical Thinking Process</details> block: give the conclusion and "
            "the evidence behind it without narrating your deliberation.\n"
        )

    system_parts.append(
        "CRITICAL RESPONSE RULES:\n"
        + reasoning_rule +
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

def handle_single_variant(variant_id, user_input, conversation_id, ai_enabled,
                          thinking_enabled=False):
    classification = router_genomic.classify(variant_id)
    variant_data = fetcher.fetch_variant_data(
        variant_id=classification.extracted_identifier,
        query_type=classification.query_type,
    )
    analysis = analyzer.analyze_variant(variant_data)
    clin_sig = analysis.get("clinical_relevance", {}).get("clinical_significance", "N/A")

    # Gene resolution.
    #
    # VEP used to be left out of this, so a variant that ClinVar and MyVariant
    # know nothing about resolved to "Unknown" even when VEP had named the gene
    # outright. rs34764978 is the case: VEP returns DHFR on the MANE transcript,
    # the details table showed DHFR, and the model was still told the gene was
    # unspecified and duly reported that it could not assess gene-disease
    # validity.
    clinvar_data = variant_data.get("clinvar_data", {})
    myvariant_data = variant_data.get("myvariant_data", {})
    gene = _resolve_gene(clinvar_data, myvariant_data, variant_data.get("vep_data"))

    # Papers dbSNP has linked to this exact variant. The fast path never looked
    # for literature at all, so an answer here carried no citations while the
    # agent path cited freely — and for rs34764978 the linked set is squarely on
    # point (DHFR 3'UTR miRNA binding, methotrexate response).
    literature = fetch_pubmed_by_ids(pubmed_ids_from_vep(variant_data.get("vep_data"))[:6])
    lit_scope = "variant" if literature else "none"
    if not literature and gene != "Unknown":
        # Nothing variant-specific. A gene-level search at least gives the
        # counselor somewhere to start, but it must be labelled as such: these
        # are recent papers about the gene, not evidence about this variant, and
        # presenting them as variant-linked would invite exactly the kind of
        # citation the grounding rule exists to prevent.
        literature = query_pubmed(f"{gene}[Gene] AND (variant OR polymorphism OR mutation)")[:5]
        lit_scope = "gene" if literature else "none"
    for paper in literature:
        paper["scope"] = lit_scope

    meta = {
        "type": "variant_analysis",
        "variant_id": variant_id,
        "gene": gene,
        "pathogenicity": analysis["pathogenicity_prediction"]["classification"],
        "confidence": analysis["pathogenicity_prediction"]["confidence"],
        "protein_effect": analysis["functional_impact"]["protein_effect"],
        "clinical_significance": clin_sig,
        "literature": literature,
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
            prompt = _build_variant_prompt(
                variant_id, gene, variant_data, analysis, user_input, thinking_enabled,
                literature,
            )
            try:
                response_text, model_used = generate_with_fallback(
                    genai, prompt, thinking=thinking_enabled
                )
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


def _first(val):
    """dbNSFP repeats a score once per transcript; they are the same number."""
    if isinstance(val, list):
        for v in val:
            if v not in (None, "", "."):
                return v
        return None
    return val if val not in (None, "", ".") else None


def _resolve_gene(clinvar_data, myvariant_data, vep_data) -> str:
    """Gene symbol from whichever source actually knows it.

    Ordered by how specific the source is to this variant: ClinVar's curated
    record, then MyVariant's annotations, then VEP's transcript consequences —
    which is the only one that answers for variants no clinical database has
    catalogued yet.
    """
    if isinstance(clinvar_data, dict) and clinvar_data.get("gene_symbol"):
        return clinvar_data["gene_symbol"]

    if isinstance(myvariant_data, dict):
        genename = (myvariant_data.get("dbnsfp") or {}).get("genename")
        for candidate in [
            ((myvariant_data.get("clinvar") or {}).get("gene") or {}).get("symbol"),
            genename[0] if isinstance(genename, list) and genename else genename,
            ((myvariant_data.get("snpeff") or {}).get("ann") or {}).get("genename")
            if isinstance((myvariant_data.get("snpeff") or {}).get("ann"), dict) else None,
        ]:
            if candidate:
                return candidate

    records = vep_data if isinstance(vep_data, list) else [vep_data]
    transcripts = []
    for rec in records:
        if isinstance(rec, dict):
            transcripts.extend(rec.get("transcript_consequences") or [])
    for pick in (lambda t: t.get("mane_select"), lambda t: t.get("canonical") == 1, lambda t: True):
        for t in transcripts:
            if pick(t) and t.get("gene_symbol"):
                return t["gene_symbol"]

    return "Unknown"


def _variant_evidence_block(variant_data, analysis, literature=None) -> str:
    """Curated evidence for the single-variant prompt.

    This used to be `json.dumps(myvariant_data)[:2000]`. MyVariant records run
    to ~100 kB for a well-studied variant, and the keys arrive alphabetically,
    so 2,000 characters bought nothing but the interior of the `cadd` object —
    mapability windows and distance-to-TSE. Every field a counselor cares about
    (gnomad_genome, gnomad_exome, dbnsfp, exac) sat past the cut. The model was
    therefore reasoning about frequencies and predictors it had never been
    shown, for every variant, whether or not the lookup succeeded.
    """
    mv = variant_data.get("myvariant_data") or {}
    dbnsfp = mv.get("dbnsfp") or {}
    lines = []

    # ── Population frequency ──
    pop = analysis.get("population_frequency") or {}
    afs = [r.get("allele_frequency") for r in pop.values()
           if isinstance(r, dict) and r.get("allele_frequency") is not None]
    if afs and all(af == 0 for af in afs):
        # gnomAD answered, and the answer was zero observations everywhere.
        # Printing nine rows of "0 (0%)" invited the model to read them as nine
        # separate measurements and cite them as PM2 support; it is one fact.
        src = next((r.get("source", "gnomAD") for r in pop.values() if isinstance(r, dict)), "gnomAD")
        lines.append(
            f"POPULATION FREQUENCY: zero observations in {src} across all "
            f"{len(afs)} ancestry groups reported. The variant is catalogued in dbSNP but "
            "was not seen in this gnomAD release — treat as absent, not as a measured 0%."
        )
    elif afs:
        lines.append("POPULATION FREQUENCY (gnomAD):")
        for label, rec in pop.items():
            if not isinstance(rec, dict):
                continue
            af = rec.get("allele_frequency")
            if af is None:
                continue
            lines.append(f"  {label}: {af:.6g} ({rec.get('percent', 0):.4g}%) [{rec.get('source', 'gnomAD')}]")
    else:
        lines.append("POPULATION FREQUENCY: not retrieved (no gnomAD record returned for this variant).")

    # ── Functional predictors ──
    sift = _first(dbnsfp.get("sift", {}).get("pred") if isinstance(dbnsfp.get("sift"), dict) else dbnsfp.get("sift_pred"))
    sift_score = _first(dbnsfp.get("sift", {}).get("score") if isinstance(dbnsfp.get("sift"), dict) else dbnsfp.get("sift_score"))
    pp2 = dbnsfp.get("polyphen2") or {}
    hdiv = pp2.get("hdiv") if isinstance(pp2, dict) else {}
    polyphen = _first(hdiv.get("pred") if isinstance(hdiv, dict) else dbnsfp.get("polyphen2_hdiv_pred"))
    polyphen_score = _first(hdiv.get("score") if isinstance(hdiv, dict) else dbnsfp.get("polyphen2_hdiv_score"))
    revel = _first((dbnsfp.get("revel") or {}).get("score") if isinstance(dbnsfp.get("revel"), dict) else dbnsfp.get("revel_score"))
    cadd_obj = mv.get("cadd") or dbnsfp.get("cadd") or {}
    cadd = _first(cadd_obj.get("phred") if isinstance(cadd_obj, dict) else None)

    preds = []
    if sift is not None:
        preds.append(f"  SIFT: {sift}" + (f" (score {sift_score})" if sift_score is not None else "") + "  [<0.05 deleterious; missense only]")
    if polyphen is not None:
        preds.append(f"  PolyPhen-2 HDIV: {polyphen}" + (f" (score {polyphen_score})" if polyphen_score is not None else "") + "  [>0.85 probably damaging]")
    if revel is not None:
        preds.append(f"  REVEL: {revel}  [>0.75 likely pathogenic; most reliable missense ensemble]")
    if cadd is not None:
        preds.append(f"  CADD (Phred): {cadd}  [>20 top 1%, >30 top 0.1%; works for all variant types]")

    if preds:
        lines.append("FUNCTIONAL PREDICTORS (dbNSFP):")
        lines.extend(preds)
    else:
        lines.append(
            "FUNCTIONAL PREDICTORS: not retrieved. dbNSFP is trained on missense SNVs, "
            "so frameshifts, indels and non-coding variants legitimately have no scores."
        )

    # ── ClinVar ──
    cv = variant_data.get("clinvar_data") or {}
    if cv and "error" not in cv:
        lines.append("CLINVAR (aggregate):")
        lines.append(f"  Classification: {cv.get('clinical_significance', 'N/A')}")
        lines.append(f"  Review status: {cv.get('review_status', 'N/A')}")
        conds = cv.get("conditions")
        if conds:
            lines.append(f"  Conditions: {', '.join(conds) if isinstance(conds, list) else conds}")
        if cv.get("protein_change"):
            lines.append(f"  Protein change: {cv['protein_change']}")
        if cv.get("title"):
            lines.append(f"  ClinVar title: {cv['title']}")
    else:
        lines.append("CLINVAR: no aggregate record retrieved.")

    rcv = (mv.get("clinvar") or {}).get("rcv")
    rcvs = rcv if isinstance(rcv, list) else ([rcv] if rcv else [])
    if rcvs:
        from collections import Counter
        tally = Counter(str(r.get("clinical_significance", "")).strip() for r in rcvs if r.get("clinical_significance"))
        lines.append(f"  Submitted interpretations ({len(rcvs)} records): " +
                     "; ".join(f"{k} x{v}" for k, v in tally.most_common()))

    if literature:
        if literature[0].get("scope") == "gene":
            lines.append(
                "LITERATURE (gene-level search — NOT specific to this variant; dbSNP links "
                "no papers to it. Cite these as background on the gene, never as evidence "
                "about this variant):"
            )
        else:
            lines.append("LITERATURE (PubMed records dbSNP links to this exact variant):")
        for paper in literature:
            lines.append(f"  [PMID: {paper['pmid']}] {paper['title']} — {paper['journal']} {paper.get('pubdate', '')}".rstrip())
    else:
        lines.append("LITERATURE: no PubMed records retrieved for this variant.")

    return "\n".join(lines)


def _build_variant_prompt(variant_id, gene, variant_data, analysis, user_input,
                          thinking_enabled=False, literature=None):
    # Same split as the agent path: Thinking mode buys the audit trail and costs
    # the wait; with it off the counselor wants the interpretation on its own.
    if thinking_enabled:
        closing = (
            "Wrap your reasoning in:\n"
            "<details><summary>Clinical Thinking Process</summary>\n"
            "... reasoning ...\n"
            "</details>\n"
            "Then provide a clear clinical interpretation."
        )
    else:
        closing = (
            "Give a clear clinical interpretation directly. Do NOT emit a "
            "<details>Clinical Thinking Process</details> block."
        )

    prompt = f"""You are a clinical genetics expert. Interpret the following variant for a genetic counselor.
Use Unicode symbols (Δ, α, β) instead of LaTeX. Do NOT format as a letter.

User question: {user_input}
Variant: {variant_id} | Gene: {gene}
Pathogenicity: {analysis['pathogenicity_prediction']['classification']} ({analysis['pathogenicity_prediction']['confidence']})
Protein Effect: {analysis['functional_impact']['protein_effect']}
Clinical Significance: {analysis.get('clinical_relevance', {}).get('clinical_significance', 'N/A')}

RETRIEVED EVIDENCE:
{_variant_evidence_block(variant_data, analysis, literature)}

GROUNDING: the block above is everything that was actually retrieved for this
variant. If something is missing from it - no gnomAD frequencies, no predictor
scores - say it was not retrieved rather than supplying the number from prior
knowledge. General knowledge is fine when labelled as such; it must never be
presented as a database lookup. Cite only the PMIDs listed above, as markdown
links ([PMID: 12345678](https://pubmed.ncbi.nlm.nih.gov/12345678/)); if none are
listed, say so rather than recalling citations.

{closing}"""
    return prompt
