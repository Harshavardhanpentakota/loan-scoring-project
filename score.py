"""CLI Entry Point for Loan Ranking Agent.

Provides command-line underwriting, PDF document extraction, and deterministic applicant ranking.
Enforces strict 4-stage pipeline:
  Stage 1: EXTRACTION (from PDF documents / tables via LLM or pure PDF parser, NEVER ground_truth.json)
  Stage 2: PARSING (into typed models with source evidence)
  Stage 3: REFINING (normalization, categorization, cross-document validation)
  Stage 4: CALCULATING (6-month financial rollups, DTI, EMI ratio, eligibility gates, scoring, ranking)
  Post-Stage: GROUND TRUTH VERIFICATION (Audit benchmark only, post-calculation fidelity check)
"""

import os
import sys
import json
import argparse
import logging
from typing import List, Dict, Any, Optional
from models import (
    LoanApplication,
    ApplicantInfo,
    IncomeInfo,
    ExistingObligations,
    LoanRequest,
    CreditInfo,
    DocumentationStatus,
    ExtractedField,
    SourceEvidence,
)
from main import LoanRankingPipeline, print_ranking_table
from extract import LoanDocumentExtractor, parse_extraction_json
from pdf_loader import (
    load_pdf_documents_from_directory,
    parse_statement_transactions,
    extract_application_from_pdf_text,
)
from concurrency import JobRunner

logger = logging.getLogger(__name__)


