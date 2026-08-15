import json
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from core.history_db import SQLiteHistoryDB
from core.session import require_session, verify_owns
from analysis.vcf_parser import VCFParser
from analysis.vcf_prioritizer import VCFPrioritizer, DEEP_CONTEXT_LIMIT

router = APIRouter()
db = SQLiteHistoryDB()


def _build_compact_table(all_prioritized: dict) -> str:
    """One-line-per-variant compact table for basic context mode."""
    ORDER = ["dangerous", "possibly_harmful", "vus", "unannotated", "benign"]
    rows = [
        "| # | Variant | Gene | ClinSig | Impact | GlobalAF | Consequence |",
        "|---|---------|------|---------|--------|----------|-------------|",
    ]
    n = 0
    for cat in ORDER:
        for v in all_prioritized.get(cat, []):
            n += 1
            af = v.get("af")
            af_str = f"{af:.2e}" if af and float(af) > 0 else "N/A"
            cons = (v.get("consequences") or ["N/A"])[0]
            rows.append(
                f"| {n} | {v['variant']} | {v.get('gene','?')} | "
                f"{v.get('clinical_sig','N/A')} | {v.get('impact','?')} | {af_str} | {cons} |"
            )
    return "\n".join(rows)


def _count_conversation_variants(conversation_id: str) -> int:
    """Count total variants from all VCF enriched files already in this conversation."""
    files = db.get_files_with_labels(conversation_id)
    total = 0
    for f in files:
        if f["file_type"] == "vcf_enriched":
            try:
                raw = db.get_file_by_type(conversation_id, "vcf_enriched", f["patient_label"])
                if raw:
                    data = json.loads(raw.decode("utf-8"))
                    total += len(data.get("enriched_data", {}))
            except Exception:
                pass
    return total


@router.post("/")
async def upload_vcf(
    conversation_id: str = Form(...),
    session_id: str = Depends(require_session),
    patient_label: str = Form(default=""),
    file: UploadFile = File(...),
):
    try:
        verify_owns(db, conversation_id, session_id)

        # ── Guard: max 3 VCF files per conversation ──
        vcf_count = db.count_vcf_files(conversation_id)
        if vcf_count >= 3:
            raise HTTPException(
                status_code=409,
                detail="Maximum of 3 VCF files per conversation reached. Start a new conversation to analyse additional files."
            )

        # ── Parse ──
        file_bytes = await file.read()
        label = patient_label.strip() or f"Patient-{vcf_count + 1}"

        db.upsert_file(conversation_id, file.filename, file_bytes, "vcf", label)

        parser = VCFParser()
        variants = parser.parse(file_bytes, file.filename)

        # ── Prioritize + enrich ──
        prioritizer = VCFPrioritizer()
        prioritized = prioritizer.prioritize_variants(variants)
        enriched_data: dict = prioritized.pop("enriched_data", {})

        # ── Store enriched JSON for this patient ──
        enriched_payload = {
            "patient_label": label,
            "filename": file.filename,
            "total_variants": len(variants),
            "enriched_data": enriched_data,
            "compact_table": _build_compact_table(prioritized),
        }
        db.upsert_file(
            conversation_id,
            f"enriched_{label}.json",
            json.dumps(enriched_payload).encode("utf-8"),
            "vcf_enriched",
            label,
        )

        # ── Decide context mode (across ALL files in conversation) ──
        prev_total = _count_conversation_variants(conversation_id) - len(enriched_data)
        total_across_all = prev_total + len(enriched_data)
        context_mode = "deep" if total_across_all <= DEEP_CONTEXT_LIMIT else "basic"

        # ── Summary ──
        summary = (
            f"VCF ({label}): {len(variants)} variants — "
            f"🔴 {len(prioritized['dangerous'])} dangerous, "
            f"🟡 {len(prioritized['possibly_harmful'])} possibly harmful, "
            f"🔵 {len(prioritized['vus'])} VUS, "
            f"⚪ {len(prioritized['unannotated'])} unannotated, "
            f"🟢 {len(prioritized['benign'])} benign"
        )
        meta = {
            "type": "vcf_analysis",
            "patient_label": label,
            "total": len(variants),
            "summary": summary,
            "prioritized": prioritized,
            "context_mode": context_mode,
        }

        db.save_message(conversation_id, "user", f"📎 Uploaded `{file.filename}` (Patient: {label})")
        db.save_message(conversation_id, "assistant", summary, metadata=meta)

        # Auto-title conversation
        convs = db.list_conversations(session_id)
        for c in convs:
            if c["id"] == conversation_id and c["title"] == "New Conversation":
                db.rename_conversation(conversation_id, f"VCF: {label} — {file.filename}")
                break

        return {
            "status": "success",
            "summary": summary,
            "prioritized": prioritized,
            "enriched_data": enriched_data,
            "patient_label": label,
            "total_vcf_count": vcf_count + 1,
            "context_mode": context_mode,
            "compact_table": enriched_payload["compact_table"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
