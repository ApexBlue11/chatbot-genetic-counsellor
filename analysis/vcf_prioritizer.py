import time
from typing import List, Dict, Any, Optional
from core.api_clients import query_myvariant_batch, query_vep_batch


DEEP_CONTEXT_LIMIT = 35   # total variants across all files before switching to basic context
PER_FILE_CAP       = 25   # max variants per single VCF file

PREDICTOR_GUIDE = """\
=== FUNCTIONAL PREDICTOR INTERPRETATION GUIDE ===
SIFT          : Best for missense variants. Score <0.05 = deleterious. NOT valid for indels/frameshifts.
PolyPhen-2 HDIV: Best for disease association in amino-acid changing variants. Score >0.85 = probably damaging.
REVEL (ensemble): MOST RELIABLE overall missense score. Combines 13 tools. Score >0.75 = likely pathogenic.
CADD (Phred)  : Universal — works for ALL variant types including indels and regulatory. >20 = top 1%, >30 = top 0.1%.
LRT           : Best for evolutionarily conserved functional sites.
MutationTaster: Good for splice-site and regulatory variants.
FATHMM        : Best for protein functional domain variants. Weighted version is more reliable.
Note: For indels and frameshifts, rely on CADD and VEP impact (HIGH) rather than SIFT/PolyPhen.
"""