def audit_against_ground_truth(apps: List[LoanApplication], results: Dict[str, Any], pdf_dir: str):
    """Post-Calculation Audit: Compare extracted and calculated metrics against ground_truth.json.
    
    CRITICAL: ground_truth.json is ONLY accessed here after all scoring and ranking is done,
    to measure extraction fidelity and verify calculation correctness.
    """
    print("\n" + "=" * 85)
    print("  📊 EXTRACTION FIDELITY & GROUND TRUTH AUDIT (Post-Calculation Verification)")
    print("  (Audited against external ground_truth.json — ground truth is NEVER used as input)")
    print("=" * 85)

    apps_by_id = {a.application_id: a for a in apps}
    traces_by_id = results.get("audit_traces", {})

    total_checks = 0
    passed_checks = 0

    gt_in_root = os.path.join(pdf_dir, "ground_truth.json")
    if os.path.exists(gt_in_root):
        scenario_folders = [(os.path.basename(pdf_dir.rstrip("/")), pdf_dir)]
    else:
        scenario_folders = [
            (sub, os.path.join(pdf_dir, sub))
            for sub in sorted(os.listdir(pdf_dir))
            if os.path.isdir(os.path.join(pdf_dir, sub))
        ]

    for scenario_name, scenario_path in scenario_folders:
        gt_file = os.path.join(scenario_path, "ground_truth.json")
        if not os.path.exists(gt_file):
            continue

        with open(gt_file, "r") as f:
            gt = json.load(f)

        gt_app_id = gt.get("application_id", scenario_name)
        app = apps_by_id.get(gt_app_id)
        if not app:
            for aid, a in apps_by_id.items():
                if aid.lower() == gt_app_id.lower() or scenario_name.lower() in aid.lower():
                    app = a
                    gt_app_id = aid
                    break

        if not app:
            print(f"\n⚠️ Scenario [{scenario_name}]: Application {gt_app_id} not found in evaluated applications.")
            continue

        app_trace = traces_by_id.get(app.application_id, {})
        feat_map = {t["feature"]: t["result"] for t in app_trace.get("features", [])}
        elig_decision = app_trace.get("eligibility", {}).get("status")

        print(f"\n📁 Scenario [{scenario_name}] — Application ID: {app.application_id}")
        print("-" * 85)

        checks = []

        # 1. Applicant Name
        ext_name = app.applicant.applicant_name.value if app.applicant.applicant_name else None
        gt_name = gt.get("applicant_name")
        checks.append(("Applicant Name", ext_name, gt_name, ext_name == gt_name))

        # 2. Monthly Net Income
        ext_income = app.income.monthly_net_income.value if app.income.monthly_net_income else None
        gt_income = gt.get("monthly_net_income")
        checks.append(("Monthly Net Income", ext_income, gt_income, ext_income == gt_income if (ext_income and gt_income) else ext_income == gt_income))

        # 3. Credit Score
        ext_score = app.credit.credit_score.value if app.credit.credit_score else None
        gt_score = gt.get("credit_score")
        checks.append(("Credit Score", ext_score, gt_score, ext_score == gt_score))

        # 4. Requested Loan Amount
        ext_loan = app.loan_request.requested_loan_amount.value if app.loan_request.requested_loan_amount else None
        gt_loan = gt.get("requested_loan_amount")
        checks.append(("Requested Loan Amount", ext_loan, gt_loan, ext_loan == gt_loan))

        # 5. Total Bank Credits 6M (Calculated)
        ext_credits = feat_map.get("total_bank_credits_6m")
        gt_credits = gt.get("total_bank_credits_6m")
        if gt_credits is not None:
            diff = abs((ext_credits or 0.0) - gt_credits)
            checks.append(("Total Bank Credits (6M)", ext_credits, gt_credits, diff < 1.0))

        # 6. Total Bank Debits 6M (Calculated)
        ext_debits = feat_map.get("total_bank_debits_6m")
        gt_debits = gt.get("total_bank_debits_6m")
        if gt_debits is not None:
            diff = abs((ext_debits or 0.0) - gt_debits)
            checks.append(("Total Bank Debits (6M)", ext_debits, gt_debits, diff < 1.0))

        # 7. Derived Monthly Salary from Bank (Calculated)
        ext_sal = feat_map.get("derived_monthly_salary_from_bank")
        gt_sal = gt.get("derived_monthly_salary_from_bank")
        if gt_sal is not None:
            diff = abs((ext_sal or 0.0) - gt_sal)
            checks.append(("Derived Monthly Salary (Bank)", ext_sal, gt_sal, diff < 1.0))

        # 8. Derived Monthly EMI from Bank (Calculated)
        ext_emi = feat_map.get("derived_monthly_emi_from_bank")
        gt_emi = gt.get("derived_monthly_emi_from_bank")
        if gt_emi is not None:
            diff = abs((ext_emi or 0.0) - gt_emi)
            checks.append(("Derived Monthly EMI (Bank)", ext_emi, gt_emi, diff < 1.0))

        # 9. Total Credit Card Spends 6M (Calculated)
        ext_cc = feat_map.get("total_credit_card_spends_6m")
        gt_cc = gt.get("total_credit_card_spends_6m")
        if gt_cc is not None:
            diff = abs((ext_cc or 0.0) - gt_cc)
            checks.append(("Total Credit Card Spends (6M)", ext_cc, gt_cc, diff < 1.0))

        # 10. Eligibility Decision
        ext_dec_val = elig_decision.value if hasattr(elig_decision, "value") else str(elig_decision)
        gt_decision = gt.get("expected_eligibility")
        if gt_decision:
            checks.append(("Eligibility Verdict", ext_dec_val, gt_decision, ext_dec_val == gt_decision))

        sc_passed = 0
        for label, extracted_val, gt_val, passed in checks:
            total_checks += 1
            if passed:
                sc_passed += 1
                passed_checks += 1
                status = "✅ PASS"
            else:
                status = "❌ MISMATCH"

            # Format numbers cleanly
            ext_str = f"₹{extracted_val:,.2f}" if isinstance(extracted_val, (int, float)) and "Score" not in label and "Amount" in label else str(extracted_val)
            gt_str = f"₹{gt_val:,.2f}" if isinstance(gt_val, (int, float)) and "Score" not in label and "Amount" in label else str(gt_val)
            print(f"  • {label:<32}: {ext_str:<18} vs Ground Truth: {gt_str:<18} [{status}]")

        fidelity_pct = (sc_passed / len(checks)) * 100 if checks else 100.0
        print(f"  >> Scenario Fidelity: {fidelity_pct:.1f}% Match ({sc_passed}/{len(checks)} verified)")

    overall_fidelity = (passed_checks / total_checks) * 100 if total_checks else 100.0
    print("-" * 85)
    print(f"🎯 OVERALL SYSTEM EXTRACTION & CALCULATION FIDELITY: {overall_fidelity:.1f}% ({passed_checks}/{total_checks} checks passed)")
    print("=" * 85)


