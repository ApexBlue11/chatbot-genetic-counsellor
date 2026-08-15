"""
Pedigree generation: free-text family history in, SVG chart out.

The model's only job is to extract *who exists* and *how they are related*.
Everything downstream of that — generation levels, left-to-right ordering,
spouse placement, connector routing and canvas sizing — is computed
deterministically by :mod:`analysis.pedigree_layout`, and the geometry is
machine-checked by :mod:`analysis.pedigree_validator`.

    Free-text family description
               ↓
      Gemini (relationship extraction only)
               ↓
      {individuals, relationships}
               ↓
      compute_layout  →  validate_layout  →  render_svg
"""

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import requests

from analysis.pedigree_layout import PedigreeLayout, compute_layout
from analysis.pedigree_logging import PedigreeTrace, log_pedigree_step  # noqa: F401
from analysis.pedigree_svg import render_svg
from analysis.pedigree_validator import validate_layout


@dataclass
class Individual:
    """Represents an individual in the pedigree."""
    id: str
    name: str
    gender: str                 # 'male' | 'female' | 'unknown'
    age: Optional[int]
    status: str                 # 'unaffected' | 'affected' | 'carrier' | 'unknown'
    conditions: List[str]
    deceased: bool
    generation: int


@dataclass
class Relationship:
    """Represents a relationship between two individuals."""
    type: str                   # 'marriage' | 'parent-child' | 'sibling'
    person1: str
    person2: str


class SimplePedigreeParser:
    """Regex fallback for when the model is unreachable.

    Handles the common shorthand a counselor types — ``David (40 M, carrier)``
    and ``Sarah is a 34-year-old female`` — well enough to draw something
    useful. Generation levels are left to the layout engine.
    """

    def parse(self, text: str) -> Dict[str, Any]:
        individuals: List[Individual] = []
        relationships: List[Relationship] = []
        self.extract_individuals(text, individuals)
        self.extract_relationships(text, individuals, relationships)
        return {
            "individuals": [asdict(i) for i in individuals],
            "relationships": [asdict(r) for r in relationships],
        }

    def extract_individuals(self, text: str, individuals: List[Individual]) -> None:
        seen = set()

        def add(name, age, gender, status, generation=0):
            key = name.lower()
            if key in seen:
                return
            seen.add(key)
            individuals.append(Individual(
                id=key, name=name, gender=self.normalize_gender(gender),
                age=int(age) if age else None,
                status=(status or "unaffected").lower(),
                conditions=[], deceased=(status or "").lower() == "deceased",
                generation=generation,
            ))

        # "David (40 M, carrier)" / "David (40, male, affected)"
        pattern = (r'(\w+)\s*\((\d+)[\s,]*([MF]|male|female)[\s,]*'
                   r'(carrier|affected|unaffected|deceased)?\)')
        for match in re.finditer(pattern, text, re.IGNORECASE):
            add(match.group(1), match.group(2), match.group(3), match.group(4))

        # "John is a 45-year-old male"
        for match in re.finditer(
                r'(\w+)\s+is\s+an?\s+(\d+)[-\s]year[-\s]old\s+(male|female)',
                text, re.IGNORECASE):
            add(match.group(1), match.group(2), match.group(3), None)

        # Children listed after a "children — ..." style lead-in.
        for lead in (r'children\s*[—\-:]\s*([^.]+)',
                     r'(?:son|daughter|child)(?:ren)?\s*[—\-:]\s*([^.]+)'):
            for match in re.finditer(lead, text, re.IGNORECASE):
                for child in re.finditer(pattern, match.group(1), re.IGNORECASE):
                    add(child.group(1), child.group(2), child.group(3),
                        child.group(4), generation=1)

    def extract_relationships(self, text: str, individuals: List[Individual],
                              relationships: List[Relationship]) -> None:
        parents = [i for i in individuals if i.generation == 0]
        children = [i for i in individuals if i.generation == 1]

        match = re.search(r'(\w+)\s*\([^)]+\)\s+and\s+(\w+)\s*\([^)]+\)', text, re.IGNORECASE)
        spouses = None
        if match:
            a = next((i for i in individuals if i.name.lower() == match.group(1).lower()), None)
            b = next((i for i in individuals if i.name.lower() == match.group(2).lower()), None)
            if a and b:
                spouses = (a, b)
        if spouses is None and len(parents) == 2:
            spouses = (parents[0], parents[1])
        if spouses:
            relationships.append(Relationship("marriage", spouses[0].id, spouses[1].id))

        for parent in parents:
            for child in children:
                relationships.append(Relationship("parent-child", parent.id, child.id))

    @staticmethod
    def normalize_gender(gender: Optional[str]) -> str:
        value = (gender or "").lower()
        if value in ("m", "male"):
            return "male"
        if value in ("f", "female"):
            return "female"
        return "unknown"


