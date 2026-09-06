"""Grounded Explanation Agent and Lightweight Grounding Validator.

Strict constraints:
- Operates ONLY on already-computed scores, features, and raw facts.
- Never sends full original documents.
- Produces exactly 3 bullet points.
- Grounding validator verifies that no hallucinated numbers, ungrounded attributes,
  or score modifications are present. If checks fail, marks explanation INVALID.
"""

import re
import json
import logging
from typing import List, Dict, Any, Set, Tuple, Optional
from models import (
    LoanApplication,
    DerivedFeatures,
    ScoringResult,
    EligibilityResult,
    CriticalityPoint,
    ApplicationEvaluationSummary,
    OpenAICompatibleProvider,
)

LLMProvider = OpenAICompatibleProvider

from prompts.template_manager import TemplateManager
from llm_utils import initialize_llm_provider, extract_json_from_response
from prompt import DEFAULT_MODEL, MODEL_PARAMETERS

logger = logging.getLogger(__name__)



class ExplanationGroundingValidator:
    """Validates that an LLM-generated explanation is strictly grounded in the provided data."""

    def __init__(self, tolerance: float = 0.05):
        self.tolerance = tolerance

    def extract_numbers(self, text: str) -> List[float]:
        """Extract all numerical values from text, supporting Indian commas and percentages."""
        clean_text = text.replace(",", "")
        # Match integers, floats, and percentages
        tokens = re.findall(r"[-+]?\d*\.?\d+", clean_text)
        numbers = []
        for t in tokens:
            try:
                numbers.append(float(t))
            except ValueError:
                pass
        return numbers

    def validate(
        self,
        bullets: List[str],
        allowed_numbers: Set[float],
        allowed_components: Set[str],
        expected_score: float,
    ) -> Tuple[bool, List[str]]:
        """Validate explanation output.
        
        Returns:
            (is_valid: bool, issues: List[str])
        """
        issues = []

        # 1. Check bullet count: must be exactly 3
        if len(bullets) != 3:
            issues.append(f"Expected exactly 3 bullets, but got {len(bullets)}.")

        # 2. Extract and check all numbers mentioned in text
        for idx, bullet in enumerate(bullets, start=1):
            nums = self.extract_numbers(bullet)
            for n in nums:
                # Check if number matches any allowed number or percentage variant
                is_match = False
                for allowed in allowed_numbers:
                    # Direct match or percentage match (e.g. 0.144 and 14.4)
                    if abs(n - allowed) <= self.tolerance:
                        is_match = True
                        break
                    if abs(n - (allowed * 100.0)) <= self.tolerance:
                        is_match = True
                        break
                    if abs(n - (allowed / 100.0)) <= self.tolerance:
                        is_match = True
                        break

                if not is_match:
                    issues.append(
                        f"Bullet #{idx} contains ungrounded number {n} not present in input context."
                    )

        # 3. Check if any score is claimed that contradicts expected_score
        full_text = " ".join(bullets)
        score_mentions = re.findall(r"(?:score|scored|final score)[^\d]*([\d.]+)", full_text, re.IGNORECASE)
        for sm in score_mentions:
            clean_sm = sm.strip().rstrip(".")
            try:
                val = float(clean_sm)
                if abs(val - expected_score) > self.tolerance:
                    issues.append(
                        f"Explanation claims final score {val}, which differs from calculated {expected_score}."
                    )
            except ValueError:
                pass

        is_valid = len(issues) == 0
        return is_valid, issues


