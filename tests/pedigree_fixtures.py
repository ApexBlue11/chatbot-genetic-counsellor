"""
Deterministic pedigree fixtures for the layout regression suite.

These are the structured graphs the layout engine consumes, so the whole suite
runs offline with no Gemini calls. Several fixtures reproduce charts that the
old renderer got visibly wrong — they exist specifically to stop those
regressions coming back.
"""

from typing import Any, Dict

FIXTURES: Dict[str, Dict[str, Any]] = {}


def _fixture(key: str, description: str, individuals, relationships,
             expectations: Dict[str, Any] | None = None) -> None:
    FIXTURES[key] = {
        "description": description,
        "individuals": individuals,
        "relationships": relationships,
        "expectations": expectations or {},
    }


# ── 1. Nuclear family, autosomal recessive ─────────────────────────────────
_fixture(
    "nuclear_ar",
    "Two carrier parents with an affected son and an unaffected daughter.",
    [
        {"id": "father", "name": "Father", "gender": "male", "status": "carrier", "age": 41},
        {"id": "mother", "name": "Mother", "gender": "female", "status": "carrier", "age": 39},
        {"id": "proband", "name": "Proband", "gender": "male", "status": "affected", "age": 9},
        {"id": "sister", "name": "Sister", "gender": "female", "status": "unaffected", "age": 12},
    ],
    [
        {"type": "marriage", "person1": "father", "person2": "mother"},
        {"type": "parent-child", "person1": "father", "person2": "proband"},
        {"type": "parent-child", "person1": "mother", "person2": "proband"},
        {"type": "parent-child", "person1": "father", "person2": "sister"},
        {"type": "parent-child", "person1": "mother", "person2": "sister"},
    ],
    {"generations": 2, "individuals": 4},
)

# ── 2. Three generations down one line ─────────────────────────────────────
_fixture(
    "three_generations",
    "Deceased affected grandfather, carrier mother, affected proband.",
    [
        {"id": "gf", "name": "Grandfather", "gender": "male", "status": "affected",
         "deceased": True, "age": 78},
        {"id": "gm", "name": "Grandmother", "gender": "female", "status": "unaffected", "age": 76},
        {"id": "father", "name": "Father", "gender": "male", "status": "unaffected", "age": 48},
        {"id": "mother", "name": "Mother", "gender": "female", "status": "carrier", "age": 46},
        {"id": "proband", "name": "Proband", "gender": "male", "status": "affected", "age": 14},
    ],
    [
        {"type": "marriage", "person1": "gf", "person2": "gm"},
        {"type": "parent-child", "person1": "gf", "person2": "mother"},
        {"type": "parent-child", "person1": "gm", "person2": "mother"},
        {"type": "marriage", "person1": "father", "person2": "mother"},
        {"type": "parent-child", "person1": "father", "person2": "proband"},
        {"type": "parent-child", "person1": "mother", "person2": "proband"},
    ],
    {"generations": 3, "individuals": 5},
)

# ── 3. Consanguineous union (first cousins) ────────────────────────────────
_fixture(
    "consanguineous",
    "First cousins marry; their child is affected. Expect a double marriage bar.",
    [
        {"id": "gf", "name": "Grandfather", "gender": "male", "status": "unaffected"},
        {"id": "gm", "name": "Grandmother", "gender": "female", "status": "unaffected"},
        {"id": "son_a", "name": "Son A", "gender": "male", "status": "carrier"},
        {"id": "wife_a", "name": "Wife A", "gender": "female", "status": "unaffected"},
        {"id": "son_b", "name": "Son B", "gender": "male", "status": "carrier"},
        {"id": "wife_b", "name": "Wife B", "gender": "female", "status": "unaffected"},
        {"id": "cousin_m", "name": "Cousin M", "gender": "male", "status": "carrier"},
        {"id": "cousin_f", "name": "Cousin F", "gender": "female", "status": "carrier"},
        {"id": "child", "name": "Affected Child", "gender": "female", "status": "affected", "age": 4},
    ],
    [
        {"type": "marriage", "person1": "gf", "person2": "gm"},
        {"type": "parent-child", "person1": "gf", "person2": "son_a"},
        {"type": "parent-child", "person1": "gm", "person2": "son_a"},
        {"type": "parent-child", "person1": "gf", "person2": "son_b"},
        {"type": "parent-child", "person1": "gm", "person2": "son_b"},
        {"type": "marriage", "person1": "son_a", "person2": "wife_a"},
        {"type": "marriage", "person1": "son_b", "person2": "wife_b"},
        {"type": "parent-child", "person1": "son_a", "person2": "cousin_m"},
        {"type": "parent-child", "person1": "wife_a", "person2": "cousin_m"},
        {"type": "parent-child", "person1": "son_b", "person2": "cousin_f"},
        {"type": "parent-child", "person1": "wife_b", "person2": "cousin_f"},
        {"type": "marriage", "person1": "cousin_m", "person2": "cousin_f"},
        {"type": "parent-child", "person1": "cousin_m", "person2": "child"},
        {"type": "parent-child", "person1": "cousin_f", "person2": "child"},
    ],
    {"generations": 4, "individuals": 9, "consanguineous": True},
)

