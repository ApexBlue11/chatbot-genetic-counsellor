"""
Complete Pedigree Tree Generator in Python
Replicates the JavaScript functionality with Python/PIL rendering
"""

import os
import json
import re
import requests
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from PIL import Image, ImageDraw, ImageFont
import io
import sys

def log_pedigree_step(step_name: str, message: str, details: Any = None):
    """Structured console logger for tracing pedigree inputs, processing, and rendering steps."""
    timestamp = os.environ.get("CURRENT_TIME_STAMP", "LOG")
    detail_str = f" | Details: {json.dumps(details)}" if details is not None else ""
    print(f"[{timestamp}] [{step_name}] {message}{detail_str}", flush=True)


@dataclass
class Individual:
    """Represents an individual in the pedigree"""
    id: str
    name: str
    gender: str  # 'male', 'female', 'unknown'
    age: Optional[int]
    status: str  # 'unaffected', 'affected', 'carrier', 'deceased'
    conditions: List[str]
    deceased: bool
    generation: int


@dataclass
class Relationship:
    """Represents a relationship between individuals"""
    type: str  # 'marriage', 'parent-child', 'sibling'
    person1: str
    person2: str


class SimplePedigreeParser:
    """Regex-based parser for family descriptions (Python equivalent of JS version)"""
    
    def parse(self, text: str) -> Dict[str, Any]:
        """Parse natural language text into pedigree data structure"""
        individuals = []
        relationships = []
        
        # Extract individuals using patterns
        self.extract_individuals(text, individuals)
        
        # Extract relationships
        self.extract_relationships(text, individuals, relationships)
        
        # Organize generations properly
        self.organize_generations(individuals, relationships)
        
        # Group by generation
        gen_map = {}
        for individual in individuals:
            gen = individual.generation
            if gen not in gen_map:
                gen_map[gen] = []
            gen_map[gen].append(individual)
        
        generations = [
            {"generation": gen, "individuals": [asdict(ind) for ind in indivs]}
            for gen, indivs in sorted(gen_map.items())
        ]
        
        return {
            "individuals": [asdict(ind) for ind in individuals],
            "relationships": [asdict(rel) for rel in relationships],
            "generations": generations
        }
    
    def extract_individuals(self, text: str, individuals: List[Individual]):
        """Extract individuals from text using multiple patterns"""
        # Pattern 1: "David (40 M, carrier)" or "David (40, M, carrier)"
        pattern1 = r'(\w+)\s*\((\d+)[\s,]*([MF]|male|female|M|F)[\s,]*(carrier|affected|unaffected|deceased)?\)'
        for match in re.finditer(pattern1, text, re.IGNORECASE):
            name = match.group(1)
            age = int(match.group(2))
            gender = self.normalize_gender(match.group(3))
            status = match.group(4).lower() if match.group(4) else 'unaffected'
            
            individuals.append(Individual(
                id=name.lower(),
                name=name,
                gender=gender,
                age=age,
                status=status,
                conditions=[],
                deceased=(status == 'deceased'),
                generation=0
            ))
        
        # Pattern 2: "John is a 45-year-old male"
        pattern2 = r'(\w+)\s+is\s+a(?:n)?\s+(\d+)[-\s]year[-\s]old\s+(male|female)'
        for match in re.finditer(pattern2, text, re.IGNORECASE):
            name = match.group(1)
            age = int(match.group(2))
            gender = match.group(3).lower()
            
            # Check if already added
            if not any(i.name == name for i in individuals):
                individuals.append(Individual(
                    id=name.lower(),
                    name=name,
                    gender=gender,
                    age=age,
                    status='unaffected',
                    conditions=[],
                    deceased=False,
                    generation=0
                ))
        
        # Pattern 3: Children mentioned in various formats
        children_patterns = [
            r'children\s*[—\-:]\s*([^.]+)',
            r'have\s+(?:children|a\s+child|two\s+children|three\s+children|four\s+children|five\s+children)[—\-:\s]*([^.]+)',
            r'(?:son|daughter|child)(?:ren)?\s*[—\-:]\s*([^.]+)'
        ]
        
        for pattern in children_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                children_text = match.group(1)
                child_pattern = r'(\w+)\s*\((\d+)[\s,]*([MF]|male|female)[\s,]*(carrier|affected|unaffected|deceased)?\)'
                for child_match in re.finditer(child_pattern, children_text, re.IGNORECASE):
                    name = child_match.group(1)
                    age = int(child_match.group(2))
                    gender = self.normalize_gender(child_match.group(3))
                    status = child_match.group(4).lower() if child_match.group(4) else 'unaffected'
                    
                    # Don't add duplicates
                    if not any(i.name == name for i in individuals):
                        individuals.append(Individual(
                            id=name.lower(),
                            name=name,
                            gender=gender,
                            age=age,
                            status=status,
                            conditions=[],
                            deceased=(status == 'deceased'),
                            generation=1
                        ))
    
    def extract_relationships(self, text: str, individuals: List[Individual], relationships: List[Relationship]):
        """Extract relationships between individuals"""
        # Find parents (generation 0) and children (generation 1)
        parents = [i for i in individuals if i.generation == 0]
        children = [i for i in individuals if i.generation == 1]
        
        # Look for marriage patterns: "Alex and Beth" or "Alex (30 M, affected) and Beth (28 F, carrier)"
        marriage_pattern = r'(\w+)\s*\([^)]+\)\s+and\s+(\w+)\s*\([^)]+\)'
        marriage_match = re.search(marriage_pattern, text, re.IGNORECASE)
        
        if marriage_match:
            spouse1 = marriage_match.group(1)
            spouse2 = marriage_match.group(2)
            
            person1 = next((i for i in individuals if i.name == spouse1), None)
            person2 = next((i for i in individuals if i.name == spouse2), None)
            
            if person1 and person2:
                relationships.append(Relationship(
                    type="marriage",
                    person1=person1.id,
                    person2=person2.id
                ))
        elif len(parents) == 2:
            # Fallback: assume first two generation 0 individuals are married
            relationships.append(Relationship(
                type="marriage",
                person1=parents[0].id,
                person2=parents[1].id
            ))
        
        # Add parent-child relationships for all parents to all children
        for parent in parents:
            for child in children:
                relationships.append(Relationship(
                    type="parent-child",
                    person1=parent.id,
                    person2=child.id
                ))
    
    def organize_generations(self, individuals: List[Individual], relationships: List[Relationship]):
        """Organize individuals into proper generations based on relationships"""
        # Find individuals with parents
        has_parents = set()
        for rel in relationships:
            if rel.type == 'parent-child':
                has_parents.add(rel.person2)  # person2 is the child
        
        # Assign generation 0 to individuals with no parents
        for individual in individuals:
            if individual.id not in has_parents:
                individual.generation = 0
        
        # Propagate generations downward
        max_iterations = 5
        changed = True
        
        while changed and max_iterations > 0:
            changed = False
            max_iterations -= 1
            
            for rel in relationships:
                if rel.type == 'parent-child':
                    parent = next((i for i in individuals if i.id == rel.person1), None)
                    child = next((i for i in individuals if i.id == rel.person2), None)
                    
                    if parent and child:
                        expected_child_gen = parent.generation + 1
                        if child.generation != expected_child_gen:
                            child.generation = expected_child_gen
                            changed = True
    
    def normalize_gender(self, gender: str) -> str:
        """Normalize gender string to 'male', 'female', or 'unknown'"""
        g = gender.lower()
        if g in ['m', 'male']:
            return 'male'
        if g in ['f', 'female']:
            return 'female'
        return 'unknown'


