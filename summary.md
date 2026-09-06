# Hiring Agent — Repository Summary

> **What this project is:** A **Resume-to-Score pipeline** that converts a PDF résumé into a structured JSON object, enriches it with live GitHub signals, then asks an LLM to produce a fair, explainable evaluation score against a configurable role rubric.
>
> Originally built at HackerRank to rank ~50,000–60,000 intern applications per year. Open-sourced as a transparent, auditable alternative to black-box ATS tools.

---

## Table of Contents

1. [End-to-End Flow](#end-to-end-flow)
2. [Architecture Diagram](#architecture-diagram)
3. [File Index](#file-index)
4. [Provider Support](#provider-support)
5. [Development Mode](#development-mode)
6. [How to Add a New Role](#how-to-add-a-new-role)
7. [Dependencies](#dependencies)

---

## End-to-End Flow

```
User CLI
  │
  ▼
score.py                          ← Entry point. Parses args, wires all stages.
  │
  ├─ 1. PDF → Markdown
  │     pymupdf_rag.py            ← Converts PDF pages to Markdown-like text
  │     pdf.py (PDFHandler)       ← Per-section LLM extraction using Jinja templates
  │       └─ prompts/templates/   ← basics / work / education / skills / projects / awards
  │           └─ → JSONResume     ← Pydantic model assembled in models.py
  │
  ├─ 2. GitHub Enrichment
  │     github.py                 ← Extracts GitHub username from resume profiles,
  │                                  fetches profile + repos via GitHub API,
  │                                  asks LLM to pick the top-7 most relevant projects
  │
  ├─ 3. Text Serialisation
  │     transform.py              ← convert_json_resume_to_text()
  │                                  convert_github_data_to_text()
  │                                  convert_blog_data_to_text()
  │                                  All merged into one big evaluation string
  │
  ├─ 4. Evaluation
  │     evaluator.py (ResumeEvaluator)
  │       ├─ roles/<role>/criteria.jinja       ← Scoring rubric prompt
  │       ├─ roles/<role>/system_message.jinja ← System-level instructions
  │       └─ → LLM call → EvaluationData      ← Pydantic model built dynamically by models.py
  │
  └─ 5. Output
        score.py:print_evaluation_results()   ← Pretty-prints to stdout
        transform.py:transform_evaluation_response()  ← CSV row
        resume_evaluations_<role>.csv         ← Appended (dev mode only)
        cache/resumecache_<name>.json         ← PDF extraction cache (dev mode)
        cache/githubcache_<name>.json         ← GitHub fetch cache (dev mode)
```

### Stage-by-Stage Detail

| # | Stage | Key Input | Key Output |
|---|-------|-----------|------------|
| 1 | **PDF → Markdown** | `.pdf` file | Plain Markdown text per page |
| 2 | **Section Extraction** | Markdown text + Jinja prompts | `JSONResume` Pydantic object |
| 3 | **GitHub Enrichment** | GitHub URL from resume | Dict with profile + selected repos |
| 4 | **Text Assembly** | `JSONResume` + GitHub dict | Single plain-text string for the evaluator |
| 5 | **LLM Evaluation** | Text string + role rubric | `EvaluationData` Pydantic object |
| 6 | **Output** | `EvaluationData` + `Role` | Terminal report + (optionally) CSV row |

---

## Architecture Diagram

```
providers.json ──► config.py ──► llm_utils.py ──► OpenAICompatibleProvider (models.py)
                                                         │
                                                    HTTP POST /chat/completions
                                                         │
            ┌────────────────────────────────────────────┤
            │                                            │
          pdf.py                                  evaluator.py
     (section extraction)                       (resume scoring)
            │                                            │
     prompts/templates/                     roles/<name>/criteria.jinja
            │                               roles/<name>/system_message.jinja
     prompts/template_manager.py                         │
                                             models.build_evaluation_model()
                                                    (dynamic Pydantic schema)
```

---

## File Index

### Root-level Python Modules

#### `score.py`
**The main entry point.** Orchestrates the entire pipeline end-to-end.

- Parses CLI arguments (`pdf_path`, `--role`, `--init-role`).
- Loads or scaffolds a `Role` via `roles.py`.
- Checks for cached PDF extraction and GitHub data under `cache/` (dev mode).
- Calls `PDFHandler.extract_json_from_pdf()` → `fetch_and_display_github_info()` → `_evaluate_resume()`.
- Calls `print_evaluation_results()` to display the final score.
- When `DEVELOPMENT_MODE=True`, appends a row to `resume_evaluations_<role>.csv`.

**CLI usage:**
```bash
python score.py ./resume/sample.pdf --role software_engineering_intern
python score.py --init-role backend_engineer   # scaffolds a new role
```

---

#### `pdf.py`
**Converts a PDF into a structured `JSONResume` object.**

- Contains the `PDFHandler` class.
- Uses `pymupdf_rag.py` to convert the PDF to Markdown.
- Calls the LLM once per resume section (basics, work, education, skills, projects, awards) using the Jinja templates from `prompts/templates/`.
- Merges section responses into a single `JSONResume` Pydantic model.
- Retries on parse failures, handles partial extraction gracefully.

---

#### `pymupdf_rag.py`
**Low-level PDF-to-Markdown converter** (~1,300 lines).

- Wraps [PyMuPDF](https://pymupdf.readthedocs.io/) and [pymupdf4llm](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/).
- Converts PDF pages to readable Markdown-style text, handling headings, links, tables, and basic formatting.
- Used exclusively by `pdf.py`.

---

#### `github.py`
**Fetches and enriches GitHub profile and repository data.**

- Extracts the GitHub username from the resume's `profiles` list.
- Calls the GitHub REST API (with optional `GITHUB_TOKEN` for higher rate limits).
- Fetches repos, computes commit counts, classifies project types.
- Asks the LLM (via `github_project_selection.jinja`) to select exactly **7 unique, high-signal projects**.
- Returns a dict with `profile` and `selected_projects` keys, used downstream by `transform.py`.

---

#### `evaluator.py`
**LLM-powered resume scorer.**

- Contains the `ResumeEvaluator` class.
- Initializes the LLM provider via `llm_utils.initialize_llm_provider()`.
- Renders `role.criteria_source` (via `TemplateManager`) into the evaluation prompt.
- Makes a structured-output LLM call with the role's dynamic Pydantic JSON schema as the `format` constraint.
- Parses the JSON response back into the role-specific `EvaluationData` Pydantic model.

---

#### `roles.py`
**Loads, validates, and scaffolds role definitions.**

- Defines the `Category` and `Role` dataclasses.
- `load_role(name)` — reads `roles/<name>/role.json`, `criteria.jinja`, and `system_message.jinja`; returns a fully-validated `Role` object.
- `list_available_roles()` — scans the `roles/` directory.
- `scaffold_role(name)` — creates a new `roles/<name>/` directory with placeholder files ready to edit (called via `--init-role`).

---

#### `models.py`
**All Pydantic data models and the LLM provider implementation.**

Key classes:

| Class | Purpose |
|-------|---------|
| `LLMProvider` | Protocol (interface) all providers must satisfy |
| `JSONResume` | Complete résumé structure (JSON Resume standard) |
| `Basics`, `Work`, `Education`, `Skill`, `Project`, `Award`, … | Section-level sub-models |
| `CategoryScore` | Score + max + evidence for one rubric category |
| `Deductions` | Total deduction amount + reasons |
| `GitHubProfile` | GitHub profile data shape |
| `OpenAICompatibleProvider` | Generic HTTP provider — POSTs to `{base_url}/chat/completions`; handles retries, rate-limit backoff (429), transient server errors (5xx), and structured-output formatting |
| `build_scores_model(categories)` | Dynamically creates a `Scores` Pydantic model with one field per role category |
| `build_evaluation_model(role)` | Builds the full `EvaluationData` model (scores + bonus + deductions + strengths/improvements) |

---

#### `transform.py`
**Data transformation and serialisation utilities** (~850 lines).

- `convert_json_resume_to_text()` — converts a `JSONResume` to a readable text block for the evaluator.
- `convert_github_data_to_text()` — serialises selected GitHub projects to text.
- `convert_blog_data_to_text()` — serialises blog/portfolio data to text.
- `transform_evaluation_response()` — flattens an `EvaluationData` object + resume data into a `dict` row suitable for CSV export.
- Various normalisation helpers for dates, URLs, lists, etc.

---

#### `llm_utils.py`
**LLM provider bootstrapping and response cleanup utilities.**

- `initialize_llm_provider(model_name)` — calls `config.provider_for(model_name)` then constructs and returns an `OpenAICompatibleProvider`.
- `extract_json_from_response(text)` — strips markdown code fences (` ```json … ``` `) and `<think>…</think>` reasoning blocks from LLM responses before JSON parsing.

---

#### `config.py`
**Configuration loader — the single source of truth for provider/model resolution.**

- Loads `.env` via `python-dotenv`.
- Reads `providers.json` and exposes:
  - `DEFAULT_MODEL` — overridable by the `DEFAULT_MODEL` env var.
  - `MODEL_PARAMETERS` — flat `{model_name: {temperature, top_p}}` map.
  - `provider_for(model_name)` — resolves a model name to `{base_url, api_key, structured_output, extra_body}`; raises `ValueError` for unknown models or missing API keys.
- `DEVELOPMENT_MODE = True` flag controls caching and CSV export.

---

#### `prompt.py`
**Thin re-export shim.**

- Re-exports `DEFAULT_MODEL` and `MODEL_PARAMETERS` from `config.py` so legacy import paths in `evaluator.py`, `pdf.py`, `github.py`, and `score.py` continue to work without change.

---

### Configuration & Environment

#### `providers.json`
**The single source of truth for all LLM providers and models.**

Supported out of the box:

| Provider | Base URL | Models |
|----------|----------|--------|
| `ollama` | `http://localhost:11434/v1` | `qwen3:1.7b`, `gemma3:1b`, `qwen3:4b`, `gemma3:4b`, `gemma3:12b`, `gemma4:latest`, `mistral:7b` |
| `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.5-pro` |
| `anthropic` | `https://api.anthropic.com/v1` | `claude-opus-4-8`, `claude-sonnet-5`, `claude-haiku-4-5` |

Adding a new provider requires **zero Python changes** — just add an entry to this file.

---

#### `.env.example`
Template environment file. Copy to `.env` and fill in values:

```bash
DEFAULT_MODEL=gemma4:latest
GEMINI_API_KEY=your_key_here
```

---

#### `.python-version`
Pins Python to **3.11.13** (used by `pyenv` and similar version managers).

---

#### `requirements.txt`
Python dependencies:

| Package | Purpose |
|---------|---------|
| `PyMuPDF==1.26.3` | PDF page rendering |
| `pymupdf4llm==0.0.27` | PDF → LLM-ready Markdown |
| `pydantic==2.11.7` | Data validation and JSON schema generation |
| `requests==2.33.0` | HTTP calls to LLM APIs |
| `Jinja2==3.1.6` | Prompt templating |
| `google-generativeai==0.4.0` | (Kept for compatibility) |
| `python-dotenv==1.2.2` | `.env` file loading |
| `black==25.9.0` | Code formatting |

---

### Prompts System (`prompts/`)

#### `prompts/template_manager.py`
**Jinja2 template loader and renderer.**

- `TemplateManager` class initialises a Jinja `Environment` pointed at `prompts/templates/`.
- `render_template(section_name, **kwargs)` — renders a named template by section key.
- `render_string(source, **kwargs)` — renders an arbitrary Jinja string (used for role-specific `criteria.jinja` and `system_message.jinja`, which are read from `roles/<name>/`).

---

#### `prompts/templates/system_message.jinja`
System-level instruction sent before every section-extraction call. Sets the LLM's persona as a structured data extractor.

#### `prompts/templates/basics.jinja`
Prompt template for extracting the `basics` section (name, email, phone, location, profiles).

#### `prompts/templates/work.jinja`
Prompt template for extracting work experience entries (company, role, dates, highlights).

#### `prompts/templates/education.jinja`
Prompt template for extracting education entries (institution, degree, dates, courses).

#### `prompts/templates/skills.jinja`
Prompt template for extracting the skills section (name, level, keywords).

#### `prompts/templates/projects.jinja`
Prompt template for extracting personal/academic projects (name, dates, description, technologies, URL).

#### `prompts/templates/awards.jinja`
Prompt template for extracting awards and recognitions (title, date, awarder, summary).

#### `prompts/templates/github_project_selection.jinja`
Prompt template used by `github.py` to ask the LLM to select the **top 7 most meaningful GitHub projects** from the candidate's full repository list, applying minimum author-commit thresholds and relevance filtering.

---

### Roles System (`roles/`)

Each role lives in its own subdirectory: `roles/<role_name>/`

#### `roles/software_engineering_intern/role.json`
Machine-readable rubric definition for the **Software Engineering Intern** role:

| Category | Max Score | Icon |
|----------|-----------|------|
| Open Source | 35 | 🌐 |
| Self Projects | 30 | 🚀 |
| Production Experience | 25 | 🏢 |
| Technical Skills | 10 | 💻 |
| **Bonus (max)** | 20 | ⭐ |
| **Total max** | **120** | |

Score range: -20 to 120.

#### `roles/software_engineering_intern/criteria.jinja`
The detailed **scoring rubric prompt** for the evaluator. Defines point breakdowns, evidence requirements, bonus conditions, and deduction rules for each category. Receives `{{ text_content }}` (the assembled resume text) at render time.

#### `roles/software_engineering_intern/system_message.jinja`
The **system-level fairness and format instructions** for the evaluator LLM call. Enforces that scores must not depend on name, gender, institution, grades, or location — only on demonstrated skills and experience.

---

### Resume Samples (`resume/`)

#### `resume/sample.pdf`
A sample résumé PDF included for quick testing and smoke-checking the pipeline without needing a real candidate's document.

---

### Documentation (`docs/`)

> Reference documents — read these to understand design intent and past decisions.

#### `docs/superpowers/specs/2026-06-29-config-driven-providers-design.md`
**Design specification** for the config-driven LLM provider system.

- **Problem:** adding a provider previously required editing Python in 4 files.
- **Goal:** zero-Python-edit provider addition via `providers.json`.
- **Approach:** one generic `OpenAICompatibleProvider` class; Ollama and Gemini become config entries pointing at their `/v1` compat endpoints.
- **Constraints:** no new dependencies; preserves the `provider.chat(…)` call contract.
- **Status:** Approved and implemented.

#### `docs/superpowers/plans/2026-06-29-config-driven-providers.md`
**Detailed implementation plan** (task checklist) for the config-driven provider migration.

- References the design spec above.
- Lists every file to create/modify with step-by-step tasks and verification scripts.
- Served as the agentic execution guide for implementing the design.

---

### Project Meta

#### `README.md`
Full project documentation covering:
- Context and intent (what this is and is not)
- Press coverage and community articles
- Architecture overview
- Installation, configuration, and CLI usage
- Directory layout, provider details, contributing, and license.

#### `CONTRIBUTING.md`
Contributor guide covering bug reporting, feature requests, coding style (Black), prompt guidelines (provider-agnostic), smoke test requirements, and commit message conventions.

#### `LICENSE`
MIT License © HackerRank.

#### `.gitignore`
Standard Python `.gitignore` covering `__pycache__`, `.venv`, `.env`, `cache/`, build artifacts, etc.

---

## Provider Support

The system uses a single `OpenAICompatibleProvider` class that adapts to any provider supporting the OpenAI `/chat/completions` endpoint. Provider resolution flows:

```
DEFAULT_MODEL env var (or providers.json "default_model")
        │
        ▼
config.provider_for(model_name)   ← reads providers.json
        │
        ▼
{base_url, api_key, structured_output, extra_body}
        │
        ▼
llm_utils.initialize_llm_provider()
        │
        ▼
OpenAICompatibleProvider instance
        │
        ▼
POST {base_url}/chat/completions
```

Structured output strategy:

| Mode | Used by | Behaviour |
|------|---------|-----------|
| `json_schema` | Ollama, Gemini | Sends `response_format: {type: "json_schema", json_schema: {...}}` |
| `json_object` | Anthropic Claude | Sends `response_format: {type: "json_object"}` |
| `none` | Custom providers | No format constraint; relies on prompt-only JSON extraction |

---

## Development Mode

When `DEVELOPMENT_MODE = True` in `config.py`:

| Feature | Detail |
|---------|--------|
| **PDF cache** | Extracted `JSONResume` is saved to `cache/resumecache_<basename>.json` and reused on subsequent runs |
| **GitHub cache** | Fetched GitHub data is saved to `cache/githubcache_<basename>.json` |
| **CSV export** | Each evaluation is appended to `resume_evaluations_<role>.csv` with columns matching the role's categories |

Set `DEVELOPMENT_MODE = False` to disable all caching and CSV output (e.g. for production batch processing).

---

## How to Add a New Role

```bash
# 1. Scaffold the role directory
python score.py --init-role backend_engineer

# 2. Edit the three generated files:
#    roles/backend_engineer/role.json           ← categories, weights, score bounds
#    roles/backend_engineer/criteria.jinja      ← scoring rubric and evidence requirements
#    roles/backend_engineer/system_message.jinja ← fairness and format instructions

# 3. Run against a resume
python score.py ./resume/sample.pdf --role backend_engineer
```

The `role.json` schema drives everything automatically: the dynamic Pydantic model, the LLM's structured-output JSON schema, the printed report layout, and the CSV column names.

---

## Dependencies

```
Python 3.11+
  ├── PyMuPDF           — PDF rendering
  ├── pymupdf4llm       — PDF → LLM-ready Markdown
  ├── pydantic          — Data models & JSON schema
  ├── requests          — HTTP calls to LLM APIs
  ├── Jinja2            — Prompt templating
  ├── python-dotenv     — .env loading
  ├── google-generativeai — (compatibility shim, not in active provider path)
  └── black             — Code formatter (dev)

LLM Backend (one of):
  ├── Ollama (local)    — ollama serve + ollama pull <model>
  ├── Google Gemini     — GEMINI_API_KEY required
  └── Anthropic Claude  — ANTHROPIC_API_KEY required
```

---

## Deep Dive: PDF Input → Data Extraction Module

This section traces every sub-step, every design decision, and every failure-handling path in the PDF-to-`JSONResume` pipeline.

---

### Stage 0 — Entry Point (`score.py`)

`score.py::main()` is the caller. Before touching the PDF at all, it checks for a dev-mode cache:

```
cache/resumecache_<basename>.json   ← if present AND DEVELOPMENT_MODE=True → skip PDF entirely
```

Only when the cache is missing (or corrupted/empty) does it construct a `PDFHandler` and call:
```python
resume_data = pdf_handler.extract_json_from_pdf(pdf_path)
```

---

### Stage 1 — PDF → Markdown (`pymupdf_rag.py :: to_markdown`)

#### What it is
`pymupdf_rag.py` is a **1,378-line custom PDF-to-Markdown renderer** derived from the open-source `pymupdf4llm` library (AGPLv3 / Artifex). It is vendored directly into the repo rather than imported as a package so the team can apply custom patches.

#### Entry call (from `pdf.py`)
```python
with pymupdf.open(pdf_path) as doc:
    resume_text = to_markdown(doc, pages=range(doc.page_count))
```

All pages are converted in a single call. The result is a plain `str` — one continuous Markdown document.

#### How `to_markdown` works internally

**Step 1 — Document normalization**
- If the document is a **form PDF** (fillable fields) or has annotations, `.bake()` is called first, which merges form widget content into the static page layer so text becomes extractable.
- If the document is **reflowable** (e.g., EPUB), it is re-paginated to a standard `612pt` wide page.

**Step 2 — Header detection (`IdentifyHeaders`)**
- Scans every text span on every page and counts characters per rounded font-size bucket.
- The **most frequent font size** is treated as body text.
- Font sizes larger than body are mapped to Markdown heading levels (`# `, `## `, …, up to `######`).
- Alternative: if the PDF has a Table of Contents (`doc.get_toc()`), `TocHeaders` uses the TOC hierarchy directly — faster and more accurate for professionally built documents.

**Step 3 — Per-page processing loop**
For each selected page:
1. **Column detection** — calls `column_boxes()` to split the page into logical reading columns (handles two-column résumé layouts).
2. **Graphics detection** — vector drawings are analyzed; those containing non-trivial paths (not just horizontal/vertical lines) are treated as image blocks.
3. **Text line extraction** — calls `get_raw_lines()` to get text runs sorted in Western reading order (left→right, top→bottom) within each column.
4. **Table detection** — uses the `table_strategy="lines_strict"` strategy to find ruled tables and renders them as Markdown `|col|col|` syntax.
5. **Span-level rendering**:
   - Spans with font size > body limit → prefixed with `#` header tags
   - Monospace font spans → wrapped in `` ` `` backticks (unless `ignore_code=True`)
   - Bullet-starting spans → preserved with `-` Markdown list syntax
   - Hyperlinks → rendered as `[text](url)` Markdown
   - Images → either embedded as base64 `![]()` or written to disk (disabled by default for résumés)
6. **Background-color text filtering** — text whose color matches the page background can be stripped (important: this is a known attack vector where white-on-white invisible text can inflate scores; see the Pinggy security article in README coverage).

**Output**: A single flat Markdown string like:
```markdown
# Jane Doe
jane@example.com | github.com/janedoe

## Work Experience
### Software Engineer — Acme Corp (2022-01 – Present)
- Led migration of monolith to microservices …

## Education
### B.Tech Computer Science — IIT Bombay (2018 – 2022)
…
```

#### Key `to_markdown` parameters used by `pdf.py`
| Parameter | Value | Effect |
|-----------|-------|--------|
| `pages` | `range(doc.page_count)` | All pages |
| `write_images` | `False` (default) | No image files written |
| `embed_images` | `False` (default) | No base64 images |
| `table_strategy` | `"lines_strict"` (default) | Only detect tables with explicit ruling lines |
| `force_text` | `True` (default) | Output text even if it sits on an image background |

---

### Stage 2 — Per-Section LLM Extraction (`pdf.py :: PDFHandler`)

#### Design choice: one LLM call per section
Instead of asking the LLM to parse the entire résumé in one call (which risks JSON truncation, hallucinated fields, and mixed-up sections for longer résumés), the pipeline makes **6 separate, focused LLM calls** — one per section.

Each call receives the **full Markdown text** as context but is given a **narrow, section-specific JSON schema** to fill in. This keeps outputs small and predictable.

#### The extraction loop (`_extract_all_sections_separately`)

```
sections = ["basics", "work", "education", "skills", "projects", "awards"]

for section_name in sections:
    section_data = _extract_section_data(text_content, section_name)

    if section_data is None:          ← first attempt failed
        section_data = _extract_section_data(…)   ← one automatic retry

    if section_data:
        complete_resume.update(section_data)   ← merge into master dict
    elif section_data is None:        ← retry also failed → ABORT entire extraction
        return None
    # else: empty but valid (no awards, etc.) → continue

return JSONResume(**complete_resume)
```

**Abort-on-failure policy**: if any section fails twice, the entire extraction is abandoned and `None` is returned. `score.py` treats `None` as a fatal error and exits. This prevents a partial/corrupt `JSONResume` from silently flowing into the evaluator and producing a wrong score.

---

### Stage 3 — LLM Call Mechanics (`_call_llm_for_section`)

For each section, the flow is:

```
1. Render system_message.jinja
       → "You are an expert resume parser. Extract ONLY the {section} section…"

2. Render <section>.jinja
       → Injects {{ text_content }} (the full Markdown) into the prompt

3. Build chat_params:
       model   = DEFAULT_MODEL
       messages= [system, user]
       options = {temperature, top_p}   ← from providers.json per model
       format  = <Section>.model_json_schema()   ← structured output schema

4. provider.chat(**chat_params, format=schema)
       → POST {base_url}/chat/completions
       → response["message"]["content"]  (a JSON string)

5. extract_json_from_response(response_text)
       → strips <think>…</think> blocks (reasoning models like DeepSeek-R1)
       → strips ```json … ``` fences

6. json_start = text.find("{")
   json_end   = text.rfind("}")
   → slice out only the JSON object (ignores any preamble text)

7. json.loads(response_text)  → raw dict

8. transform_parsed_data(raw_dict)  → normalized dict
```

---

### Stage 4 — The Six Jinja Prompt Templates

Each template follows the same structure:

```
[Task sentence — what to extract]

--- The input resume markdown starts here ---
{{ text_content }}
--- The input resume markdown ends here ---

Return ONLY a JSON object with this structure:
{ … exact schema … }

**IMPORTANT / CRITICAL** rules…
```

#### Template details

| Template | Output key | JSON fields extracted | Notable rules |
|----------|------------|----------------------|---------------|
| `basics.jinja` | `basics` | `name`, `email`, `phone`, `url`, `summary`, `location.{city, countryCode}`, `profiles[].{network, url, username}` | **CRITICAL**: Only extract URLs that are explicitly present in the Markdown. Do NOT fabricate `github.com` or `linkedin.com` URLs unless they appear verbatim. If `About Me` section exists → map to `summary`. |
| `work.jinja` | `work[]` | `name`, `position`, `startDate` (YYYY-MM), `endDate`, `summary`, `highlights[]` | Handles en dash `–`, em dash `—`, hyphen `-`, and the word `to` as date-range separators. Recognizes `Present` / `Current` / `Now` / `Ongoing` as open-ended end dates. |
| `education.jinja` | `education[]` | `institution`, `area`, `studyType`, `startDate`, `endDate`, `score` (GPA/%) | Minimal schema; straightforward extraction. |
| `skills.jinja` | `skills[]` | `name` (category), `level` (null), `keywords[]` | Groups technologies into categories (e.g., "Languages", "Frameworks"). `level` is always null — evaluated later by the rubric. |
| `projects.jinja` | `projects[]` | `name`, `description`, `url`, `technologies[]` | URL extraction is optional (projects may lack links). |
| `awards.jinja` | `awards[]` | `title`, `date`, `awarder` | Returns empty array if no awards section found — this is valid, not an error. |

#### System message template
```
You are an expert resume parser.
Extract ONLY the {{ section_name_param }} section…
CRITICAL: respond with ONLY valid JSON.
No explanatory text, no thinking process, no markdown formatting, no <think> tags.
```

The `<think>` tag rule is critical: reasoning models (e.g., `qwen3` with extended thinking enabled) emit a `<think>…</think>` block before their JSON. `extract_json_from_response()` strips this before parsing.

---

### Stage 5 — Response Normalization (`transform.py :: transform_parsed_data`)

After JSON parsing, the raw dict passes through `transform_parsed_data()`. This handles **LLM output variance** — different models use different field names for the same concept:

| Canonical field | Also accepted as |
|-----------------|-----------------|
| `work` | `work_experience`, `experience` |
| `awards` | `achievements`, `honors_and_awards` |
| `skills` | `librariesFrameworks`, `toolsPlatforms`, `databases` |
| `projects` | `projectsOpenSource` |

Sub-transformers handle further normalisation:
- **`transform_basics()`** — strips stray whitespace, normalises phone formats, validates profile URLs.
- **`transform_work_experience()`** — normalises date strings to `YYYY-MM` format; handles en dash/em dash; splits "Company — Role" combined strings.
- **`transform_education()`** — normalises degree type (`B.Tech` → `Bachelor`, etc.), standardises GPA format.
- **`transform_skills_comprehensive()`** — flattens nested skill sub-categories (e.g., a model returning `{"languages": ["Python"], "frameworks": ["FastAPI"]}` is merged into a single canonical list).
- **`transform_projects_comprehensive()`** — deduplicates projects that appear in both the `projects` key and `projectsOpenSource` key.
- **`transform_achievements()`** — normalises date formats and strips trailing punctuation from award titles.

---

### Stage 6 — Final Assembly (`JSONResume`)

After all 6 section dicts are collected and normalised, they are merged into `complete_resume` (a plain Python dict) then passed to:

```python
json_resume = JSONResume(**complete_resume)
```

Pydantic validates every field against the schema defined in `models.py`:
- Unknown fields are silently ignored.
- Required fields that are missing default to `None` (all fields are `Optional`).
- `Basics` gets an additional instantiation step (`Basics(**complete_resume["basics"])`) before the `JSONResume` is built, to catch any mis-shaped basics dict early.

The final `JSONResume` object is returned to `score.py`, which optionally writes it to cache, then proceeds to the GitHub enrichment stage.

---

### Error Handling & Resilience Summary

| Failure scenario | Behaviour |
|------------------|-----------|
| PDF file not found | `extract_text_from_pdf` raises `FileNotFoundError`; `extract_json_from_pdf` catches and returns `None` |
| PDF has no extractable text | `to_markdown` returns empty string; pipeline returns `None` |
| LLM returns malformed JSON | `json.JSONDecodeError` caught; section returns `None`; automatic retry |
| Section fails after retry | Entire extraction aborted (`return None`); `score.py` exits |
| Section returns empty (e.g., no awards) | Treated as valid; pipeline continues |
| Pydantic validation error on `JSONResume` | Caught; logs error; returns `None` |
| Cache file corrupted | Detected by `is_valid_resume_data()`; cache deleted; fresh extraction triggered |
| Rate limit (HTTP 429) | `OpenAICompatibleProvider` retries with exponential backoff (up to 5× with jitter, max 120s) |
| Transient server error (5xx) | Same exponential backoff retry strategy |

---

### Complete Data Flow Diagram

```
resume.pdf
    │
    ▼  pymupdf.open(pdf_path)
┌─────────────────────────────┐
│  pymupdf_rag.to_markdown()  │
│  ┌─────────────────────┐    │
│  │ IdentifyHeaders     │    │  → detect body vs heading font sizes
│  │ column_boxes()      │    │  → detect multi-column layout
│  │ get_raw_lines()     │    │  → sort text in reading order
│  │ Table detection     │    │  → render as Markdown tables
│  │ Hyperlink rendering │    │  → [text](url)
│  │ Header tagging      │    │  → # ## ### ...
│  └─────────────────────┘    │
└─────────────────────────────┘
    │
    ▼  resume_text: str  (full Markdown of entire PDF)
    │
    │  ── repeated 6 times, once per section ──────────────────────────────
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  _call_llm_for_section(section_name, resume_text, prompt)        │
│                                                                  │
│  system_message.jinja → "Expert resume parser, JSON only"        │
│  <section>.jinja      → task + schema + resume_text injected     │
│                                                                  │
│  provider.chat(model, messages, options, format=json_schema)     │
│       → POST {base_url}/chat/completions                         │
│                                                                  │
│  extract_json_from_response()  → strip <think>, strip fences     │
│  json.loads()                  → raw dict                        │
│  transform_parsed_data()       → normalised dict                 │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼  complete_resume dict (basics + work + education + skills + projects + awards)
    │
    ▼  Pydantic validation
┌─────────────────────────────┐
│  JSONResume(**complete_resume) │
└─────────────────────────────┘
    │
    ▼
JSONResume object  →  score.py  →  (cache write)  →  GitHub stage
```
