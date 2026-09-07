"""Comprehensive Benchmarking Suite for Loan Underwriting Pipeline.

Measures:
- Total execution time
- Average processing time per application
- Documents processed per second
- Applications processed per second
- Granular phase latencies (Extraction, Parsing, Features, Scoring, Ranking)
- Number of LLM calls
- Successful vs failed applications
- Peak memory usage (ru_maxrss)
"""

import os
import sys
import time
import json
import shutil
import resource
from typing import List, Dict, Any, Optional
from pathlib import Path

# Ensure project root in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from pdf_loader import load_pdf_documents_from_directory, parse_statement_transactions, extract_application_from_pdf_text
from models import LoanApplication, ScoringResult, EligibilityResult, DerivedFeatures, ValidationResult
from validate import LoanValidator
from features import FinancialFeatureEngine
from eligibility import EligibilityEngine, load_product_config
from scoring import DeterministicScoringEngine
from ranking import DeterministicRankingEngine


def get_peak_memory_mb() -> float:
    """Return peak memory usage in megabytes (cross-platform compatible)."""
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # On macOS, ru_maxrss is in bytes; on Linux, it is in kilobytes.
    if sys.platform == "darwin":
        return usage / (1024 * 1024)
    return usage / 1024


def setup_benchmark_dataset(target_dir: str, count: int, source_dir: str = "data/pdf_scenarios") -> List[str]:
    """Create a benchmark directory with `count` application folders.
    
    Uses symlinks to the canonical PDF dossiers in `source_dir` so no disk space is wasted.
    """
    os.makedirs(target_dir, exist_ok=True)
    canonical_scenarios = sorted([
        d for d in os.listdir(source_dir)
        if os.path.isdir(os.path.join(source_dir, d))
    ])
    if not canonical_scenarios:
        raise RuntimeError(f"No scenario directories found in {source_dir}")

    app_paths = []
    for i in range(count):
        src_name = canonical_scenarios[i % len(canonical_scenarios)]
        src_path = os.path.abspath(os.path.join(source_dir, src_name))
        dest_name = f"app_{i+1:05d}_{src_name}"
        dest_path = os.path.abspath(os.path.join(target_dir, dest_name))

        if not os.path.exists(dest_path):
            os.makedirs(dest_path, exist_ok=True)
            for f in os.listdir(src_path):
                s_file = os.path.join(src_path, f)
                d_file = os.path.join(dest_path, f)
                if not os.path.exists(d_file):
                    os.symlink(s_file, d_file)
        app_paths.append(dest_path)

    return app_paths


