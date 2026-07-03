import sys
sys.path.append('.')
import unittest
from analysis.vcf_parser import VCFParser
from analysis.vcf_prioritizer import VCFPrioritizer

class TestVCFPrioritization(unittest.TestCase):
    def setUp(self):
        # A simple VCF mock data
        self.mock_vcf_content = b"""##fileformat=VCFv4.2
##INFO=<ID=AF,Number=A,Type=Float,Description="Allele Frequency">
##INFO=<ID=CLNSIG,Number=.,Type=String,Description="ClinVar Significance">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
1\t1000\trs1801133\tC\tT\t100\tPASS\tAF=0.005;CLNSIG=Pathogenic
1\t2000\trs80359876\tA\tG\t100\tPASS\tAF=0.0001;CLNSIG=Likely_pathogenic
1\t3000\trs3520\tG\tA\t100\tPASS\tAF=0.5;CLNSIG=Benign
1\t4000\trs111\tC\tG\t100\tPASS\tAF=0.001;CLNSIG=Uncertain_significance
"""
        self.parser = VCFParser()
        self.variants = self.parser.parse(self.mock_vcf_content, "mock.vcf")

    def test_parser_extraction(self):
        self.assertEqual(len(self.variants), 4)
        self.assertEqual(self.variants[0]["clnsig"], "Pathogenic")
        self.assertEqual(self.variants[0]["af"], 0.005)
        self.assertEqual(self.variants[2]["clnsig"], "Benign")
        self.assertEqual(self.variants[2]["af"], 0.5)

    def test_prioritization_categories(self):
        prioritizer = VCFPrioritizer(frequency_threshold=0.01)
        prioritized = prioritizer.prioritize_variants(self.variants)
        
        # rs3520 has AF=0.5 (>0.01) -> benign tab
        self.assertTrue(any(v["variant"] == "rs3520" for v in prioritized["benign"]))
        
        # rs1801133 has Pathogenic & low AF -> dangerous tab
        self.assertTrue(any(v["variant"] == "rs1801133" for v in prioritized["dangerous"]))
        
        # rs80359876 has Likely_pathogenic & low AF -> dangerous tab
        self.assertTrue(any(v["variant"] == "rs80359876" for v in prioritized["dangerous"]))
        
        # rs111 has Uncertain_significance & low AF -> vus tab
        self.assertTrue(any(v["variant"] == "rs111" for v in prioritized["vus"]))

if __name__ == "__main__":
    unittest.main()
