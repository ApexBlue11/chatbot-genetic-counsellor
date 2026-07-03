from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from .api_clients import query_clinvar # Import query_clinvar

@dataclass
class DiseaseMatch:
    disease_name: str
    sources: List[str]
    clinical_significance: str
    inheritance_pattern: str | None
    summary: str
    confidence: str

CLIN_SIG_PRIORITY = {
    "Pathogenic": 3,
    "Likely pathogenic": 2,
    "Conflicting interpretations": 1,
    "Uncertain significance": 0,
    "Benign": -1,
    "Likely benign": -1,
}

def correlate_diseases(myvariant_data: Dict[str, Any], vep_data: List[Dict[str, Any]], clingen_data: Dict[str, Any]) -> List[DiseaseMatch]:
    matches = []
    clinvar = myvariant_data.get("clinvar", {})

    gene_symbol = None
    # Try to get gene symbol from VEP data
    if isinstance(vep_data, list) and len(vep_data) > 0 and isinstance(vep_data[0], dict) and 'error' not in vep_data[0]:
        transcript_consequences = vep_data[0].get('transcript_consequences', [])
        if transcript_consequences:
            for transcript in transcript_consequences:
                if transcript.get('gene_symbol'):
                    gene_symbol = transcript['gene_symbol']
                    break
    
    # Fallback to ClinGen data for gene symbol
    if not gene_symbol and clingen_data and clingen_data.get("gene"):
        gene_symbol = clingen_data["gene"].get("symbol")

    if clinvar.get("rcv"):
        rcvs = clinvar["rcv"]
        if not isinstance(rcvs, list):
            rcvs = [rcvs]
            
        for record in rcvs:
            if not isinstance(record, dict):
                continue
            cond = record.get("conditions", {})
            name = cond.get("name") if isinstance(cond, dict) else None
            significance = record.get("clinical_significance", "Not provided")
            score = CLIN_SIG_PRIORITY.get(significance, 0)

            matches.append(
                DiseaseMatch(
                    disease_name=name or "Condition not specified",
                    sources=[f"ClinVar RCV {record.get('accession', 'N/A')}"],
                    clinical_significance=significance,
                    inheritance_pattern=record.get("inheritance"),
                    summary=record.get("condition_summary", "See ClinVar record."),
                    confidence="High" if score >= 2 else "Moderate" if score == 1 else "Low",
                )
            )

    # If no ClinVar RCV data from MyVariant, try querying ClinVar directly with gene symbol
    if not clinvar.get("rcv") and gene_symbol:
        try:
            clinvar_gene_data = query_clinvar(gene_symbol=gene_symbol)
            if clinvar_gene_data and clinvar_gene_data.get("esearchresult", {}).get("idlist"):
                # For now, just indicate that a gene-based search was performed
                # Further parsing of E-utilities results would be needed for detailed matches
                matches.append(
                    DiseaseMatch(
                        disease_name=f"Diseases associated with {gene_symbol}",
                        sources=["ClinVar (gene-based search)"],
                        clinical_significance="Inferred",
                        inheritance_pattern=None,
                        summary=f"Potential disease associations found for gene {gene_symbol} in ClinVar. Further investigation needed.",
                        confidence="Low (gene-based)",
                    )
                )
        except Exception as e:
            print(f"Error querying ClinVar with gene symbol {gene_symbol}: {e}")

    # Fallback to OMIM IDs if present
    omim = clinvar.get("omim", {})
    if isinstance(omim, dict) and omim.get("phenotype_ids"):
        for pid in omim["phenotype_ids"]:
            matches.append(
                DiseaseMatch(
                    disease_name=f"OMIM phenotype {pid}",
                    sources=["OMIM link via ClinVar"],
                    clinical_significance="Not specified",
                    inheritance_pattern=None,
                    summary="Consult OMIM entry for inheritance and phenotype details.",
                    confidence="Context needed",
                )
            )

    # Optional: Add dbNSFP disease annotations
    dbnsfp = myvariant_data.get("dbnsfp", {})
    if isinstance(dbnsfp, dict) and dbnsfp.get("disease_name"):
        disease = dbnsfp["disease_name"]
        matches.append(
            DiseaseMatch(
                disease_name=disease if isinstance(disease, str) else disease[0],
                sources=["dbNSFP annotation"],
                clinical_significance="Computational association",
                inheritance_pattern=None,
                summary="dbNSFP provides literature or computationally associated phenotype.",
                confidence="Exploratory",
            )
        )

    return matches