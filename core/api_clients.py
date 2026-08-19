import requests
import time
from typing import Dict, Any, List, Optional
from urllib.parse import quote

CLINGEN_BASE = "https://reg.clinicalgenome.org/allele"
MYVARIANT_BASE = "https://myvariant.info/v1"
VEP_BASE = "https://rest.ensembl.org/vep/human/hgvs"
CLINVAR_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Global log collector for debugging and visual logging in the UI/tests
API_LOGS = []

def clear_api_logs():
    """Clear the stored API logs."""
    global API_LOGS
    API_LOGS.clear()

def log_api_step(step_name: str, message: str, raw_payload: Any = None):
    """Log a step in API execution with timestamp and optional raw payload."""
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "step": step_name,
        "message": message,
        "raw_payload": raw_payload
    }
    API_LOGS.append(log_entry)
    print(f"[{log_entry['timestamp']}] [{step_name}] {message}")

# Retried: rate limits, upstream 5xx, and the connection resets and read
# timeouts NCBI and Ensembl produce under load. Not retried: any other 4xx,
# which means the request itself is wrong and will fail identically next time.
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _is_transient(exc: Exception) -> bool:
    """Whether a failure is worth trying again.

    The old policy retried on 429 alone, so a dropped connection or a 503 from
    NCBI failed the whole lookup on the first attempt — the variant would come
    back as an error and, a moment later, succeed on a manual retry. Those are
    exactly the failures a retry is for.
    """
    if isinstance(exc, (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout,
                        requests.exceptions.ChunkedEncodingError)):
        return True
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        return status in _RETRY_STATUS
    return "429" in str(exc)


