# VariantMind: Intelligent Variant Curation & Pedigree Workbench

VariantMind is a production-grade web application for genetic counselors, clinical geneticists, and researchers. It features AI-assisted variant interpretation, batch VCF processing with differential prompting context, multi-patient session management, and pedigree chart generation.

The application is structured as a **FastAPI backend** and a modern **React (Vite) frontend**.

---

## 🏛️ Architecture Overview

```
chatbot-genetic-counsellor/
├── api/                       # FastAPI Backend
│   ├── routers/
│   │   ├── chat.py           # Differential context mode, AI conversation & tools router
│   │   ├── conversations.py  # Conversation history management
│   │   └── upload.py         # Multi-patient VCF upload router (max 3 files, 25/file cap)
│   └── main.py                # Backend application entry point
├── frontend/                  # React Frontend (Vite + Vanilla CSS)
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatArea.jsx          # Live Chat UI, patient labels, context trigger
│   │   │   ├── MessageBubble.jsx     # Markdown rendering, expandable details tabs
│   │   │   ├── Sidebar.jsx           # Conversation management & search
│   │   │   ├── VariantDetailsTabs.jsx # Predictors, frequencies & submissions tabs
│   │   │   └── VcfVariantTable.jsx   # 5-per-page paginated variant viewer with search
│   │   ├── services/
│   │   │   └── api.js                # API client integration
│   │   ├── App.jsx                   # Main layout container
│   │   └── index.css                 # Color palettes, custom typography & CSS variables
├── core/                      # Core Genomics Logic
│   ├── api_clients.py         # MyVariant.info, VEP, ClinVar, PubMed, and ClinGen integrations
│   ├── gemini_client.py       # Google Gemini agent configuration & 5 tool schemas
│   ├── history_db.py          # SQLite database wrapper for persistent chat & VCF tracking
│   └── query_router.py        # Regex classifier for HGVS, rsID, and genes
├── analysis/                  # Variant Processing & Prioritization
│   ├── vcf_parser.py          # Robust VCF parser (QUAL checks & chr prefix stripping)
│   ├── vcf_prioritizer.py     # Variant prioritizer, gene cluster analyser, and data enricher
│   └── variant_analyser.py    # Single variant analysis orchestrator
├── tests/                     # Developer Testing Suite
│   ├── test_integration_v2.py # Comprehensive 38-check integration & scenario suite
│   ├── test_qa_full.py        # 26-check unit & regression test suite
│   └── test_all_input_types.py# Regex query router tests
└── data/                      # Demo Clinical Datasets
    ├── demo_500_variants.vcf  # Large VCF for batching limits validation
    ├── demo_annotated.vcf     # Annotated VCF featuring CFTR, HBB, and BRCA1 variants
    └── demo_unannotated.vcf   # Unannotated VCF for coordinates pipeline testing
```

---

## 🛠️ Installation & Setup

### Prerequisites
* Python 3.9+
* Node.js 18+
* Google Gemini API Key

### Backend Setup
1. From the project root, install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your Gemini API key in your terminal session or environment variables:
   * **Windows (PowerShell)**:
     ```powershell
     $env:GEMINI_API_KEY="your-api-key-here"
     ```
   * **Linux/macOS**:
     ```bash
     export GEMINI_API_KEY="your-api-key-here"
     ```
3. Run the backend development server (listens on port 8000):
   ```bash
   uvicorn api.main:app --port 8000 --reload
   ```

### Frontend Setup
1. Navigate to the `frontend/` directory:
   ```bash
   cd frontend
   ```
2. Install Node packages:
   ```bash
   npm install
   ```
3. Start the Vite local server:
   ```bash
   npm run dev
   ```
4. Access the web app in your browser at `http://localhost:5173/`.

---

## 🔬 Core Systems

### 1. Differential Prompting Context Modes
To maintain high responsiveness and stay within strict model token efficiency, VariantMind dynamically adjusts context details based on variant count:
* **Deep Context Mode (≤ 35 variants across all files)**: The LLM prompt is injected with full annotated records including SIFT, PolyPhen, CADD, REVEL, 8 population frequency ancestries, and ClinVar submissions.
* **Basic Context Mode (> 35 variants)**: The prompt is injected with a compact Markdown table. The LLM uses `read_enriched_data` proactively to retrieve full annotations on-demand.

### 2. Multi-Patient Session uploads (Max 3 files)
- Enables trio analysis (Proband + Sibling + Mother).
- Up to 3 VCFs can be uploaded simultaneously under the same conversation ID.
- Each VCF is capped at `PER_FILE_CAP = 25` variants for processing efficiency.
- A 4th upload attempt is automatically rejected with a clean `HTTP 409 Conflict`.

### 3. Integrated AI Agent Tools (5 tools)
VariantMind's LLM agent is equipped with five tools to gather live literature and drill into local variant files:
1. `read_patient_vcf`: Read raw coordinate segments from uploaded VCF files.
2. `read_enriched_data`: Read cached annotator data (predictors, frequencies) instantly.
3. `Clinical_Variant_Analyzer`: Fetch live details from MyVariant, VEP, and ClinVar for novel variants.
4. `search_pubmed`: Perform targeted search queries for literature.
5. `create_pedigree_chart`: Generate pedigree metadata to render family histories.

---

## 🧪 Running Developer Test Suites

VariantMind has two developer test suites to prevent regressions and verify API contracts:

### 1. Unit & Regression Tests (`test_qa_full.py`)
Runs 26 checks validating individual modules like VCF parsers, API endpoints, dbNSFP parsing, VEP batch chunking, and SQLite history tracking.
```bash
$env:PYTHONPATH="."
python tests/test_qa_full.py
```

### 2. End-to-End & Integration Tests (`test_integration_v2.py`)
Runs 38 checks testing frontend-backend contracts, patient isolation, pedigree triggers, and simulated clinical scenarios:
* **Scenario A (Family Trio)**: Simulates uploading Proband, Sibling, and Mother files, verifying that the AI isolates patients and maps variant classifications correctly.
* **Scenario B (Researcher Search)**: Verifies variant routing triggers without context leaks.
* **Scenario C (Pedigree Session)**: Verifies automated pedigree generation from family descriptors.
```bash
$env:PYTHONPATH="."
python tests/test_integration_v2.py
```

---

*For Research and Educational Use Only. Ensure all clinical decisions are confirmed by a board-certified professional.*