class VCFPrioritizer:
    def __init__(self, max_candidates: int = None):
        # max_candidates ignored — we always query all variants up to PER_FILE_CAP
        self.myvariant_results: Dict = {}   # exposed after prioritize_variants()

    def prioritize_variants(self, variants: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Prioritizes and categorizes variants from a single VCF file.
        Returns prioritized dict WITH enriched_data for deep-context building.
        """
        # Cap per-file
        variants = variants[:PER_FILE_CAP]

        prioritized = {
            "dangerous": [],
            "possibly_harmful": [],
            "vus": [],
            "unannotated": [],
            "benign": [],
            "gene_clusters": [],
        }
        enriched_data: Dict[str, Dict] = {}

        # ── Step 0: Batch-resolve gene names + VEP impact for ALL variants ──
        all_rsids = [v["query_id"] for v in variants if v["query_id"].startswith("rs")]
        gene_map: Dict[str, str] = {}
        vep_impact_map: Dict[str, tuple] = {}

        if all_rsids:
            IMPACT_PRIORITY = {"HIGH": 0, "MODERATE": 1, "LOW": 2, "MODIFIER": 3}
            vep_results_raw = query_vep_batch(all_rsids)
            for item in vep_results_raw:
                if isinstance(item, dict) and "id" in item:
                    rsid = item["id"]
                    best_impact = "LOW"
                    best_priority = IMPACT_PRIORITY.get("LOW", 99)
                    best_consequences = []
                    for tc in item.get("transcript_consequences", []):
                        if tc.get("gene_symbol") and not gene_map.get(rsid):
                            gene_map[rsid] = tc["gene_symbol"]
                        impact = tc.get("impact", "LOW")
                        priority = IMPACT_PRIORITY.get(impact, 99)
                        if priority < best_priority:
                            best_priority = priority
                            best_impact = impact
                            best_consequences = tc.get("consequence_terms", [])
                    vep_impact_map[rsid] = (best_impact, best_consequences)

        def _resolve_gene(var: Dict) -> str:
            qid = var.get("query_id", "")
            if qid in gene_map:
                return gene_map[qid]
            info = var.get("info", {})
            gene = info.get("GENE") or info.get("GENEINFO", "")
            if gene and ":" in gene:
                gene = gene.split(":")[0]
            return gene or "Unknown"

        # ── Step 1: Pre-filter variants with ClinVar annotations from VCF INFO ──
        candidates = []
        for var in variants:
            gene = _resolve_gene(var)
            af = var.get("af")
            clnsig = var.get("clnsig")
            if clnsig:
                parsed = self._make_variant_record(var, gene, af, clnsig, source="VCF CLNSIG")
                self._categorize(parsed, prioritized)
                enriched_data[var["query_id"]] = self._make_enriched_record(
                    var, gene, clnsig, af, {}, vep_impact_map
                )
                continue
            candidates.append(var)

        # ── Step 2: Batch query MyVariant for ALL candidates ──
        rsids = [v["query_id"] for v in candidates if v["query_id"].startswith("rs")]
        self.myvariant_results = {}

        if rsids:
            mv_list = query_myvariant_batch(rsids)
            for item in mv_list:
                if isinstance(item, dict):
                    key = item.get("query") or item.get("_id", "")
                    self.myvariant_results[key] = item

        # Fallback single queries for non-rsID genomic coordinates (limited to ≤15)
        genomic_ids = [v["query_id"] for v in candidates if not v["query_id"].startswith("rs")]
        if genomic_ids and len(genomic_ids) <= 15:
            from core.api_clients import query_myvariant
            for gid in genomic_ids[:15]:
                time.sleep(0.15)
                self.myvariant_results[gid] = query_myvariant(gid)

        # ── Step 3: Categorize candidates using MyVariant's embedded ClinVar ──
        for var in candidates:
            qid = var["query_id"]
            gene = _resolve_gene(var)
            mv_res = self.myvariant_results.get(qid, {})

            # Use MyVariant's embedded ClinVar (faster than separate API call)
            mv_clinvar = mv_res.get("clinvar", {})
            if isinstance(mv_clinvar, dict):
                rcv = mv_clinvar.get("rcv", {})
                if isinstance(rcv, list) and rcv:
                    rcv = rcv[0]
                clinical_sig = rcv.get("clinical_significance", "") if isinstance(rcv, dict) else ""
                clinical_sig = mv_clinvar.get("clinical_significance", clinical_sig) or clinical_sig
                gene_from_clinvar = mv_clinvar.get("gene", {})
                if isinstance(gene_from_clinvar, dict) and gene_from_clinvar.get("symbol"):
                    gene = gene_from_clinvar["symbol"]
            else:
                clinical_sig = ""

            clinical_sig = clinical_sig or "Not Annotated"

            dbnsfp = mv_res.get("dbnsfp", {})
            sift_pred = self._get_first(dbnsfp.get("sift_pred", ""))
            polyphen_pred = self._get_first(dbnsfp.get("polyphen2_hdiv_pred", ""))

            vep_impact, consequences = vep_impact_map.get(qid, ("LOW", []))

            parsed = {
                "variant": qid,
                "gene": gene,
                "location": f"chr{var['chrom']}:{var['pos']}",
                "ref_alt": f"{var['ref']}>{var['alt']}",
                "clinical_sig": clinical_sig,
                "sift": sift_pred,
                "polyphen": polyphen_pred,
                "consequences": consequences,
                "impact": vep_impact,
                "af": var.get("af") or self._extract_af(mv_res),
            }
            self._categorize(parsed, prioritized)

            enriched_data[qid] = self._make_enriched_record(
                var, gene, clinical_sig, parsed["af"], mv_res, vep_impact_map
            )

        prioritized["gene_clusters"] = self._analyze_gene_clusters(prioritized)
        prioritized["enriched_data"] = enriched_data
        return prioritized

    # ── Helpers ──

    def _get_first(self, val) -> str:
        """Return first element if list, else val as string."""
        if isinstance(val, list):
            return str(val[0]) if val else ""
        return str(val) if val else ""

    def _make_variant_record(self, var, gene, af, clinical_sig, source=""):
        return {
            "variant": var["query_id"],
            "gene": gene,
            "location": f"chr{var['chrom']}:{var['pos']}",
            "ref_alt": f"{var['ref']}>{var['alt']}",
            "clinical_sig": clinical_sig,
            "af": af,
            "source": source,
        }

    def _make_enriched_record(self, var, gene, clinical_sig, af, mv_res, vep_impact_map) -> Dict:
        """Build a structured enriched record with all clinical/functional/population data."""
        qid = var["query_id"]
        mv_clinvar = mv_res.get("clinvar", {}) if mv_res else {}
        dbnsfp = mv_res.get("dbnsfp", {}) if mv_res else {}

        # Population frequencies — gnomAD stores AFs nested under gg['af']
        def _get_pop(src_dict, key):
            af_sub = src_dict.get("af", {})
            if isinstance(af_sub, dict):
                return af_sub.get(key) or src_dict.get(key)
            return src_dict.get(key)

        gg = mv_res.get("gnomad_genome", {}) if mv_res else {}
        ge = mv_res.get("gnomad_exome", {}) if mv_res else {}

        def pop(key):
            return _get_pop(gg, key) or _get_pop(ge, key)

        # ClinVar submissions (up to 20)
        rcv_raw = mv_clinvar.get("rcv", []) if isinstance(mv_clinvar, dict) else []
        if isinstance(rcv_raw, dict):
            rcv_raw = [rcv_raw]
        submissions = []
        for r in rcv_raw[:20]:
            if not isinstance(r, dict):
                continue
            cond = r.get("conditions", {})
            cond_name = ""
            if isinstance(cond, dict):
                cond_name = cond.get("name", "")
            elif isinstance(cond, list) and cond:
                cond_name = cond[0].get("name", "") if isinstance(cond[0], dict) else str(cond[0])
            submissions.append({
                "accession": r.get("accession", ""),
                "significance": r.get("clinical_significance", ""),
                "condition": cond_name,
                "last_evaluated": r.get("last_evaluated", ""),
            })

        vep_impact, consequences = vep_impact_map.get(qid, ("", []))

        return {
            "variant": qid,
            "gene": gene,
            "location": f"chr{var['chrom']}:{var['pos']}",
            "ref_alt": f"{var['ref']}>{var['alt']}",
            "hgvs_c": mv_clinvar.get("hgvs", {}).get("coding", "") if isinstance(mv_clinvar, dict) else "",
            "clinical": {
                "significance": clinical_sig,
                "review_status": mv_clinvar.get("review_status", "") if isinstance(mv_clinvar, dict) else "",
                "conditions": list({s["condition"] for s in submissions if s["condition"]}),
                "submissions": submissions,
            },
            "functional": {
                "impact": vep_impact,
                "consequences": consequences,
                "sift":             self._get_first(dbnsfp.get("sift_pred")),
                "sift_score":       self._get_first(dbnsfp.get("sift_score")),
                "polyphen":         self._get_first(dbnsfp.get("polyphen2_hdiv_pred")),
                "polyphen_score":   self._get_first(dbnsfp.get("polyphen2_hdiv_score")),
                "revel":            self._get_first(dbnsfp.get("revel_score")),
                "cadd":             self._get_first(dbnsfp.get("cadd", {}).get("phred") if isinstance(dbnsfp.get("cadd"), dict) else dbnsfp.get("cadd_phred")),
                "lrt":              self._get_first(dbnsfp.get("lrt_pred")),
                "mutationtaster":   self._get_first(dbnsfp.get("mutationtaster_pred")),
                "fathmm":           self._get_first(dbnsfp.get("fathmm_pred")),
                "provean":          self._get_first(dbnsfp.get("provean_pred")),
            },
            "population": {
                "global":           pop("af"),
                "african":          pop("af_afr"),
                "east_asian":       pop("af_eas"),
                "south_asian":      pop("af_sas"),
                "european_nfe":     pop("af_nfe"),
                "european_fin":     pop("af_fin"),
                "latino":           pop("af_amr"),
                "ashkenazi":        pop("af_asj"),
            },
        }

    def _categorize(self, parsed: Dict, prioritized: Dict):
        sig = parsed.get("clinical_sig", "").lower()
        impact = parsed.get("impact", "LOW")
        sift = str(parsed.get("sift", "")).lower()
        polyphen = str(parsed.get("polyphen", "")).lower()

        if ("pathogenic" in sig and "benign" not in sig) or impact == "HIGH":
            prioritized["dangerous"].append(parsed)
        elif "benign" in sig:
            prioritized["benign"].append(parsed)
        elif "uncertain" in sig or "vus" in sig:
            prioritized["vus"].append(parsed)
        elif ("deleterious" in sift or "damaging" in polyphen
              or impact == "MODERATE" or "conflicting" in sig):
            prioritized["possibly_harmful"].append(parsed)
        elif sig in ("not annotated", ""):
            prioritized["unannotated"].append(parsed)
        else:
            prioritized["vus"].append(parsed)

    def _extract_af(self, mv_res: Dict) -> Optional[float]:
        try:
            for src in ["gnomad_genome", "gnomad_exome"]:
                g = mv_res.get(src, {})
                af_data = g.get("af", {})
                if isinstance(af_data, dict):
                    v = af_data.get("af")
                    if v is not None:
                        return v
                elif isinstance(af_data, (int, float)):
                    return af_data
        except Exception:
            pass
        return None

    def _analyze_gene_clusters(self, prioritized: Dict) -> List[Dict]:
        gene_counts: Dict = {}
        for category in ["dangerous", "possibly_harmful", "vus", "benign", "unannotated"]:
            for v in prioritized.get(category, []):
                gene = v.get("gene", "Unknown")
                if gene and gene not in ("Unknown", "N/A"):
                    gene_counts.setdefault(gene, {"count": 0, "categories": set(), "variants": []})
                    gene_counts[gene]["count"] += 1
                    gene_counts[gene]["categories"].add(category)
                    gene_counts[gene]["variants"].append(v.get("variant", ""))
        clusters = []
        for gene, info in gene_counts.items():
            if info["count"] >= 3:
                clusters.append({
                    "gene": gene,
                    "variant_count": info["count"],
                    "categories": list(info["categories"]),
                    "variant_ids": info["variants"],
                    "note": f"{gene} has {info['count']} variants across categories — worth investigating even if individually benign."
                })
        clusters.sort(key=lambda x: x["variant_count"], reverse=True)
        return clusters
