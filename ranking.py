"""Deterministic Ranking Engine for Loan Applications.

Sorts applications strictly by mathematical score with configurable, multi-key tie breaking.
Segments applications into:
- Qualified Ranked Applicants
- Manual Review Queue
- Ineligible Queue

The LLM plays ZERO role in ordering applicants.
"""

from typing import List, Dict, Optional, Tuple
from models import (
    RankedApplicant,
    ScoringResult,
    EligibilityResult,
    DerivedFeatures,
    ValidationResult,
    LoanApplication,
)


class DeterministicRankingEngine:
    """Ranks scored applications deterministically using score descending and multi-key tie breakers."""

    def __init__(
        self,
        tie_breaker_keys: Optional[List[str]] = None,
    ):
        # Default tie-breaking hierarchy: credit score (high), DTI (low), monthly income (high), application_id (asc)
        self.tie_breaker_keys = tie_breaker_keys or [
            "final_score",
            "credit_score",
            "dti",
            "monthly_income",
            "application_id",
        ]

    def rank(
        self,
        applications: List[LoanApplication],
        scores: Dict[str, ScoringResult],
        eligibilities: Dict[str, EligibilityResult],
        features: Dict[str, DerivedFeatures],
        validations: Optional[Dict[str, ValidationResult]] = None,
    ) -> Tuple[List[RankedApplicant], List[RankedApplicant], List[RankedApplicant]]:
        """Ranks all applications deterministically.
        
        Returns:
            Tuple of:
            - qualified_ranked (List[RankedApplicant]): Eligible applicants sorted 1..N
            - manual_review_queue (List[RankedApplicant]): Applicants flagged for review
            - ineligible_queue (List[RankedApplicant]): Ineligible applicants
        """
        validations = validations or {}

        eligible_items = []
        review_items = []
        ineligible_items = []

        for app in applications:
            app_id = app.application_id
            score_res = scores.get(app_id)
            if not score_res:
                continue

            elig_res = eligibilities.get(app_id)
            feat_res = features.get(app_id)
            val_res = validations.get(app_id)

            elig_status = elig_res.status if elig_res else "UNKNOWN"
            val_status = val_res.status if val_res else "VALID"

            # Extract fields for sorting
            final_score = score_res.final_score
            cs = app.credit.credit_score.value if app.credit.credit_score else -1
            dti = feat_res.dti if (feat_res and feat_res.dti is not None) else 999.0
            gross_inc = app.income.monthly_gross_income.value if app.income.monthly_gross_income and app.income.monthly_gross_income.value else 0.0
            net_inc = app.income.monthly_net_income.value if app.income.monthly_net_income and app.income.monthly_net_income.value else 0.0
            eff_inc = gross_inc if gross_inc > 0 else net_inc

            comp_scores_map = {
                k: v.raw_score for k, v in score_res.components.items()
            }

            ranked_item = RankedApplicant(
                rank=0,  # Assigned after sorting
                application_id=app_id,
                applicant_name=app.applicant.applicant_name.value if app.applicant.applicant_name else None,
                applicant_type=app.applicant.applicant_type.value if app.applicant.applicant_type else None,
                final_score=final_score,
                eligibility_status=elig_status,
                scoring_model=score_res.scoring_model,
                component_scores=comp_scores_map,
                dti=feat_res.dti if feat_res else None,
                credit_score=app.credit.credit_score.value if app.credit.credit_score else None,
                monthly_income=eff_inc if eff_inc > 0 else None,
                validation_status=val_status,
            )


            # Route by eligibility & review
            if elig_status == "ELIGIBLE":
                eligible_items.append((ranked_item, cs, dti, gross_inc))
            elif elig_status == "MANUAL_REVIEW":
                review_items.append((ranked_item, cs, dti, gross_inc))
            else:
                ineligible_items.append((ranked_item, cs, dti, gross_inc))

        # Deterministic sort function:
        # 1. final_score DESC
        # 2. credit_score DESC
        # 3. dti ASC (lower debt burden is better)
        # 4. gross_inc DESC
        # 5. application_id ASC (absolute tie breaker)
        def sort_key(item_tuple):
            r, cs, dti_val, inc = item_tuple
            return (
                -r.final_score,
                -cs,
                dti_val,
                -inc,
                r.application_id,
            )

        eligible_items.sort(key=sort_key)
        review_items.sort(key=sort_key)
        ineligible_items.sort(key=sort_key)

        # Assign ordinal ranks (1-indexed)
        qualified_ranked: List[RankedApplicant] = []
        for idx, (r, _, _, _) in enumerate(eligible_items, start=1):
            r.rank = idx
            qualified_ranked.append(r)

        review_queue: List[RankedApplicant] = []
        for idx, (r, _, _, _) in enumerate(review_items, start=1):
            r.rank = idx
            review_queue.append(r)

        ineligible_queue: List[RankedApplicant] = []
        for idx, (r, _, _, _) in enumerate(ineligible_items, start=1):
            r.rank = idx
            ineligible_queue.append(r)

        return qualified_ranked, review_queue, ineligible_queue