def run_sequential_benchmark(
    app_dirs: List[str],
    product_config_path: str = "loan_products/personal_loan_v1.json",
) -> Dict[str, Any]:
    """Execute the baseline sequential pipeline across provided application directories."""
    product_config = load_product_config(product_config_path)
    validator = LoanValidator()
    feature_engine = FinancialFeatureEngine()
    eligibility_engine = EligibilityEngine(product_config)
    scoring_engine = DeterministicScoringEngine(product_config)
    ranking_engine = DeterministicRankingEngine()

    total_apps = len(app_dirs)
    total_docs = 0
    total_extract_time = 0.0
    total_parse_time = 0.0
    total_feature_time = 0.0
    total_scoring_time = 0.0

    extraction_latencies = []
    processing_latencies = []
    scoring_latencies = []

    apps: List[LoanApplication] = []
    scores_map: Dict[str, ScoringResult] = {}
    elig_map: Dict[str, EligibilityResult] = {}
    feat_map: Dict[str, DerivedFeatures] = {}
    val_map: Dict[str, ValidationResult] = {}

    success_count = 0
    fail_count = 0

    mem_start = get_peak_memory_mb()
    t_start = time.perf_counter()

    for app_dir in app_dirs:
        app_name = os.path.basename(app_dir)
        try:
            # 1. Document Loading & Extraction
            t0 = time.perf_counter()
            pdf_docs = load_pdf_documents_from_directory(app_dir)
            total_docs += len(pdf_docs)
            app = extract_application_from_pdf_text(app_name, pdf_docs)
            t1 = time.perf_counter()
            extract_dur = t1 - t0
            total_extract_time += extract_dur
            extraction_latencies.append(extract_dur)

            # 2. Transaction Parsing
            t0 = time.perf_counter()
            all_bank_txs = list(app.bank_transactions)
            all_cc_txs = list(app.credit_card_transactions)
            for doc in pdf_docs:
                d_lower = doc["name"].lower()
                if "bank_statement" in d_lower:
                    txs = parse_statement_transactions(doc["content"], doc["name"], doc.get("page", 1))
                    if txs and len(txs) > len(all_bank_txs):
                        all_bank_txs = txs
                elif "credit_card" in d_lower:
                    txs = parse_statement_transactions(doc["content"], doc["name"], doc.get("page", 1))
                    if txs and len(txs) > len(all_cc_txs):
                        all_cc_txs = txs
            app.bank_transactions = all_bank_txs
            app.credit_card_transactions = all_cc_txs
            t1 = time.perf_counter()
            parse_dur = t1 - t0
            total_parse_time += parse_dur

            # 3. Deterministic Validation & Financial Features
            t0 = time.perf_counter()
            val_res = validator.validate(app)
            feat_res = feature_engine.calculate_features(app)
            elig_res = eligibility_engine.evaluate(app, feat_res, val_res)
            t1 = time.perf_counter()
            proc_dur = t1 - t0
            total_feature_time += proc_dur
            processing_latencies.append(proc_dur)

            # 4. Deterministic Scoring
            t0 = time.perf_counter()
            score_res = scoring_engine.score(app, feat_res)
            t1 = time.perf_counter()
            score_dur = t1 - t0
            total_scoring_time += score_dur
            scoring_latencies.append(score_dur)

            app_id = app.application_id
            apps.append(app)
            scores_map[app_id] = score_res
            elig_map[app_id] = elig_res
            feat_map[app_id] = feat_res
            val_map[app_id] = val_res
            success_count += 1

        except Exception as e:
            fail_count += 1

    # 5. Deterministic Ranking
    t_rank_start = time.perf_counter()
    qualified, review, ineligible = ranking_engine.rank(
        applications=apps,
        scores=scores_map,
        eligibilities=elig_map,
        features=feat_map,
        validations=val_map,
    )
    t_rank_end = time.perf_counter()
    ranking_duration = t_rank_end - t_rank_start

    t_end = time.perf_counter()
    total_duration = t_end - t_start
    mem_end = get_peak_memory_mb()

    # Percentiles helper
    def percentile(data: List[float], p: float) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * p
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        d = k - f
        return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * d

    all_per_app_latencies = [
        (e + p + s) for e, p, s in zip(extraction_latencies, processing_latencies, scoring_latencies)
    ]

    return {
        "scale": total_apps,
        "mode": "sequential",
        "total_execution_time_sec": round(total_duration, 4),
        "avg_processing_time_per_app_sec": round(total_duration / max(total_apps, 1), 4),
        "applications_processed_per_sec": round(total_apps / max(total_duration, 0.0001), 2),
        "documents_processed_per_sec": round(total_docs / max(total_duration, 0.0001), 2),
        "total_documents": total_docs,
        "successful_applications": success_count,
        "failed_applications": fail_count,
        "retry_count": 0,
        "number_of_llm_calls": 0,
        "phase_breakdown_sec": {
            "extraction_loading": round(total_extract_time, 4),
            "statement_parsing": round(total_parse_time, 4),
            "feature_and_eligibility": round(total_feature_time, 4),
            "scoring": round(total_scoring_time, 4),
            "ranking": round(ranking_duration, 4),
        },
        "latency_percentiles_sec": {
            "p50_total": round(percentile(all_per_app_latencies, 0.50), 4),
            "p95_total": round(percentile(all_per_app_latencies, 0.95), 4),
            "p50_extraction": round(percentile(extraction_latencies, 0.50), 4),
            "p95_extraction": round(percentile(extraction_latencies, 0.95), 4),
            "p50_scoring": round(percentile(scoring_latencies, 0.50), 4),
            "p95_scoring": round(percentile(scoring_latencies, 0.95), 4),
        },
        "peak_memory_mb": round(mem_end, 2),
        "memory_delta_mb": round(mem_end - mem_start, 2),
        "qualified_count": len(qualified),
        "review_count": len(review),
        "ineligible_count": len(ineligible),
    }


