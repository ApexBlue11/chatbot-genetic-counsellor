# Pedigree System Architecture

VariantMind contains a complete pedigree tree generator that accepts natural language inputs from a genetic counselor and outputs a structured medical pedigree chart (family tree) directly in the conversation.

---

## 🏛️ Pipeline Mechanics

```
Free-text Family Description
           ↓
    Gemini SDK Parser (uses gemini-2.5-flash)
           ↓
   Cleaned JSON Schema (Individuals & Relationships)
           ↓
Generation Level Propagation Algorithm
           ↓
 Pillow Vector Canvas (Calculates coordinates & draws icons)
           ↓
      Base64 PNG Image response
```

### 1. Schema Definition
The family structure is parsed into a clean JSON layout:
```json
{
  "individuals": [
    {
      "id": "proband",
      "name": "Proband",
      "gender": "male",
      "age": 10,
      "status": "affected",
      "conditions": ["cystic_fibrosis"],
      "deceased": false,
      "generation": 1
    }
  ],
  "relationships": [
    {
      "type": "parent-child",
      "person1": "father",
      "person2": "proband"
    }
  ]
}
```

### 2. Generational Sorting Algorithm
Before rendering, generations are calculated dynamically:
1. Individuals without parent relationships are assigned `generation = 0` (roots).
2. The tree is traversed downwards. Children are assigned `generation = parent_generation + 1`.
3. The layout canvas (`PedigreeRenderer`) allocates vertical levels ($y$) based on generation spacing, and horizontal positions ($x$) relative to siblings.

---

## 🪵 Diagnostic Log Tracer (`log_pedigree_step`)

To monitor execution health in real-time, the engine logs execution steps to standard output:

* `[PEDIGREE_INPUT]`: Captures the user's raw text description.
* `[PEDIGREE_AI_REQUEST]`: Logs the model selection and prompt assembly.
* `[PEDIGREE_AI_RESPONSE]`: Prints the raw text returned by the model.
* `[PEDIGREE_VALIDATE_START]` / `[PEDIGREE_VALIDATE_COMPLETE]`: Ensures gender normalization, removes dead references, and prints valid individual/marriage counts.
* `[PEDIGREE_ORGANIZE_START]` / `[PEDIGREE_ORGANIZE_COMPLETE]`: Logs output generation distribution.
* `[PEDIGREE_FALLBACK]`: Alerts if AI endpoints are unreachable and the engine falls back to standard regex parsing rules.
