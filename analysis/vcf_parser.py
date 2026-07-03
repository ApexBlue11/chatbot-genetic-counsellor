from typing import Any, Dict, List, Optional
import pandas as pd
import gzip

class VCFParser:
    def __init__(self):
        self.variants: List[Dict[str, Any]] = []
        self.samples: List[str] = []

    def parse(self, file_bytes: bytes, filename: str):
        text = self._decode(file_bytes, filename)
        header, records = self._separate_lines(text)
        self.samples = header[9:] if len(header) > 9 else []
        self.variants = [self._parse_record(line, header) for line in records]
        return self.variants

    def _decode(self, file_bytes: bytes, filename: str) -> str:
        return (
            gzip.decompress(file_bytes).decode("utf-8")
            if filename.endswith(".gz")
            else file_bytes.decode("utf-8")
        )

    def _separate_lines(self, text: str):
        columns = []
        records = []
        for line in text.splitlines():
            if line.startswith("##"):
                continue
            if line.startswith("#CHROM"):
                columns = line[1:].split("\t")
            elif line.strip():
                records.append(line)
        if not columns:
            raise ValueError("Invalid VCF: missing column header")
        return columns, records

    def _parse_record(self, line: str, header: List[str]):
        fields = line.split("\t")
        data = dict(zip(header, fields))
        info = self._parse_info(data.get("INFO", ""))

        # Extract ClinVar significance and allele frequency from VCF INFO field
        clnsig = info.get("CLNSIG", None)
        af_val = info.get("AF", info.get("GMAF", info.get("ExAC_AF", None)))

        try:
            af = float(af_val) if af_val is not None else None
        except (ValueError, TypeError):
            af = None

        qual_raw = data.get("QUAL", ".")
        try:
            qual = None if qual_raw in (".", "", None) else float(qual_raw)
        except (ValueError, TypeError):
            qual = None

        # Normalise chromosome: strip 'chr' prefix for consistency
        chrom_raw = data.get("CHROM", "")
        chrom = chrom_raw[3:] if chrom_raw.lower().startswith("chr") else chrom_raw

        try:
            pos = int(data.get("POS", 0))
        except (ValueError, TypeError):
            pos = 0

        rec_id = data.get("ID", ".")
        rec_id = None if rec_id == "." else rec_id

        query_id = self._choose_query_id_safe(rec_id, chrom, pos,
                                              data.get("REF", ""), data.get("ALT", ""))
        return {
            "chrom": chrom,
            "pos": pos,
            "id": rec_id,
            "ref": data.get("REF", ""),
            "alt": data.get("ALT", ""),
            "qual": qual,
            "filter": data.get("FILTER", "."),
            "info": info,
            "clnsig": clnsig,
            "af": af,
            "query_id": query_id,
            "variant_id": query_id,   # alias used by read_patient_vcf tool
        }

    def _parse_info(self, info_field: str):
        if info_field == ".":
            return {}
        info = {}
        for part in info_field.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                info[k] = v
            else:
                info[part] = True
        return info

    def _choose_query_id_safe(self, rec_id, chrom, pos, ref, alt) -> str:
        if rec_id and rec_id.lower().startswith("rs"):
            return rec_id
        return f"chr{chrom}:g.{pos}{ref}>{alt}"

    # Legacy alias kept for compatibility
    def _choose_query_id(self, record: Dict[str, Any], info: Dict[str, Any]):
        record_id = record.get("ID")
        if record_id and record_id.startswith("rs"):
            return record_id
        chrom = record.get('CHROM', '')
        if chrom.lower().startswith('chr'):
            chrom = chrom[3:]
        return f"chr{chrom}:g.{record.get('POS','0')}{record.get('REF','')}>{record.get('ALT','')}"

    def to_dataframe(self, variants: Optional[List[Dict[str, Any]]] = None):
        variants = variants or self.variants
        if not variants:
            return pd.DataFrame()
        rows = []
        for var in variants:
            rows.append(
                {
                    "Chromosome": var["chrom"],
                    "Position": var["pos"],
                    "ID": var["id"] or "N/A",
                    "Reference": var["ref"],
                    "Alternate": var["alt"],
                    "Quality": var["qual"] if var["qual"] is not None else None,
                    "Filter": var["filter"],
                    "Gene": var["info"].get("GENE") or var["info"].get("GENEINFO", "").split(":")[0] if var["info"].get("GENEINFO") else var["info"].get("GENE", "N/A"),
                    "ClinVar Sig": var["clnsig"] or "N/A",
                    "Allele Freq": f"{var['af']:.5f}" if var["af"] is not None else "N/A",
                    "Query ID": var["query_id"],
                }
            )
        return pd.DataFrame(rows)