# ── 4. X-linked recessive ──────────────────────────────────────────────────
_fixture(
    "x_linked",
    "Carrier mother, affected son, carrier daughter. Long names force wrapping.",
    [
        {"id": "father", "name": "Father", "gender": "male", "status": "unaffected"},
        {"id": "mother", "name": "Mother (Obligate Carrier)", "gender": "female", "status": "carrier"},
        {"id": "proband", "name": "Proband (Affected Male)", "gender": "male", "status": "affected"},
        {"id": "sister", "name": "Sister (Carrier)", "gender": "female", "status": "carrier"},
        {"id": "brother", "name": "Brother", "gender": "male", "status": "unaffected"},
    ],
    [
        {"type": "marriage", "person1": "father", "person2": "mother"},
        {"type": "parent-child", "person1": "father", "person2": "proband"},
        {"type": "parent-child", "person1": "mother", "person2": "proband"},
        {"type": "parent-child", "person1": "father", "person2": "sister"},
        {"type": "parent-child", "person1": "mother", "person2": "sister"},
        {"type": "parent-child", "person1": "father", "person2": "brother"},
        {"type": "parent-child", "person1": "mother", "person2": "brother"},
    ],
    {"generations": 2, "individuals": 5},
)

# ── 5. Unknown sex and unknown disease status ──────────────────────────────
_fixture(
    "unknown_status",
    "Diamond symbols for unrecorded sex, '?' for unrecorded disease status.",
    [
        {"id": "p1", "name": "Deceased Grandfather", "gender": "male",
         "status": "unaffected", "deceased": True},
        {"id": "p2", "name": "Grandmother", "gender": "female", "status": "unknown"},
        {"id": "c1", "name": "Carrier Son", "gender": "male", "status": "carrier"},
        {"id": "c2", "name": "Unknown Sex", "gender": "unknown", "status": "carrier"},
        {"id": "c3", "name": "Status Unknown", "gender": "unknown", "status": "unknown"},
    ],
    [
        {"type": "marriage", "person1": "p1", "person2": "p2"},
        {"type": "parent-child", "person1": "p1", "person2": "c1"},
        {"type": "parent-child", "person1": "p2", "person2": "c1"},
        {"type": "parent-child", "person1": "p1", "person2": "c2"},
        {"type": "parent-child", "person1": "p2", "person2": "c2"},
        {"type": "parent-child", "person1": "p1", "person2": "c3"},
        {"type": "parent-child", "person1": "p2", "person2": "c3"},
    ],
    {"generations": 2, "individuals": 5},
)