class LoanExplanationAgent:
    """Generates and validates factual explanations for already-scored applications."""

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        model_name: str = DEFAULT_MODEL,
        template_manager: Optional[TemplateManager] = None,
    ):
        self.model_name = model_name
        self.provider = provider or initialize_llm_provider(model_name)
        self.template_manager = template_manager or TemplateManager()
        self.validator = ExplanationGroundingValidator()

    def generate_explanation(
        self,
        app: LoanApplication,
        features: DerivedFeatures,
        scoring: ScoringResult,
        eligibility: EligibilityResult,
    ) -> Tuple[List[str], str]:
        """Generate 3-bullet explanation and validate grounding.
        
        Returns:
            Tuple of (bullets: List[str], explanation_status: "VALID" | "INVALID")
        """
        # Prepare context
        components_dict = {
            name: {
                "raw_score": c.raw_score,
                "weight": c.weight,
                "contribution": c.contribution,
            }
            for name, c in scoring.components.items()
        }

        features_list = [
            {
                "feature": t.feature,
                "formula": t.formula,
                "inputs": t.inputs,
                "result": t.result,
            }
            for t in features.traces
            if t.result is not None
        ]

        facts_list = []
        if app.income.monthly_gross_income and app.income.monthly_gross_income.value is not None:
            facts_list.append({
                "field": "monthly_gross_income",
                "value": app.income.monthly_gross_income.value,
                "currency": app.income.monthly_gross_income.currency or "INR",
                "evidence": app.income.monthly_gross_income.source.evidence if app.income.monthly_gross_income.source else "",
            })
        if app.credit.credit_score and app.credit.credit_score.value is not None:
            facts_list.append({
                "field": "credit_score",
                "value": app.credit.credit_score.value,
                "currency": None,
                "evidence": app.credit.credit_score.source.evidence if app.credit.credit_score.source else "",
            })
        if app.obligations.missed_payments and app.obligations.missed_payments.value is not None:
            facts_list.append({
                "field": "missed_payments",
                "value": app.obligations.missed_payments.value,
                "currency": None,
                "evidence": app.obligations.missed_payments.source.evidence if app.obligations.missed_payments.source else "",
            })

        prompt = self.template_manager.render_template(
            "explanation",
            application_id=app.application_id,
            final_score=scoring.final_score,
            scoring_model=scoring.scoring_model,
            eligibility_status=eligibility.status,
            components=components_dict,
            features=features_list,
            facts=facts_list,
        )

        messages = [
            {
                "role": "system",
                "content": "You are a factual explanation generator. Never invent numbers or alter scores.",
            },
            {"role": "user", "content": prompt},
        ]

        response = self.provider.chat(
            model=self.model_name,
            messages=messages,
            options=MODEL_PARAMETERS,
        )

        raw_text = response["message"]["content"].strip()
        bullets = [
            line.lstrip("-*• ").strip()
            for line in raw_text.splitlines()
            if line.strip().startswith(("-", "*", "•", "1.", "2.", "3."))
        ]
        if not bullets:
            # Fallback split by lines
            bullets = [line.strip() for line in raw_text.splitlines() if line.strip()][:3]

        # Gather allowed ground numbers
        allowed_nums = {
            scoring.final_score,
            float(app.credit.credit_score.value) if app.credit.credit_score and app.credit.credit_score.value is not None else -999,
            float(app.income.monthly_gross_income.value) if app.income.monthly_gross_income and app.income.monthly_gross_income.value is not None else -999,
            float(app.obligations.missed_payments.value) if app.obligations.missed_payments and app.obligations.missed_payments.value is not None else 0.0,
            features.dti if features.dti is not None else -999,
            features.emi_ratio if features.emi_ratio is not None else -999,
        }
        for c in scoring.components.values():
            allowed_nums.add(c.raw_score)
            allowed_nums.add(c.contribution)
            allowed_nums.add(c.weight)

        allowed_components = set(scoring.components.keys())

        is_grounded, issues = self.validator.validate(
            bullets=bullets,
            allowed_numbers=allowed_nums,
            allowed_components=allowed_components,
            expected_score=scoring.final_score,
        )

        explanation_status = "VALID" if is_grounded else "INVALID"
        if not is_grounded:
            logger.warning(f"Explanation failed grounding validation: {issues}")

        return bullets, explanation_status


