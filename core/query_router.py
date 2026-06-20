import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class QueryClassification:
    is_genomic: bool
    query_type: str
    extracted_identifier: Optional[str]

class GenomicQueryRouter:
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
        query = query.strip()
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