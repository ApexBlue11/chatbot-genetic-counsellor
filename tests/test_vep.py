import requests
import json

def fetch_vep(variant_id):
    url = f"https://rest.ensembl.org/vep/human/id/{variant_id}?content-type=application/json"
    response = requests.get(url)
    return response.json()

def main():
    rsid_data = fetch_vep("rs113993960")
    with open("vep_test_rsid.json", "w") as f:
        json.dump(rsid_data, f, indent=2)

if __name__ == "__main__":
    main()