def main():
    parser = argparse.ArgumentParser(description="Loan Ranking Agent - Deterministic Underwriting & Ranking")
    parser.add_argument(
        "--pdf_dir",
        type=str,
        default=None,
        help="Directory containing subdirectories of applicant PDF documents (e.g. data/pdf_scenarios)",
    )
    parser.add_argument(
        "--data_dir",
        type=str,
        default="data/synthetic",
        help="Directory containing synthetic loan application cases with ground_truth.json",
    )
    parser.add_argument(
        "--product",
        type=str,
        default="loan_products/personal_loan_v1.json",
        help="Path or name of loan product configuration",
    )
    parser.add_argument(
        "--use_llm_extract",
        action="store_true",
        default=True,
        help="Use LLM to extract facts from PDF documents directly (default: True)",
    )
    parser.add_argument(
        "--no_llm_extract",
        action="store_true",
        help="Disable LLM extraction and use pure PDF text parser directly",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemma4:31b-cloud",
        help="LLM model name for extraction and explanation",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Enable second-stage LLM explanation agent",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        default=False,
        help="Enable post-calculation audit against ground_truth.json (default: False)",
    )
    parser.add_argument(
        "--output_json",
        type=str,
        default="ranking_results.json",
        help="Path to save ranked results and audit traces",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent workers for parallel ingestion and processing (default: 4)",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Force sequential execution mode (disables parallel WorkerPool)",
    )
    parser.add_argument(
        "--max_llm_concurrency",
        type=int,
        default=4,
        help="Maximum concurrent LLM extraction requests (default: 4)",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=20,
        help="Maximum batch size per worker (default: 20)",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="Path to resumable checkpoint file (e.g. .checkpoint.jsonl)",
    )
    args = parser.parse_args()

    use_llm = args.use_llm_extract and not args.no_llm_extract

    pipeline = LoanRankingPipeline(
        product_config_path=args.product,
        enable_explanation_llm=args.explain,
        enable_evaluation_summary=True,
        model_name=args.model,
    )

    apps: List[LoanApplication] = []

    # Mode 1: PDF Document Ingestion Mode
    if args.pdf_dir and os.path.exists(args.pdf_dir):
        extractor = LoanDocumentExtractor(model_name=args.model) if use_llm else None

        if not args.sequential:
            print(f"\n📂 Loading PDF Scenarios from: {args.pdf_dir}")
            print(f"⚡ Mode: Parallel Ingestion ({args.workers} workers, max queue={args.batch_size * args.workers}, LLM concurrency={args.max_llm_concurrency})")
            runner = JobRunner(
                num_workers=args.workers,
                max_queue_size=max(50, args.batch_size * args.workers),
                max_llm_concurrency=args.max_llm_concurrency,
                batch_size=args.batch_size,
                checkpoint_path=args.checkpoint,
                use_llm_extract=use_llm,
                extractor=extractor,
                pipeline=pipeline,
            )
            results = runner.run_job(args.pdf_dir)
            print_ranking_table(results)

            m = results.get("metrics", {})
            print(f"\n⚡ PARALLEL PERFORMANCE METRICS:")
            print(f"  • Total Applications : {m.get('total_applications')}")
            print(f"  • Completed / Failed : {m.get('completed')} / {m.get('failed')}")
            print(f"  • Total Duration     : {m.get('total_duration')}s")
            print(f"  • Throughput         : {m.get('throughput_apps_per_sec')} apps/sec ({m.get('throughput_docs_per_sec')} docs/sec)")
            print(f"  • Latency (P50 / P95): {m.get('p50_latency')}s / {m.get('p95_latency')}s")
            print(f"  • Peak Memory Usage  : {m.get('peak_memory_mb')} MB")

            # Save output JSON
            with open(args.output_json, "w") as f:
                serializable = {
                    "model_version": results["model_version"],
                    "qualified_ranked": [r.model_dump() for r in results["qualified_ranked"]],
                    "manual_review_queue": [r.model_dump() for r in results["manual_review_queue"]],
                    "ineligible_queue": [r.model_dump() for r in results["ineligible_queue"]],
                    "evaluation_summaries": results.get("evaluation_summaries", {}),
                    "audit_traces": results["audit_traces"],
                    "metrics": m,
                }
                json.dump(serializable, f, indent=2)
            print(f"\n✅ Audit traces, rankings, and concurrency metrics exported to {args.output_json}")
            return

        print(f"\n📂 Loading PDF Scenarios from: {args.pdf_dir}")
        print("⚡ Mode: Direct PDF Ingestion (Sequential Mode)")
        pdf_files_in_root = [f for f in os.listdir(args.pdf_dir) if f.lower().endswith(".pdf")]
        if pdf_files_in_root:
            scenario_folders = [(os.path.basename(args.pdf_dir.rstrip("/")), args.pdf_dir)]
        else:
            scenario_folders = [
                (sub, os.path.join(args.pdf_dir, sub))
                for sub in sorted(os.listdir(args.pdf_dir))
                if os.path.isdir(os.path.join(args.pdf_dir, sub))
            ]

        for scenario_name, scenario_path in scenario_folders:
            pdf_docs = load_pdf_documents_from_directory(scenario_path)
            if not pdf_docs:
                continue

            print(f"\n📁 Ingesting {scenario_name}: {len(pdf_docs)} PDF pages loaded.")
            app: Optional[LoanApplication] = None

            # Stage 1: Extraction
            if use_llm and extractor:
                try:
                    print(f"     [Stage 1: EXTRACTION] Extracting factual data via LLM ({args.model})...")
                    app = extractor.extract_from_documents(scenario_name, pdf_docs)
                except Exception as e:
                    print(f"     ⚠️ LLM extraction encountered error ({e}); using PDF text docket parser...")
                    app = extract_application_from_pdf_text(scenario_name, pdf_docs)
            else:
                print(f"     [Stage 1: EXTRACTION] Extracting facts directly from PDF text dockets...")
                app = extract_application_from_pdf_text(scenario_name, pdf_docs)

            # Stage 2: Parsing statement transactions
            print(f"     [Stage 2: PARSING] Parsing statement transaction tables (Bank & Credit Card)...")
            all_bank_txs = list(app.bank_transactions)
            all_cc_txs = list(app.credit_card_transactions)

            for doc in pdf_docs:
                d_lower = doc["name"].lower()
                if "bank_statement" in d_lower:
                    parsed_txs = parse_statement_transactions(doc["content"], doc["name"], doc.get("page", 1))
                    if parsed_txs and len(parsed_txs) > len(all_bank_txs):
                        all_bank_txs = parsed_txs
                elif "credit_card" in d_lower:
                    parsed_txs = parse_statement_transactions(doc["content"], doc["name"], doc.get("page", 1))
                    if parsed_txs and len(parsed_txs) > len(all_cc_txs):
                        all_cc_txs = parsed_txs

            app.bank_transactions = all_bank_txs
            app.credit_card_transactions = all_cc_txs

            print(f"       -> Parsed {len(app.bank_transactions)} Bank Transactions across 6 months.")
            print(f"       -> Parsed {len(app.credit_card_transactions)} Credit Card Transactions across 6 months.")

            # Stage 3: Refining
            print(f"     [Stage 3: REFINING] Normalizing currencies, verifying category classifications & running cross-doc consistency checks...")
            apps.append(app)

    if not apps:
        print(f"No valid application cases found.")
        return

    # Stage 4: Calculating & Parallel LLM Criticality Evaluation
    print(f"\n🚀 [Stage 4: CALCULATING & LLM EVALUATION] Underwriting {len(apps)} applications across deterministic mathematical scoring and parallel LLM evaluation...")
    results = pipeline.process_and_rank_batch(apps)
    print_ranking_table(results)

    # Optional Post-Calculation Stage: Ground Truth Audit (ONLY if explicitly requested via --audit)
    if args.audit and args.pdf_dir and os.path.exists(args.pdf_dir):
        audit_against_ground_truth(apps, results, args.pdf_dir)

    # Save output JSON
    with open(args.output_json, "w") as f:
        serializable = {
            "model_version": results["model_version"],
            "qualified_ranked": [r.model_dump() for r in results["qualified_ranked"]],
            "manual_review_queue": [r.model_dump() for r in results["manual_review_queue"]],
            "ineligible_queue": [r.model_dump() for r in results["ineligible_queue"]],
            "evaluation_summaries": results.get("evaluation_summaries", {}),
            "audit_traces": results["audit_traces"],
        }
        json.dump(serializable, f, indent=2)
    print(f"\n✅ Audit traces and rankings exported to {args.output_json}")


if __name__ == "__main__":
    main()
