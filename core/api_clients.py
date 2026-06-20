import requests
import time
from typing import Dict, Any, List, Optional
from urllib.parse import quote

CLINGEN_BASE = "https://reg.clinicalgenome.org/allele"
MYVARIANT_BASE = "https://myvariant.info/v1/variant"
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

def retry_with_backoff(func, max_retries=3, initial_delay=1):
    """Retry a function with exponential backoff for rate limiting."""
    for attempt in range(max_retries):
        try:
            return func()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Rate limit
                if attempt < max_retries - 1:
                    delay = initial_delay * (2 ** attempt)
                    log_api_step("RATE_LIMIT", f"Rate limit hit (429). Retrying in {delay}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(delay)
                    continue
            raise
        except Exception as e:
            if attempt < max_retries - 1 and "429" in str(e):
                delay = initial_delay * (2 ** attempt)
                log_api_step("RATE_LIMIT", f"Rate limit hit (429-like error). Retrying in {delay}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
                continue
            raise
    raise Exception("Max retries exceeded")

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
        url = f"{MYVARIANT_BASE}/{identifier}"
        params = {"assembly": "hg38"}
        log_api_step("MYVARIANT_HTTP_REQUEST", f"GET Request to: {url} with params {params}")
        
        resp = requests.get(url, params=params, timeout=30)
        log_api_step("MYVARIANT_HTTP_RESPONSE", f"HTTP Status: {resp.status_code}")
        resp.raise_for_status()
        
        data = resp.json()
        if isinstance(data, list) and data:
            data = data[0]
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
        if hgvs.startswith('rs'):
            url = f"https://rest.ensembl.org/vep/human/id/{quote(hgvs, safe='')}"
        elif hgvs.startswith('NP_'):
            err_msg = "VEP does not support protein-level HGVS notation (NP_...). Use transcript-level HGVS (NM_...) instead."
            log_api_step("VEP_SKIP", err_msg)
            return {"error": err_msg}
        else:
            url = f"{VEP_BASE}/{quote(hgvs, safe='')}"

        log_api_step("VEP_HTTP_REQUEST", f"GET Request to: {url}")
        resp = requests.get(url, headers=headers, timeout=30)
        
        log_api_step("VEP_HTTP_RESPONSE", f"HTTP Status: {resp.status_code}")
        resp.raise_for_status()
        
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
    
    if rsid:
        rsid = rsid.replace('rs', '')
    
    # Formulate search query
    if variation_id:
        search_term = f"{variation_id}[VariationID]"
    elif rsid:
        search_term = f"{rsid}[rs]"
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
        search_resp = requests.get(search_url, params=search_params, timeout=15)
        
        log_api_step("CLINVAR_SEARCH_RESPONSE", f"HTTP Status: {search_resp.status_code}")
        search_resp.raise_for_status()
        search_data = search_resp.json()
        log_api_step("CLINVAR_SEARCH_RAW", "Raw esearch response payload", search_data)
        
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            log_api_step("CLINVAR_SEARCH_EMPTY", f"No ClinVar records found for term: '{search_term}'")
            return {"error": "No ClinVar records found"}
        
        # Step 2: Fetch summary for the first ID found
        summary_url = f"{CLINVAR_BASE}/esummary.fcgi"
        summary_params = {
            "db": "clinvar",
            "id": id_list[0],
            "retmode": "json"
        }
        
        log_api_step("CLINVAR_SUMMARY_REQUEST", f"GET Summary Request to: {summary_url} for ID: {id_list[0]}")
        summary_resp = requests.get(summary_url, params=summary_params, timeout=15)
        
        log_api_step("CLINVAR_SUMMARY_RESPONSE", f"HTTP Status: {summary_resp.status_code}")
        summary_resp.raise_for_status()
        summary_data = summary_resp.json()
        log_api_step("CLINVAR_SUMMARY_RAW", "Raw esummary response payload", summary_data)
        
        result = summary_data.get("result", {})
        target_id = id_list[0]
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
