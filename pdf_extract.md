# PDF Input → Data Extraction Module — Deep Dive

This document traces every sub-step, design decision, and failure-handling path in the PDF-to-`JSONResume` pipeline.

**Files covered:**
- [`pdf.py`](./pdf.py) — `PDFHandler` class, the orchestrator
- [`pymupdf_rag.py`](./pymupdf_rag.py) — low-level PDF → Markdown renderer
- [`prompts/templates/`](./prompts/templates/) — 6 Jinja extraction templates
- [`prompts/template_manager.py`](./prompts/template_manager.py) — template loader
- [`transform.py`](./transform.py) — response normalisation (`transform_parsed_data`)
- [`llm_utils.py`](./llm_utils.py) — JSON cleanup (`extract_json_from_response`)
- [`models.py`](./models.py) — `JSONResume` Pydantic schema

---

## Table of Contents

1. [Stage 0 — Cache Check (score.py)](#stage-0--cache-check-scorepy)
2. [Stage 1 — PDF → Markdown (pymupdf_rag.py)](#stage-1--pdf--markdown-pymupdf_ragpy)
3. [Stage 2 — Per-Section LLM Extraction (PDFHandler)](#stage-2--per-section-llm-extraction-pdfhandler)
4. [Stage 3 — LLM Call Mechanics](#stage-3--llm-call-mechanics)
5. [Stage 4 — The Six Jinja Prompt Templates](#stage-4--the-six-jinja-prompt-templates)
6. [Stage 5 — Response Normalisation (transform.py)](#stage-5--response-normalisation-transformpy)
7. [Stage 6 — Final Assembly (JSONResume)](#stage-6--final-assembly-jsonresume)
8. [Error Handling & Resilience](#error-handling--resilience)
9. [Complete Data Flow Diagram](#complete-data-flow-diagram)

---

## Stage 0 — Cache Check (`score.py`)

`score.py::main()` is the caller. Before the PDF is touched at all, it checks
for a dev-mode cache hit:

```
cache/resumecache_<basename>.json
```

If the file **exists and is valid** while `DEVELOPMENT_MODE=True`, the entire
PDF extraction is **skipped** and the cached `JSONResume` dict is deserialised
directly. The cache is invalidated (deleted) if:

- `json.loads` fails (corrupt file)
- The loaded object passes `is_valid_resume_data()` returning `False`
  (none of the core sections — basics, work, education, skills, projects — are
  populated)

Only when the cache is absent or invalid does `score.py` construct a
`PDFHandler` and call:

```python
resume_data = pdf_handler.extract_json_from_pdf(pdf_path)
```

---

## Stage 1 — PDF → Markdown (`pymupdf_rag.py :: to_markdown`)

### What it is

`pymupdf_rag.py` is a **1,378-line custom PDF-to-Markdown renderer** derived
from the open-source `pymupdf4llm` library (AGPLv3 / Artifex Software). It is
**vendored directly** into the repo (rather than installed as a package) so
the team can patch it without waiting for upstream releases.

### Entry call (from `pdf.py`)

```python
with pymupdf.open(pdf_path) as doc:
    resume_text = to_markdown(doc, pages=range(doc.page_count))
```

All pages are converted in a single call. The result is a plain `str` — one
continuous Markdown document representing the entire PDF.

### `to_markdown` parameters used

| Parameter | Value used | Effect |
|-----------|-----------|--------|
| `pages` | `range(doc.page_count)` | All pages |
| `write_images` | `False` (default) | No image files saved to disk |
| `embed_images` | `False` (default) | No base64 image data in output |
| `table_strategy` | `"lines_strict"` (default) | Tables detected only when explicit ruling lines are present |
| `force_text` | `True` (default) | Text extracted even when it sits on an image background |
| `fontsize_limit` | `3` (default) | Text smaller than 3pt is ignored |

### Internal processing steps

#### Step 1 — Document normalisation

```python
if doc.is_form_pdf or (doc.is_pdf and doc.has_annots()):
    doc.bake()
```

**Form PDF baking**: Fillable PDF form fields are "baked" — their widget
content is merged into the static page layer. Without this, typed text in form
fields would be invisible to the text extractor.

```python
if doc.is_reflowable:
    doc.layout(width=612, height=792)
```

**Reflowable documents** (e.g., ePub résumés) are re-paginated to standard
US Letter dimensions before rendering.

---

#### Step 2 — Header detection (`IdentifyHeaders`)

```python
hdr_info = IdentifyHeaders(doc)
get_header_id = hdr_info.get_header_id
```

`IdentifyHeaders` scans every text span across all pages and tallies character
counts per rounded font size. The algorithm:

1. Build a frequency map: `{font_size: total_characters_at_that_size}`.
2. The **most frequent font size** is treated as body text (`body_limit`).
3. Font sizes larger than body text are mapped to Markdown heading tags
   (`# `, `## `, …, up to `######`).
4. The smallest heading size sets the final `body_limit`.

```python
# Example output for a typical résumé:
header_id = {
    14: "# ",    # candidate name
    12: "## ",   # section headers (Work, Education, …)
    11: "### ",  # sub-entries (company names, degree titles)
}
body_limit = 10  # body text is 10pt
```

**Alternative — `TocHeaders`**: If the PDF has an embedded Table of Contents
(`doc.get_toc()` returns entries), `TocHeaders` uses the TOC hierarchy directly.
This is faster and more accurate for professionally formatted PDF documents
because heading levels map 1-to-1 with TOC nesting levels.

---

#### Step 3 — Per-page processing loop

For each selected page number `pno`:

**3a. Column detection**
```python
column_boxes(page)  # returns list of bounding-box rectangles per column
```
Splits the page into logical reading columns. Handles two-column résumé layouts
so text from column 1 is ordered before column 2, not interleaved by `y`
coordinate.

**3b. Graphics detection**
Vector graphic paths are collected. `is_significant(box, paths)` checks whether
a region contains non-trivial drawings (not just horizontal/vertical lines). If
significant, the region is treated as an image block.

**3c. Text line extraction**
```python
get_raw_lines(page, clip=column_rect)
```
Returns text runs sorted in Western reading order (left→right, top→bottom)
within each column clip region.

**3d. Table detection**
Tables with explicit ruling lines are detected using the `"lines_strict"`
strategy and rendered as Markdown:
```markdown
| Column A | Column B |
|----------|----------|
| value 1  | value 2  |
```

**3e. Span-level rendering**

| Span type | How rendered in Markdown |
|-----------|--------------------------|
| Font size > `body_limit` | Prefixed with `# ` … `###### ` |
| Monospace (code) font | Wrapped in `` ` `` backticks |
| Bullet-starting text | Preserved with `- ` list syntax |
| Hyperlink span | Rendered as `[text](url)` |
| Image region | `![]()` placeholder (or skipped if `ignore_images=True`) |

**3f. Background-colour text filtering**
Text whose colour matches the page background colour can be detected and
excluded. This is relevant as a **known attack vector**: white-on-white
invisible text embedded in résumé PDFs can contain keyword-stuffed content
that the LLM reads but a human reviewer cannot see (documented in the
[Pinggy security article](https://pinggy.io/blog/hackerrank_open_source_ats_inconsistent_scoring/)).

---

#### Output example

A two-page résumé typically produces output like:

```markdown
# Jane Doe
jane@example.com | +91-9000000000
[github.com/janedoe](https://github.com/janedoe) | [linkedin.com/in/janedoe](https://linkedin.com/in/janedoe)

## Work Experience

### Software Engineer — Acme Corp
*2022-01 – Present*
- Led migration from monolith to microservices, reducing p99 latency by 40%
- Designed and shipped the billing pipeline processing ₹10Cr/month

### Intern — StartupXYZ
*2021-06 – 2021-12*
- Built a React dashboard used by 500+ internal users

## Education

### B.Tech Computer Science — IIT Bombay
*2018 – 2022* | GPA: 8.7/10

## Skills
Languages: Python, Go, TypeScript
Frameworks: FastAPI, React, gRPC
Tools: Docker, Kubernetes, PostgreSQL

## Projects
### PaymentFlow (github.com/janedoe/paymentflow)
A distributed payment processing system built with Go and Kafka …
```

---

## Stage 2 — Per-Section LLM Extraction (`pdf.py :: PDFHandler`)

### Design rationale: one LLM call per section

The pipeline makes **6 separate, focused LLM calls** — one per resume section —
rather than one call for the entire document. Reasons:

| Problem with one big call | How per-section calls solve it |
|--------------------------|-------------------------------|
| LLM may truncate long JSON | Each section output is short |
| Fields from different sections mix up | Schema is narrowly scoped |
| Hard to retry a specific failed section | Each section can be retried independently |
| Structured output schema is complex | Each schema is tiny and concrete |

### The extraction loop (`_extract_all_sections_separately`)

```python
sections = ["basics", "work", "education", "skills", "projects", "awards"]

complete_resume = {
    "basics": None, "work": None, "volunteer": None,
    "education": None, "awards": None, "certificates": None,
    "publications": None, "skills": None, "languages": None,
    "interests": None, "references": None, "projects": None, "meta": None,
}

for section_name in sections:
    section_data = _extract_section_data(text_content, section_name)

    if section_data is None:                        # first attempt failed
        section_data = _extract_section_data(...)   # one automatic retry

    if section_data:
        complete_resume.update(section_data)        # merge into master dict
    elif section_data is None:                      # retry also failed
        return None                                 # ABORT: return None to score.py
    # else: {} / empty dict — valid (e.g. no awards) → continue
```

**Abort-on-failure policy**: if any section fails both attempts, the entire
extraction is abandoned and `None` returned. `score.py` treats `None` as a
fatal error and exits. This prevents a partial or corrupt `JSONResume` from
silently producing a biased score.

### Section dispatcher (`_extract_section_data`)

```python
section_extractors = {
    "basics":    self.extract_basics_section,
    "work":      self.extract_work_section,
    "education": self.extract_education_section,
    "skills":    self.extract_skills_section,
    "projects":  self.extract_projects_section,
    "awards":    self.extract_awards_section,
}
```

Each `extract_<section>_section` method:
1. Renders its Jinja template via `TemplateManager.render_template(section, text_content=resume_text)`.
2. Calls `_call_llm_for_section(section_name, resume_text, prompt, SectionModel)`.

---

## Stage 3 — LLM Call Mechanics (`_call_llm_for_section`)

```
┌─────────────────────────────────────────────────────────────┐
│  1. Render system_message.jinja                             │
│     → "You are an expert resume parser.                     │
│        Extract ONLY the {section} section…                  │
│        Respond with ONLY valid JSON. No <think> tags."      │
│                                                             │
│  2. Render <section>.jinja                                  │
│     → task description + exact JSON schema                  │
│     → {{ text_content }} = full resume Markdown injected    │
│                                                             │
│  3. Build request                                           │
│     model    = DEFAULT_MODEL (from providers.json / .env)   │
│     messages = [system_message, user_prompt]                │
│     options  = {temperature, top_p}  ← per-model from JSON  │
│     format   = <Section>.model_json_schema()  ← structured  │
│                                                             │
│  4. provider.chat(**chat_params, format=schema)             │
│     → POST {base_url}/chat/completions                      │
│     → response["message"]["content"]  (a JSON string)       │
│                                                             │
│  5. extract_json_from_response(response_text)               │
│     → strip <think>…</think> block (reasoning models)       │
│     → strip ```json … ``` fences                            │
│                                                             │
│  6. Slice: text[text.find("{") : text.rfind("}")+1]         │
│     → isolate the JSON object, discard any preamble text    │
│                                                             │
│  7. json.loads(response_text)  → raw dict                   │
│                                                             │
│  8. transform_parsed_data(raw_dict)  → normalised dict      │
│     → returned to the extraction loop                       │
└─────────────────────────────────────────────────────────────┘
```

### Structured output enforcement

The `format` kwarg passes the section's Pydantic JSON schema to the provider:

```python
kwargs["format"] = return_model.model_json_schema()
# e.g. BasicsSection, WorkSection, EducationSection, …
```

`OpenAICompatibleProvider` translates this to:
```json
"response_format": {
    "type": "json_schema",
    "json_schema": { "name": "response", "schema": <schema> }
}
```
(or `"type": "json_object"` for Anthropic Claude, which uses `json_object` mode).

This forces compliant providers (Ollama, Gemini, OpenAI) to return valid JSON
matching the schema, eliminating most parse errors without needing complex
retry logic.

### Timing

Each section call is individually timed:
```python
start_time = time.time()
# … LLM call …
end_time = time.time()
logger.debug(f"⏱️ Total time for {section_name} extraction: {total_time:.2f}s")
```

The total across all 6 sections is also logged at `INFO` level after assembly.

---

## Stage 4 — The Six Jinja Prompt Templates

All templates live in [`prompts/templates/`](./prompts/templates/). Each follows
this skeleton:

```
[Task instruction — what to extract]

--- The input resume markdown starts here ---
{{ text_content }}
--- The input resume markdown ends here ---

Return ONLY a JSON object with this structure:
{ … exact schema … }

**IMPORTANT / CRITICAL** rules and examples
```

### `system_message.jinja`

```
You are an expert resume parser.
Extract ONLY the {{ section_name_param }} section from resumes
and format it according to the JSON Resume specification.

CRITICAL: You must respond with ONLY valid JSON.
Do not include any explanatory text, thinking process,
markdown formatting, or <think> tags.
Return ONLY the {{ section_name_param }} section in JSON format.
```

The `<think>` tag restriction is critical for reasoning models
(e.g., `qwen3`, `deepseek-r1`) that emit a `<think>…</think>` chain-of-thought
block before their answer. `extract_json_from_response()` in `llm_utils.py`
strips this block before JSON parsing.

---

### `basics.jinja`

**Output key:** `basics`

**Extracted fields:**
```json
{
  "basics": {
    "name": "Full name",
    "email": "Email address",
    "phone": "Phone number",
    "url": null,
    "summary": null,
    "location": { "city": "City", "countryCode": "Country code" },
    "profiles": [
      { "network": "Platform name", "url": "Full URL", "username": "Username" }
    ]
  }
}
```

**Critical prompt rules:**
- **URL fabrication prevention**: Only extract URLs that are **explicitly present** in the Markdown. Do NOT generate `https://github.com` or `https://linkedin.com` unless they literally appear in the résumé text.
- **About Me / Summary mapping**: If the résumé has an "About Me" or "Summary" section, its text maps to `basics.summary`.
- **Portfolio URLs**: If a link is a GitHub Pages domain (`github.io`) or personal domain, mark `network` as `"Portfolio"`.
- **Empty profiles**: If no URLs are found, return `"profiles": []` — not `null`, not omitted.

**Why strict URL rules matter**: A model that fabricates a GitHub URL could cause `github.py` to try fetching a real (or wrong) GitHub profile, corrupting the enrichment stage.

---

### `work.jinja`

**Output key:** `work[]`

**Extracted fields:**
```json
{
  "work": [{
    "name": "Company name",
    "position": "Job title",
    "startDate": "YYYY-MM",
    "endDate": "YYYY-MM or Present",
    "summary": "Job description",
    "highlights": ["Achievement 1", "Achievement 2"]
  }]
}
```

**Critical prompt rules — date parsing:**

Date ranges in résumés appear in many formats. The prompt explicitly covers:

| Separator | Example |
|-----------|---------|
| Hyphen `-` | `Jan 2022 - Dec 2023` |
| En dash `–` | `Jan 2022 – Dec 2023` |
| Em dash `—` | `Jan 2022 — Dec 2023` |
| Word "to" | `Jan 2022 to Dec 2023` |
| Open-ended | `Jan 2022 – Present` / `Current` / `Now` / `Ongoing` |

All dates are normalised to `YYYY-MM`. Year-only ranges (`2019-2021`) keep
just the year.

---

### `education.jinja`

**Output key:** `education[]`

**Extracted fields:**
```json
{
  "education": [{
    "institution": "School/University name",
    "area": "Field of study",
    "studyType": "Degree type",
    "startDate": "YYYY-MM",
    "endDate": "YYYY-MM",
    "score": "GPA/Percentage"
  }]
}
```

Minimal schema; straightforward extraction. `score` captures whatever format
the résumé uses (`8.7/10`, `87%`, `3.9 GPA`, etc.) — normalisation is
deferred to `transform.py`.

---

### `skills.jinja`

**Output key:** `skills[]`

**Extracted fields:**
```json
{
  "skills": [{
    "name": "Skill category",
    "level": null,
    "keywords": ["Skill 1", "Skill 2"]
  }]
}
```

Groups individual technologies into categories (e.g., `"Languages"`,
`"Frameworks"`, `"Tools"`). `level` is always `null` at extraction time —
proficiency levels are assessed by the evaluator's rubric, not inferred from
résumé wording.

---

### `projects.jinja`

**Output key:** `projects[]`

**Extracted fields:**
```json
{
  "projects": [{
    "name": "Project name",
    "description": "Project description",
    "url": "Project URL",
    "technologies": ["Tech 1", "Tech 2"]
  }]
}
```

`url` is optional — many résumé projects list no link. `technologies` comes
from any tech stack, "built with", or "technologies used" text near the project.

---

### `awards.jinja`

**Output key:** `awards[]`

**Extracted fields:**
```json
{
  "awards": [{
    "title": "Award name",
    "date": "YYYY-MM",
    "awarder": "Awarding organization"
  }]
}
```

Covers competitive programming achievements, hackathon wins, academic
recognitions, etc. If no awards section exists in the résumé, the model
returns `"awards": []` — this is a **valid empty response**, not an error.
The extraction loop handles it with:
```python
elif section_data is not None:
    logger.warning(f"⚠️ {section_name} section empty; continuing")
```

---

## Stage 5 — Response Normalisation (`transform.py :: transform_parsed_data`)

After `json.loads()` succeeds, the raw dict is passed to `transform_parsed_data()`.
This layer handles **LLM output variance** — different models use different
field names for identical concepts.

### Field name aliases resolved

| Canonical field | Also accepted from LLM |
|-----------------|------------------------|
| `work` | `work_experience`, `experience` |
| `awards` | `achievements`, `honors_and_awards` |
| `skills` | raw dict, or nested `librariesFrameworks`, `toolsPlatforms`, `databases` |
| `projects` | `projectsOpenSource` |

### Per-section sub-transformers

**`transform_basics(data)`**
- Strips leading/trailing whitespace from all string fields.
- Normalises phone numbers (removes formatting noise).
- Validates that profile URLs are non-empty strings before including them.

**`transform_work_experience(data)`**
- Normalises date strings to `YYYY-MM`.
- Handles en dash / em dash date range separators.
- Splits combined "Company — Role" strings if the model merges them.

**`transform_education(data)`**
- Standardises degree type labels (`B.Tech` → `Bachelor of Technology`, etc.).
- Passes `score` through as-is (e.g., `"8.7/10"`).

**`transform_skills_comprehensive(data)`**
- Flattens nested skill dicts.
- Example: if the model returns `{"languages": ["Python"], "frameworks": ["FastAPI"]}`,
  this is converted to `[{"name": "Languages", "keywords": ["Python"]}, {"name": "Frameworks", "keywords": ["FastAPI"]}]`.

**`transform_projects_comprehensive(data)`**
- Deduplicates projects appearing in both `projects` and `projectsOpenSource` keys.
- Merges technology lists.

**`transform_achievements(data)`**
- Normalises award date formats.
- Strips trailing punctuation from award titles.

---

## Stage 6 — Final Assembly (`JSONResume`)

After all 6 section dicts are normalised and merged into `complete_resume`:

```python
# Special case: validate basics sub-object first
if complete_resume.get("basics") and isinstance(complete_resume["basics"], dict):
    complete_resume["basics"] = Basics(**complete_resume["basics"])

# Build the full resume
json_resume = JSONResume(**complete_resume)
```

**Why basics gets its own validation step**: Pydantic validation inside `JSONResume`
would silently set `basics=None` on failure. By instantiating `Basics` first,
any schema mismatch is caught and logged explicitly before the outer model is
built.

Pydantic validation rules:
- All fields are `Optional` → missing fields default to `None`, not errors.
- Unknown extra fields are silently ignored.
- Type coercion is applied where possible (e.g., string `"2022"` in a list field).

The validated `JSONResume` is returned to `score.py`, which:
1. Writes it to `cache/resumecache_<name>.json` (if `DEVELOPMENT_MODE=True` and data is valid).
2. Passes it to the GitHub enrichment stage.

---

## Error Handling & Resilience

| Failure scenario | Handling |
|------------------|----------|
| PDF file not found | `FileNotFoundError` raised in `extract_text_from_pdf`; caught in `extract_json_from_pdf`; returns `None` |
| PDF has no extractable text | `to_markdown` returns empty string; pipeline returns `None` |
| Form PDF with unreadable fields | `.bake()` called automatically before text extraction |
| LLM returns malformed JSON | `json.JSONDecodeError` caught in `_call_llm_for_section`; section returns `None`; one automatic retry triggered |
| Section fails both attempts | Entire extraction aborted; `None` returned; `score.py` exits |
| Section returns empty (e.g., no awards) | Treated as valid; pipeline continues |
| `<think>` reasoning block in response | Stripped by `extract_json_from_response()` before `json.loads()` |
| Markdown code fence in response | Stripped by `extract_json_from_response()` |
| Extra preamble text before JSON | `text.find("{")` / `text.rfind("}")` slice discards it |
| Pydantic validation error on `JSONResume` | Caught; error logged; returns `None` |
| Cache file corrupted | Detected by `is_valid_resume_data()` in `score.py`; cache deleted; fresh extraction triggered |
| HTTP 429 rate limit | `OpenAICompatibleProvider` retries with exponential backoff (up to 5×, max 120s, with ±20% jitter) |
| HTTP 5xx server error | Same exponential backoff retry strategy |
| Template file missing | `TemplateManager` logs warning; `_call_llm_for_section` returns `None`; section fails |

---

## Complete Data Flow Diagram

```
resume.pdf
    │
    ▼  pymupdf.open(pdf_path)
┌──────────────────────────────────────────────────┐
│  pymupdf_rag.to_markdown()                       │
│                                                  │
│  ┌─ doc.bake() if form PDF or has annotations   │
│  ├─ IdentifyHeaders: scan font sizes             │
│  │    most-frequent size = body text             │
│  │    larger sizes → # ## ### heading tags       │
│  │                                               │
│  └─ for each page:                               │
│       column_boxes()   → detect columns          │
│       get_raw_lines()  → text in reading order   │
│       table detection  → | col | col | rows      │
│       span rendering:                            │
│         heading → # prefix                       │
│         code    → `backticks`                    │
│         bullet  → - list                         │
│         link    → [text](url)                    │
└──────────────────────────────────────────────────┘
    │
    ▼  resume_text: str  (full Markdown of entire PDF)
    │
    │  ── repeated 6 times, once per section ──────────────────────────────
    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PDFHandler._call_llm_for_section(section, resume_text)              │
│                                                                      │
│  TemplateManager.render("system_message")                            │
│       → "Expert parser. ONLY JSON. No <think> tags."                │
│                                                                      │
│  TemplateManager.render("<section>.jinja")                           │
│       → task + schema + {{ text_content }} injected                  │
│                                                                      │
│  provider.chat(model, messages, options, format=json_schema)         │
│       → POST {base_url}/chat/completions                             │
│       → HTTP retry on 429 / 5xx (exponential backoff, max 5×)       │
│       → response["message"]["content"]                               │
│                                                                      │
│  extract_json_from_response()                                        │
│       → strip <think>…</think>                                       │
│       → strip ```json … ``` fences                                   │
│       → slice text[find("{"):rfind("}")+1]                           │
│                                                                      │
│  json.loads()  → raw dict                                            │
│  transform_parsed_data()  → normalised dict                          │
└──────────────────────────────────────────────────────────────────────┘
    │
    │  ── after all 6 sections complete ───────────────────────────────────
    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  complete_resume dict                                                │
│  { basics, work, education, skills, projects, awards, … }           │
│                                                                      │
│  Basics(**complete_resume["basics"])   ← validate basics first      │
│  JSONResume(**complete_resume)         ← Pydantic full validation    │
└──────────────────────────────────────────────────────────────────────┘
    │
    ▼
JSONResume object
    │
    ├── score.py writes cache/resumecache_<name>.json  (DEVELOPMENT_MODE)
    │
    └── → GitHub enrichment stage (github.py)
```