# ── 6. Cousins, fully connected (the chart scenario 1 should have produced) ─
_fixture(
    "cousins_connected",
    "Maternal grandparents with two children; the proband and a cousin. "
    "Regression guard for the disconnected-uncle bug.",
    [
        {"id": "mgf", "name": "Maternal Grandfather", "gender": "male", "status": "unaffected"},
        {"id": "mgm", "name": "Maternal Grandmother", "gender": "female", "status": "unaffected"},
        {"id": "father", "name": "Father", "gender": "male", "status": "affected"},
        {"id": "mother", "name": "Mother", "gender": "female", "status": "unaffected"},
        {"id": "uncle", "name": "Uncle", "gender": "male", "status": "unaffected"},
        {"id": "aunt", "name": "Aunt", "gender": "female", "status": "unaffected"},
        {"id": "proband", "name": "Proband", "gender": "male", "status": "affected", "age": 8},
        {"id": "cousin", "name": "Cousin", "gender": "female", "status": "unaffected", "age": 11},
    ],
    [
        {"type": "marriage", "person1": "mgf", "person2": "mgm"},
        {"type": "parent-child", "person1": "mgf", "person2": "mother"},
        {"type": "parent-child", "person1": "mgm", "person2": "mother"},
        {"type": "parent-child", "person1": "mgf", "person2": "uncle"},
        {"type": "parent-child", "person1": "mgm", "person2": "uncle"},
        {"type": "marriage", "person1": "father", "person2": "mother"},
        {"type": "marriage", "person1": "uncle", "person2": "aunt"},
        {"type": "parent-child", "person1": "father", "person2": "proband"},
        {"type": "parent-child", "person1": "mother", "person2": "proband"},
        {"type": "parent-child", "person1": "uncle", "person2": "cousin"},
        {"type": "parent-child", "person1": "aunt", "person2": "cousin"},
    ],
    {"generations": 3, "individuals": 8,
     "same_generation": [["proband", "cousin"], ["mother", "uncle", "father", "aunt"]]},
)

# ── 7. Cousins, disconnected (what the model actually emitted) ─────────────
_fixture(
    "cousins_disconnected",
    "The uncle's link to the grandparents is missing — exactly the graph that "
    "made the old renderer float an entire branch a row too high. Role hints "
    "should still land everyone on the correct row.",
    [
        {"id": "mgf", "name": "Maternal Grandfather", "gender": "male", "status": "unaffected"},
        {"id": "mgm", "name": "Maternal Grandmother", "gender": "female", "status": "unaffected"},
        {"id": "father", "name": "Father", "gender": "male", "status": "affected"},
        {"id": "mother", "name": "Mother", "gender": "female", "status": "unaffected"},
        {"id": "uncle", "name": "Uncle", "gender": "male", "status": "unaffected"},
        {"id": "aunt", "name": "Aunt", "gender": "female", "status": "unaffected"},
        {"id": "proband", "name": "Proband", "gender": "male", "status": "affected"},
        {"id": "cousin", "name": "Cousin", "gender": "female", "status": "unaffected"},
    ],
    [
        {"type": "marriage", "person1": "mgf", "person2": "mgm"},
        {"type": "parent-child", "person1": "mgf", "person2": "mother"},
        {"type": "parent-child", "person1": "mgm", "person2": "mother"},
        {"type": "marriage", "person1": "father", "person2": "mother"},
        {"type": "marriage", "person1": "uncle", "person2": "aunt"},
        {"type": "parent-child", "person1": "father", "person2": "proband"},
        {"type": "parent-child", "person1": "mother", "person2": "proband"},
        {"type": "parent-child", "person1": "uncle", "person2": "cousin"},
        {"type": "parent-child", "person1": "aunt", "person2": "cousin"},
    ],
    {"individuals": 8, "allow_disconnected": True,
     "same_generation": [["proband", "cousin"], ["mother", "uncle"]]},
)

