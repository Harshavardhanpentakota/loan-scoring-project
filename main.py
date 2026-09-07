"""Main entry point and orchestration pipeline for Loan Ranking Agent.

Runs the complete underwriting pipeline:
Documents -> Extraction -> Structured Facts -> Validation ->
Financial Features -> Eligibility Rules -> Mathematical Scoring ->
Ranking -> Parallel LLM Criticality Evaluation Summary
"""

import os
import sys
import json
import logging
import concurrent.futures
from typing import List, Dict, Any, Optional
from models import (
    LoanApplication,
    ValidationResult,
    DerivedFeatures,
    EligibilityResult,
    ScoringResult,
    RankedApplicant,
    ApplicationEvaluationSummary,
)
from validate import LoanValidator
from features import FinancialFeatureEngine
from eligibility import EligibilityEngine, load_product_config
from scoring import DeterministicScoringEngine
from ranking import DeterministicRankingEngine
from explain import LoanExplanationAgent, LoanEvaluationSummarizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class LoanRankingPipeline:
    """End-to-end pipeline orchestrator ensuring strict separation between LLM and deterministic logic."""

    def __init__(
        self,
        product_config_path: str = "loan_products/personal_loan_v1.json",
        enable_explanation_llm: bool = False,
        enable_evaluation_summary: bool = True,
        model_name: Optional[str] = None,
    ):
        self.product_config = load_product_config(product_config_path)
        self.validator = LoanValidator()
        self.feature_engine = FinancialFeatureEngine()
        self.eligibility_engine = EligibilityEngine(self.product_config)
        self.scoring_engine = DeterministicScoringEngine(self.product_config)
        self.ranking_engine = DeterministicRankingEngine()
        self.enable_explanation = enable_explanation_llm
        self.explanation_agent = (
            LoanExplanationAgent(model_name=model_name) if (enable_explanation_llm and model_name)
            else (LoanExplanationAgent() if enable_explanation_llm else None)
        )
        self.enable_evaluation_summary = enable_evaluation_summary
        self.summarizer = (
            LoanEvaluationSummarizer(model_name=model_name) if (enable_evaluation_summary and model_name)
            else (LoanEvaluationSummarizer() if enable_evaluation_summary else None)
        )

    def process_application(
        self,
        app: LoanApplication,
    ) -> Dict[str, Any]:
        """Execute validation, feature derivation, eligibility, and scoring on a single application."""
        # Step 1: Validation
        val_res = self.validator.validate(app)

        # Step 2: Feature derivation (always runs to provide mathematical features)
        feat_res = self.feature_engine.calculate_features(app)

        # Step 3: Eligibility checks
        elig_res = self.eligibility_engine.evaluate(app, feat_res, val_res)

        # Step 4: Mathematical Scoring
        score_res = self.scoring_engine.score(app, feat_res)

        return {
            "application": app,
            "validation": val_res,
            "features": feat_res,
            "eligibility": elig_res,
            "scoring": score_res,
        }

    def process_and_rank_batch(
        self,
        applications: List[LoanApplication],
    ) -> Dict[str, Any]:
        """Run batch underwriting, deterministic ranking, and parallel LLM evaluation summaries."""
        scores_map: Dict[str, ScoringResult] = {}
        elig_map: Dict[str, EligibilityResult] = {}
        feat_map: Dict[str, DerivedFeatures] = {}
        val_map: Dict[str, ValidationResult] = {}

        # 1. Deterministic Calculation (Validation, Features, Eligibility, Mathematical Scoring)
        for app in applications:
            res = self.process_application(app)
            app_id = app.application_id
            scores_map[app_id] = res["scoring"]
            elig_map[app_id] = res["eligibility"]
            feat_map[app_id] = res["features"]
            val_map[app_id] = res["validation"]

        # 2. Deterministic Ranking
        qualified, review, ineligible = self.ranking_engine.rank(
            applications=applications,
            scores=scores_map,
            eligibilities=elig_map,
            features=feat_map,
            validations=val_map,
        )

        # 3. LLM Criticality Evaluation Summary & Explanations
        summaries = self.attach_summaries_and_explanations(
            applications=applications,
            qualified=qualified,
            review=review,
            ineligible=ineligible,
            scores_map=scores_map,
            elig_map=elig_map,
            feat_map=feat_map,
        )

        return {
            "model_version": self.product_config.get("model_version"),
            "qualified_ranked": qualified,
            "manual_review_queue": review,
            "ineligible_queue": ineligible,
            "evaluation_summaries": {aid: s.model_dump() for aid, s in summaries.items()},
            "audit_traces": {
                app_id: {
                    "features": [t.model_dump() for t in feat_map[app_id].traces],
                    "scoring": scores_map[app_id].model_dump(),
                    "eligibility": elig_map[app_id].model_dump(),
                    "validation": val_map[app_id].model_dump(),
                }
                for app_id in scores_map
            },
        }

    def attach_summaries_and_explanations(
        self,
        applications: List[LoanApplication],
        qualified: List[RankedApplicant],
        review: List[RankedApplicant],
        ineligible: List[RankedApplicant],
        scores_map: Dict[str, ScoringResult],
        elig_map: Dict[str, EligibilityResult],
        feat_map: Dict[str, DerivedFeatures],
    ) -> Dict[str, ApplicationEvaluationSummary]:
        """Attach criticality, LLM evaluation summaries, and grounded explanations to ranked applicants."""
        summaries: Dict[str, ApplicationEvaluationSummary] = {}
        if self.enable_evaluation_summary and self.summarizer:
            app_lookup = {a.application_id: a for a in applications}
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_id = {
                    executor.submit(
                        self.summarizer.summarize_evaluation,
                        app_lookup[aid],
                        feat_map[aid],
                        scores_map[aid],
                        elig_map[aid],
                    ): aid
                    for aid in app_lookup
                    if aid in feat_map and aid in scores_map and aid in elig_map
                }
                for future in concurrent.futures.as_completed(future_to_id):
                    aid = future_to_id[future]
                    try:
                        summary = future.result()
                        summaries[aid] = summary
                    except Exception as e:
                        logger.warning(f"Error generating LLM evaluation summary for {aid}: {e}")

        # Attach criticality and evaluation summaries to ranked applicants
        for group in (qualified, review, ineligible):
            for applicant in group:
                aid = applicant.application_id
                if aid in scores_map:
                    applicant.criticality = scores_map[aid].criticality
                if aid in summaries:
                    applicant.evaluation_summary = summaries[aid]

        # Optional 3-bullet explanation (if requested)
        if self.enable_explanation and self.explanation_agent:
            app_lookup = {a.application_id: a for a in applications}
            for ranked_list in (qualified, review):
                for applicant in ranked_list:
                    app = app_lookup.get(applicant.application_id)
                    if app and app.application_id in feat_map and app.application_id in scores_map and app.application_id in elig_map:
                        bullets, status = self.explanation_agent.generate_explanation(
                            app=app,
                            features=feat_map[app.application_id],
                            scoring=scores_map[app.application_id],
                            eligibility=elig_map[app.application_id],
                        )
                        applicant.explanation = bullets
                        applicant.explanation_status = status

        return summaries


