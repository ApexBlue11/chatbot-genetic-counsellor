import sys
sys.path.append('.')
from core.gemini_client import detect_rsid, detect_hgvs, is_genetics_related


def test_variant_detection():
    print("Testing variant detection in natural language...")

    # rsID detection
    assert detect_rsid("What about rs1801133?") == "rs1801133"
    assert detect_rsid("analyze rs80359876 please") == "rs80359876"
    assert detect_rsid("hello how are you?") is None
    assert detect_rsid("Tell me about BRCA2 gene") is None
    print("  rsID detection: PASS")

    # HGVS detection
    assert detect_hgvs("NM_005957.5:c.665C>T is pathogenic") == "NM_005957.5:c.665C>T"
    assert detect_hgvs("What does rs1801133 do?") is None
    print("  HGVS detection: PASS")

    # Genetics scope
    assert is_genetics_related("Tell me about BRCA2 gene") is True
    assert is_genetics_related("What is rs1801133?") is True
    assert is_genetics_related("What is the weather today?") is False
    assert is_genetics_related("pedigree of a family with autosomal recessive condition") is True
    print("  Genetics scope detection: PASS")

    print("All detection tests passed!")


if __name__ == '__main__':
    test_variant_detection()