# ── 8. Both lineages with nieces and nephews ───────────────────────────────
_fixture(
    "nieces_nephews",
    "Paternal grandparents, the proband's parents, an aunt-and-uncle couple, "
    "and their two children. Two sibships share one generation gap.",
    [
        {"id": "pgf", "name": "Paternal Grandfather", "gender": "male", "status": "affected"},
        {"id": "pgm", "name": "Paternal Grandmother", "gender": "female", "status": "carrier"},
        {"id": "mother", "name": "Mother", "gender": "female", "status": "unaffected"},
        {"id": "father", "name": "Father", "gender": "male", "status": "unaffected"},
        {"id": "aunt", "name": "Aunt", "gender": "female", "status": "affected"},
        {"id": "uncle", "name": "Uncle", "gender": "male", "status": "unaffected"},
        {"id": "proband", "name": "Proband", "gender": "male", "status": "affected"},
        {"id": "sister", "name": "Sister", "gender": "female", "status": "unaffected"},
        {"id": "niece", "name": "Niece", "gender": "female", "status": "affected"},
        {"id": "nephew", "name": "Nephew", "gender": "male", "status": "carrier"},
    ],
    [
        {"type": "marriage", "person1": "pgf", "person2": "pgm"},
        {"type": "parent-child", "person1": "pgf", "person2": "father"},
        {"type": "parent-child", "person1": "pgm", "person2": "father"},
        {"type": "parent-child", "person1": "pgf", "person2": "aunt"},
        {"type": "parent-child", "person1": "pgm", "person2": "aunt"},
        {"type": "marriage", "person1": "father", "person2": "mother"},
        {"type": "marriage", "person1": "aunt", "person2": "uncle"},
        {"type": "parent-child", "person1": "father", "person2": "proband"},
        {"type": "parent-child", "person1": "mother", "person2": "proband"},
        {"type": "parent-child", "person1": "father", "person2": "sister"},
        {"type": "parent-child", "person1": "mother", "person2": "sister"},
        {"type": "parent-child", "person1": "aunt", "person2": "niece"},
        {"type": "parent-child", "person1": "uncle", "person2": "niece"},
        {"type": "parent-child", "person1": "aunt", "person2": "nephew"},
        {"type": "parent-child", "person1": "uncle", "person2": "nephew"},
    ],
    {"generations": 3, "individuals": 10,
     "same_generation": [["proband", "sister", "niece", "nephew"],
                         ["father", "mother", "aunt", "uncle"]]},
)

# ── 9. Autosomal dominant across both lineages ─────────────────────────────
_fixture(
    "dominant_both_lineages",
    "Four grandparents, affected mother, three children. Regression guard for "
    "descent lines drawn through the parents' symbols.",
    [
        {"id": "pgf", "name": "Paternal Grandfather", "gender": "male",
         "status": "affected", "deceased": True},
        {"id": "pgm", "name": "Paternal Grandmother", "gender": "female", "status": "unaffected"},
        {"id": "mgf", "name": "Maternal Grandfather", "gender": "male", "status": "carrier"},
        {"id": "mgm", "name": "Maternal Grandmother", "gender": "female",
         "status": "unaffected", "deceased": True},
        {"id": "father", "name": "Father", "gender": "male", "status": "carrier"},
        {"id": "mother", "name": "Mother", "gender": "female", "status": "affected"},
        {"id": "proband", "name": "Proband", "gender": "male", "status": "affected"},
        {"id": "sister", "name": "Sister", "gender": "female", "status": "affected"},
        {"id": "brother", "name": "Brother", "gender": "male", "status": "unknown"},
    ],
    [
        {"type": "marriage", "person1": "pgf", "person2": "pgm"},
        {"type": "marriage", "person1": "mgf", "person2": "mgm"},
        {"type": "parent-child", "person1": "pgf", "person2": "father"},
        {"type": "parent-child", "person1": "pgm", "person2": "father"},
        {"type": "parent-child", "person1": "mgf", "person2": "mother"},
        {"type": "parent-child", "person1": "mgm", "person2": "mother"},
        {"type": "marriage", "person1": "father", "person2": "mother"},
        {"type": "parent-child", "person1": "father", "person2": "proband"},
        {"type": "parent-child", "person1": "mother", "person2": "proband"},
        {"type": "parent-child", "person1": "father", "person2": "sister"},
        {"type": "parent-child", "person1": "mother", "person2": "sister"},
        {"type": "parent-child", "person1": "father", "person2": "brother"},
        {"type": "parent-child", "person1": "mother", "person2": "brother"},
    ],
    {"generations": 3, "individuals": 9},
)