class GeminiPedigreeParser:
    """AI-enhanced parser using Google Gemini API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.endpoints = [
            'https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent',
            'https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent',
            'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent',
        ]
    
    def parse_to_json(self, prompt: str) -> Dict[str, Any]:
        """Parse family description using Gemini AI"""
        log_pedigree_step("PEDIGREE_INPUT", "Processing raw family description input", {"prompt": prompt})

        system_prompt = """You are a medical genetics expert. Convert the following family description into a strictly valid JSON object for pedigree tree generation.

REQUIRED JSON STRUCTURE:
{
  "individuals": [
    {
      "id": "unique_id",
      "name": "Full Name",
      "gender": "male|female|unknown",
      "age": number|null,
      "status": "unaffected|affected|carrier|deceased",
      "conditions": ["condition1", "condition2"],
      "deceased": boolean,
      "generation": number
    }
  ],
  "relationships": [
    {
      "type": "marriage|parent-child|sibling",
      "person1": "id1",
      "person2": "id2"
    }
  ]
}

RULES:
1) Output ONLY raw JSON with double quotes; no markdown or prose.
2) Use lowercase names as ids (e.g., "john").
3) If information is missing, infer conservatively and keep fields valid.
4) Create BOTH parent-child links for each parent to each child.
5) Keep arrays present even if empty."""

        # Attempt 1: Standard SDK integration using google-generativeai client
        try:
            log_pedigree_step("PEDIGREE_AI_REQUEST", "Attempting SDK-based generative model parsing", {"model": "gemini-2.5-flash"})
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(f"{system_prompt}\n\nFAMILY DESCRIPTION:\n{prompt}")
            text = response.text
            log_pedigree_step("PEDIGREE_AI_RESPONSE", "Received raw text from SDK client", {"text": text[:300]})
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                parsed = json.loads(json_match.group(0))
                return self.validate_and_clean_json(parsed)
        except Exception as sdk_err:
            log_pedigree_step("PEDIGREE_SDK_WARNING", "SDK parsing failed or import error; falling back to direct endpoints", {"error": str(sdk_err)})

        # Attempt 2: REST fallback endpoints
        body = {
            "contents": [{
                "parts": [{"text": f"{system_prompt}\n\nFAMILY DESCRIPTION:\n{prompt}"}]
            }]
        }
        
        last_error = None
        for endpoint in self.endpoints:
            try:
                log_pedigree_step("PEDIGREE_HTTP_REQUEST", f"POST query to direct REST endpoint", {"url": endpoint})
                response = requests.post(
                    f"{endpoint}?key={self.api_key}",
                    headers={"Content-Type": "application/json"},
                    json=body,
                    timeout=45
                )
                if not response.ok:
                    last_error = Exception(f"Gemini API HTTP error: {response.status_code}")
                    continue
                
                data = response.json()
                text = ""
                if "candidates" in data and data["candidates"]:
                    parts = data["candidates"][0].get("content", {}).get("parts", [])
                    text = "".join([p.get("text", "") for p in parts])
                
                log_pedigree_step("PEDIGREE_AI_RESPONSE", "Received raw text from REST fallback", {"text": text[:300]})
                json_match = re.search(r'\{[\s\S]*\}', text)
                if not json_match:
                    last_error = Exception("No valid JSON found in response")
                    continue
                
                parsed = json.loads(json_match.group(0))
                return self.validate_and_clean_json(parsed)
                
            except Exception as e:
                last_error = e
        
        log_pedigree_step("PEDIGREE_AI_FATAL", "All pedigree parser execution routes exhausted", {"last_error": str(last_error)})
        raise last_error or Exception("Gemini API failed on all endpoints")
    
    def validate_and_clean_json(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean the JSON structure"""
        log_pedigree_step("PEDIGREE_VALIDATE_START", "Starting data cleaning and schema validation")
        if "individuals" not in data or not isinstance(data["individuals"], list):
            raise ValueError("Invalid JSON: missing individuals array")
        
        if "relationships" not in data or not isinstance(data["relationships"], list):
            data["relationships"] = []
        
        # Validate individuals
        valid_ids = set()
        for i, person in enumerate(data["individuals"]):
            person["id"] = person.get("id") or person.get("name", "").lower() or f"person_{i}"
            person["name"] = person.get("name") or f"Person {i + 1}"
            person["gender"] = person.get("gender", "unknown")
            if person["gender"] not in ["male", "female", "unknown"]:
                person["gender"] = "unknown"
            person["status"] = person.get("status", "unaffected")
            if person["status"] not in ["unaffected", "affected", "carrier", "deceased", "unknown"]:
                person["status"] = "unaffected"
            person["deceased"] = person.get("deceased", False) or person.get("status") == "deceased"
            person["conditions"] = person.get("conditions", [])
            if not isinstance(person["conditions"], list):
                person["conditions"] = []
            person["generation"] = person.get("generation", 0)
            valid_ids.add(person["id"])
        
        # Validate relationships
        data["relationships"] = [
            rel for rel in data["relationships"]
            if rel.get("type") in ["marriage", "parent-child", "sibling"]
            and rel.get("person1") in valid_ids
            and rel.get("person2") in valid_ids
        ]
        
        log_pedigree_step("PEDIGREE_VALIDATE_COMPLETE", "Schema validation succeeded", {
            "total_individuals": len(data["individuals"]),
            "total_relationships": len(data["relationships"])
        })
        return data


