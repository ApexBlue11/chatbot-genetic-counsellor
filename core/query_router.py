import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class QueryClassification:
    is_genomic: bool
    query_type: str
    extracted_identifier: Optional[str]

class GenomicQueryRouter:
    # A gene symbol in parentheses — NM_000492.4(CFTR):c.1521_1523delCTT — is how
    # ClinVar itself displays a variant, so counselors paste that form constantly.
    # It is stripped rather than matched, because the downstream APIs want the
    # bare accession. Without this the string matched nothing, the identifier
    # resolved to None, and ClinGen/MyVariant/VEP were all silently queried with
    # None while the model filled the gap from memory.
    GENE_IN_PARENS = re.compile(r"\((?:[A-Za-z0-9\-]{1,15})\)(?=\s*:)")

    HGVS_PATTERNS = {
        "transcript": [
            r"\b(NM_\d+(?:\.\d+)?):c\.[A-Za-z0-9\-+*>_]+",
            r"\b(ENST\d+(?:\.\d+)?):c\.[A-Za-z0-9\-+*>_]+",
        ],
        "genomic": [
            r"\b(NC_\d+(?:\.\d+)?):g\.[A-Za-z0-9\-+*>_]+",
            r"\b(chr(?:\d+|X|Y|MT?)):g\.\d+[A-Za-z]+>[A-Za-z]+",
        ],
        "protein": [
            r"\b(NP_\d+(?:\.\d+)?):p\.[A-Za-z0-9\-+*>_()]+",
            r"\b(ENSP\d+(?:\.\d+)?):p\.[A-Za-z0-9\-+*>_()]+",
        ],
    }
    RSID_PATTERN = r"\b(rs\d+)\b"

    def classify(self, query: str) -> QueryClassification:
        query = self.GENE_IN_PARENS.sub("", query.strip())
        for vtype, patterns in self.HGVS_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, query, re.IGNORECASE)
                if match:
                    return QueryClassification(True, f"hgvs_{vtype}", match.group(0))
        rsid = re.search(self.RSID_PATTERN, query, re.IGNORECASE)
        if rsid:
            return QueryClassification(True, "rsid", rsid.group(1))
        
        # Match potential gene symbols (2-10 alphanumeric characters, excluding rsIDs)
        if re.match(r"^[A-Za-z0-9]{2,10}$", query) and not query.lower().startswith("rs"):
            return QueryClassification(True, "gene_symbol", query.upper())
            
        return QueryClassification(False, "general", None)