# ── 10. Single parent recorded ─────────────────────────────────────────────
_fixture(
    "single_parent",
    "Only one parent is known — the descent line drops straight from them.",
    [
        {"id": "mother", "name": "Mother", "gender": "female", "status": "affected"},
        {"id": "child_a", "name": "Son", "gender": "male", "status": "affected"},
        {"id": "child_b", "name": "Daughter", "gender": "female", "status": "unaffected"},
    ],
    [
        {"type": "parent-child", "person1": "mother", "person2": "child_a"},
        {"type": "parent-child", "person1": "mother", "person2": "child_b"},
    ],
    {"generations": 2, "individuals": 3},
)

# ── 11. Second marriage / half siblings ────────────────────────────────────
_fixture(
    "second_marriage",
    "A man with children by two partners — half-siblings share one parent.",
    [
        {"id": "first_wife", "name": "First Wife", "gender": "female", "status": "unaffected"},
        {"id": "man", "name": "Father", "gender": "male", "status": "affected"},
        {"id": "second_wife", "name": "Second Wife", "gender": "female", "status": "carrier"},
        {"id": "child_1", "name": "Elder Son", "gender": "male", "status": "affected"},
        {"id": "child_2", "name": "Younger Daughter", "gender": "female", "status": "unaffected"},
    ],
    [
        {"type": "marriage", "person1": "man", "person2": "first_wife"},
        {"type": "marriage", "person1": "man", "person2": "second_wife"},
        {"type": "parent-child", "person1": "man", "person2": "child_1"},
        {"type": "parent-child", "person1": "first_wife", "person2": "child_1"},
        {"type": "parent-child", "person1": "man", "person2": "child_2"},
        {"type": "parent-child", "person1": "second_wife", "person2": "child_2"},
    ],
    {"generations": 2, "individuals": 5},
)

# ── 12. Four-generation extended stress test ───────────────────────────────
_fixture(
    "four_generation_extended",
    "Four generations with multiple sibships per row — stresses spacing, bus "
    "levels and crossing reduction.",
    [
        {"id": "ggf", "name": "Great Grandfather", "gender": "male",
         "status": "affected", "deceased": True},
        {"id": "ggm", "name": "Great Grandmother", "gender": "female",
         "status": "unaffected", "deceased": True},
        {"id": "gf", "name": "Grandfather", "gender": "male", "status": "carrier"},
        {"id": "gm", "name": "Grandmother", "gender": "female", "status": "unaffected"},
        {"id": "great_aunt", "name": "Great Aunt", "gender": "female", "status": "affected"},
        {"id": "great_uncle", "name": "Great Uncle", "gender": "male", "status": "unaffected"},
        {"id": "father", "name": "Father", "gender": "male", "status": "carrier"},
        {"id": "mother", "name": "Mother", "gender": "female", "status": "unaffected"},
        {"id": "uncle", "name": "Uncle", "gender": "male", "status": "unaffected"},
        {"id": "second_cousin_p", "name": "Second Cousin", "gender": "female", "status": "carrier"},
        {"id": "proband", "name": "Proband", "gender": "male", "status": "affected", "age": 6},
        {"id": "sister", "name": "Sister", "gender": "female", "status": "carrier", "age": 9},
    ],
    [
        {"type": "marriage", "person1": "ggf", "person2": "ggm"},
        {"type": "parent-child", "person1": "ggf", "person2": "gf"},
        {"type": "parent-child", "person1": "ggm", "person2": "gf"},
        {"type": "parent-child", "person1": "ggf", "person2": "great_aunt"},
        {"type": "parent-child", "person1": "ggm", "person2": "great_aunt"},
        {"type": "marriage", "person1": "gf", "person2": "gm"},
        {"type": "marriage", "person1": "great_aunt", "person2": "great_uncle"},
        {"type": "parent-child", "person1": "gf", "person2": "father"},
        {"type": "parent-child", "person1": "gm", "person2": "father"},
        {"type": "parent-child", "person1": "gf", "person2": "uncle"},
        {"type": "parent-child", "person1": "gm", "person2": "uncle"},
        {"type": "parent-child", "person1": "great_aunt", "person2": "second_cousin_p"},
        {"type": "parent-child", "person1": "great_uncle", "person2": "second_cousin_p"},
        {"type": "marriage", "person1": "father", "person2": "mother"},
        {"type": "parent-child", "person1": "father", "person2": "proband"},
        {"type": "parent-child", "person1": "mother", "person2": "proband"},
        {"type": "parent-child", "person1": "father", "person2": "sister"},
        {"type": "parent-child", "person1": "mother", "person2": "sister"},
    ],
    {"generations": 4, "individuals": 12},
)