def retry_with_backoff(func, max_retries=3, initial_delay=1):
    """Retry a network call with exponential backoff while the failure looks transient."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_exc = e
            if attempt >= max_retries - 1 or not _is_transient(e):
                raise
            delay = initial_delay * (2 ** attempt)
            log_api_step(
                "RETRY",
                f"Transient failure ({type(e).__name__}: {str(e)[:120]}). "
                f"Retrying in {delay}s... (Attempt {attempt+1}/{max_retries})"
            )
            time.sleep(delay)
    raise last_exc if last_exc else Exception("Max retries exceeded")

def query_clingen(hgvs: str) -> Dict[str, Any]:
    """Query ClinGen Allele Registry API for variant information."""
    log_api_step("CLINGEN_QUERY", f"Querying ClinGen Allele Registry for: '{hgvs}'")
    try:
        encoded_hgvs = quote(hgvs, safe=':.')
        url = f"{CLINGEN_BASE}/{encoded_hgvs}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        log_api_step("CLINGEN_HTTP_REQUEST", f"GET Request to: {url}")
        resp = requests.get(url, headers=headers, timeout=30)
        
        log_api_step("CLINGEN_HTTP_RESPONSE", f"HTTP Status: {resp.status_code}")
        resp.raise_for_status()
        
        data = resp.json()
        log_api_step("CLINGEN_PARSE", "Successfully parsed ClinGen response JSON", data)
        return data
        
    except requests.exceptions.HTTPError as e:
        err_msg = f"ClinGen API HTTP error: {e.response.status_code}"
        if e.response.status_code == 404:
            err_msg = f"Variant '{hgvs}' not found in ClinGen Allele Registry (404)"
        log_api_step("CLINGEN_ERROR", err_msg, getattr(e.response, 'text', str(e)))
        return {"error": err_msg}
    except Exception as e:
        err_msg = f"Error querying ClinGen: {str(e)}"
        log_api_step("CLINGEN_ERROR", err_msg)
        return {"error": err_msg}

def query_myvariant(identifier: str) -> Dict[str, Any]:
    """Query MyVariant.info API with retry logic for rate limiting."""
    log_api_step("MYVARIANT_QUERY", f"Querying MyVariant.info for: '{identifier}'")
    
    def _query():
        if identifier.startswith('rs') or not identifier.startswith('chr'):
            url = f"{MYVARIANT_BASE}/query"
            params = {"q": identifier, "fields": "all"}
        else:
            url = f"{MYVARIANT_BASE}/variant/{identifier}"
            params = {"assembly": "hg38"}
            
        log_api_step("MYVARIANT_HTTP_REQUEST", f"GET Request to: {url} with params {params}")
        
        resp = requests.get(url, params=params, timeout=30)
        log_api_step("MYVARIANT_HTTP_RESPONSE", f"HTTP Status: {resp.status_code}")
        
        # If variant endpoint gave 404, fallback to query endpoint
        if resp.status_code == 404 and "/variant/" in url:
            fallback_url = f"{MYVARIANT_BASE}/query"
            fallback_params = {"q": identifier, "fields": "all"}
            log_api_step("MYVARIANT_HTTP_REQUEST", f"Fallback GET Request to: {fallback_url} with params {fallback_params}")
            resp = requests.get(fallback_url, params=fallback_params, timeout=30)
            log_api_step("MYVARIANT_HTTP_RESPONSE", f"Fallback HTTP Status: {resp.status_code}")
            
        resp.raise_for_status()
        data = resp.json()
        
        # If it was a query, it returns { "hits": [...] }
        if isinstance(data, dict) and "hits" in data:
            data = data["hits"]
            
        if isinstance(data, list):
            if not data:
                return {}  # No hits — return empty dict (not list)
            best_record = data[0]
            best_score = -1
            for r in data:
                if not isinstance(r, dict): continue
                score = 0
                if 'clinvar' in r: score += 10
                if 'gnomad_genome' in r or 'gnomad_exome' in r: score += 5
                if 'dbnsfp' in r: score += 3
                if 'uniprot' in r: score += 2
                score += len(r.keys()) * 0.1
                if score > best_score:
                    best_score = score
                    best_record = r
            data = best_record if isinstance(best_record, dict) else {}
        # Ensure we always return a dict
        if not isinstance(data, dict):
            return {}
        return data
    
    try:
        data = retry_with_backoff(_query, max_retries=3, initial_delay=2)
        log_api_step("MYVARIANT_PARSE", "Successfully parsed MyVariant.info response", data)
        return data
    except Exception as e:
        err_msg = f"Error querying MyVariant: {str(e)}"
        log_api_step("MYVARIANT_ERROR", err_msg)
        return {"error": err_msg}

def query_vep(hgvs: str) -> Dict[str, Any]:
    """Query Ensembl VEP API for variant effect prediction."""
    log_api_step("VEP_QUERY", f"Querying Ensembl VEP for: '{hgvs}'")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        import re
        # If HGVS transcript has a version number (e.g. NM_000492.3:c...), strip version for VEP compatibility
        clean_hgvs = re.sub(r'(N[MCGP]_\d+)\.\d+:', r'\1:', hgvs)
        
        if clean_hgvs.startswith('rs'):
            url = f"https://rest.ensembl.org/vep/human/id/{quote(clean_hgvs, safe='')}"
        elif clean_hgvs.startswith('NP_'):
            err_msg = "VEP does not support protein-level HGVS notation (NP_...). Use transcript-level HGVS (NM_...) instead."
            log_api_step("VEP_SKIP", err_msg)
            return {"error": err_msg}
        elif len(clean_hgvs.split(':')) == 4:
            # Format is chr:pos:ref:alt for region lookup
            url = f"https://rest.ensembl.org/vep/human/region/{quote(clean_hgvs, safe='')}"
        else:
            url = f"{VEP_BASE}/{quote(clean_hgvs, safe='')}"

        # Ensembl omits these annotations unless they are asked for. Without
        # them every transcript comes back unflagged, so a caller trying to pick
        # "the primary transcript" has nothing to pick on and falls back to
        # whichever one Ensembl happened to list first — for BRCA1 rs80357906
        # that is ENST00000352993, not the ENST00000357654 / NM_007294.4 record
        # ClinVar actually reports against. mane_select ties the two together;
        # hgvs adds the c. and p. notation the counselor reads.
        params = {"canonical": 1, "mane": 1, "hgvs": 1}
        log_api_step("VEP_HTTP_REQUEST", f"GET Request to: {url} with params {params}")

        def _request():
            r = requests.get(url, headers=headers, params=params, timeout=30)
            log_api_step("VEP_HTTP_RESPONSE", f"HTTP Status: {r.status_code}")
            r.raise_for_status()
            return r

        resp = retry_with_backoff(_request, max_retries=3, initial_delay=2)
        data = resp.json()
        log_api_step("VEP_PARSE", "Successfully parsed VEP response", data)
        return data
    except Exception as e:
        err_msg = f"Error querying VEP: {str(e)}"
        log_api_step("VEP_ERROR", err_msg)
        return {"error": err_msg}

def query_clinvar(variation_id: str = None, rsid: str = None, gene_symbol: Optional[str] = None) -> Dict[str, Any]:
    """Query ClinVar via NCBI E-utilities (esearch.fcgi and esummary.fcgi)."""
    log_api_step("CLINVAR_QUERY", f"Querying ClinVar. Params - variation_id: {variation_id}, rsid: {rsid}, gene_symbol: {gene_symbol}")
    
    # Formulate search query
    if variation_id:
        search_term = f"{variation_id}[VariationID]"
    elif rsid:
        search_term = f"{rsid}"
    elif gene_symbol:
        search_term = f"{gene_symbol}[Gene Name]"
    else:
        log_api_step("CLINVAR_SKIP", "No query parameters provided for ClinVar search")
        return {}
    
    search_url = f"{CLINVAR_BASE}/esearch.fcgi"
    search_params = {
        "db": "clinvar",
        "term": search_term,
        "retmode": "json"
    }
    
    try:
        log_api_step("CLINVAR_SEARCH_REQUEST", f"GET Search Request to: {search_url} with term: '{search_term}'")

        def _search():
            r = requests.get(search_url, params=search_params, timeout=15)
            log_api_step("CLINVAR_SEARCH_RESPONSE", f"HTTP Status: {r.status_code}")
            r.raise_for_status()
            return r

        search_resp = retry_with_backoff(_search, max_retries=3, initial_delay=2)
        search_data = search_resp.json()
        log_api_step("CLINVAR_SEARCH_RAW", "Raw esearch response payload", search_data)
        
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            log_api_step("CLINVAR_SEARCH_EMPTY", f"No ClinVar records found for term: '{search_term}'")
            return {"error": "No ClinVar records found"}
        
        # Step 2: Fetch summaries for every candidate, not just the first.
        #
        # ClinVar's free-text search matches an rsID anywhere in a record, so the
        # first hit is frequently a different variant in a different gene. For
        # rs1801133 (MTHFR c.665C>T) esearch returns 128852, 3522, 3521, 3520 —
        # and 128852 is a CPS1 variant carrying rs1047891. Taking id_list[0]
        # meant the app reported CPS1's classification, CPS1's conditions
        # ("Congenital hyperammonemia, type I") and CPS1's protein change for an
        # MTHFR query, then fed all of it to the model as retrieved fact.
        # Below, the record is chosen by matching the dbSNP cross-reference.
        candidate_ids = id_list[:10]
        summary_url = f"{CLINVAR_BASE}/esummary.fcgi"
        summary_params = {
            "db": "clinvar",
            "id": ",".join(candidate_ids),
            "retmode": "json"
        }
        
        log_api_step("CLINVAR_SUMMARY_REQUEST", f"GET Summary Request to: {summary_url} for IDs: {candidate_ids}")

        def _summary():
            r = requests.get(summary_url, params=summary_params, timeout=15)
            log_api_step("CLINVAR_SUMMARY_RESPONSE", f"HTTP Status: {r.status_code}")
            r.raise_for_status()
            return r

        summary_resp = retry_with_backoff(_summary, max_retries=3, initial_delay=2)
        summary_data = summary_resp.json()
        log_api_step("CLINVAR_SUMMARY_RAW", "Raw esummary response payload", summary_data)
        
        result = summary_data.get("result", {})

        def _rsids_of(rec):
            out = set()
            for vset in rec.get("variation_set") or []:
                for xref in vset.get("variation_xrefs") or []:
                    if str(xref.get("db_source", "")).lower() == "dbsnp" and xref.get("db_id"):
                        out.add(f"rs{str(xref['db_id']).lstrip('rs')}")
            return out

        target_id = candidate_ids[0]
        if rsid:
            wanted = f"rs{str(rsid).lower().lstrip('rs')}"
            matched = next(
                (cid for cid in candidate_ids
                 if cid in result and wanted in _rsids_of(result[cid])),
                None,
            )
            if matched:
                target_id = matched
                log_api_step("CLINVAR_RSID_MATCH", f"Selected ClinVar ID {matched} by dbSNP xref {wanted}")
            else:
                # Better to report nothing than to report a different variant's
                # classification as though it belonged to the one asked for.
                log_api_step("CLINVAR_RSID_NO_MATCH",
                             f"No ClinVar record cross-references {wanted}; candidates were {candidate_ids}")
                return {"error": f"No ClinVar record cross-referencing {wanted}"}

        if target_id in result:
            record = result[target_id]
            
            germline = record.get("germline_classification", {})
            clinical_sig = germline.get("description", "Not provided")
            review_status = germline.get("review_status", "Not provided")
            
            conditions = []
            for trait in germline.get("trait_set", []):
                trait_name = trait.get("trait_name")
                if trait_name:
                    conditions.append(trait_name)
            
            extracted_gene = None
            if record.get("genes"):
                extracted_gene = record["genes"][0].get("symbol")
            
            parsed_result = {
                "uid": record.get("uid"),
                "title": record.get("title"),
                "clinical_significance": clinical_sig,
                "review_status": review_status,
                "conditions": conditions,
                "gene_symbol": extracted_gene,
                "protein_change": record.get("protein_change"),
                "molecular_consequence": record.get("molecular_consequence_list", []),
            }
            log_api_step("CLINVAR_PARSE", "Successfully parsed ClinVar summary fields", parsed_result)
            return parsed_result
        
        log_api_step("CLINVAR_PARSE_ERROR", f"Could not find ID {target_id} in summary result")
        return {"error": "Could not parse ClinVar response"}
        
    except Exception as e:
        err_msg = f"Error querying ClinVar: {str(e)}"
        log_api_step("CLINVAR_ERROR", err_msg)
        return {"error": err_msg}

def query_pubmed(query_term: str) -> List[Dict[str, Any]]:
    """Query PubMed via NCBI E-utilities for papers related to a variant/gene."""
    log_api_step("PUBMED_QUERY", f"Searching PubMed for: '{query_term}'")
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "pubmed",
        "term": query_term,
        "retmode": "json",
        "retmax": 5
    }
    try:
        log_api_step("PUBMED_SEARCH_REQUEST", f"GET Search Request to: {search_url} with query '{query_term}'")

        def _search():
            r = requests.get(search_url, params=search_params, timeout=15)
            r.raise_for_status()
            return r

        search_data = retry_with_backoff(_search, max_retries=3, initial_delay=2).json()
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            log_api_step("PUBMED_EMPTY", f"No papers found for term: '{query_term}'")
            return []
            
        results = fetch_pubmed_by_ids(id_list)
        log_api_step("PUBMED_PARSE", f"Successfully parsed {len(results)} PubMed papers", results)
        return results
    except Exception as e:
        log_api_step("PUBMED_ERROR", f"Error querying PubMed: {str(e)}")
        return []


def fetch_pubmed_by_ids(pmids: List[Any]) -> List[Dict[str, Any]]:
    """Resolve PMIDs to citation records.

    dbSNP already curates the papers that describe a variant, and VEP hands them
    back on colocated_variants[].pubmed. Those are far better than anything a
    keyword search reconstructs — searching "DHFR 3 prime UTR variant" returns
    nothing at all — so this exists to turn that ready-made list into citations.
    """
    ids = [str(p).strip() for p in (pmids or []) if str(p).strip().isdigit()]
    if not ids:
        return []

    summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    summary_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
    try:
        log_api_step("PUBMED_SUMMARY_REQUEST", f"GET Summary Request to: {summary_url} for IDs: {ids}")

        def _summary():
            r = requests.get(summary_url, params=summary_params, timeout=15)
            r.raise_for_status()
            return r

        result_dict = retry_with_backoff(_summary, max_retries=3, initial_delay=2).json().get("result", {})
    except Exception as e:
        log_api_step("PUBMED_ERROR", f"Error fetching PubMed summaries: {str(e)}")
        return []

    results = []
    for pmid in ids:
        paper = result_dict.get(pmid)
        if not paper:
            continue
        results.append({
            "pmid": pmid,
            "title": paper.get("title", "No Title"),
            "authors": ", ".join(author.get("name", "") for author in paper.get("authors", [])),
            "journal": paper.get("source", "Unknown Journal"),
            "pubdate": paper.get("pubdate", "Unknown Date"),
            "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        })
    return results



def primary_transcript(vep_data: Any) -> Optional[Dict[str, Any]]:
    """The transcript a clinical report would quote.

    MANE Select first — it is the accession ClinVar reports against — then
    Ensembl canonical, then whatever came back first. VEP only annotates the
    first two when the query asks for them, which query_vep now does.
    """
    records = vep_data if isinstance(vep_data, list) else [vep_data]
    transcripts: List[Dict[str, Any]] = []
    for rec in records:
        if isinstance(rec, dict):
            transcripts.extend(rec.get("transcript_consequences") or [])
    for pick in (lambda t: bool(t.get("mane_select")),
                 lambda t: "MANE_SELECT" in (t.get("flags") or []),
                 lambda t: t.get("canonical") == 1,
                 lambda t: True):
        for t in transcripts:
            if isinstance(t, dict) and pick(t):
                return t
    return None


def resolve_gene_symbol(clinvar_data: Any, myvariant_data: Any, vep_data: Any) -> str:
    """Gene symbol from whichever source actually knows it.

    Ordered by how specific the source is to this variant: ClinVar's curated
    record, then MyVariant's annotations, then VEP's transcript consequences —
    the only one that answers for variants no clinical database has catalogued.
    """
    if isinstance(clinvar_data, dict) and clinvar_data.get("gene_symbol"):
        return clinvar_data["gene_symbol"]

    if isinstance(myvariant_data, dict):
        genename = (myvariant_data.get("dbnsfp") or {}).get("genename")
        snpeff_ann = (myvariant_data.get("snpeff") or {}).get("ann")
        if isinstance(snpeff_ann, list):
            snpeff_ann = snpeff_ann[0] if snpeff_ann else None
        for candidate in [
            ((myvariant_data.get("clinvar") or {}).get("gene") or {}).get("symbol"),
            genename[0] if isinstance(genename, list) and genename else genename,
            (snpeff_ann or {}).get("genename") if isinstance(snpeff_ann, dict) else None,
        ]:
            if candidate:
                return candidate

    transcript = primary_transcript(vep_data)
    if transcript and transcript.get("gene_symbol"):
        return transcript["gene_symbol"]

    return "Unknown"

def pubmed_ids_from_vep(vep_data: Any) -> List[str]:
    """PMIDs dbSNP has linked to this exact variant, via VEP's colocated list."""
    records = vep_data if isinstance(vep_data, list) else [vep_data]
    out: List[str] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for colocated in rec.get("colocated_variants") or []:
            for pmid in colocated.get("pubmed") or []:
                pid = str(pmid).strip()
                if pid.isdigit() and pid not in out:
                    out.append(pid)
    return out

