import json
import sys
sys.path.append('.')
from analysis.vcf_parser import VCFParser
from analysis.variant_analyser import VariantDataFetcher, VariantAnalyzer

def test_vcf_live():
    print("Testing real VCF file parsing and live API query...")
    
    # 1. Parse sample_variants.vcf
    parser = VCFParser()
    with open("sample_variants.vcf", "rb") as f:
        file_bytes = f.read()
    
    variants = parser.parse(file_bytes, "sample_variants.vcf")
    print(f"Successfully parsed {len(variants)} variants from sample_variants.vcf.")
    
    # 2. Take a coordinate-based or rsID variant from parsed list
    test_var = variants[4] # rs80359507 (BRCA2 variant in the VCF)
    print(f"\nSelecting representative variant for live querying:")
    print(f"ID: {test_var['id']}, CHROM: {test_var['chrom']}, POS: {test_var['pos']}, Query ID: {test_var['query_id']}")
    
    # 3. Query external API dynamically using VariantDataFetcher
    fetcher = VariantDataFetcher()
    print("\nQuerying ClinVar, MyVariant, and VEP live...")
    variant_data = fetcher.fetch_variant_data(test_var['query_id'], 'rsid')
    
    # Verify result
    clinvar = variant_data.get("clinvar_data", {})
    print("\n--- Live ClinVar Response ---")
    print(f"UID: {clinvar.get('uid')}")
    print(f"Title: {clinvar.get('title')}")
    print(f"Pathogenicity: {clinvar.get('clinical_significance')}")
    print(f"Associated Conditions: {clinvar.get('conditions')}")
    print(f"Gene Symbol: {clinvar.get('gene_symbol')}")
    
    # 4. Run VariantAnalyzer to verify interpretation output
    analyzer = VariantAnalyzer()
    print("\nRunning VariantAnalyzer interpretation...")
    analysis = analyzer.analyze_variant(variant_data)
    print(f"Pathogenicity Classification: {analysis['pathogenicity_prediction']['classification']}")
    print(f"Functional Impact (Protein Effect): {analysis['functional_impact']['protein_effect']}")

if __name__ == "__main__":
    test_vcf_live()
