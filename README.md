# 🏦 Loan Underwriting & Scoring Agent

[![Deterministic Scoring](https://img.shields.io/badge/Scoring-Deterministic%20100%25-brightgreen)](scoring.py)
[![Policy Gates](https://img.shields.io/badge/Policy-Configurable%20Gates-blue)](loan_products/)
[![Throughput](https://img.shields.io/badge/Throughput-31.2%20apps%2Fsec-brightgreen)](#-performance-benchmarks--concurrency-scaling)
[![Scale](https://img.shields.io/badge/Scale-10%2C000%2B%20Applications-blue)](#-high-throughput-parallel-architecture-10000-applications)
[![Tests](https://img.shields.io/badge/Tests-22%2F22%20Passing-success)](run_tests.py)
[![Sample PDF Report](https://img.shields.io/badge/Output-result.pdf%20(8%20Pages)-crimson?logo=adobe-acrobat-reader)](result.pdf)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Loan Underwriting & Scoring Agent** is an automated credit assessment platform that evaluates loan applicants from raw financial PDF documents (bank statements, pay slips, credit bureau reports, and tax filings).

### 💡 What does this agent do?
- 📑 **Reads Real Financial Documents**: Extracts applicant data, income proofs, credit scores, and 6 months of itemized bank and credit card transactions directly from PDFs.
- 🧮 **100% Mathematical & Auditable Scoring**: Eliminates AI hallucination and score variance. Credit scores (0–100) are computed using transparent deterministic formulas and versioned product policies.
- ⚡ **High-Throughput Parallel Ingestion**: Ingests and scores **10,000+ loan applications** concurrently using bounded process worker pools, workload-aware batching, backpressure queues, and atomic checkpointing.
- 🚪 **Enforces Policy Gates**: Automatically checks eligibility rules (such as minimum CIBIL score, maximum debt-to-income ratio, and mandatory KYC documents) and flags ineligible profiles with clear rejection reasons.
- 🤖 **Parallel AI Executive Summaries**: Uses an LLM to generate plain-English underwriting verdicts and highlights strengths (**Pros**) and risk factors (**Cons**) tagged by criticality (`HIGH`, `MED`, `LOW`).
- 🏆 **Ranks Applicant Portfolios**: Sorts applicants into an executive **Portfolio Leaderboard** (Rank 1 to $N$) and an **Ineligible Queue**.
- 📄 **Generates Complete Dossier Reports**: Exports publication-ready PDF reports with full calculation traces and transaction rollups.

---

> 📄 **Live Portfolio Report**: Download or inspect the sample underwriting report: **[`result.pdf`](result.pdf)** (8-page dossier featuring the portfolio leaderboard, 7 applicant dossiers, 6-month transaction rollups, and LLM evaluations).

---

## 📑 Table of Contents

- [Core Principles & Architectural Guarantee](#-core-principles--architectural-guarantee)
- [System Architecture](#-system-architecture)
- [High-Throughput Parallel Architecture (10,000+ Applications)](#-high-throughput-parallel-architecture-10000-applications)
- [Performance Benchmarks & Concurrency Scaling](#-performance-benchmarks--concurrency-scaling)
- [4-Stage Ingestion & Processing Pipeline](#-4-stage-ingestion--processing-pipeline)
- [Deterministic Scoring Engine & Mathematical Rubric](#-deterministic-scoring-engine--mathematical-rubric)
- [Policy Gating & Eligibility Engine](#-policy-gating--eligibility-engine)
- [Parallel LLM Underwriting Evaluation (Pros & Cons by Criticality)](#-parallel-llm-underwriting-evaluation)
- [Portfolio Leaderboard & Ranking Engine](#-portfolio-leaderboard--ranking-engine)
- [Executive PDF Dossier Report (`result.pdf`)](#-executive-pdf-dossier-report)
- [Synthetic PDF Test Scenarios](#-synthetic-pdf-test-scenarios)
- [Getting Started & Quickstart](#-getting-started--quickstart)
- [CLI Reference](#-cli-reference)
- [Automated 4-Layer Test Suite](#-automated-4-layer-test-suite)
- [Lineage & Copyright Notice](#-lineage--copyright-notice)

---

## 🎯 Core Principles & Architectural Guarantee

In credit underwriting, **non-deterministic scores and hallucinatory policy decisions are unacceptable**. Traditional LLM-as-judge implementations produce high score variance across identical applicant inputs and can be vulnerable to prompt injection or hallucinated figures.

This system guarantees **100% mathematical reproducibility**:

$$\text{PDF Documents} \longrightarrow \text{Strict Extraction} \longrightarrow \text{Validation} \longrightarrow \text{Feature Rollups} \longrightarrow \text{Policy Gating} \longrightarrow \text{Deterministic Scoring} \longrightarrow \text{Leaderboard Ranking}$$

### The Boundary of the LLM:
1. **Document Fact Extraction**: Extracts verbatim figures from documents with mandatory source attribution (`document`, `page`, and `verbatim_quote`). Missing values strictly remain `null` (never silently substituted with zero).
2. **Parallel Grounded Evaluation**: Generates executive underwriting verdicts and categorizes pros/cons by criticality (`HIGH`, `MED`, `LOW`). Code validators verify that all financial metrics mentioned in explanations exist within the deterministic trace.
3. **Zero Influence on Numerical Ranks**: The LLM **cannot** alter numeric scores, adjust weights, or change portfolio ranks.

---

## 🏗️ System Architecture

```
                                  MULTI-PAGE FINANCIAL PDF DOSSIER
                                (Bank Statements, Tax Returns, ITR,
                               Credit Bureau, Pay Slips, Loan Form)
                                                │
                                                ▼
                             ┌──────────────────────────────────────┐
                             │    STAGE 1: EXTRACTION (extract.py)  │
                             │  • LLM / PyMuPDF text & tables       │
                             │  • Ground truth NEVER used as input  │
                             └──────────────────┬───────────────────┘
                                                ▼
                             ┌──────────────────────────────────────┐
                             │      STAGE 2: PARSING (models.py)    │
                             │  • Typed Pydantic models             │
                             │  • SourceEvidence citations          │
                             └──────────────────┬───────────────────┘
                                                ▼
                             ┌──────────────────────────────────────┐
                             │    STAGE 3: REFINING (validate.py)   │
                             │  • Currency & range sanity checks    │
                             │  • Cross-document coherence (ITR/Pay)│
                             │  • Itemized 6M transaction parsing   │
                             └──────────────────┬───────────────────┘
                                                ▼
                             ┌──────────────────────────────────────┐
                             │   STAGE 4: CALCULATING (features.py) │
                             │  • DTI, EMI-to-income, LTI ratios    │
                             │  • 6M Bank credits, debits, salary   │
                             │  • Credit card utilization & spends  │
                             └──────────────────┬───────────────────┘
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
     ┌───────────────────────────────┐                     ┌───────────────────────────────┐
     │ POLICY ENGINE (eligibility.py)│                     │  SCORING ENGINE (scoring.py)  │
     │ • Product JSON policy gates   │                     │  • Pure mathematical functions│
     │ • Min Bureau Score (e.g. 600) │                     │  • Linear & stepwise mappings │
     │ • Max DTI (e.g. 50%)          │                     │  • Fully auditable trace      │
     │ • Delinquency cutoffs         │                     │  • Criticality: LOW/MED/HIGH  │
     └───────────────┬───────────────┘                     └───────────────┬───────────────┘
                     │                                                     │
                     └──────────────────────────┬──────────────────────────┘
                                                ▼
                             ┌──────────────────────────────────────┐
                             │     RANKING ENGINE (ranking.py)      │
                             │  • Multi-key deterministic sort      │
                             │  • Qualified Leaderboard (1..N)      │
                             │  • Ineligible Queue (Policy Failures)│
                             └──────────────────┬───────────────────┘
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
     ┌───────────────────────────────┐                     ┌───────────────────────────────┐
     │ LLM EVALUATION (explain.py)   │                     │   REPORTING (generate_pdf.py) │
     │ • Parallel multithreaded run  │                     │  • Executive PDF Dossiers     │
     │ • Executive Verdict           │                     │  • Portfolio Leaderboard      │
     │ • Pros & Cons by Criticality  │                     │  • Component Score Tables     │
     │ • Grounding validation checks │                     │  • 6M Financial Rollups       │
     └───────────────────────────────┘                     └───────────────────────────────┘
```

---

## ⚡ High-Throughput Parallel Architecture (10,000+ Applications)

To support production-grade portfolio underwriting, the engine is designed to ingest and score **10,000+ loan applications** concurrently while preserving **100% determinism, memory bounds, and failure isolation**.

```
                      INCOMING APPLICATION DOSSIERS (10,000+)
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │          JOB RUNNER          │
                         │ • Application Discovery      │
                         │ • Workload Estimator (Docs)  │
                         │ • Greedy Min-Heap Batching   │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │      BOUNDED WORK QUEUE      │
                         │  • Queue Backpressure Buffer │
                         │  • Bounded Memory Ingestion  │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │     WORKER POOL MANAGER      │
                         │ • ProcessPoolExecutor (GIL-free)
                         │ • Dynamic Concurrency (1..100)│
                         │ • LLM Semaphore Rate Limiter │
                         └──────┬───────┬───────┬───────┘
                                │       │       │
                   ┌────────────┘       │       └────────────┐
                   ▼                    ▼                    ▼
              [Worker 1]           [Worker 2]           [Worker N]
                   │                    │                    │
                   ▼                    ▼                    ▼
              [Batch 1]            [Batch 2]            [Batch N]
                   │                    │                    │
                   └────────────┬───────┴────────────────────┘
                                ▼
         ┌─────────────────────────────────────────────────────────────┐
         │                  STATELESS PIPELINE TASK                    │
         │  • Isolated Process Address Space                           │
         │  • Thread-Safe PyMuPDF Parsing (_pymupdf_lock)             │
         │  • 6M Statement Transaction Parsing                         │
         │  • Deterministic Sanity & Cross-Document Validation         │
         │  • Financial Ratios (DTI, EMI-to-Income, CC Utilization)   │
         │  • Policy Eligibility Gates (Cutoffs, Delinquency Rules)    │
         │  • Mathematical Scoring (7 Weighted Components)             │
         └──────────────────────────────┬──────────────────────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │    RESILIENT RESULT STORE    │
                         │ • Atomic JSONL Checkpointing │
                         │ • Resumable Crash Recovery   │
                         │ • Granular Failure Isolation │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │      COMPLETION BARRIER      │
                         │ • Synchronizes All Batches   │
                         │ • Assembles Portfolio State  │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │  DETERMINISTIC RANKING ENGINE│
                         │ • Multi-Key Portfolio Sort   │
                         │ • 10,000 Applicants in 75ms  │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │   PORTFOLIO LEADERBOARD &    │
                         │      AUDIT METRICS TRACE     │
                         └──────────────────────────────┘
```

### Core Concurrency Mechanisms:

1. **Workload-Aware Greedy Batching (`concurrency/batching.py`)**:
   - Loan folders vary widely in document weight (e.g., 2 simple KYC docs vs. 12 dense multi-page bank statements).
   - Rather than naive round-robin partitioning, each application is weighted by document count $W = \text{doc\_count}$.
   - Applications are sorted in descending order of weight, and a min-heap dynamically routes each application to the worker batch with the lowest accumulated load, preventing stragglers and worker starvation.

2. **Bounded Queue Backpressure & Memory Guarantees (`concurrency/worker_pool.py`)**:
   - Ingesting 10,000 dossiers without bounds would exhaust host RAM by loading thousands of PDF trees simultaneously.
   - The queue between `JobRunner` and `WorkerPool` enforces strict backpressure with `max_queue_size = batch_size * num_workers`.
   - The ingestion producer pauses when worker buffers are full, keeping resident memory flat ($< 82\text{ MB}$) regardless of portfolio size.

3. **Multi-Core ProcessPool Scaling & GIL Bypass (`concurrency/worker_task.py`)**:
   - Processing is distributed across independent OS processes via `ProcessPoolExecutor`, bypassing Python’s Global Interpreter Lock (GIL) to fully utilize multi-core server hardware.
   - Tasks are pure, picklable functions that accept application paths and product configurations, returning structured scores without mutating global state.

4. **Thread-Safe PyMuPDF Ingestion (`pdf_loader.py`)**:
   - PyMuPDF (`pymupdf4llm` / `fitz`) contains internal C-library textpage structures that are not thread-safe. Concurrent access across shared memory can cause `RuntimeError: not a textpage of this page`.
   - Added an internal synchronization lock (`_pymupdf_lock`) in `pdf_loader.py` for multithreaded workflows, while multi-process execution isolates each document parser into independent process address spaces.

5. **Failure Isolation & Resilient Worker Lifecycles (`concurrency/models.py`)**:
   - Each application is tracked through explicit states: `PENDING` $\to$ `RUNNING` $\to$ `COMPLETED` or `FAILED`.
   - If a corrupted PDF or malformed document is encountered, the failure is caught, retried with exponential backoff up to `max_retries`, and quarantined into `failed_applications`. The worker pool continues running uninterrupted.

6. **Atomic Checkpointing & Crash Resumability (`concurrency/result_store.py`)**:
   - A thread-safe `ResultStore` writes atomic append-only JSONL checkpoints (`--checkpoint .checkpoint.jsonl`).
   - If a batch of 10,000 applicants is interrupted at application 7,500, re-running the command with `--checkpoint` immediately detects the completed records, skips them, and finishes the remaining 2,500 applicants without redundant processing.

7. **Rate-Limited LLM Throttling (`concurrency/worker_pool.py`)**:
   - When generating AI executive underwriting summaries, a bounded semaphore (`--max_llm_concurrency`) throttles LLM requests to prevent API rate limits, timeouts, or GPU memory exhaustion.

8. **Strict Invariant Verification**:
   - The system guarantees:
     $$\text{Sequential Output} \equiv \text{Parallel Output}$$
   - Verified across 100% of extracted values, validated amounts, financial ratios, policy gate verdicts, component scores, and ranking positions.

---

## 📈 Performance Benchmarks & Concurrency Scaling

All benchmarks were recorded on an 8–10 core environment using standard loan scenarios and product policy configurations (`personal_loan_v1.json`). Full raw benchmark data is stored in [`benchmarks/benchmark_comparison.json`](benchmarks/benchmark_comparison.json).

### 1. Concurrency Worker Sweep (100 Applications)

Evaluating worker scaling from 1 to 100 parallel workers:

| Workers | Execution Time | Throughput | Speedup Factor | Peak Memory | Operating Profile |
| :---: | :---: | :---: | :---: | :---: | :--- |
| **1** | 15.53s | 6.44 apps/sec | 1.00x | 81.2 MB | Baseline sequential execution |
| **5** | 4.31s | 23.22 apps/sec | 3.61x | 81.3 MB | Near-linear multi-core scaling |
| **10** | **3.20s** | **31.24 apps/sec** | **4.85x** | **81.3 MB** | **Optimal runtime concurrency (80% time reduction)** |
| **20** | 3.54s | 28.29 apps/sec | 4.39x | 81.3 MB | Worker pool capacity ceiling reached |
| **50** | 5.10s | 19.61 apps/sec | 3.04x | 81.3 MB | Context switching & IPC overhead |
| **100** | 7.74s | 12.92 apps/sec | 2.01x | 81.3 MB | Process scheduling contention |

> [!TIP]
> **Recommended Concurrency**: **10 workers** delivers the peak throughput of **31.24 applications/sec**. Increasing beyond 20 workers on an 8–10 core machine introduces unnecessary inter-process communication (IPC) and scheduling overhead.

---

### 2. Scale Comparison: Sequential Baseline vs. Parallel Optimized (10 Workers)

| Application Portfolio Size | Sequential Time | Parallel Time | Speedup Factor | Execution Time Reduction | Sequential Throughput | Parallel Throughput |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **10 Applications** | 1.71s | **0.64s** | **2.69x** | **62.8%** | 5.85 apps/sec | 15.71 apps/sec |
| **100 Applications** | 16.02s | **3.24s** | **4.94x** | **79.8%** | 6.24 apps/sec | 30.83 apps/sec |
| **1,000 Applications** | 160.64s | **33.80s** | **4.75x** | **79.0%** | 6.23 apps/sec | 29.59 apps/sec |
| **10,000 Applications** *(Projected)* | ~1,605s (26.8 min) | **~335s (5.6 min)** | **~4.8x** | **~79.1%** | ~6.2 apps/sec | ~29.9 apps/sec |

---

### 3. Isolated Deterministic Ranking Engine Performance

Benchmarking [`ranking.py`](ranking.py) sorting pre-scored applicants with multi-key tie-breaking:

| Portfolio Scale | Sorting Time | Throughput | Peak Memory | Sorting Complexity |
| :---: | :---: | :---: | :---: | :--- |
| **100 Applicants** | 0.28 ms | 363,086 apps/sec | 227.2 MB | Sub-millisecond sorting |
| **1,000 Applicants** | 3.14 ms | 318,129 apps/sec | 227.2 MB | Multi-key sort (Score, CIBIL, DTI, Income) |
| **10,000 Applicants** | **74.98 ms** | **133,360 apps/sec** | **227.2 MB** | Ranks entire 10k portfolio in under **75 ms** |

---

## ⚙️ 4-Stage Ingestion & Processing Pipeline

The ingestion pipeline strictly decouples input processing from post-scoring verification:

| Stage | Module | Responsibility |
|---|---|---|
| **1. EXTRACTION** | `extract.py`, `pdf_loader.py` | Extracts facts and tables from PDF pages using Jinja prompt templates (`loan_extraction.jinja`) or deterministic rule-based table parsers. `ground_truth.json` is never read as input. |
| **2. PARSING** | `models.py`, `pdf_loader.py` | Populates typed Pydantic models (`LoanApplication`, `ExtractedField[T]`, `SourceEvidence`) retaining page numbers, document names, and verbatim quotes. |
| **3. REFINING** | `validate.py` | Validates data consistency: checks bounds (credit score $\in [300, 900]$, DTI $\ge 0$), currency uniformity, net vs. gross sanity, and cross-document reconciliation (e.g. pay slip monthly income $\times 12$ vs Form 16 / ITR). |
| **4. CALCULATING** | `features.py`, `scoring.py`, `eligibility.py` | Aggregates 6-month statement transactions, derives debt ratios, evaluates product eligibility gates, and calculates weighted component scores. |

---

## 🧮 Deterministic Scoring Engine & Mathematical Rubric

The scoring engine in [`scoring.py`](scoring.py) uses pure mathematical functions without floating-point drift or external heuristics:

$$\text{Final Score} = \sum_{i=1}^{N} \left( \text{Raw Score}_i \times \text{Weight}_i \right)$$

### Standard Personal Loan Model (`personal_loan_v1`):

| Component | Weight | Mathematical Function | Scoring Schedule |
|---|---|---|---|
| **Credit History** | 25% | `calculate_credit_score_rating` | Linear scale: $100 \times \frac{\text{CIBIL} - 300}{900 - 300}$ |
| **Repayment Behavior** | 20% | `calculate_repayment_behavior_score` | $100 - (30 \times \text{Missed Payments}) - (20 \text{ if Overdue} > 0)$ (min: 5.0) |
| **Income Stability** | 15% | `calculate_income_stability_score` | Tenure base score + 6M bank payroll deposit variance penalty |
| **Debt Burden (DTI)** | 15% | `calculate_debt_burden_score` | Stepwise: $\le 20\% \to 100$, $\le 35\% \to 85$, $\le 45\% \to 60$, $\le 55\% \to 25$, $> 55\% \to 10$; revolving CC utilization modifier |
| **Employment Stability**| 10% | `calculate_employment_stability_score`| $\ge 5\text{ yrs} \to 100$, $\ge 3\text{ yrs} \to 80$, $\ge 1\text{ yr} \to 60$, $< 1\text{ yr} \to 40$ |
| **Affordability** | 10% | `calculate_affordability_score` | Proposed EMI-to-income: $\le 20\% \to 100$, $\le 35\% \to 80$, $\le 50\% \to 50$, $> 50\% \to 20$; surplus cash flow buffer |
| **Documentation Quality**| 5% | `calculate_documentation_quality_score`| Verified documents $\div$ Mandatory required documents $\times 100$ |

### Application Criticality Classification:
- **🟢 LOW CRITICALITY (Prime Grade / Low Risk)**: Score $\ge 80$, 0 missed payments, 0 overdue, DTI $\le 35\%$, CIBIL $\ge 720$.
- **🟡 MED CRITICALITY (Moderate Risk / Standard)**: Score $\ge 60$, $\le 1$ missed payment, DTI $\le 45\%$, CIBIL $\ge 650$.
- **🔴 HIGH CRITICALITY (High Risk / Subprime)**: Score $< 60$, multiple missed payments, active overdue balance, or severe debt saturation.

---

## 🚪 Policy Gating & Eligibility Engine

Scoring is decoupled from policy eligibility. Products are declared via versioned JSON files in `loan_products/`:

```json
{
  "product_id": "personal_loan_v1",
  "min_credit_score": 600,
  "max_dti": 0.50,
  "max_emi_to_income": 0.50,
  "max_missed_payments_12m": 2,
  "mandatory_documents": [
    "IDENTITY_VERIFIED",
    "INCOME_PROOF_VERIFIED",
    "BANK_STATEMENT_VERIFIED"
  ]
}
```

Applicants who breach hard policy gates (such as severe delinquencies, credit score below 600, or missing KYC) are segregated into the **Ineligible Queue** with explicit reason codes (e.g., `CREDIT_SCORE_BELOW_THRESHOLD`, `MISSING_MANDATORY_DOC_IDENTITY_VERIFIED`), regardless of secondary metrics.

---

## 🤖 Parallel LLM Underwriting Evaluation

In parallel with mathematical scoring, the LLM (`explain.py`) generates a structured underwriting evaluation:
1. **Executive Underwriting Verdict**: A concise 1–2 sentence synthesis of credit posture.
2. **Pros (Strengths)**: Tagged with criticality: `[HIGH CRITICALITY]`, `[MED CRITICALITY]`, or `[LOW CRITICALITY]`.
3. **Cons (Risks & Vulnerabilities)**: Tagged with criticality: `[HIGH CRITICALITY]`, `[MED CRITICALITY]`, or `[LOW CRITICALITY]`.
4. **Grounding Assertion**: Code validates that figures mentioned in the summary match verified features in the deterministic calculation trace.

---

## 🏆 Portfolio Leaderboard & Ranking Engine

When multiple applicants are evaluated, [`ranking.py`](ranking.py) applies a multi-key deterministic sort:
$$\text{Sort Key} = (\text{Final Score DESC}, \text{Credit Score DESC}, \text{DTI ASC}, \text{Net Monthly Income DESC}, \text{App ID ASC})$$

### Sample CLI Terminal Output:

```
==============================================================================================================
  🏆 FINAL LOAN APPLICATION RANKING & PORTFOLIO LEADERBOARD
  Model: personal_loan_v1 | Total Applications Evaluated: 7
==============================================================================================================

  ⭐ QUALIFIED APPLICANTS (Ranked 1 to 5 by Score):
  ----------------------------------------------------------------------------------------------------------
  Rank  | App ID                             | Applicant Name     | Score    | Criticality     | Credit   | DTI      | Monthly Net
  ----------------------------------------------------------------------------------------------------------
  1     | test1_salaried_good                | Rohan Sharma       | 94.17    | 🟢 LOW RISK      | 784      | 14.4%    | ₹125,000.00
  2     | test3_business_good                | Meera Iyer         | 87.08    | 🟢 LOW RISK      | 770      | N/A      | ₹150,000.00
  3     | test7_business_moderate_margin   | Amitav Sen         | 78.18    | 🟡 MED RISK      | 680      | 23.5%    | ₹85,000.00
  4     | test6_salaried_fair_credit_high_cc | Priya Nambiar      | 77.17    | 🟡 MED RISK      | 670      | 12.9%    | ₹62,000.00
  5     | test5_salaried_moderate_dti        | Vikram Malhotra    | 71.58    | 🟡 MED RISK      | 710      | 22.2%    | ₹72,000.00
  ----------------------------------------------------------------------------------------------------------

  ❌ INELIGIBLE QUEUE (Failed Policy Gates / Severe Delinquencies):
  ----------------------------------------------------------------------------------------------------------
  App ID                   | Applicant Name     | Score    | Criticality     | Primary Gate Failure(s)
  ----------------------------------------------------------------------------------------------------------
  test4_business_bad       | Rajesh Gupta       | 40.67    | 🔴 HIGH RISK     | MISSING_MANDATORY_DOC_IDENTITY_VERIFIED
  test2_salaried_bad       | Karan Malhotra     | 30.52    | 🔴 HIGH RISK     | CREDIT_SCORE_BELOW_THRESHOLD (Got 550, Req 600)
  ----------------------------------------------------------------------------------------------------------
==============================================================================================================
```

---

## 📊 Executive PDF Dossier Report (`result.pdf`)

The agent includes a publication-grade PDF generator ([`scripts/generate_result_pdf.py`](scripts/generate_result_pdf.py)) creating [`result.pdf`](result.pdf):

- **Page 1: Executive Portfolio Summary & Leaderboard**: KPI cards (Evaluated: 7, Qualified: 5, Ineligible: 2, Avg Score: 81.6), full applicant comparison matrix, qualified ranking table, and adverse policy rejection queue.
- **Pages 2–8: Comprehensive Applicant Dossiers**:
  - Underwriting decision status, score pill, and risk criticality badge.
  - Component scoring breakdown table (Component, Raw Score, Weight, Contribution, Audit Trace).
  - 6-Month statement transaction rollups & financial ratios (credits, debits, verified payroll salary, EMI debits, credit card utilization, spends).
  - Parallel LLM Underwriting Evaluation (Executive verdict, pros & cons categorized by criticality).
  - Audit stamp & running pagination ("Page X of 8").

---

## 📁 Synthetic PDF Test Scenarios

The test repository in [`data/pdf_scenarios/`](data/pdf_scenarios/) features realistic PDF scenarios equipped with fantastical bank names and 6 months of itemized transactions:

| Scenario Directory | Profile | CIBIL | Financial Institution | 6M Card Util | Expected Score | Outcome |
|---|---|---|---|---|---|---|
| `test1_salaried_good` | Rohan Sharma | 784 | Bank of Wonderland & Mars | 9.3% | **94.17** | 🟢 Eligible |
| `test3_business_good` | Meera Iyer | 770 | Intergalactic Bank of Andromeda | 9.0% | **87.08** | 🟢 Eligible |
| `test7_business_moderate_margin` | Amitav Sen | 680 | Cybertron Sovereign NeoBank | 41.0% | **78.18** | 🟡 Eligible |
| `test6_salaried_fair_credit_high_cc` | Priya Nambiar | 670 | Valhalla Alpine Commercial Bank | 68.0% | **77.17** | 🟡 Eligible |
| `test5_salaried_moderate_dti` | Vikram Malhotra | 710 | Mystic River International Bank | 32.0% | **71.58** | 🟡 Eligible |
| `test4_business_bad` | Rajesh Gupta | 580 | Gryffindor Magical Vault Bank | 90.4% | **40.67** | 🔴 Ineligible |
| `test2_salaried_bad` | Karan Malhotra | 550 | Atlantis Subsea Crypto Bank | 98.5% | **30.52** | 🔴 Ineligible |

---

## 🚀 Getting Started & Quickstart

### 1. Prerequisites
- Python 3.9+ (Python 3.11 recommended)
- Local Ollama instance (or remote cloud model via OpenAI-compatible endpoint)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/Harshavardhanpentakota/loan-scoring-project.git
cd loan-scoring-project

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Model Configuration
Configure your model endpoint in `providers.json` or through environment variables (`.env`):
```json
{
  "default_model": "gemma4:31b-cloud",
  "providers": {
    "ollama": {
      "base_url": "http://localhost:11434/v1",
      "models": {
        "gemma4:31b-cloud": {
          "temperature": 0.0,
          "top_p": 1.0
        }
      }
    }
  }
}
```

---

## 💻 CLI Reference

### High-Throughput Parallel Ingestion (Default)
Ingests and underwrites applicant portfolios concurrently using bounded worker pools:
```bash
# Ingest all scenarios with auto-detected multi-core worker pool
python score.py --pdf_dir data/pdf_scenarios --product loan_products/personal_loan_v1.json

# Specify 10 parallel workers with batch size of 20
python score.py --pdf_dir data/pdf_scenarios --product loan_products/personal_loan_v1.json --workers 10 --batch_size 20

# Enable crash-resilient atomic checkpointing for 10,000+ application runs
python score.py --pdf_dir /path/to/10k_applications --product loan_products/personal_loan_v1.json --checkpoint .checkpoint.jsonl
```

### Single-Threaded Sequential Mode (Baseline Invariant)
To execute the pipeline strictly sequentially without spawning worker pools:
```bash
python score.py --pdf_dir data/pdf_scenarios --product loan_products/personal_loan_v1.json --sequential
```

### Underwrite a Single Applicant Folder
```bash
python score.py --pdf_dir data/pdf_scenarios/test1_salaried_good --product loan_products/personal_loan_v1.json
```

### Audit Extracted Data Against Ground Truth Benchmark
```bash
python score.py --pdf_dir data/pdf_scenarios --product loan_products/personal_loan_v1.json --audit
```

### Generate the Executive Multi-Page PDF Report
```bash
python scripts/generate_result_pdf.py
```

### CLI Flag Reference Table

| Flag | Type | Default | Description |
|---|---|---|---|
| `--pdf_dir` | `str` | *Required* | Path to folder containing PDFs or root directory containing application subfolders. |
| `--product` | `str` | *Required* | Path to loan product policy JSON (e.g., `loan_products/personal_loan_v1.json`). |
| `--workers` | `int` | `CPU + 4` (max 32) | Number of parallel worker processes. Set to 10 for peak throughput. |
| `--sequential` | `flag` | `False` | Run applications in a single thread sequentially for strict baseline comparison. |
| `--batch_size` | `int` | `10` | Maximum applications grouped into a single worker batch. |
| `--max_llm_concurrency`| `int` | `4` | Max concurrent LLM requests to throttle API/GPU consumption during explanation. |
| `--checkpoint` | `str` | `.checkpoint.jsonl` | Path to atomic JSONL checkpoint file for resume capability on crash/interruption. |
| `--output_dir` | `str` | `output/` | Directory where ranking leaderboards and underwriting traces are saved. |
| `--audit` | `flag` | `False` | Compares extracted applicant data against `ground_truth.json` benchmarks. |

---

## 🧪 Automated 4-Layer Test Suite

Run the full test suite verifying determinism, invariants, validation rules, grounding, and concurrency:
```bash
# Run core test suite (22 / 22 Tests Passing)
python run_tests.py

# Run parallel concurrency & invariant verification suite
python -m unittest tests/test_concurrency.py
```

### Test Coverage (22 / 22 Core Suites + Concurrency Suite):
- **Layer 1: Extraction & Null Safety** (`test_extraction.py`): Verifies structured field extraction; enforces that missing fields remain `None` (no silent substitution with 0).
- **Layer 2: Calculation & Ratios** (`test_features.py`): Mathematical correctness of DTI, EMI-to-income, LTI, debt-to-revenue, and revolving card utilization.
- **Layer 3: Scoring Invariants** (`test_scoring.py`): Verifies exact scoring reproducibility across 100 repeated runs, custom weight schedules, and contribution traces.
- **Layer 4: Explanation Grounding** (`test_explanation.py`): Catches and rejects hallucinated numbers, altered final scores, and ungrounded statements.
- **Integration Tests** (`test_validation.py`, `test_ranking.py`, `test_end_to_end_pipeline.py`): Tests multi-applicant ranking, tie-breaking, and policy gating.
- **Concurrency & Invariant Suite** (`tests/test_concurrency.py`):
  - Greedy min-heap batch load balancing and variance minimization.
  - Resumable checkpointing and recovery without duplicate work.
  - Failure isolation across malformed or corrupted application directories.
  - Mathematical and ranking identity: `Sequential Result == Parallel Result`.

---

## 📜 Lineage & Copyright Notice

This repository originated from the [HackerRank hiring-agent](https://github.com/interviewstreet/hiring-agent) architecture and has been re-architected into a deterministic loan underwriting and applicant ranking agent.

- Original codebase copyright: **Copyright (c) 2025 HackerRank**
- Licensed under the **MIT License**. See the [`LICENSE`](LICENSE) file for complete terms and copyright preservation.
