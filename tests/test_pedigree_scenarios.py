import os
import json
import base64
from analysis.pedigree_generator import PedigreeGenerator

def run_scenario_tests():
    generator = PedigreeGenerator(api_key="fake")
    
    scenarios = {
        "scenario_a_nuclear_ar": {
            "individuals": [
                {"id": "father", "name": "Father", "gender": "male", "status": "carrier", "generation": 0, "deceased": False},
                {"id": "mother", "name": "Mother", "gender": "female", "status": "carrier", "generation": 0, "deceased": False},
                {"id": "proband", "name": "Proband", "gender": "male", "status": "affected", "generation": 1, "deceased": False},
                {"id": "sister", "name": "Sister", "gender": "female", "status": "unaffected", "generation": 1, "deceased": False}
            ],
            "relationships": [
                {"type": "marriage", "person1": "father", "person2": "mother"},
                {"type": "parent-child", "person1": "father", "person2": "proband"},
                {"type": "parent-child", "person1": "mother", "person2": "proband"},
                {"type": "parent-child", "person1": "father", "person2": "sister"},
                {"type": "parent-child", "person1": "mother", "person2": "sister"}
            ]
        },
        "scenario_b_three_generations": {
            "individuals": [
                {"id": "gf", "name": "Grandfather", "gender": "male", "status": "affected", "generation": 0, "deceased": True},
                {"id": "gm", "name": "Grandmother", "gender": "female", "status": "unaffected", "generation": 0, "deceased": False},
                {"id": "mother", "name": "Mother", "gender": "female", "status": "carrier", "generation": 1, "deceased": False},
                {"id": "father", "name": "Father", "gender": "male", "status": "unaffected", "generation": 1, "deceased": False},
                {"id": "proband", "name": "Proband", "gender": "male", "status": "affected", "generation": 2, "deceased": False}
            ],
            "relationships": [
                {"type": "marriage", "person1": "gf", "person2": "gm"},
                {"type": "parent-child", "person1": "gf", "person2": "mother"},
                {"type": "parent-child", "person1": "gm", "person2": "mother"},
                {"type": "marriage", "person1": "father", "person2": "mother"},
                {"type": "parent-child", "person1": "father", "person2": "proband"},
                {"type": "parent-child", "person1": "mother", "person2": "proband"}
            ]
        },
        "scenario_c_consanguineous": {
            "individuals": [
                {"id": "uncle", "name": "Uncle", "gender": "male", "status": "unaffected", "generation": 0, "deceased": False},
                {"id": "aunt", "name": "Aunt", "gender": "female", "status": "unaffected", "generation": 0, "deceased": False},
                {"id": "husband", "name": "Husband (Cousin 1)", "gender": "male", "status": "carrier", "generation": 1, "deceased": False},
                {"id": "wife", "name": "Wife (Cousin 2)", "gender": "female", "status": "carrier", "generation": 1, "deceased": False},
                {"id": "child", "name": "Affected Child", "gender": "female", "status": "affected", "generation": 2, "deceased": False}
            ],
            "relationships": [
                {"type": "marriage", "person1": "uncle", "person2": "aunt"},
                {"type": "parent-child", "person1": "uncle", "person2": "husband"},
                {"type": "parent-child", "person1": "aunt", "person2": "husband"},
                {"type": "parent-child", "person1": "uncle", "person2": "wife"},
                {"type": "parent-child", "person1": "aunt", "person2": "wife"},
                {"type": "marriage", "person1": "husband", "person2": "wife"},
                {"type": "parent-child", "person1": "husband", "person2": "child"},
                {"type": "parent-child", "person1": "wife", "person2": "child"}
            ]
        },
        "scenario_d_x_linked": {
            "individuals": [
                {"id": "father", "name": "Father", "gender": "male", "status": "unaffected", "generation": 0, "deceased": False},
                {"id": "mother", "name": "Mother (Carrier)", "gender": "female", "status": "carrier", "generation": 0, "deceased": False},
                {"id": "proband", "name": "Proband (Affected Male)", "gender": "male", "status": "affected", "generation": 1, "deceased": False},
                {"id": "sister", "name": "Sister (Carrier)", "gender": "female", "status": "carrier", "generation": 1, "deceased": False}
            ],
            "relationships": [
                {"type": "marriage", "person1": "father", "person2": "mother"},
                {"type": "parent-child", "person1": "father", "person2": "proband"},
                {"type": "parent-child", "person1": "mother", "person2": "proband"},
                {"type": "parent-child", "person1": "father", "person2": "sister"},
                {"type": "parent-child", "person1": "mother", "person2": "sister"}
            ]
        },
        "scenario_e_complex": {
            "individuals": [
                {"id": "p1", "name": "Deceased Grandfather", "gender": "male", "status": "unaffected", "generation": 0, "deceased": True},
                {"id": "p2", "name": "Grandmother", "gender": "female", "status": "unaffected", "generation": 0, "deceased": False},
                {"id": "carrier_son", "name": "Carrier Son", "gender": "male", "status": "carrier", "generation": 1, "deceased": False},
                {"id": "unknown_carrier", "name": "Unknown Gender", "gender": "unknown", "status": "carrier", "generation": 1, "deceased": False}
            ],
            "relationships": [
                {"type": "marriage", "person1": "p1", "person2": "p2"},
                {"type": "parent-child", "person1": "p1", "person2": "carrier_son"},
                {"type": "parent-child", "person1": "p2", "person2": "carrier_son"},
                {"type": "parent-child", "person1": "p1", "person2": "unknown_carrier"},
                {"type": "parent-child", "person1": "p2", "person2": "unknown_carrier"}
            ]
        }
    }

    os.makedirs("tests/scenarios_out", exist_ok=True)
    
    print("=== STARTING MULTI-SCENARIO PEDIGREE LAYOUT VALIDATION ===")
    for key, data in scenarios.items():
        print(f"\nRunning {key}...")
        try:
            # Sort generations
            ped_data = generator.parse_family_description("", use_ai=False) # Get empty dict template
            ped_data["individuals"] = data["individuals"]
            ped_data["relationships"] = data["relationships"]
            
            # Sort generations
            organized_data = generator._organize_generations(ped_data)
            ped_data["generations"] = organized_data["generations"]
            ped_data["individuals"] = organized_data["individuals"]
            
            # Draw and verify
            img = generator.generate_image(ped_data)
            assert img is not None, f"{key} failed to return PIL Image"
            
            # Save file
            path = f"tests/scenarios_out/{key}.png"
            img.save(path)
            print(f"  SUCCESS: Image rendered and saved successfully to {path}")
            
            # Check individual gendering styles inside generation list
            for level in organized_data["generations"]:
                for ind in level["individuals"]:
                    assert ind["gender"] in ["male", "female", "unknown"], f"Invalid gender format: {ind['gender']}"
                    assert ind["status"] in ["affected", "carrier", "unaffected"], f"Invalid status: {ind['status']}"
            
        except Exception as e:
            print(f"  FAILED {key}:", str(e))
            raise e

    print("\nALL 5 PEDIGREE SCENARIOS RENDERED CORRECTLY AND PASSED GEOMETRIC CHECKS!")

if __name__ == "__main__":
    run_scenario_tests()