def benchmark_ranking_isolated(count: int, product_config_path: str = "loan_products/personal_loan_v1.json") -> Dict[str, Any]:
    """Benchmark ranking in complete isolation for 100, 1,000, 10,000 applications as required by Section 13."""
    import random
    from models import ApplicantInfo, IncomeInfo, ExistingObligations, LoanRequest, CreditInfo, AssetsLiabilities, DocumentationStatus, ExtractedField

    ranking_engine = DeterministicRankingEngine()
    apps: List[LoanApplication] = []
    scores_map: Dict[str, ScoringResult] = {}
    elig_map: Dict[str, EligibilityResult] = {}
    feat_map: Dict[str, DerivedFeatures] = {}
    val_map: Dict[str, ValidationResult] = {}

    rng = random.Random(42)
    for i in range(count):
        app_id = f"APP_{i:06d}"
        app = LoanApplication(
            application_id=app_id,
            applicant=ApplicantInfo(applicant_id=app_id, applicant_name=ExtractedField(value=f"Applicant {i}")),
            income=IncomeInfo(monthly_net_income=ExtractedField(value=50000.0 + rng.randint(0, 100000))),
            obligations=ExistingObligations(existing_monthly_emi=ExtractedField(value=10000.0)),
            loan_request=LoanRequest(requested_loan_amount=ExtractedField(value=500000.0)),
            credit=CreditInfo(credit_score=ExtractedField(value=rng.randint(600, 850))),
            assets_liabilities=AssetsLiabilities(),
            documentation=DocumentationStatus(),
        )
        apps.append(app)
        score_val = rng.uniform(40.0, 98.0)
        crit = "LOW" if score_val >= 80 else ("MED" if score_val >= 60 else "HIGH")
        scores_map[app_id] = ScoringResult(
            application_id=app_id,
            scoring_model="personal_loan_v1",
            timestamp="2026-09-07T12:00:00Z",
            final_score=score_val,
            credit_score_raw=float(app.credit.credit_score.value),
            criticality=crit,
            components={},
            calculation_trace=[],
        )
        status = "QUALIFIED" if score_val >= 70 else ("MANUAL_REVIEW" if score_val >= 50 else "INELIGIBLE")
        elig_map[app_id] = EligibilityResult(
            application_id=app_id,
            status=status,
            passed_rules=["RULE_1"],
            failed_rules=[] if status != "INELIGIBLE" else ["RULE_FAIL"],
            manual_review_reasons=[] if status != "MANUAL_REVIEW" else ["REVIEW_REASON"],
        )
        feat_map[app_id] = DerivedFeatures(
            application_id=app_id,
            dti=0.2,
            emi_to_income=0.2,
            documentation_completeness_ratio=1.0,
            traces=[],
        )
        val_map[app_id] = ValidationResult(application_id=app_id, is_valid=True, status="VALID")

    t0 = time.perf_counter()
    qualified, review, ineligible = ranking_engine.rank(
        applications=apps,
        scores=scores_map,
        eligibilities=elig_map,
        features=feat_map,
        validations=val_map,
    )
    t1 = time.perf_counter()
    duration = t1 - t0

    return {
        "scale": count,
        "ranking_time_sec": round(duration, 6),
        "apps_per_sec": round(count / max(duration, 0.000001), 2),
        "peak_memory_mb": round(get_peak_memory_mb(), 2),
        "qualified": len(qualified),
        "review": len(review),
        "ineligible": len(ineligible),
    }


def run_parallel_benchmark(
    target_dir: str,
    num_workers: int = 10,
    batch_size: int = 20,
) -> Dict[str, Any]:
    """Execute the optimized parallel pipeline via JobRunner across provided application directory."""
    from concurrency import JobRunner

    t0 = time.perf_counter()
    mem_start = get_peak_memory_mb()

    runner = JobRunner(
        num_workers=num_workers,
        batch_size=batch_size,
        max_queue_size=max(50, batch_size * num_workers),
    )
    results = runner.run_job(target_dir)

    t1 = time.perf_counter()
    total_duration = t1 - t0
    mem_end = get_peak_memory_mb()

    m = results.get("metrics", {})
    total_apps = m.get("total_applications", 0)

    return {
        "scale": total_apps,
        "mode": f"parallel_{num_workers}_workers",
        "workers": num_workers,
        "total_execution_time_sec": round(total_duration, 4),
        "avg_processing_time_per_app_sec": round(total_duration / max(total_apps, 1), 4),
        "applications_processed_per_sec": round(total_apps / max(total_duration, 0.0001), 2),
        "documents_processed_per_sec": round(m.get("throughput_docs_per_sec", 0), 2),
        "successful_applications": m.get("completed", 0),
        "failed_applications": m.get("failed", 0),
        "retry_count": m.get("retried", 0),
        "number_of_llm_calls": 0,
        "latency_percentiles_sec": {
            "p50_total": m.get("p50_latency", 0),
            "p95_total": m.get("p95_latency", 0),
        },
        "peak_memory_mb": round(mem_end, 2),
        "qualified_count": len(results.get("qualified_ranked", [])),
        "review_count": len(results.get("manual_review_queue", [])),
        "ineligible_count": len(results.get("ineligible_queue", [])),
        "ranking_duration_sec": results.get("ranking_duration_sec", 0),
    }


