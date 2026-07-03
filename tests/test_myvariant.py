import requests
import json

def fetch_myvariant(variant_id):
    if variant_id.startswith("rs"):
        url = f"https://myvariant.info/v1/query?q={variant_id}&fields=all"
    else:
        url = f"https://myvariant.info/v1/variant/{variant_id}?assembly=hg38"
    response = requests.get(url)
    return response.json()

def main():
    rsid_data = fetch_myvariant("rs113993960")
    hgvs_data = fetch_myvariant("chr7:g.117559590ATCT>A") # Genomic coordinate for rs113993960
    
    with open("myvariant_test_rsid.json", "w") as f:
        json.dump(rsid_data, f, indent=2)
        
    with open("myvariant_test_hgvs.json", "w") as f:
        json.dump(hgvs_data, f, indent=2)

if __name__ == "__main__":
    main()
