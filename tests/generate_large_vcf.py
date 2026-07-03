import random

def generate_large_vcf(filename="demo_500_variants.vcf", num_variants=500):
    header = """##fileformat=VCFv4.2
##fileDate=20260629
##source=GeneticCounsellingWorkbench
##reference=GRCh38
##contig=<ID=chr1,length=248956422>
##contig=<ID=chr7,length=159345973>
##contig=<ID=chr11,length=135086622>
##contig=<ID=chr17,length=83257441>
##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL|Gene">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
"""
    
    known_variants = [
        ("chr7", 117559590, "rs113993960", "ATCT", "A", "CSQ=A|inframe_deletion|MODERATE|CFTR|ENSG00000001626"),
        ("chr17", 43094895, "rs28934578", "G", "A", "CSQ=A|missense_variant|MODERATE|BRCA1|ENSG00000012048"),
        ("chr11", 5248232, "rs334", "T", "A", "CSQ=A|missense_variant|HIGH|HBB|ENSG00000000001"),
        ("chr7", 117559590, "rs121909001", "G", "A", "CSQ=A|missense_variant|MODERATE|CFTR|ENSG00000001626"),
    ]
    
    chromosomes = [f"chr{i}" for i in range(1, 23)] + ["chrX", "chrY"]
    genes = ["TP53", "EGFR", "KRAS", "MYC", "APOE", "MTHFR", "PAH", "LDLR", "HTT", "DMD"]
    impacts = ["HIGH", "MODERATE", "LOW", "MODIFIER"]
    consequences = ["missense_variant", "synonymous_variant", "frameshift_variant", "stop_gained", "intron_variant"]
    bases = ["A", "C", "G", "T"]
    
    rows = []
    # Add known key variants first
    for chrom, pos, vid, ref, alt, info in known_variants:
        rows.append(f"{chrom}\t{pos}\t{vid}\t{ref}\t{alt}\t100\tPASS\t{info}")
        
    # Fill remaining variants up to num_variants
    for i in range(len(known_variants), num_variants):
        chrom = random.choice(chromosomes)
        pos = random.randint(100000, 100000000)
        vid = f"rs{random.randint(1000000, 999999999)}" if i % 2 == 0 else "."
        ref = random.choice(bases)
        alt = random.choice([b for b in bases if b != ref])
        
        if i % 3 == 0:
            # Unannotated entry
            info = "."
        else:
            gene = random.choice(genes)
            impact = random.choice(impacts)
            cons = random.choice(consequences)
            info = f"CSQ={alt}|{cons}|{impact}|{gene}|ENSG{random.randint(10000, 99999)}"
            
        rows.append(f"{chrom}\t{pos}\t{vid}\t{ref}\t{alt}\t100\tPASS\t{info}")
        
    with open(filename, "w") as f:
        f.write(header + "\n".join(rows) + "\n")
        
    print(f"Successfully generated {filename} with {len(rows)} variants.")

if __name__ == "__main__":
    generate_large_vcf()