def print_ranking_table(results: Dict[str, Any]):
    """Prints comprehensive underwriting results: mathematical scoring breakdown, overall score, criticality, and LLM summary."""
    all_applicants: List[RankedApplicant] = (
        results.get("qualified_ranked", [])
        + results.get("manual_review_queue", [])
        + results.get("ineligible_queue", [])
    )
    audit_traces = results.get("audit_traces", {})

    print("\n" + "=" * 90)
    print(f"  LOAN APPLICATION UNDERWRITING & RANKING REPORT")
    print(f"  Model Version: {results.get('model_version')} | Total Evaluated: {len(all_applicants)}")
    print("=" * 90)

    # 1. Print Executive Summary Table
    print(f"\n📊 APPLICANT SUMMARY OVERVIEW:")
    print("-" * 90)
    print(f"{'App ID':<18} | {'Applicant Name':<20} | {'Score':<8} | {'Criticality':<14} | {'Status':<12}")
    print("-" * 90)
    for app in all_applicants:
        name = app.applicant_name or "N/A"
        crit = app.criticality or "N/A"
        crit_label = f"{crit} RISK"
        print(f"{app.application_id:<18} | {name:<20} | {app.final_score:<8.2f} | {crit_label:<14} | {app.eligibility_status:<12}")
    print("-" * 90)

    # 2. Detailed Breakdown for each applicant
    for app in all_applicants:
        aid = app.application_id
        trace = audit_traces.get(aid, {})
        scoring_data = trace.get("scoring", {})
        components = scoring_data.get("components", {})
        features_data = {f["feature"]: f for f in trace.get("features", [])}

        crit_color = {
            "LOW": "🟢 LOW CRITICALITY (Prime Grade / Low Risk)",
            "MED": "🟡 MED CRITICALITY (Moderate Risk / Standard)",
            "HIGH": "🔴 HIGH CRITICALITY (High Risk / Subprime)",
        }.get(app.criticality, f"{app.criticality} CRITICALITY")

        print("\n" + "=" * 90)
        print(f"  📋 APPLICATION DOSSIER: [{aid}] — {app.applicant_name or 'N/A'}")
        print("=" * 90)
        print(f"  • Underwriting Decision   : {app.eligibility_status}")
        print(f"  • Deterministic Score     : {app.final_score:.2f} / 100")
        print(f"  • Risk Criticality        : {crit_color}")

        # Mathematical Scoring Breakdown
        print("\n  🔢 MATHEMATICAL SCORING BREAKDOWN (Deterministic Functions):")
        print("  " + "-" * 86)
        print(f"  {'Component':<24} | {'Raw Score':<10} | {'Weight':<8} | {'Contribution':<14} | {'Details'}")
        print("  " + "-" * 86)
        for comp_key, comp in components.items():
            c_name = comp_key.replace("_", " ").title()
            raw = f"{comp.get('raw_score', 0.0):.1f}/100"
            w = f"{comp.get('weight', 0.0) * 100:.0f}%"
            contrib = f"{comp.get('contribution', 0.0):.2f} pts"
            notes = comp.get("notes") or ""
            print(f"  {c_name:<24} | {raw:<10} | {w:<8} | {contrib:<14} | {notes[:35]}")
        print("  " + "-" * 86)
        print(f"  {'OVERALL FINAL SCORE':<24} | {'':<10} | {'100%':<8} | {app.final_score:.2f} pts       | Fully Deterministic Sum")
        print("  " + "-" * 86)

        # 6-Month Statement Transaction Rollups
        tx_features = [
            f for f in trace.get("features", [])
            if any(k in f.get("feature", "") for k in ["bank", "credit_card", "dti", "emi_ratio"]) and f.get("result") is not None
        ]
        if tx_features:
            print("\n  💳 6-MONTH STATEMENT FINANCIAL ROLLUPS & RATIOS:")
            for f in tx_features:
                f_name = f["feature"].replace("_", " ").title()
                val = f["result"]
                val_str = f"₹{val:,.2f}" if "credits" in f["feature"] or "debits" in f["feature"] or "salary" in f["feature"] or "spends" in f["feature"] else (f"{val * 100:.1f}%" if "dti" in f["feature"] or "ratio" in f["feature"] or "utilization" in f["feature"] else str(val))
                print(f"    • {f_name:<32}: {val_str}  ({f['formula']})")

        # LLM Criticality Evaluation Summary
        summary = app.evaluation_summary
        if summary:
            print("\n  🤖 LLM UNDERWRITING EVALUATION SUMMARY (Pros & Cons by Criticality):")
            print("  " + "-" * 86)
            if summary.executive_verdict:
                print(f"  Executive Verdict:")
                print(f"  \"{summary.executive_verdict}\"\n")

            if summary.pros:
                print("  🟢 PROS (Application Strengths):")
                # Group/sort by HIGH, MED, LOW
                crit_order = {"HIGH": 0, "MED": 1, "LOW": 2}
                sorted_pros = sorted(summary.pros, key=lambda x: crit_order.get(x.criticality, 3))
                for p in sorted_pros:
                    ev_str = f" — [{p.evidence}]" if p.evidence else ""
                    print(f"    • [{p.criticality} CRITICALITY] {p.point}{ev_str}")

            if summary.cons:
                print("\n  🔴 CONS (Risk Factors & Vulnerabilities):")
                crit_order = {"HIGH": 0, "MED": 1, "LOW": 2}
                sorted_cons = sorted(summary.cons, key=lambda x: crit_order.get(x.criticality, 3))
                for c in sorted_cons:
                    ev_str = f" — [{c.evidence}]" if c.evidence else ""
                    print(f"    • [{c.criticality} CRITICALITY] {c.point}{ev_str}")

    print("\n" + "=" * 90 + "\n")

    # 3. Final Portfolio Ranking Leaderboard Table (displayed at the very end when multiple applicants exist)
    if len(all_applicants) > 1:
        print("\n" + "=" * 110)
        print("  🏆 FINAL LOAN APPLICATION RANKING & PORTFOLIO LEADERBOARD")
        print(f"  Model: {results.get('model_version')} | Total Applications Evaluated: {len(all_applicants)}")
        print("=" * 110)

        qualified = results.get("qualified_ranked", [])
        if qualified:
            print(f"\n  ⭐ QUALIFIED APPLICANTS (Ranked 1 to {len(qualified)} by Score):")
            print("  " + "-" * 106)
            print(f"  {'Rank':<5} | {'App ID':<24} | {'Applicant Name':<18} | {'Score':<8} | {'Criticality':<15} | {'Credit':<8} | {'DTI':<8} | {'Monthly Net'}")
            print("  " + "-" * 106)
            for q in qualified:
                name = q.applicant_name or "N/A"
                crit = q.criticality or "N/A"
                crit_icon = "🟢" if crit == "LOW" else ("🟡" if crit == "MED" else "🔴")
                crit_badge = f"{crit_icon} {crit} RISK"
                cs = str(q.credit_score) if q.credit_score else "N/A"
                dti = f"{q.dti * 100:.1f}%" if q.dti is not None else "N/A"
                inc = f"₹{q.monthly_income:,.2f}" if q.monthly_income else "N/A"
                print(f"  {q.rank:<5} | {q.application_id:<24} | {name:<18} | {q.final_score:<8.2f} | {crit_badge:<15} | {cs:<8} | {dti:<8} | {inc}")
            print("  " + "-" * 106)

        review = results.get("manual_review_queue", [])
        if review:
            print(f"\n  ⚠️  MANUAL REVIEW QUEUE (Pending Underwriter Verification):")
            print("  " + "-" * 106)
            print(f"  {'App ID':<24} | {'Applicant Name':<18} | {'Score':<8} | {'Criticality':<15} | {'Underwriting Review Reasons'}")
            print("  " + "-" * 106)
            for r in review:
                name = r.applicant_name or "N/A"
                crit = r.criticality or "N/A"
                crit_icon = "🟡" if crit == "MED" else ("🟢" if crit == "LOW" else "🔴")
                crit_badge = f"{crit_icon} {crit} RISK"
                reasons = audit_traces.get(r.application_id, {}).get("eligibility", {}).get("manual_review_reasons", [])
                reason_str = "; ".join(reasons) if reasons else (r.validation_status or "Manual Review Required")
                print(f"  {r.application_id:<24} | {name:<18} | {r.final_score:<8.2f} | {crit_badge:<15} | {reason_str[:42]}")
            print("  " + "-" * 106)

        ineligible = results.get("ineligible_queue", [])
        if ineligible:
            print(f"\n  ❌ INELIGIBLE QUEUE (Failed Policy Gates / Severe Delinquencies):")
            print("  " + "-" * 106)
            print(f"  {'App ID':<24} | {'Applicant Name':<18} | {'Score':<8} | {'Criticality':<15} | {'Primary Gate Failure(s)'}")
            print("  " + "-" * 106)
            for inelig in ineligible:
                name = inelig.applicant_name or "N/A"
                crit = inelig.criticality or "N/A"
                crit_icon = "🔴" if crit == "HIGH" else ("🟡" if crit == "MED" else "🟢")
                crit_badge = f"{crit_icon} {crit} RISK"
                failed = audit_traces.get(inelig.application_id, {}).get("eligibility", {}).get("failed_rules", [])
                fail_str = "; ".join(failed) if failed else "Ineligible under policy criteria"
                print(f"  {inelig.application_id:<24} | {name:<18} | {inelig.final_score:<8.2f} | {crit_badge:<15} | {fail_str[:42]}")
            print("  " + "-" * 106)

        print("=" * 110 + "\n")


if __name__ == "__main__":
    print("Loan Ranking Agent pipeline initialized.")

