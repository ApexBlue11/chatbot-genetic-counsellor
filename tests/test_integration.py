#!/usr/bin/env python3
"""
Test script to verify the integration of VariantAnalyzer and VariantDataFetcher
"""

import sys
sys.path.append('.')
from analysis.variant_analyser import VariantAnalyzer, VariantDataFetcher
from core.query_router import GenomicQueryRouter

def test_variant_analyzer_integration():
    """Test the integration of VariantAnalyzer with existing components"""
    print("Testing VariantAnalyzer integration...")
    
    # Initialize components
    router = GenomicQueryRouter()
    variant_analyzer = VariantAnalyzer()
    variant_data_fetcher = VariantDataFetcher()
    
    # Test with a known variant
    test_variant = "rs80359876"  # BRCA2 variant
    
    # Classify the variant
    classification = router.classify(test_variant)
    print(f"Variant classified as: {classification.query_type}")
    
    # Fetch variant data
    print("Fetching variant data...")
    variant_data = variant_data_fetcher.fetch_variant_data(
        variant_id=classification.extracted_identifier,
        query_type=classification.query_type
    )
    
    # Analyze the variant
    print("Analyzing variant...")
    analysis_results = variant_analyzer.analyze_variant(variant_data)
    
    # Print analysis results
    print("\n=== Analysis Results ===")
    print(f"Pathogenicity: {analysis_results['pathogenicity_prediction']['classification']}")
    print(f"Confidence: {analysis_results['pathogenicity_prediction']['confidence']}")
    print(f"Protein Effect: {analysis_results['functional_impact']['protein_effect']}")
    print(f"Clinical Significance: {analysis_results['clinical_relevance']['clinical_significance']}")
    
    print("\nIntegration test completed successfully!")

if __name__ == "__main__":
    test_variant_analyzer_integration()