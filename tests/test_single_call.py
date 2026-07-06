import google.generativeai as genai
from core.gemini_client import init_gemini
import json

def test_single_call():
    genai_obj = init_gemini()
    if not genai_obj:
        print("Failed to load Gemini key")
        return

    # Define the structured parameters for the single call pedigree tool
    pedigree_tool_schema = {
        "name": "create_pedigree_chart",
        "description": "Generate a pedigree chart from structured family tree data.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "individuals": {
                    "type": "ARRAY",
                    "description": "List of individuals in the family tree.",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "id": {"type": "STRING", "description": "Unique short identifier (e.g. proband, father, mother, sister1)"},
                            "name": {"type": "STRING", "description": "Display name"},
                            "gender": {"type": "STRING", "enum": ["male", "female", "unknown"]},
                            "status": {"type": "STRING", "enum": ["affected", "carrier", "unaffected"]},
                            "deceased": {"type": "BOOLEAN"}
                        },
                        "required": ["id", "name", "gender", "status", "deceased"]
                    }
                },
                "relationships": {
                    "type": "ARRAY",
                    "description": "List of connections between individuals.",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "type": {"type": "STRING", "enum": ["marriage", "parent-child", "sibling"]},
                            "person1": {"type": "STRING", "description": "ID of first person"},
                            "person2": {"type": "STRING", "description": "ID of second person"}
                        },
                        "required": ["type", "person1", "person2"]
                    }
                }
            },
            "required": ["individuals", "relationships"]
        }
    }

    # Use the latest model
    model = genai_obj.GenerativeModel("gemini-3.5-flash", tools=[pedigree_tool_schema])
    chat = model.start_chat(enable_automatic_function_calling=False)
    
    prompt = (
        "The proband is an affected male child. His father and mother are unaffected carriers. "
        "He has one unaffected sister. Please draw a pedigree and explain the inheritance pattern."
    )
    
    print("Sending single call prompt to gemini-3.5-flash...")
    response = chat.send_message(prompt)
    
    # Check if a function call was generated in a single turn
    print("\n=== Model Response Output ===")
    has_call = False
    for part in response.candidates[0].content.parts:
        if part.function_call:
            has_call = True
            print("Function Call Generated!")
            print("Name:", part.function_call.name)
            # Convert protobuf message to dict safely
            try:
                from proto.marshal.collections.repeated import RepeatedComposite
                def clean_proto(val):
                    if isinstance(val, (list, RepeatedComposite)):
                        return [clean_proto(x) for x in val]
                    elif hasattr(val, "items"):
                        return {k: clean_proto(v) for k, v in val.items()}
                    return val
                clean_args = clean_proto(part.function_call.args)
                print("Arguments:\n", json.dumps(clean_args, indent=2))
            except Exception as ex:
                print("Error printing args:", str(ex))
        elif part.text:
            print("Text Response:\n", part.text)
            
    if has_call:
        print("\nSUCCESS: Single-call structured tool invocation succeeded!")
    else:
        print("\nFAILED: Model did not invoke the tool in the single call.")

if __name__ == "__main__":
    test_single_call()