class PedigreeRenderer:
    """Renders pedigree trees using PIL/Pillow (Python equivalent of Fabric.js renderer)"""
    
    def __init__(self, width: int = 800, height: int = 600):
        self.width = width
        self.height = height
        self.symbol_size = 30
        self.generation_spacing = 100
        self.individual_spacing = 80
        self.colors = {
            "male": "#ffffff",
            "female": "#ffffff",
            "affected": "#000000",
            "carrier": "#666666",
            "deceased": "#ffffff",
            "border": "#000000",
            "connection": "#000000",
            "text": "#333333"
        }
        self.positions = {}
    
    def render(self, pedigree_data: Dict[str, Any]) -> Image.Image:
        """Render pedigree data into a PIL Image"""
        # Create image with white background
        img = Image.new("RGB", (self.width, self.height), "white")
        draw = ImageDraw.Draw(img)
        
        # Try to load a font, fallback to default if not available
        try:
            font_name = ImageFont.truetype("arial.ttf", 12)
            font_age = ImageFont.truetype("arial.ttf", 10)
        except:
            try:
                font_name = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
                font_age = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 10)
            except:
                font_name = ImageFont.load_default()
                font_age = ImageFont.load_default()
        
        # Calculate positions
        self.calculate_positions(pedigree_data)
        
        # Draw connections first (so they appear behind symbols)
        self.draw_connections(draw, pedigree_data)
        
        # Draw individuals
        self.draw_individuals(draw, pedigree_data, font_name, font_age)
        
        return img
    
    def calculate_positions(self, pedigree_data: Dict[str, Any]):
        """Calculate positions for all individuals"""
        self.positions = {}
        
        generations = pedigree_data.get("generations", [])
        if not generations:
            # If no generations, try to organize by generation field
            individuals = pedigree_data.get("individuals", [])
            gen_map = {}
            for ind in individuals:
                gen = ind.get("generation", 0)
                if gen not in gen_map:
                    gen_map[gen] = []
                gen_map[gen].append(ind)
            generations = [
                {"generation": gen, "individuals": indivs}
                for gen, indivs in sorted(gen_map.items())
            ]
        
        # --- Topological-like sorting to prevent line crossings ---
        relationships = pedigree_data.get("relationships", [])
        
        # Build child-to-parents map
        child_to_parents = {}
        for rel in relationships:
            is_rel_dict = hasattr(rel, "get")
            if (rel.get("type") if is_rel_dict else getattr(rel, "type", "")) == "parent-child":
                child = rel.get("person2") if is_rel_dict else getattr(rel, "person2", "")
                parent = rel.get("person1") if is_rel_dict else getattr(rel, "person1", "")
                if child not in child_to_parents:
                    child_to_parents[child] = []
                child_to_parents[child].append(parent)
        
        # Sort each generation's individuals bottom-to-top
        sorted_gen_indices = sorted([g.get("generation", 0) for g in generations], reverse=True)
        gen_by_index = {g.get("generation", 0): g for g in generations}
        
        if sorted_gen_indices:
            # Sort bottom generation (keep patient/proband first)
            bottom_idx = sorted_gen_indices[0]
            bottom_gen = gen_by_index[bottom_idx]
            indivs = bottom_gen.get("individuals", [])
            
            def bottom_key(ind):
                name = (ind.get("name") if hasattr(ind, "get") else getattr(ind, "name", "")).lower()
                ind_id = (ind.get("id") if hasattr(ind, "get") else getattr(ind, "id", "")).lower()
                if "patient" in name or "proband" in name or "patient" in ind_id or "proband" in ind_id:
                    return 0
                return 1
            bottom_gen["individuals"] = sorted(indivs, key=bottom_key)
            
        # Walk up generations and sort parents according to child order
        for idx in range(len(sorted_gen_indices) - 1):
            current_gen_idx = sorted_gen_indices[idx]
            parent_gen_idx = sorted_gen_indices[idx + 1]
            
            current_gen = gen_by_index[current_gen_idx]
            parent_gen = gen_by_index[parent_gen_idx]
            
            ordered_children = current_gen.get("individuals", [])
            parent_individuals = parent_gen.get("individuals", [])
            
            new_parent_order = []
            seen_parents = set()
            
            for child in ordered_children:
                child_id = child.get("id") if hasattr(child, "get") else getattr(child, "id", None)
                parents_of_child = child_to_parents.get(child_id, [])
                
                # Fetch parent objects
                sorted_parents = []
                for p_id in parents_of_child:
                    p_obj = next((p for p in parent_individuals if (p.get("id") if hasattr(p, "get") else getattr(p, "id", None)) == p_id), None)
                    if p_obj:
                        sorted_parents.append(p_obj)
                
                # Sort parents: male (father) on the left, female (mother) on the right
                def gender_key(p):
                    g = (p.get("gender") if hasattr(p, "get") else getattr(p, "gender", "")).lower()
                    if g == "male":
                        return 0
                    if g == "female":
                        return 1
                    return 2
                sorted_parents = sorted(sorted_parents, key=gender_key)
                
                for p in sorted_parents:
                    p_id = p.get("id") if hasattr(p, "get") else getattr(p, "id", None)
                    if p_id not in seen_parents:
                        new_parent_order.append(p)
                        seen_parents.add(p_id)
            
            # Add any leftover parent individuals (e.g. aunts, uncles with no children in chart)
            for p in parent_individuals:
                p_id = p.get("id") if hasattr(p, "get") else getattr(p, "id", None)
                if p_id not in seen_parents:
                    new_parent_order.append(p)
                    seen_parents.add(p_id)
            
            parent_gen["individuals"] = new_parent_order
        # -------------------------------------------------------------
        
        for gen_data in generations:
            gen_index = gen_data.get("generation", 0)
            individuals = gen_data.get("individuals", [])
            y = 50 + (gen_index * self.generation_spacing)
            
            total_width = (len(individuals) - 1) * self.individual_spacing if len(individuals) > 1 else 0
            start_x = (self.width - total_width) / 2
            
            for idx, individual in enumerate(individuals):
                x = start_x + (idx * self.individual_spacing) if len(individuals) > 1 else self.width / 2
                is_dict_like = hasattr(individual, "get")
                ind_id = individual.get("id") if is_dict_like else getattr(individual, "id", None)
                self.positions[ind_id] = (x, y)
    
    def draw_connections(self, draw: ImageDraw.Draw, pedigree_data: Dict[str, Any]):
        """Draw relationship connections"""
        relationships = pedigree_data.get("relationships", [])
        
        # Draw marriage connections
        marriages = [r for r in relationships if r["type"] == "marriage"]
        for marriage in marriages:
            pos1 = self.positions.get(marriage["person1"])
            pos2 = self.positions.get(marriage["person2"])
            if pos1 and pos2:
                draw.line([pos1[0], pos1[1], pos2[0], pos2[1]], 
                         fill=self.colors["connection"], width=2)
                # Marriage symbol (small square in middle)
                mid_x = (pos1[0] + pos2[0]) / 2
                mid_y = (pos1[1] + pos2[1]) / 2
                draw.rectangle([mid_x - 3, mid_y - 3, mid_x + 3, mid_y + 3],
                              fill=self.colors["border"], outline=None)
        
        # Draw parent-child connections
        parent_child_rels = [r for r in relationships if r["type"] == "parent-child"]
        
        # Group by child
        child_to_parents = {}
        for rel in parent_child_rels:
            child_id = rel["person2"]
            parent_id = rel["person1"]
            if child_id not in child_to_parents:
                child_to_parents[child_id] = []
            child_to_parents[child_id].append(parent_id)
        
        for child_id, parent_ids in child_to_parents.items():
            child_pos = self.positions.get(child_id)
            if not child_pos:
                continue
            
            if len(parent_ids) == 1:
                # Single parent
                parent_pos = self.positions.get(parent_ids[0])
                if parent_pos:
                    draw.line([parent_pos[0], parent_pos[1] + self.symbol_size/2,
                              child_pos[0], child_pos[1] - self.symbol_size/2],
                             fill=self.colors["connection"], width=2)
            elif len(parent_ids) == 2:
                # Both parents
                parent1_pos = self.positions.get(parent_ids[0])
                parent2_pos = self.positions.get(parent_ids[1])
                
                if parent1_pos and parent2_pos:
                    mid_x = (parent1_pos[0] + parent2_pos[0]) / 2
                    mid_y = (parent1_pos[1] + parent2_pos[1]) / 2
                    
                    # Vertical line from parents' midpoint down
                    draw.line([mid_x, mid_y + 20, mid_x, child_pos[1] - 20],
                             fill=self.colors["connection"], width=2)
                    # Horizontal line to child
                    draw.line([mid_x, child_pos[1] - 20, child_pos[0], child_pos[1] - 20],
                             fill=self.colors["connection"], width=2)
                    # Final vertical line to child
                    draw.line([child_pos[0], child_pos[1] - 20,
                              child_pos[0], child_pos[1] - self.symbol_size/2],
                             fill=self.colors["connection"], width=2)
    
    def draw_individuals(self, draw: ImageDraw.Draw, pedigree_data: Dict[str, Any],
                        font_name, font_age):
        """Draw all individual symbols"""
        for individual in pedigree_data.get("individuals", []):
            is_dict_like = hasattr(individual, "get")
            ind_id = individual.get("id") if is_dict_like else getattr(individual, "id", None)
            pos = self.positions.get(ind_id)
            if not pos:
                continue
            
            x, y = pos
            # Convert to dictionary safely
            ind_dict = {}
            if is_dict_like:
                try:
                    ind_dict = dict(individual.items())
                except Exception:
                    ind_dict = individual
            else:
                try:
                    ind_dict = asdict(individual)
                except Exception:
                    ind_dict = individual
            
            self.draw_symbol(draw, ind_dict, x, y, font_name, font_age)
    
    def draw_symbol(self, draw: ImageDraw.Draw, individual: Dict[str, Any],
                   x: float, y: float, font_name, font_age):
        """Draw a single individual symbol"""
        size = self.symbol_size
        half_size = size / 2
        
        # Determine fill color
        if individual["status"] == "affected":
            fill = self.colors["affected"]
        elif individual["status"] == "carrier":
            fill = self.colors["male"]  # Will add dot overlay
        else:
            fill = self.colors["male"] if individual["gender"] == "male" else self.colors["female"]
        
        # Draw base shape
        if individual["gender"] == "male":
            # Square
            draw.rectangle([x - half_size, y - half_size, x + half_size, y + half_size],
                          fill=fill, outline=self.colors["border"], width=2)
        elif individual["gender"] == "female":
            # Circle
            draw.ellipse([x - half_size, y - half_size, x + half_size, y + half_size],
                        fill=fill, outline=self.colors["border"], width=2)
        else:
            # Diamond for unknown gender
            points = [
                (x, y - half_size),
                (x + half_size, y),
                (x, y + half_size),
                (x - half_size, y)
            ]
            draw.polygon(points, fill=fill, outline=self.colors["border"], width=2)
        
        # Add special markings
        if individual["status"] == "carrier":
            # Carrier dot in center
            draw.ellipse([x - 4, y - 4, x + 4, y + 4],
                        fill=self.colors["carrier"], outline=None)
        
        if individual["status"] == "unknown":
            # Draw "?" inside symbol to indicate unknown disease status
            bbox = draw.textbbox((0, 0), "?", font=font_name)
            t_w = bbox[2] - bbox[0]
            t_h = bbox[3] - bbox[1]
            draw.text((x - t_w/2, y - t_h/2 - 2), "?", fill=self.colors["text"], font=font_name)

        if individual.get("deceased") or individual["status"] == "deceased":
            # Deceased diagonal line
            draw.line([x - half_size, y - half_size, x + half_size, y + half_size],
                     fill=self.colors["border"], width=2)
        
        # Add labels with word-wrapping
        name = individual["name"]
        words = name.split()
        lines = []
        current_line = []
        for word in words:
            if len(" ".join(current_line + [word])) > 12:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
            else:
                current_line.append(word)
        if current_line:
            lines.append(" ".join(current_line))
            
        y_offset = y + half_size + 5
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_name)
            t_w = bbox[2] - bbox[0]
            t_h = bbox[3] - bbox[1]
            draw.text((x - t_w/2, y_offset), line, fill=self.colors["text"], font=font_name)
            y_offset += t_h + 2
        
        # Age
        if individual.get("age"):
            age_text = f"{individual['age']}y"
            bbox = draw.textbbox((0, 0), age_text, font=font_age)
            text_width = bbox[2] - bbox[0]
            draw.text((x - text_width/2, y_offset),
                     age_text, fill="#666666", font=font_age)
    
    def export_as_png(self, pedigree_data: Dict[str, Any]) -> bytes:
        """Export pedigree as PNG bytes"""
        img = self.render(pedigree_data)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()


