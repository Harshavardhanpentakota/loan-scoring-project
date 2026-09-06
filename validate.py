"""Deterministic Validation Layer for Loan Applications.

Runs before feature calculation and scoring to ensure data integrity, cross-document
consistency, range validity, and source evidence provenance.
Never uses an LLM to decide correctness or pick between conflicting numbers.
"""

import logging
from typing import List, Optional
from models import (
    LoanApplication,
    ValidationResult,
    ValidationIssue,
    ExtractedField,
)

logger = logging.getLogger(__name__)


class LoanValidator:
    """Validates an extracted LoanApplication for mathematical and logical consistency."""

    def __init__(self, income_tolerance_pct: float = 0.20):
        """
        Args:
            income_tolerance_pct: Maximum allowed discrepancy between annualized monthly
                                 income and declared annual income (default 20%).
        """
        self.income_tolerance_pct = income_tolerance_pct

    def validate(self, app: LoanApplication) -> ValidationResult:
        issues: List[ValidationIssue] = []

        # 1. Provenance / Evidence checks
        self._check_evidence_presence(app, issues)

        # 2. Impossible values & range checks
        self._check_ranges_and_impossible_values(app, issues)

        # 3. Currency consistency
        self._check_currency_consistency(app, issues)

        # 4. Cross-document / Internal consistency checks
        self._check_cross_document_consistency(app, issues)

        # 5. Determine overall status
        status = "VALID"
        is_valid = True

        has_inconsistency = any(i.issue_type == "DATA_INCONSISTENCY" for i in issues)
        has_insufficient = any(i.issue_type == "INSUFFICIENT_DATA" for i in issues)
        has_error = any(i.severity == "ERROR" for i in issues)

        if has_inconsistency:
            status = "DATA_INCONSISTENCY"
            is_valid = False
        elif has_insufficient:
            status = "INSUFFICIENT_DATA"
            is_valid = False
        elif has_error:
            status = "INVALID"
            is_valid = False

        return ValidationResult(status=status, is_valid=is_valid, issues=issues)

    def _check_evidence_presence(self, app: LoanApplication, issues: List[ValidationIssue]):
        """Ensure non-null extracted fields carry verifiable document evidence."""
        fields_to_check = [
            ("monthly_gross_income", app.income.monthly_gross_income),
            ("monthly_net_income", app.income.monthly_net_income),
            ("annual_income", app.income.annual_income),
            ("existing_monthly_emi", app.obligations.existing_monthly_emi),
            ("outstanding_debt", app.obligations.outstanding_debt),
            ("requested_loan_amount", app.loan_request.requested_loan_amount),
            ("credit_score", app.credit.credit_score),
        ]
        for field_name, field in fields_to_check:
            if field and field.value is not None:
                if not field.source or not field.source.document or not field.source.evidence:
                    issues.append(
                        ValidationIssue(
                            field=field_name,
                            issue_type="MISSING_EVIDENCE",
                            severity="WARNING",
                            message=f"Field '{field_name}' has extracted value {field.value} without full source evidence citation.",
                        )
                    )

    def _check_ranges_and_impossible_values(self, app: LoanApplication, issues: List[ValidationIssue]):
        """Validate bounded variables against domain rules."""
        # Credit Score (Standard CIBIL/Experian 300 - 900)
        cs = app.credit.credit_score.value if app.credit.credit_score else None
        if cs is not None:
            if cs < 300 or cs > 900:
                issues.append(
                    ValidationIssue(
                        field="credit_score",
                        issue_type="OUT_OF_RANGE",
                        severity="ERROR",
                        message=f"Credit score {cs} is outside valid bureau range [300, 900].",
                    )
                )

        # Net Income vs Gross Income
        gross = app.income.monthly_gross_income.value if app.income.monthly_gross_income else None
        net = app.income.monthly_net_income.value if app.income.monthly_net_income else None

        if gross is not None and gross < 0:
            issues.append(
                ValidationIssue(
                    field="monthly_gross_income",
                    issue_type="OUT_OF_RANGE",
                    severity="ERROR",
                    message=f"Monthly gross income cannot be negative: {gross}",
                )
            )
        if net is not None and net < 0:
            issues.append(
                ValidationIssue(
                    field="monthly_net_income",
                    issue_type="OUT_OF_RANGE",
                    severity="ERROR",
                    message=f"Monthly net income cannot be negative: {net}",
                )
            )

        if gross is not None and net is not None:
            if net > gross:
                issues.append(
                    ValidationIssue(
                        field="monthly_net_income",
                        issue_type="DATA_INCONSISTENCY",
                        severity="ERROR",
                        message=f"Impossible income: Net income ({net}) exceeds Gross income ({gross}).",
                    )
                )

        # Age check if present
        age = app.applicant.age.value if app.applicant.age else None
        if age is not None and (age < 18 or age > 100):
            issues.append(
                ValidationIssue(
                    field="age",
                    issue_type="OUT_OF_RANGE",
                    severity="ERROR",
                    message=f"Applicant age {age} is outside eligible working boundaries [18, 100].",
                )
            )

        # Loan request amount
        req_amount = app.loan_request.requested_loan_amount.value if app.loan_request.requested_loan_amount else None
        if req_amount is not None and req_amount <= 0:
            issues.append(
                ValidationIssue(
                    field="requested_loan_amount",
                    issue_type="OUT_OF_RANGE",
                    severity="ERROR",
                    message=f"Requested loan amount must be positive, got {req_amount}.",
                )
            )

        # Tenure months
        tenure = app.loan_request.tenure_months.value if app.loan_request.tenure_months else None
        if tenure is not None and tenure <= 0:
            issues.append(
                ValidationIssue(
                    field="tenure_months",
                    issue_type="OUT_OF_RANGE",
                    severity="ERROR",
                    message=f"Tenure months must be positive, got {tenure}.",
                )
            )

        # Existing obligations
        emi = app.obligations.existing_monthly_emi.value if app.obligations.existing_monthly_emi else None
        if emi is not None and emi < 0:
            issues.append(
                ValidationIssue(
                    field="existing_monthly_emi",
                    issue_type="OUT_OF_RANGE",
                    severity="ERROR",
                    message=f"Monthly EMI obligations cannot be negative, got {emi}.",
                )
            )

        missed = app.obligations.missed_payments.value if app.obligations.missed_payments else None
        if missed is not None and missed < 0:
            issues.append(
                ValidationIssue(
                    field="missed_payments",
                    issue_type="OUT_OF_RANGE",
                    severity="ERROR",
                    message=f"Missed payments count cannot be negative, got {missed}.",
                )
            )

    def _check_currency_consistency(self, app: LoanApplication, issues: List[ValidationIssue]):
        """Ensure all financial values use identical currency units."""
        currencies = set()
        fields_with_currency = [
            ("monthly_gross_income", app.income.monthly_gross_income),
            ("monthly_net_income", app.income.monthly_net_income),
            ("annual_income", app.income.annual_income),
            ("annual_revenue", app.income.annual_revenue),
            ("existing_monthly_emi", app.obligations.existing_monthly_emi),
            ("outstanding_debt", app.obligations.outstanding_debt),
            ("requested_loan_amount", app.loan_request.requested_loan_amount),
        ]
        for name, f in fields_with_currency:
            if f and f.currency:
                c = f.currency.upper().strip()
                currencies.add(c)

        if len(currencies) > 1:
            issues.append(
                ValidationIssue(
                    field="currency",
                    issue_type="DATA_INCONSISTENCY",
                    severity="ERROR",
                    message=f"Multiple conflicting currencies detected in application: {list(currencies)}",
                )
            )

    def _check_cross_document_consistency(self, app: LoanApplication, issues: List[ValidationIssue]):
        """Compare documents across sources (e.g. Salary Slip Monthly vs Form 16 Annual)."""
        gross = app.income.monthly_gross_income.value if app.income.monthly_gross_income else None
        annual = app.income.annual_income.value if app.income.annual_income else None

        if gross is not None and annual is not None and gross > 0:
            annualized_gross = gross * 12.0
            discrepancy = abs(annualized_gross - annual) / max(annualized_gross, annual)

            if discrepancy > self.income_tolerance_pct:
                issues.append(
                    ValidationIssue(
                        field="income_consistency",
                        issue_type="DATA_INCONSISTENCY",
                        severity="ERROR",
                        message=(
                            f"Cross-document income mismatch: Monthly salary ({gross}) "
                            f"annualized to {annualized_gross:.2f} differs significantly "
                            f"from declared annual income {annual:.2f} (Discrepancy: {discrepancy * 100:.1f}%)."
                        ),
                    )
                )

        # Basic viability check: Has neither income nor revenue
        has_any_income = any([
            gross is not None and gross > 0,
            annual is not None and annual > 0,
            (app.income.annual_revenue.value if app.income.annual_revenue else None) is not None,
        ])
        if not has_any_income:
            issues.append(
                ValidationIssue(
                    field="income",
                    issue_type="INSUFFICIENT_DATA",
                    severity="ERROR",
                    message="Application lacks all primary income and revenue data required for financial evaluation.",
                )
            )