def query_myvariant_batch(ids: List[str]) -> List[Dict[str, Any]]:
    """Query MyVariant.info in batch via POST with intelligent routing for rsIDs vs HGVS."""
    log_api_step("MYVARIANT_BATCH_QUERY", f"Querying MyVariant.info in batch for {len(ids)} variants")
    if not ids:
        return []
        
    rsids = [i for i in ids if i.startswith("rs")]
    hgvs_ids = [i for i in ids if not i.startswith("rs")]
    
    merged_results = []
    
    # Process HGVS IDs using /v1/variant
    if hgvs_ids:
        try:
            url = "https://myvariant.info/v1/variant"
            data = {"ids": ",".join(hgvs_ids), "assembly": "hg38"}
            resp = requests.post(url, data=data, timeout=30)
            resp.raise_for_status()
            res_list = resp.json()
            merged_results.extend(res_list)
            log_api_step("MYVARIANT_BATCH_HGVS", f"Retrieved {len(res_list)} records for HGVS variants")
        except Exception as e:
            log_api_step("MYVARIANT_BATCH_ERROR", f"Error in MyVariant batch query (HGVS): {str(e)}")

    # Process rsIDs using /v1/query
    if rsids:
        try:
            url = "https://myvariant.info/v1/query"
            data = {"q": ",".join(rsids), "scopes": "dbsnp.rsid,clinvar.rsid", "fields": "all"}
            resp = requests.post(url, data=data, timeout=30)
            resp.raise_for_status()
            res_list = resp.json()
            
            # The query endpoint returns slightly different structure: [{"query": "rs123", "hits": [...]}, ...]
            # Or just hit list depending on if we query by comma separated.
            # Post to /v1/query returns a list of dicts with 'query' and either '_id' (if match) or 'notfound'.
            for res in res_list:
                # If there are multiple hits, take the best one, similar to single query logic
                if "hits" in res and res["hits"]:
                    hits = res["hits"]
                    best_record = hits[0]
                    best_score = -1
                    for r in hits:
                        if not isinstance(r, dict): continue
                        score = 0
                        if 'clinvar' in r: score += 10
                        if 'gnomad_genome' in r or 'gnomad_exome' in r: score += 5
                        if 'dbnsfp' in r: score += 3
                        if 'uniprot' in r: score += 2
                        score += len(r.keys()) * 0.1
                        if score > best_score:
                            best_score = score
                            best_record = r
                    # Give it the original query ID so prioritizer can match it
                    best_record['query'] = res.get('query')
                    merged_results.append(best_record)
                elif "_id" in res:
                    # Direct match
                    merged_results.append(res)
                elif "notfound" in res:
                    merged_results.append(res)
                    
            log_api_step("MYVARIANT_BATCH_RSID", f"Processed {len(rsids)} rsID queries")
        except Exception as e:
            log_api_step("MYVARIANT_BATCH_ERROR", f"Error in MyVariant batch query (rsID): {str(e)}")

    log_api_step("MYVARIANT_BATCH_PARSE", f"Returning {len(merged_results)} total records from MyVariant batch")
    return merged_results

