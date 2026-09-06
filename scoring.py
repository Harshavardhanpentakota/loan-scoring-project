"""Deterministic Scoring Engine for Loan Applications.

Implements versioned, fully deterministic mathematical scoring.
Strict invariant:
The LLM NEVER generates, modifies, or inflates numerical scores.
Scores are purely mathematical functions of extracted facts and derived features.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from models import (
    LoanApplication,
    DerivedFeatures,
    ComponentScore,
    ScoringResult,
)


# =====================================================================
# Standalone Mathematical Scoring Functions
# =====================================================================

def calculate_credit_score_rating(
    credit_score: Optional[int],
    weight: float = 0.25,
) -> Tuple[ComponentScore, Dict[str, Any]]:
    """Calculates Credit Bureau component score scaled linearly between 300 and 900.
    
    Formula: max(0.0, min(100.0, ((credit_score - 300) / 600.0) * 100.0))
    """
    if credit_score is not None:
        raw_credit = round(max(0.0, min(100.0, ((credit_score - 300) / 600.0) * 100.0)), 2)
        notes = f"Scaled from bureau credit score of {credit_score} (range 300-900)"
    else:
        raw_credit = 50.0  # Neutral baseline if bureau data missing
        notes = "Credit score unavailable; baseline neutral score assigned"

    contrib = round(raw_credit * weight, 2)
    score_obj = ComponentScore(
        raw_score=raw_credit,
        weight=weight,
        contribution=contrib,
        notes=notes,
    )
    trace = {
        "component": "credit_history",
        "formula": "max(0, min(100, (credit_score - 300) / 600 * 100))",
        "raw_score": raw_credit,
        "weight": weight,
        "contribution": contrib,
        "notes": notes,
    }
    return score_obj, trace


def calculate_repayment_behavior_score(
    missed_payments: int,
    overdue_amount: float = 0.0,
    weight: float = 0.20,
) -> Tuple[ComponentScore, Dict[str, Any]]:
    """Calculates Repayment Behavior score penalizing historical missed payments and active overdue balances."""
    if missed_payments == 0 and overdue_amount <= 0:
        raw_repay = 100.0
        repay_note = "Clean repayment track: 0 missed payments, no overdue debt"
    elif missed_payments == 1 and overdue_amount <= 0:
        raw_repay = 70.0
        repay_note = "1 historical missed payment recorded"
    elif missed_payments == 2 and overdue_amount <= 0:
        raw_repay = 40.0
        repay_note = "2 historical missed payments recorded"
    else:
        raw_repay = max(5.0, round(30.0 - (overdue_amount / 10000.0) * 5.0 - (missed_payments * 5.0), 2))
        repay_note = f"Multiple delinquencies: {missed_payments} missed payments, overdue amount ₹{overdue_amount:,.2f}"

    contrib = round(raw_repay * weight, 2)
    score_obj = ComponentScore(
        raw_score=raw_repay,
        weight=weight,
        contribution=contrib,
        notes=repay_note,
    )
    trace = {
        "component": "repayment_behavior",
        "formula": "Rule-based penalty schedule on missed payments and overdue balance",
        "raw_score": raw_repay,
        "weight": weight,
        "contribution": contrib,
        "notes": repay_note,
    }
    return score_obj, trace


def calculate_income_stability_score(
    features: DerivedFeatures,
    app: Optional[LoanApplication] = None,
    weight: float = 0.15,
) -> Tuple[ComponentScore, Dict[str, Any]]:
    """Calculates Income Stability score using employment tenure, contract type, and 6M bank cashflow consistency."""
    base_idx = features.income_stability_index if features.income_stability_index is not None else 50.0

    # Cross-check 6-month bank statement credits consistency
    bonus_or_penalty = 0.0
    notes = "Calculated from employment tenure and contract type"
    if features.derived_monthly_salary_from_bank and app and app.income.monthly_net_income and app.income.monthly_net_income.value:
        declared = app.income.monthly_net_income.value
        bank_sal = features.derived_monthly_salary_from_bank
        ratio = bank_sal / declared if declared > 0 else 1.0
        if 0.90 <= ratio <= 1.10:
            bonus_or_penalty += 5.0
            notes += "; 6M bank statement verifies payroll deposits within 10%"

    raw_income_stab = min(100.0, max(0.0, base_idx + bonus_or_penalty))
    contrib = round(raw_income_stab * weight, 2)
    score_obj = ComponentScore(
        raw_score=raw_income_stab,
        weight=weight,
        contribution=contrib,
        notes=notes,
    )
    trace = {
        "component": "income_stability",
        "formula": "features.income_stability_index + bank_statement_salary_reconciliation_adjustment",
        "raw_score": raw_income_stab,
        "weight": weight,
        "contribution": contrib,
        "notes": notes,
    }
    return score_obj, trace


def calculate_debt_burden_score(
    dti: Optional[float],
    credit_card_utilization: Optional[float] = None,
    weight: float = 0.15,
) -> Tuple[ComponentScore, Dict[str, Any]]:
    """Calculates Debt Burden score as a stepwise inverse mapping of DTI and revolving credit card utilization."""
    if dti is None:
        raw_debt = 50.0
        debt_note = "DTI unavailable; neutral baseline assigned"
    elif dti <= 0.15:
        raw_debt = 100.0
        debt_note = f"Very low debt burden (DTI {dti * 100:.1f}%)"
    elif dti <= 0.30:
        raw_debt = 85.0
        debt_note = f"Low debt burden (DTI {dti * 100:.1f}%)"
    elif dti <= 0.45:
        raw_debt = 65.0
        debt_note = f"Moderate debt burden (DTI {dti * 100:.1f}%)"
    elif dti <= 0.60:
        raw_debt = 35.0
        debt_note = f"High debt burden (DTI {dti * 100:.1f}%)"
    else:
        raw_debt = 10.0
        debt_note = f"Critical debt burden (DTI {dti * 100:.1f}%)"

    # Credit card utilization penalty if over 80%
    if credit_card_utilization is not None and credit_card_utilization > 0.80:
        raw_debt = max(5.0, raw_debt - 10.0)
        debt_note += f"; high CC utilization penalty ({credit_card_utilization * 100:.1f}%)"

    contrib = round(raw_debt * weight, 2)
    score_obj = ComponentScore(
        raw_score=raw_debt,
        weight=weight,
        contribution=contrib,
        notes=debt_note,
    )
    trace = {
        "component": "debt_burden",
        "formula": "Stepwise inverse mapping of DTI ratio with CC utilization adjustment",
        "raw_score": raw_debt,
        "weight": weight,
        "contribution": contrib,
        "notes": debt_note,
    }
    return score_obj, trace


def calculate_employment_stability_score(
    emp_years: float,
    weight: float = 0.10,
) -> Tuple[ComponentScore, Dict[str, Any]]:
    """Calculates Employment Stability score based on verified employment tenure in years."""
    if emp_years >= 5.0:
        raw_emp = 100.0
    elif emp_years >= 3.0:
        raw_emp = 80.0
    elif emp_years >= 1.0:
        raw_emp = 60.0
    elif emp_years > 0.0:
        raw_emp = 40.0
    else:
        raw_emp = 25.0

    contrib = round(raw_emp * weight, 2)
    score_obj = ComponentScore(
        raw_score=raw_emp,
        weight=weight,
        contribution=contrib,
        notes=f"Based on {emp_years} recorded years of employment",
    )
    trace = {
        "component": "employment_stability",
        "formula": "Tiered mapping based on employment tenure in years",
        "raw_score": raw_emp,
        "weight": weight,
        "contribution": contrib,
        "notes": f"{emp_years} years tenure",
    }
    return score_obj, trace


def calculate_affordability_score(
    emi_ratio: Optional[float],
    features: Optional[DerivedFeatures] = None,
    weight: float = 0.10,
) -> Tuple[ComponentScore, Dict[str, Any]]:
    """Calculates Affordability score based on proposed EMI to monthly net income and 6-month net cashflow buffer."""
    if emi_ratio is None:
        raw_afford = 50.0
        afford_note = "EMI ratio unavailable; baseline neutral score assigned"
    elif emi_ratio <= 0.20:
        raw_afford = 100.0
        afford_note = f"Excellent affordability (EMI ratio {emi_ratio * 100:.1f}%)"
    elif emi_ratio <= 0.35:
        raw_afford = 80.0
        afford_note = f"Healthy affordability (EMI ratio {emi_ratio * 100:.1f}%)"
    elif emi_ratio <= 0.50:
        raw_afford = 50.0
        afford_note = f"Moderate affordability (EMI ratio {emi_ratio * 100:.1f}%)"
    else:
        raw_afford = 20.0
        afford_note = f"Strained affordability (EMI ratio {emi_ratio * 100:.1f}%)"

    contrib = round(raw_afford * weight, 2)
    score_obj = ComponentScore(
        raw_score=raw_afford,
        weight=weight,
        contribution=contrib,
        notes=afford_note,
    )
    trace = {
        "component": "affordability",
        "formula": "Stepwise mapping of proposed EMI to Net Income ratio",
        "raw_score": raw_afford,
        "weight": weight,
        "contribution": contrib,
        "notes": afford_note,
    }
    return score_obj, trace


def calculate_documentation_quality_score(
    completeness: float,
    weight: float = 0.05,
) -> Tuple[ComponentScore, Dict[str, Any]]:
    """Calculates Documentation Completeness score as percentage of required documents verified."""
    raw_doc = round(completeness * 100.0, 2)
    contrib = round(raw_doc * weight, 2)
    score_obj = ComponentScore(
        raw_score=raw_doc,
        weight=weight,
        contribution=contrib,
        notes=f"Completeness ratio: {completeness * 100.0:.1f}%",
    )
    trace = {
        "component": "documentation_quality",
        "formula": "documentation_completeness * 100",
        "raw_score": raw_doc,
        "weight": weight,
        "contribution": contrib,
        "notes": f"{completeness * 100.0:.1f}% complete",
    }
    return score_obj, trace


def calculate_overall_score(component_scores: Dict[str, ComponentScore]) -> float:
    """Calculates final deterministic loan application score as the weighted sum of component contributions."""
    return round(sum(comp.contribution for comp in component_scores.values()), 2)


def determine_application_criticality(
    final_score: float,
    missed_payments: int = 0,
    overdue_amount: float = 0.0,
    dti: Optional[float] = None,
    credit_score: Optional[int] = None,
) -> str:
    """Determines the risk criticality level of the loan application.
    
    Returns:
      - 'LOW': (Low Risk / Prime Grade / Safe)
      - 'MED': (Moderate Risk / Standard / Borderline)
      - 'HIGH': (High Risk / Subprime / Red Flag)
    """
    # High criticality triggers: serious delinquencies, high DTI, low credit score, or failing score
    if (
        final_score < 55.0
        or missed_payments >= 2
        or overdue_amount > 0.0
        or (dti is not None and dti > 0.50)
        or (credit_score is not None and credit_score < 650)
    ):
        return "HIGH"

    # Low criticality criteria: prime credit, clean repayment, low DTI, and high overall score
    if (
        final_score >= 75.0
        and missed_payments == 0
        and overdue_amount <= 0.0
        and (dti is None or dti <= 0.40)
        and (credit_score is None or credit_score >= 720)
    ):
        return "LOW"

    # Otherwise medium criticality
    return "MED"


# =====================================================================
# Deterministic Scoring Engine Class
# =====================================================================

class DeterministicScoringEngine:
    """Computes transparent, weighted component scores and final loan scores."""

    def __init__(self, product_config: Dict[str, Any]):
        self.config = product_config
        self.model_version = self.config.get("model_version", "personal_loan_v1")
        self.weights = self.config.get("weights", {
            "credit_history": 0.25,
            "repayment_behavior": 0.20,
            "income_stability": 0.15,
            "debt_burden": 0.15,
            "employment_stability": 0.10,
            "affordability": 0.10,
            "documentation_quality": 0.05,
        })

    def score(self, app: LoanApplication, features: DerivedFeatures) -> ScoringResult:
        component_scores: Dict[str, ComponentScore] = {}
        calc_trace: List[Dict[str, Any]] = []

        # Component 1: Credit Bureau Score
        cs = app.credit.credit_score.value if app.credit.credit_score else None
        comp_credit, trace_credit = calculate_credit_score_rating(
            credit_score=cs,
            weight=self.weights.get("credit_history", 0.25),
        )
        component_scores["credit_history"] = comp_credit
        calc_trace.append(trace_credit)

        # Component 2: Repayment Behavior
        missed = app.obligations.missed_payments.value if app.obligations.missed_payments else 0
        overdue = app.obligations.overdue_amount.value if app.obligations.overdue_amount else 0.0
        comp_repay, trace_repay = calculate_repayment_behavior_score(
            missed_payments=missed,
            overdue_amount=overdue,
            weight=self.weights.get("repayment_behavior", 0.20),
        )
        component_scores["repayment_behavior"] = comp_repay
        calc_trace.append(trace_repay)

        # Component 3: Income Stability
        comp_inc, trace_inc = calculate_income_stability_score(
            features=features,
            app=app,
            weight=self.weights.get("income_stability", 0.15),
        )
        component_scores["income_stability"] = comp_inc
        calc_trace.append(trace_inc)

        # Component 4: Debt Burden & CC Utilization
        cc_util = features.credit_card_utilization
        comp_debt, trace_debt = calculate_debt_burden_score(
            dti=features.dti,
            credit_card_utilization=cc_util,
            weight=self.weights.get("debt_burden", 0.15),
        )
        component_scores["debt_burden"] = comp_debt
        calc_trace.append(trace_debt)

        # Component 5: Employment Stability
        emp_years = app.applicant.employment_duration_years.value if app.applicant.employment_duration_years else 0.0
        comp_emp, trace_emp = calculate_employment_stability_score(
            emp_years=emp_years,
            weight=self.weights.get("employment_stability", 0.10),
        )
        component_scores["employment_stability"] = comp_emp
        calc_trace.append(trace_emp)

        # Component 6: Affordability
        comp_afford, trace_afford = calculate_affordability_score(
            emi_ratio=features.emi_ratio,
            features=features,
            weight=self.weights.get("affordability", 0.10),
        )
        component_scores["affordability"] = comp_afford
        calc_trace.append(trace_afford)

        # Component 7: Documentation Quality
        comp_doc, trace_doc = calculate_documentation_quality_score(
            completeness=features.documentation_completeness,
            weight=self.weights.get("documentation_quality", 0.05),
        )
        component_scores["documentation_quality"] = comp_doc
        calc_trace.append(trace_doc)

        # Final Score: Deterministic weighted sum
        final_score = calculate_overall_score(component_scores)

        # Application Criticality
        criticality = determine_application_criticality(
            final_score=final_score,
            missed_payments=missed,
            overdue_amount=overdue,
            dti=features.dti,
            credit_score=cs,
        )

        return ScoringResult(
            application_id=app.application_id,
            scoring_model=self.model_version,
            timestamp=datetime.utcnow().isoformat() + "Z",
            components=component_scores,
            final_score=final_score,
            criticality=criticality,
            calculation_trace=calc_trace,
        )