# ── 13. Large sibship ──────────────────────────────────────────────────────
_fixture(
    "large_sibship",
    "Six children under one couple — the sibship bus has to span a wide row.",
    [
        {"id": "father", "name": "Father", "gender": "male", "status": "carrier"},
        {"id": "mother", "name": "Mother", "gender": "female", "status": "carrier"},
    ] + [
        {"id": f"child_{i}", "name": f"Child {i}", "gender": "male" if i % 2 else "female",
         "status": "affected" if i in (2, 5) else "unaffected", "age": 20 - i}
        for i in range(1, 7)
    ],
    [
        {"type": "marriage", "person1": "father", "person2": "mother"},
    ] + [
        {"type": "parent-child", "person1": parent, "person2": f"child_{i}"}
        for i in range(1, 7) for parent in ("father", "mother")
    ],
    {"generations": 2, "individuals": 8},
)

# ── 14. Possessive naming, as the model actually emits it ──────────────────
_fixture(
    "possessive_names",
    "Relatives named \"Proband's Father\" etc. Only the proband itself may carry "
    "the arrow — a substring match puts it on half the chart.",
    [
        {"id": "proband_father", "name": "Proband's Father", "gender": "male", "status": "carrier"},
        {"id": "proband_mother", "name": "Proband's Mother", "gender": "female", "status": "carrier"},
        {"id": "proband", "name": "Proband", "gender": "male", "status": "affected", "age": 8},
        {"id": "proband_cousin", "name": "Proband's Cousin", "gender": "female",
         "status": "unaffected", "age": 11},
        {"id": "maternal_uncle", "name": "Maternal Uncle", "gender": "male", "status": "unaffected"},
        {"id": "maternal_aunt", "name": "Maternal Aunt", "gender": "female", "status": "unaffected"},
    ],
    [
        {"type": "marriage", "person1": "proband_father", "person2": "proband_mother"},
        {"type": "parent-child", "person1": "proband_father", "person2": "proband"},
        {"type": "parent-child", "person1": "proband_mother", "person2": "proband"},
        {"type": "marriage", "person1": "maternal_uncle", "person2": "maternal_aunt"},
        {"type": "parent-child", "person1": "maternal_uncle", "person2": "proband_cousin"},
        {"type": "parent-child", "person1": "maternal_aunt", "person2": "proband_cousin"},
        {"type": "sibling", "person1": "proband_mother", "person2": "maternal_uncle"},
    ],
    {"individuals": 6, "generations": 2, "proband": "proband",
     "same_generation": [["proband", "proband_cousin"]]},
)

# ── 15. Hostile input: awkward names and malformed rows ────────────────────
_fixture(
    "messy_input",
    "Missing ids, an unresolvable relationship, a very long name and markup in "
    "a name — the engine must not crash and the SVG must stay escaped.",
    [
        {"name": "No Id Person", "gender": "female", "status": "affected"},
        {"id": "long", "name": "Bartholomew Fitzgerald-Montgomery III", "gender": "male",
         "status": "carrier"},
        {"id": "xss", "name": "<script>alert(1)</script>", "gender": "female",
         "status": "unaffected"},
        {"id": "kid", "name": "Child", "gender": "unknown", "status": "affected"},
    ],
    [
        {"type": "marriage", "person1": "no_id_person", "person2": "long"},
        {"type": "parent-child", "person1": "long", "person2": "kid"},
        {"type": "parent-child", "person1": "no_id_person", "person2": "kid"},
        {"type": "parent-child", "person1": "ghost", "person2": "kid"},
        {"type": "unknown-type", "person1": "long", "person2": "xss"},
    ],
    {"individuals": 4, "allow_disconnected": True},
)
