"""Deterministic Eligibility Evaluation Engine.

Applies configurable underwriting rules and policy gates.
Strict separation: Eligibility gating is distinct from numerical ranking.
Outputs:
- ELIGIBLE: Meets all policy gates
- INELIGIBLE: Violates one or more hard policy gates
- MANUAL_REVIEW: Flagged due to document discrepancies or edge-case anomalies
"""

import json
import os
import logging
from typing import Dict, Any, Optional
from models import (
    LoanApplication,
    DerivedFeatures,
    ValidationResult,
    EligibilityResult,
)

logger = logging.getLogger(__name__)


def load_product_config(config_path_or_product: str) -> Dict[str, Any]:
    """Load product configuration from file path or canonical name."""
    if os.path.exists(config_path_or_product):
        with open(config_path_or_product, "r") as f:
            return json.load(f)

    # Search in loan_products directory
    candidate = os.path.join("loan_products", f"{config_path_or_product}.json")
    if os.path.exists(candidate):
        with open(candidate, "r") as f:
            return json.load(f)

    # Fallback to personal_loan_v1
    fallback = os.path.join("loan_products", "personal_loan_v1.json")
    if os.path.exists(fallback):
        with open(fallback, "r") as f:
            return json.load(f)

    raise FileNotFoundError(f"Could not resolve loan product config: {config_path_or_product}")


class EligibilityEngine:
    """Evaluates rule-based eligibility independently of scoring."""

    def __init__(self, product_config: Dict[str, Any]):
        self.config = product_config
        self.rules = self.config.get("eligibility_rules", {})

    def evaluate(
        self,
        app: LoanApplication,
        features: DerivedFeatures,
        validation: Optional[ValidationResult] = None,
    ) -> EligibilityResult:
        passed_rules = []
        failed_rules = []
        review_reasons = []

        # 1. Validation consistency check
        if validation and validation.status == "DATA_INCONSISTENCY":
            review_reasons.append("Cross-document data inconsistency flagged during validation.")
        if validation and validation.status == "INSUFFICIENT_DATA":
            failed_rules.append("PRIMARY_DATA_MISSING")

        # 2. Mandatory document requirements
        mandatory_docs = self.rules.get("mandatory_documents", [])
        doc_map = {
            "identity_verified": app.documentation.identity_verified.value if app.documentation.identity_verified else False,
            "income_document_available": app.documentation.income_document_available.value if app.documentation.income_document_available else False,
            "bank_statement_available": app.documentation.bank_statement_available.value if app.documentation.bank_statement_available else False,
            "tax_document_available": app.documentation.tax_document_available.value if app.documentation.tax_document_available else False,
            "loan_statement_available": app.documentation.loan_statement_available.value if app.documentation.loan_statement_available else False,
            "credit_card_statement_available": app.documentation.credit_card_statement_available.value if app.documentation.credit_card_statement_available else False,
        }

        for m_doc in mandatory_docs:
            if doc_map.get(m_doc, False) is True:
                passed_rules.append(f"MANDATORY_DOC_{m_doc.upper()}")
            else:
                failed_rules.append(f"MISSING_MANDATORY_DOC_{m_doc.upper()}")

        # 3. Minimum Credit Score
        min_cs = self.rules.get("min_credit_score")
        cs = app.credit.credit_score.value if app.credit.credit_score else None
        if min_cs is not None:
            if cs is None:
                review_reasons.append("Credit score unavailable; requires manual bureau review.")
            elif cs >= min_cs:
                passed_rules.append(f"MIN_CREDIT_SCORE_{min_cs}")
            else:
                failed_rules.append(f"CREDIT_SCORE_BELOW_THRESHOLD (Got {cs}, Required {min_cs})")

        # 4. Maximum Debt-to-Income Ratio (DTI)
        max_dti = self.rules.get("max_dti")
        if max_dti is not None and features.dti is not None:
            if features.dti <= max_dti:
                passed_rules.append(f"MAX_DTI_{max_dti}")
            else:
                failed_rules.append(f"DTI_EXCEEDS_POLICY_THRESHOLD (Got {features.dti}, Max {max_dti})")

        # 5. Maximum Requested Loan Amount
        max_req = self.rules.get("max_requested_amount")
        req_amt = app.loan_request.requested_loan_amount.value if app.loan_request.requested_loan_amount else None
        if max_req is not None and req_amt is not None:
            if req_amt <= max_req:
                passed_rules.append("LOAN_AMOUNT_WITHIN_PRODUCT_CAP")
            else:
                failed_rules.append(f"LOAN_AMOUNT_EXCEEDS_PRODUCT_CAP (Got {req_amt}, Max {max_req})")

        # 6. Minimum Monthly Income
        min_inc = self.rules.get("min_monthly_income")
        gross = app.income.monthly_gross_income.value if app.income.monthly_gross_income else None
        if min_inc is not None and gross is not None:
            if gross >= min_inc:
                passed_rules.append(f"MIN_INCOME_{min_inc}")
            else:
                failed_rules.append(f"INCOME_BELOW_THRESHOLD (Got {gross}, Required {min_inc})")

        # 7. Maximum Missed Payments in History
        max_missed = self.rules.get("max_allowed_missed_payments")
        missed = app.obligations.missed_payments.value if app.obligations.missed_payments else 0
        if max_missed is not None:
            if missed <= max_missed:
                passed_rules.append(f"MISSED_PAYMENTS_WITHIN_LIMIT (Got {missed})")
            else:
                failed_rules.append(f"EXCESSIVE_MISSED_PAYMENTS (Got {missed}, Max {max_missed})")

        # Status decision
        if failed_rules:
            status = "INELIGIBLE"
        elif review_reasons:
            status = "MANUAL_REVIEW"
        else:
            status = "ELIGIBLE"

        return EligibilityResult(
            application_id=app.application_id,
            status=status,
            passed_rules=passed_rules,
            failed_rules=failed_rules,
            manual_review_reasons=review_reasons,
        )