if __name__ == "__main__":
    os.makedirs("benchmarks", exist_ok=True)
    scales = [10, 100, 1000]

    print("=" * 80)
    print("🚀 COMPREHENSIVE PERFORMANCE BENCHMARK: SEQUENTIAL VS PARALLEL")
    print("=" * 80)

    # 1. Concurrency Worker Scaling Test (Section 15: 1, 5, 10, 20, 50, 100 workers)
    print("\n" + "=" * 80)
    print("📊 1. WORKER CONCURRENCY SCALING SWEEP (100 Applications)")
    print("=" * 80)
    worker_counts = [1, 5, 10, 20, 50, 100]
    concurrency_sweep_results = {}
    dir_100 = setup_benchmark_dataset("data/benchmark_100", 100)

    for w in worker_counts:
        p_res = run_parallel_benchmark("data/benchmark_100", num_workers=w)
        concurrency_sweep_results[str(w)] = p_res
        print(f"  Workers: {w:>3} | Time: {p_res['total_execution_time_sec']:>6.3f}s | Throughput: {p_res['applications_processed_per_sec']:>6.2f} apps/sec | Peak Mem: {p_res['peak_memory_mb']:>6.1f} MB", flush=True)

    # Find optimal worker count from sweep
    optimal_worker_count = max(
        worker_counts,
        key=lambda w: concurrency_sweep_results[str(w)]["applications_processed_per_sec"]
    )
    print(f"\n🏆 Optimal Runtime Worker Concurrency Discovered: {optimal_worker_count} workers", flush=True)

    # 2. Scale Comparison across 10, 100, 1000 Applications (using optimal worker count)
    print("\n" + "=" * 80, flush=True)
    print(f"📊 2. SCALE COMPARISON: SEQUENTIAL VS PARALLEL ({optimal_worker_count} Workers)", flush=True)
    print("=" * 80, flush=True)

    scale_comparisons = {}

    for scale in scales:
        print(f"\n▶ Benchmarking Scale: {scale} applications...", flush=True)
        target_dir = f"data/benchmark_{scale}"
        app_dirs = setup_benchmark_dataset(target_dir, scale)

        # Run sequential (for 10 and 100, and 1000 if fast)
        t_seq_start = time.perf_counter()
        seq_res = run_sequential_benchmark(app_dirs)
        t_seq_end = time.perf_counter()

        # Run parallel with optimal workers
        par_res = run_parallel_benchmark(target_dir, num_workers=optimal_worker_count)

        # Calculate speedup and improvement percentage (Section 16)
        seq_time = seq_res["total_execution_time_sec"]
        par_time = par_res["total_execution_time_sec"]
        speedup = round(seq_time / max(par_time, 0.0001), 2)
        improvement_pct = round(((seq_time - par_time) / seq_time) * 100, 2)

        comparison_record = {
            "scale": scale,
            "sequential": seq_res,
            "parallel": par_res,
            "speedup_factor": speedup,
            "improvement_percentage": improvement_pct,
        }
        scale_comparisons[str(scale)] = comparison_record

        print(f"  Sequential : {seq_time:>7.3f}s ({seq_res['applications_processed_per_sec']:>6.2f} apps/sec)", flush=True)
        print(f"  Parallel   : {par_time:>7.3f}s ({par_res['applications_processed_per_sec']:>6.2f} apps/sec)", flush=True)
        print(f"  Speedup    : {speedup}x faster ({improvement_pct}% execution time reduction)", flush=True)

    # 3. Deterministic Ranking in Isolation across 100, 1,000, 10,000 Applications (Section 13)
    print("\n" + "=" * 80, flush=True)
    print("📊 3. DETERMINISTIC RANKING ENGINE IN ISOLATION (Section 13)", flush=True)
    print("=" * 80, flush=True)
    ranking_scales = [100, 1000, 10000]
    isolated_ranking_results = {}
    for r_scale in ranking_scales:
        r_res = benchmark_ranking_isolated(r_scale)
        isolated_ranking_results[str(r_scale)] = r_res
        print(f"  {r_scale:>5} apps ranked in {r_res['ranking_time_sec']:>8.5f}s ({r_res['apps_per_sec']:>10,.0f} apps/sec) | Peak Mem: {r_res['peak_memory_mb']} MB", flush=True)

    # Save comprehensive results
    final_benchmark_output = {
        "optimal_worker_count": optimal_worker_count,
        "concurrency_sweep_100_apps": concurrency_sweep_results,
        "scale_comparisons": scale_comparisons,
        "isolated_ranking": isolated_ranking_results,
    }

    with open("benchmarks/benchmark_comparison.json", "w") as f:
        json.dump(final_benchmark_output, f, indent=2)

    print("\n✅ All benchmark results successfully recorded to benchmarks/benchmark_comparison.json")