EXTRACTION_PROMPT = """You are a medical genetics expert. Convert the family \
description below into a strictly valid JSON object describing a pedigree.

Return ONLY raw JSON — no markdown fences, no prose.

{
  "individuals": [
    {
      "id": "lowercase_unique_id",
      "name": "Display Name",
      "gender": "male|female|unknown",
      "age": number or null,
      "status": "unaffected|affected|carrier|unknown",
      "conditions": ["condition"],
      "deceased": true or false
    }
  ],
  "relationships": [
    { "type": "marriage|parent-child|sibling", "person1": "id", "person2": "id" }
  ]
}

Your ONLY job is to capture who exists and how they are related. Do NOT try to \
position anyone or assign generation numbers — layout is computed separately.

RELATIONSHIP RULES — these matter most:
1. For "parent-child", person1 is the PARENT and person2 is the CHILD.
2. Record BOTH parents for every child, as two separate parent-child entries.
3. EVERY individual must connect to the rest of the family. A relative who is \
   related only by description is a bug. In particular:
   - An aunt or uncle who is a BLOOD relative is a child of the corresponding \
     grandparents — emit parent-child links from both grandparents to them.
   - An aunt or uncle who married in is NOT a child of the grandparents; link \
     them by marriage to the blood relative instead.
   - Cousins are children of an aunt/uncle couple — link them to both.
   - Nieces and nephews are children of the proband's sibling.
4. Add a "marriage" entry for every couple, including couples who already share \
   a child.
5. Do not invent people who were not described. If a connecting relative is \
   implied but unnamed (for example the grandparents an uncle descends from), \
   include them with a descriptive name so the family stays connected.

STATUS RULES:
- "affected" = has the condition; "carrier" = heterozygous/unaffected carrier;
  "unaffected" = tested or stated clear; "unknown" = not stated.
- "deceased" is a separate boolean, never a status value.
- Mark the person the history centres on with the name "Proband"."""