def query_vep_batch(ids: List[str]) -> List[Dict[str, Any]]:
    """Query Ensembl VEP in batch via POST (by rsID)."""
    log_api_step("VEP_BATCH_QUERY", f"Querying Ensembl VEP in batch for {len(ids)} variants")
    if not ids:
        return []
        
    # Filter valid rsIDs or genomic coordinates (exclude '.' or empty)
    valid_ids = [i for i in ids if isinstance(i, str) and (i.startswith("rs") or ":" in i)]
    if not valid_ids:
        return []
        
    all_results = []
    chunk_size = 200
    for i in range(0, len(valid_ids), chunk_size):
        chunk = valid_ids[i:i + chunk_size]
        try:
            url = "https://rest.ensembl.org/vep/human/id"
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            payload = {"ids": chunk}
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            res_list = resp.json()
            if isinstance(res_list, list):
                all_results.extend(res_list)
        except Exception as e:
            log_api_step("VEP_BATCH_ERROR", f"Error in VEP batch chunk query: {str(e)}")
            
    log_api_step("VEP_BATCH_PARSE", f"Retrieved {len(all_results)} records from VEP batch")
    return all_results

def query_clinvar_batch(rsids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Query ClinVar via NCBI E-utilities in batch for a list of rsids."""
    log_api_step("CLINVAR_BATCH_QUERY", f"Querying ClinVar in batch for rsids: {rsids}")
    if not rsids:
        return {}
    
    import re
    clean_rsids = [r.replace('rs', '') for r in rsids]
    term = " OR ".join(f"{r}[rs]" for r in clean_rsids)
    search_url = f"{CLINVAR_BASE}/esearch.fcgi"
    search_params = {
        "db": "clinvar",
        "term": term,
        "retmode": "json",
        "retmax": len(rsids) * 3
    }
    
    try:
        resp = requests.get(search_url, params=search_params, timeout=20)
        resp.raise_for_status()
        search_data = resp.json()
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            log_api_step("CLINVAR_BATCH_EMPTY", "No ClinVar IDs found for these rsids")
            return {}
            
        summary_url = f"{CLINVAR_BASE}/esummary.fcgi"
        summary_params = {
            "db": "clinvar",
            "id": ",".join(id_list),
            "retmode": "json"
        }
        resp2 = requests.get(summary_url, params=summary_params, timeout=20)
        resp2.raise_for_status()
        summary_data = resp2.json()
        
        result_dict = summary_data.get("result", {})
        parsed_results = {}
        for uid in id_list:
            if uid in result_dict:
                record = result_dict[uid]
                germline = record.get("germline_classification", {})
                clinical_sig = germline.get("description", "Not provided")
                review_status = germline.get("review_status", "Not provided")
                
                conditions = []
                for trait in germline.get("trait_set", []):
                    trait_name = trait.get("trait_name")
                    if trait_name:
                        conditions.append(trait_name)
                        
                extracted_gene = None
                if record.get("genes"):
                    extracted_gene = record["genes"][0].get("symbol")
                    
                variation_rsid = None
                title = record.get("title", "")
                rs_match = re.search(r'rs\d+', title)
                if rs_match:
                    variation_rsid = rs_match.group(0)
                else:
                    variation_rsid = f"uid_{uid}"
                
                parsed_results[variation_rsid] = {
                    "uid": uid,
                    "title": title,
                    "clinical_significance": clinical_sig,
                    "review_status": review_status,
                    "conditions": conditions,
                    "gene_symbol": extracted_gene,
                    "protein_change": record.get("protein_change"),
                    "molecular_consequence": record.get("molecular_consequence_list", []),
                }
        log_api_step("CLINVAR_BATCH_PARSE", f"Successfully parsed {len(parsed_results)} ClinVar records", parsed_results)
        return parsed_results
    except Exception as e:
        log_api_step("CLINVAR_BATCH_ERROR", f"Error in ClinVar batch query: {str(e)}")
        return {}

