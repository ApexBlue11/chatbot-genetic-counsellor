# Pedigree System Architecture

VariantMind turns a free-text family history into a standards-compliant medical
pedigree chart, rendered as SVG.

The design principle is a hard split of responsibilities: **the model decides
who exists and how they are related, and nothing else.** Generation levels,
left-to-right ordering, spouse placement, connector routing and canvas sizing
are all computed deterministically, then checked geometrically before the chart
is returned. Anything the model gets wrong is a relationship error, which is
visible and testable — never a silent layout defect.

---

## 🏛️ Pipeline

```
Free-text family description
           ↓
  GeminiPedigreeParser        analysis/pedigree_generator.py
  (relationship extraction only — no positions, no generation numbers)
           ↓
  { individuals, relationships }
           ↓
  compute_layout              analysis/pedigree_layout.py
    ├─ FamilyGraph            normalise; derive implicit marriages/siblings
    ├─ solve_generations      BFS over every component
    ├─ build_blocks           rigid spouse groups
    ├─ order_blocks           median-heuristic crossing reduction
    ├─ assign_x               barycentre passes + exact separation solve
    └─ route_edges            marriage bars, descent lines, sibship buses
           ↓
  validate_layout             analysis/pedigree_validator.py
           ↓
  render_svg                  analysis/pedigree_svg.py
```

If Gemini is unreachable, `SimplePedigreeParser` falls back to regex extraction
of the common shorthand (`David (40 M, carrier)`); the rest of the pipeline is
unchanged.

---

## 1. Schema

The model returns only this. Note there is no `generation` field and no ordering
hints — supplying them was a persistent source of error.

```json
{
  "individuals": [
    {
      "id": "proband",
      "name": "Proband",
      "gender": "male|female|unknown",
      "age": 8,
      "status": "unaffected|affected|carrier|unknown",
      "conditions": ["cystic_fibrosis"],
      "deceased": false
    }
  ],
  "relationships": [
    { "type": "marriage|parent-child|sibling", "person1": "father", "person2": "proband" }
  ]
}
```

`deceased` is a separate boolean from `status`, so a deceased person can still
be drawn as affected, carrier or unknown.

---

## 2. Layout engine

**Generations.** A BFS runs over *every* connected component. Seeding from a
single individual was the original bug: any relative the model failed to connect
collapsed to generation 0 and floated a row too high. Contradictory constraints
are reported rather than silently applied. Components that share no edges are
anchored relative to each other using role hints ("grandmother", "cousin"), so
even a disconnected graph lands on sensible rows.

**Blocks.** Spouses are grouped into rigid blocks so a couple can never be split
by a third person. Someone with two partners is placed *between* them. Couple
spacing is widened when needed so neither name label reaches the marriage bar's
midpoint, which is where the descent line drops.

**Ordering.** Seeded from input order and the paternal/maternal split around the
proband, then refined with median-heuristic sweeps. Afterwards `orient_couples`
turns each couple so the blood relative faces their own siblings, putting
married-in spouses on the outer edge.

**X positions.** Alternating barycentre passes (children under parents, then
parents over children). After each pass, minimum gaps are enforced by an exact
isotonic (pool-adjacent-violators) projection, which keeps every node as close
to its barycentre as spacing allows instead of shoving the row rightwards.

**Routing.** Marriage bars run edge to edge. Descent drops from the marriage
bar's midpoint to a shared sibship bus, which spans the children and drops to
each. Buses within one generation gap are interval-coloured onto separate
levels so two families' buses can never overlap. Consanguineous unions get a
double bar, detected by a shared ancestor.

**Canvas.** Sized to its content. The old renderer used a fixed 1200×800 and
left roughly half of every chart blank.

---

## 3. Geometric validation

`validate_layout` checks the resolved geometry directly rather than inspecting a
rendered image, so it is exact and fast. Every connector is axis-aligned, which
reduces intersection tests to interval overlaps.

**Errors** — defects a clinician would call wrong:

| Code | Meaning |
| --- | --- |
| `symbol_overlap` | Two symbols overlap |
| `label_overlap` / `label_symbol_overlap` | A name collides with another name or symbol |
| `line_through_symbol` | A connector is drawn through a shape |
| `line_through_label` | A connector crosses a name |
| `duplicate_connector` | Two collinear connectors drawn on top of each other |
| `out_of_canvas` | Content falls outside the canvas |
| `generation_error` | Parent/child, spouse or sibling on the wrong row |
| `couple_split` | Someone drawn between a couple |
| `multiple_probands` | More than one index-case arrow |
| `missing_nodes` | An individual was dropped from the layout |

**Warnings** — legible but not ideal: `connector_crossings`,
`children_off_centre`, `disconnected`, `wasted_canvas`.

---

## 4. Structured logging

`analysis/pedigree_logging.py` writes one JSON Lines trace per render to
`logs/pedigree/<run_id>.jsonl`, with a timed entry for every stage plus
intermediate artifacts (the description, the raw model response, the extracted
JSON) under `logs/pedigree/<run_id>-artifacts/`. Console output stays
human-readable; the JSONL file is the machine-readable record.

Set `VARIANTMIND_PEDIGREE_LOG=0` to silence console output — the test suites do
this.

---

## 5. Testing

| Suite | Network | What it covers |
| --- | --- | --- |
| `tests/test_pedigree_layout.py` | no | 15 fixtures through layout → validation → SVG. The inner loop. |
| `tests/test_pedigree_scenarios.py` | no | The `PedigreeGenerator` API surface the backend calls. |
| `tests/test_pedigree_live.py` | **yes** | Natural language → Gemini → validated SVG. Run deliberately. |
| `frontend/scripts/verify-dna-choreography.mjs` | no | Landing-page scroll geometry. |

```bash
python tests/test_pedigree_layout.py          # all fixtures
python tests/test_pedigree_layout.py -v       # with full traces
python tests/test_pedigree_layout.py nuclear_ar
python tests/svg_preview.py                   # rasterise for eyeballing
```

Several fixtures exist specifically to pin regressions: `cousins_disconnected`
(the floating-branch bug), `dominant_both_lineages` (descent lines through
parents' symbols), `possessive_names` (the arrow landing on "Proband's Father"),
and `messy_input` (missing ids, dangling relationships, markup in a name).

`tests/svg_preview.py` is a minimal rasteriser for the SVG subset the engine
emits. It parses the real SVG output rather than re-drawing from the layout
object, so a developer preview reflects what the browser is handed. It is not a
general SVG renderer.