class GeminiPedigreeParser:
    """Extracts a structured family graph from free text using Gemini."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.endpoints = [
            "https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent",
            "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        ]

    def query_gemini(self, system_prompt: str, user_content: str,
                     trace: Optional[PedigreeTrace] = None) -> str:
        """Try the SDK first, then fall back to the REST endpoints in order."""
        prompt = f"{system_prompt}\n\nCONTENT:\n{user_content}"

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(prompt)
            if trace:
                trace.event("ai", "Extraction returned via the SDK")
            return response.text
        except Exception as exc:                                    # noqa: BLE001
            if trace:
                trace.warn("ai", f"SDK call failed, trying REST: {exc}")

        body = {"contents": [{"parts": [{"text": prompt}]}]}
        for endpoint in self.endpoints:
            try:
                response = requests.post(f"{endpoint}?key={self.api_key}",
                                         headers={"Content-Type": "application/json"},
                                         json=body, timeout=45)
                if response.ok:
                    data = response.json()
                    candidates = data.get("candidates") or []
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if trace:
                            trace.event("ai", f"Extraction returned via {endpoint}")
                        return "".join(part.get("text", "") for part in parts)
                elif trace:
                    trace.warn("ai", f"{endpoint} returned HTTP {response.status_code}")
            except Exception as exc:                                # noqa: BLE001
                if trace:
                    trace.warn("ai", f"{endpoint} failed: {exc}")

        raise RuntimeError("Gemini could not be reached on any endpoint")

    def parse_to_json(self, prompt: str,
                      trace: Optional[PedigreeTrace] = None) -> Dict[str, Any]:
        """Free text in, ``{individuals, relationships}`` out."""
        if trace:
            trace.event("input", "Parsing family description", {"prompt": prompt[:600]})
            trace.dump_artifact("description.txt", prompt)

        raw = self.query_gemini(EXTRACTION_PROMPT, prompt, trace)
        if trace:
            trace.dump_artifact("model_response.txt", raw)

        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError("The model did not return a JSON object")

        data = json.loads(match.group(0))
        if "individuals" not in data or not isinstance(data["individuals"], list):
            raise ValueError("Model response is missing an 'individuals' array")
        data.setdefault("relationships", [])

        if trace:
            trace.event("input", "Extraction parsed", {
                "individuals": len(data["individuals"]),
                "relationships": len(data["relationships"]),
            })
            trace.dump_artifact("extracted.json", data)
        return data


class PedigreeGenerator:
    """Orchestrates extraction, layout, validation and SVG rendering."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.simple_parser = SimplePedigreeParser()
        self.gemini_parser = GeminiPedigreeParser(api_key) if api_key else None

    # -- extraction --

    def parse_family_description(self, description: str, use_ai: bool = True,
                                 trace: Optional[PedigreeTrace] = None) -> Dict[str, Any]:
        """Structured family graph from a natural-language description."""
        if use_ai and self.gemini_parser:
            try:
                return self.gemini_parser.parse_to_json(description, trace)
            except Exception as exc:                                # noqa: BLE001
                if trace:
                    trace.warn("input", f"AI extraction failed, using regex fallback: {exc}")

        if trace:
            trace.event("input", "Using the regex fallback parser")
        return self.simple_parser.parse(description)

    # -- layout + render --

    def build_layout(self, pedigree_data: Dict[str, Any],
                     trace: Optional[PedigreeTrace] = None) -> PedigreeLayout:
        return compute_layout(pedigree_data.get("individuals", []),
                              pedigree_data.get("relationships", []),
                              trace=trace)

    def generate_svg(self, pedigree_data: Dict[str, Any],
                     title: str = "Pedigree chart",
                     trace: Optional[PedigreeTrace] = None,
                     validate: bool = True) -> str:
        """Render a structured family graph to an SVG document."""
        layout = self.build_layout(pedigree_data, trace)

        if validate:
            report = validate_layout(layout, pedigree_data.get("individuals", []),
                                     pedigree_data.get("relationships", []))
            if trace:
                trace.event("validate", f"Geometry check: {report.summary()}",
                            {"stats": report.stats,
                             "errors": [str(i) for i in report.errors],
                             "warnings": [str(i) for i in report.warnings]})
            # Errors are reported, not raised: a slightly imperfect chart is far
            # more useful to a counselor than no chart at all.
            if report.errors:
                log_pedigree_step("PEDIGREE_GEOMETRY",
                                  f"Rendered with {len(report.errors)} geometry issue(s)",
                                  [str(i) for i in report.errors[:5]])

        return render_svg(layout, title=title)

    def render_from_description(self, description: str, use_ai: bool = True,
                                title: str = "Pedigree chart") -> Dict[str, Any]:
        """One-shot: description in, SVG plus the structured data out."""
        trace = PedigreeTrace("pedigree")
        try:
            data = self.parse_family_description(description, use_ai=use_ai, trace=trace)
            svg = self.generate_svg(data, title=title, trace=trace)
            return {"svg": svg, "pedigree_data": data, "trace": trace.finish()}
        finally:
            trace.finish()