class PedigreeGenerator:
    """Main pedigree generator class that orchestrates parsing and rendering"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.simple_parser = SimplePedigreeParser()
        self.gemini_parser = GeminiPedigreeParser(api_key) if api_key else None
        self.renderer = PedigreeRenderer()
    
    def parse_family_description(self, description: str, use_ai: bool = True) -> Dict[str, Any]:
        """
        Parse natural language family description into structured pedigree data
        
        Args:
            description: Natural language description of family tree
            use_ai: Whether to use Gemini AI (if available) or fallback to simple parser
            
        Returns:
            Dictionary with 'individuals', 'relationships', and 'generations'
        """
        if use_ai and self.gemini_parser:
            try:
                json_data = self.gemini_parser.parse_to_json(description)
                # Organize generations
                return self._organize_generations(json_data)
            except Exception as e:
                log_pedigree_step("PEDIGREE_PARSE_WARNING", "AI parsing failed; falling back to simple regex parser", {"error": str(e)})
        
        # Fallback to simple parser
        log_pedigree_step("PEDIGREE_FALLBACK", "Using regex simple parser fallback")
        return self.simple_parser.parse(description)
    
    def _organize_generations(self, pedigree_data: Dict[str, Any]) -> Dict[str, Any]:
        """Organize individuals into proper generations"""
        log_pedigree_step("PEDIGREE_ORGANIZE_START", "Organizing pedigree individuals into generations")
        individuals = pedigree_data["individuals"]
        relationships = pedigree_data.get("relationships", [])
        
        # Find individuals with no parents (generation 0)
        has_parents = set()
        for rel in relationships:
            if rel.get("type") == "parent-child":
                has_parents.add(rel.get("person2"))
        
        # Assign generation 0 to roots
        for individual in individuals:
            is_dict_like = hasattr(individual, "get")
            ind_id = individual.get("id") if is_dict_like else getattr(individual, "id", None)
            if ind_id not in has_parents:
                if is_dict_like:
                    individual["generation"] = 0
                else:
                    try:
                        individual.generation = 0
                    except Exception:
                        pass
            else:
                if is_dict_like:
                    individual["generation"] = -1  # Will be calculated
                else:
                    try:
                        individual.generation = -1
                    except Exception:
                        pass
        
        # Propagate generations downward
        max_iterations = 10
        changed = True
        
        while changed and max_iterations > 0:
            changed = False
            max_iterations -= 1
            
            for rel in relationships:
                is_rel_dict = hasattr(rel, "get")
                if (rel.get("type") if is_rel_dict else getattr(rel, "type", None)) == "parent-child":
                    parent_id = rel.get("person1") if is_rel_dict else getattr(rel, "person1", None)
                    child_id = rel.get("person2") if is_rel_dict else getattr(rel, "person2", None)
                    
                    parent = next((i for i in individuals 
                                 if (i.get("id") if hasattr(i, "get") else getattr(i, "id", None)) == parent_id), None)
                    child = next((i for i in individuals 
                                if (i.get("id") if hasattr(i, "get") else getattr(i, "id", None)) == child_id), None)
                    
                    if parent and child:
                        parent_is_dict = hasattr(parent, "get")
                        child_is_dict = hasattr(child, "get")
                        parent_gen = parent.get("generation") if parent_is_dict else getattr(parent, "generation", -1)
                        if parent_gen >= 0:
                            expected_gen = parent_gen + 1
                            child_gen = child.get("generation") if child_is_dict else getattr(child, "generation", -1)
                            if child_gen != expected_gen:
                                if child_is_dict:
                                    child["generation"] = expected_gen
                                else:
                                    try:
                                        child.generation = expected_gen
                                    except Exception:
                                        pass
                                changed = True
        
        # Group by generation
        generations = {}
        for individual in individuals:
            is_ind_dict = hasattr(individual, "get")
            gen = max(0, individual.get("generation") if is_ind_dict else getattr(individual, "generation", 0))
            if gen not in generations:
                generations[gen] = []
            generations[gen].append(individual)
        
        pedigree_data["generations"] = [
            {"generation": gen, "individuals": indivs}
            for gen, indivs in sorted(generations.items())
        ]
        
        log_pedigree_step("PEDIGREE_ORGANIZE_COMPLETE", "Successfully sorted individuals into generations", {
            "generations_count": len(pedigree_data["generations"])
        })
        return pedigree_data
    
    def generate_image(self, pedigree_data: Dict[str, Any]) -> Image.Image:
        """Generate PIL Image from pedigree data"""
        return self.renderer.render(pedigree_data)
    
    def generate_png_bytes(self, pedigree_data: Dict[str, Any]) -> bytes:
        """Generate PNG bytes from pedigree data"""
        return self.renderer.export_as_png(pedigree_data)