class LoanEvaluationSummarizer:
    """Uses LLM to summarize application PROS and CONS categorized by criticality (HIGH, MED, LOW).
    
    Strict invariant:
    - Never changes the score or criticality level.
    - Grounded in extracted facts and calculated features.
    - Categorizes each finding by criticality: HIGH, MED, or LOW.
    """

    def __init__(
        self,
        provider: Optional[OpenAICompatibleProvider] = None,
        model_name: str = DEFAULT_MODEL,
        template_manager: Optional[TemplateManager] = None,
    ):
        self.model_name = model_name
        self.provider = provider or initialize_llm_provider(model_name)
        self.template_manager = template_manager or TemplateManager()

    def summarize_evaluation(
        self,
        app: LoanApplication,
        features: DerivedFeatures,
        scoring: ScoringResult,
        eligibility: Optional[EligibilityResult] = None,
    ) -> ApplicationEvaluationSummary:
        """Generates executive verdict and pros/cons categorized by criticality (HIGH, MED, LOW)."""
        applicant_name = app.applicant.applicant_name.value if app.applicant.applicant_name else app.application_id
        
        # Prepare facts list
        facts_list = []
        if app.income.monthly_net_income and app.income.monthly_net_income.value is not None:
            facts_list.append({
                "field": "Monthly Net Income",
                "value": f"₹{app.income.monthly_net_income.value:,.2f}",
                "currency": app.income.monthly_net_income.currency or "INR",
                "evidence": app.income.monthly_net_income.source.evidence if app.income.monthly_net_income.source else "",
            })
        if app.credit.credit_score and app.credit.credit_score.value is not None:
            facts_list.append({
                "field": "Credit Bureau Score",
                "value": app.credit.credit_score.value,
                "currency": None,
                "evidence": app.credit.credit_score.source.evidence if app.credit.credit_score.source else "",
            })
        if app.obligations.missed_payments and app.obligations.missed_payments.value is not None:
            facts_list.append({
                "field": "Historical Missed Payments",
                "value": app.obligations.missed_payments.value,
                "currency": None,
                "evidence": app.obligations.missed_payments.source.evidence if app.obligations.missed_payments.source else "",
            })
        if app.obligations.overdue_amount and app.obligations.overdue_amount.value is not None:
            facts_list.append({
                "field": "Active Overdue Balance",
                "value": f"₹{app.obligations.overdue_amount.value:,.2f}",
                "currency": "INR",
                "evidence": app.obligations.overdue_amount.source.evidence if app.obligations.overdue_amount.source else "",
            })
        if app.loan_request.requested_loan_amount and app.loan_request.requested_loan_amount.value is not None:
            facts_list.append({
                "field": "Requested Loan Amount",
                "value": f"₹{app.loan_request.requested_loan_amount.value:,.2f}",
                "currency": "INR",
                "evidence": app.loan_request.requested_loan_amount.source.evidence if app.loan_request.requested_loan_amount.source else "",
            })
        if app.applicant.employment_duration_years and app.applicant.employment_duration_years.value is not None:
            employer_ev = ""
            if getattr(app.applicant, "employer_or_business_name", None) and app.applicant.employer_or_business_name:
                employer_ev = str(app.applicant.employer_or_business_name.value or "")
            facts_list.append({
                "field": "Employment Tenure",
                "value": f"{app.applicant.employment_duration_years.value} years",
                "currency": None,
                "evidence": employer_ev,
            })


        # Prepare features list
        features_list = []
        if features.dti is not None:
            features_list.append({"feature": "Debt to Income (DTI)", "result": f"{features.dti * 100:.1f}%", "units": "", "formula": "Total Debt Obligations / Gross Income"})
        if features.emi_ratio is not None:
            features_list.append({"feature": "EMI to Income Ratio", "result": f"{features.emi_ratio * 100:.1f}%", "units": "", "formula": "Proposed Loan EMI / Net Income"})
        if features.total_bank_credits_6m is not None:
            features_list.append({"feature": "Total 6M Bank Inflows", "result": f"₹{features.total_bank_credits_6m:,.2f}", "units": "INR", "formula": "Sum of 6-month bank statement credits"})
        if features.total_bank_debits_6m is not None:
            features_list.append({"feature": "Total 6M Bank Outflows", "result": f"₹{features.total_bank_debits_6m:,.2f}", "units": "INR", "formula": "Sum of 6-month bank statement debits"})
        if features.derived_monthly_salary_from_bank is not None:
            features_list.append({"feature": "Verified Monthly Bank Salary", "result": f"₹{features.derived_monthly_salary_from_bank:,.2f}", "units": "INR", "formula": "Average recurring payroll credits"})
        if features.credit_card_utilization is not None:
            features_list.append({"feature": "Credit Card Utilization", "result": f"{features.credit_card_utilization * 100:.1f}%", "units": "", "formula": "Credit Card Balance / Credit Limit"})
        if features.total_credit_card_spends_6m is not None:
            features_list.append({"feature": "Total 6M Credit Card Spends", "result": f"₹{features.total_credit_card_spends_6m:,.2f}", "units": "INR", "formula": "Sum of credit card purchases"})

        # Render Jinja prompt
        try:
            prompt = self.template_manager.render_template(
                "evaluation_summary",
                application_id=app.application_id,
                applicant_name=applicant_name,
                final_score=scoring.final_score,
                criticality=scoring.criticality,
                scoring_model=scoring.scoring_model,
                components=scoring.components,
                features=features_list,
                facts=facts_list,
            )

            messages = [
                {
                    "role": "system",
                    "content": "You are a professional credit underwriter summarizing loan applications into pros and cons by criticality (HIGH, MED, LOW). Return JSON ONLY.",
                },
                {"role": "user", "content": prompt},
            ]

            response = self.provider.chat(
                model=self.model_name,
                messages=messages,
                options={"temperature": 0.1, "top_p": 0.9},
            )

            content = response["message"]["content"].strip()
            clean_json = extract_json_from_response(content)
            data = json.loads(clean_json)

            pros = [
                CriticalityPoint(
                    criticality=str(p.get("criticality", "MED")).upper(),
                    point=p.get("point", ""),
                    evidence=p.get("evidence"),
                )
                for p in data.get("pros", [])
            ]
            cons = [
                CriticalityPoint(
                    criticality=str(c.get("criticality", "MED")).upper(),
                    point=c.get("point", ""),
                    evidence=c.get("evidence"),
                )
                for c in data.get("cons", [])
            ]
            verdict = data.get("executive_verdict")

            return ApplicationEvaluationSummary(
                application_id=app.application_id,
                overall_score=scoring.final_score,
                overall_criticality=scoring.criticality,
                executive_verdict=verdict,
                pros=pros,
                cons=cons,
            )
        except Exception as e:
            logger.warning(f"LLM Evaluation Summary generation failed ({e}), falling back to deterministic summary.")
            return self._deterministic_fallback_summary(app, features, scoring)

    def _deterministic_fallback_summary(
        self,
        app: LoanApplication,
        features: DerivedFeatures,
        scoring: ScoringResult,
    ) -> ApplicationEvaluationSummary:
        """Reliable rule-based fallback generating pros and cons by criticality."""
        pros: List[CriticalityPoint] = []
        cons: List[CriticalityPoint] = []

        cs = app.credit.credit_score.value if app.credit.credit_score else None
        if cs:
            if cs >= 750:
                pros.append(CriticalityPoint(criticality="HIGH", point=f"Excellent bureau credit score of {cs}", evidence=f"Bureau report indicates prime score {cs}"))
            elif cs >= 680:
                pros.append(CriticalityPoint(criticality="MED", point=f"Satisfactory bureau credit score of {cs}", evidence=f"Bureau credit score {cs}"))
            else:
                cons.append(CriticalityPoint(criticality="HIGH", point=f"Sub-prime bureau credit score of {cs}", evidence=f"Bureau score {cs} falls below standard threshold"))

        missed = app.obligations.missed_payments.value if app.obligations.missed_payments else 0
        overdue = app.obligations.overdue_amount.value if app.obligations.overdue_amount else 0.0

        if missed == 0 and overdue <= 0:
            pros.append(CriticalityPoint(criticality="HIGH", point="Impeccable repayment record with zero historical missed payments", evidence="0 missed payments reported"))
        elif missed == 1 and overdue <= 0:
            cons.append(CriticalityPoint(criticality="MED", point="1 historical missed payment recorded in obligations", evidence="1 missed payment reported"))
        else:
            cons.append(CriticalityPoint(criticality="HIGH", point=f"Significant repayment delinquency with {missed} missed payments and active overdue balance", evidence=f"{missed} missed payments, ₹{overdue:,.2f} overdue"))

        dti = features.dti
        if dti is not None:
            if dti <= 0.30:
                pros.append(CriticalityPoint(criticality="HIGH", point=f"Low existing debt burden with DTI of {dti * 100:.1f}%", evidence=f"DTI calculated at {dti * 100:.1f}%"))
            elif dti <= 0.45:
                pros.append(CriticalityPoint(criticality="MED", point=f"Manageable debt burden with DTI of {dti * 100:.1f}%", evidence=f"DTI calculated at {dti * 100:.1f}%"))
            else:
                cons.append(CriticalityPoint(criticality="HIGH", point=f"Elevated debt-to-income ratio of {dti * 100:.1f}% exceeds optimal limits", evidence=f"DTI calculated at {dti * 100:.1f}%"))

        # Cashflow & Salary regularity
        if features.total_bank_credits_6m and features.total_bank_debits_6m:
            net_cf = features.total_bank_credits_6m - features.total_bank_debits_6m
            if net_cf > 0:
                pros.append(CriticalityPoint(criticality="MED", point=f"Positive 6-month banking cashflow surplus of ₹{net_cf:,.2f}", evidence=f"Credits: ₹{features.total_bank_credits_6m:,.2f}, Debits: ₹{features.total_bank_debits_6m:,.2f}"))
            else:
                cons.append(CriticalityPoint(criticality="HIGH", point=f"Net cashflow deficit of ₹{abs(net_cf):,.2f} over past 6 months", evidence=f"Credits: ₹{features.total_bank_credits_6m:,.2f}, Debits: ₹{features.total_bank_debits_6m:,.2f}"))

        # Credit card utilization
        if features.credit_card_utilization is not None:
            if features.credit_card_utilization <= 0.35:
                pros.append(CriticalityPoint(criticality="LOW", point=f"Disciplined credit card utilization at {features.credit_card_utilization * 100:.1f}%", evidence=f"CC Utilization {features.credit_card_utilization * 100:.1f}%"))
            elif features.credit_card_utilization > 0.70:
                cons.append(CriticalityPoint(criticality="MED", point=f"High revolving credit card utilization at {features.credit_card_utilization * 100:.1f}%", evidence=f"CC Utilization {features.credit_card_utilization * 100:.1f}%"))

        # Employment tenure
        emp_years = app.applicant.employment_duration_years.value if app.applicant.employment_duration_years else 0.0
        if emp_years >= 3.0:
            pros.append(CriticalityPoint(criticality="MED", point=f"Stable employment track record of {emp_years} years", evidence=f"{emp_years} years tenure"))
        elif emp_years < 1.0:
            cons.append(CriticalityPoint(criticality="LOW", point=f"Short employment tenure ({emp_years} years)", evidence=f"{emp_years} years tenure"))

        verdict = (
            f"Application evaluated with overall deterministic score of {scoring.final_score:.2f}/100 "
            f"and assigned {scoring.criticality} risk criticality."
        )

        return ApplicationEvaluationSummary(
            application_id=app.application_id,
            overall_score=scoring.final_score,
            overall_criticality=scoring.criticality,
            executive_verdict=verdict,
            pros=pros,
            cons=cons,
        )

