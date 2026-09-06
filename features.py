"""Deterministic Financial Feature Engine.

Performs all financial ratio derivations and mathematical feature transformations
strictly in Python code.
Every feature produces an auditable FeatureTrace containing:
- feature name
- exact formula
- raw inputs
- calculated numerical result
- units
"""

from typing import List, Optional, Dict, Any
from models import (
    LoanApplication,
    DerivedFeatures,
    FeatureTrace,
)


class FinancialFeatureEngine:
    """Calculates deterministic financial ratios and risk features with explicit traces."""

    def calculate_features(self, app: LoanApplication) -> DerivedFeatures:
        traces: List[FeatureTrace] = []

        # 1. Resolve base numerical parameters safely without mutating missing values
        gross_monthly = app.income.monthly_gross_income.value if app.income.monthly_gross_income else None
        net_monthly = app.income.monthly_net_income.value if app.income.monthly_net_income else None
        annual_income = app.income.annual_income.value if app.income.annual_income else None
        annual_revenue = app.income.annual_revenue.value if app.income.annual_revenue else None

        existing_emi = app.obligations.existing_monthly_emi.value if app.obligations.existing_monthly_emi else None
        outstanding_debt = app.obligations.outstanding_debt.value if app.obligations.outstanding_debt else None
        requested_loan = app.loan_request.requested_loan_amount.value if app.loan_request.requested_loan_amount else None
        emp_years = app.applicant.employment_duration_years.value if app.applicant.employment_duration_years else None

        # ---------------------------------------------------------
        # Feature 1: Debt-to-Income (DTI)
        # DTI = existing_monthly_emi / monthly_gross_income
        # ---------------------------------------------------------
        dti_val: Optional[float] = None
        if existing_emi is not None and gross_monthly is not None and gross_monthly > 0:
            dti_val = round(existing_emi / gross_monthly, 4)
            traces.append(
                FeatureTrace(
                    feature="debt_to_income_ratio",
                    formula="existing_monthly_emi / monthly_gross_income",
                    inputs={"existing_monthly_emi": existing_emi, "monthly_gross_income": gross_monthly},
                    result=dti_val,
                    units="ratio",
                )
            )
        else:
            traces.append(
                FeatureTrace(
                    feature="debt_to_income_ratio",
                    formula="existing_monthly_emi / monthly_gross_income",
                    inputs={"existing_monthly_emi": existing_emi, "monthly_gross_income": gross_monthly},
                    result=None,
                    units="ratio",
                    notes="Missing required input (existing_monthly_emi or monthly_gross_income)",
                )
            )

        # ---------------------------------------------------------
        # Feature 2: EMI-to-Net-Income Ratio
        # EMI Ratio = existing_monthly_emi / monthly_net_income (or monthly_gross_income fallback)
        # ---------------------------------------------------------
        emi_ratio_val: Optional[float] = None
        effective_income = net_monthly if (net_monthly is not None and net_monthly > 0) else gross_monthly
        if existing_emi is not None and effective_income is not None and effective_income > 0:
            emi_ratio_val = round(existing_emi / effective_income, 4)
            traces.append(
                FeatureTrace(
                    feature="emi_to_income_ratio",
                    formula="existing_monthly_emi / monthly_net_income",
                    inputs={"existing_monthly_emi": existing_emi, "monthly_income": effective_income},
                    result=emi_ratio_val,
                    units="ratio",
                )
            )
        else:
            traces.append(
                FeatureTrace(
                    feature="emi_to_income_ratio",
                    formula="existing_monthly_emi / monthly_net_income",
                    inputs={"existing_monthly_emi": existing_emi, "monthly_income": effective_income},
                    result=None,
                    units="ratio",
                    notes="Missing monthly income or monthly EMI data",
                )
            )

        # ---------------------------------------------------------
        # Feature 3: Loan-to-Income (LTI)
        # LTI = requested_loan_amount / annual_income (or annualized gross)
        # ---------------------------------------------------------
        lti_val: Optional[float] = None
        eff_annual_income = annual_income if annual_income is not None else ((gross_monthly * 12.0) if gross_monthly else None)
        if requested_loan is not None and eff_annual_income is not None and eff_annual_income > 0:
            lti_val = round(requested_loan / eff_annual_income, 4)
            traces.append(
                FeatureTrace(
                    feature="loan_to_income_ratio",
                    formula="requested_loan_amount / annual_income",
                    inputs={"requested_loan_amount": requested_loan, "annual_income": eff_annual_income},
                    result=lti_val,
                    units="ratio",
                )
            )
        else:
            traces.append(
                FeatureTrace(
                    feature="loan_to_income_ratio",
                    formula="requested_loan_amount / annual_income",
                    inputs={"requested_loan_amount": requested_loan, "annual_income": eff_annual_income},
                    result=None,
                    units="ratio",
                    notes="Missing requested_loan_amount or annual_income",
                )
            )

        # ---------------------------------------------------------
        # Feature 4: Debt-to-Revenue Ratio (for businesses)
        # Debt/Revenue = outstanding_debt / annual_revenue
        # ---------------------------------------------------------
        debt_rev_val: Optional[float] = None
        if outstanding_debt is not None and annual_revenue is not None and annual_revenue > 0:
            debt_rev_val = round(outstanding_debt / annual_revenue, 4)
            traces.append(
                FeatureTrace(
                    feature="debt_to_revenue_ratio",
                    formula="outstanding_debt / annual_revenue",
                    inputs={"outstanding_debt": outstanding_debt, "annual_revenue": annual_revenue},
                    result=debt_rev_val,
                    units="ratio",
                )
            )

        # ---------------------------------------------------------
        # Feature: Credit Card Utilization (from Statement)
        # ---------------------------------------------------------
        cc_util_val: Optional[float] = None
        cc_limit = app.credit.credit_card_limit.value if app.credit.credit_card_limit else None
        cc_bal = app.credit.credit_card_total_balance.value if app.credit.credit_card_total_balance else None
        if cc_limit is not None and cc_limit > 0 and cc_bal is not None:
            cc_util_val = round(cc_bal / cc_limit, 4)
            traces.append(
                FeatureTrace(
                    feature="credit_card_utilization",
                    formula="credit_card_total_balance / credit_card_limit",
                    inputs={"credit_card_total_balance": cc_bal, "credit_card_limit": cc_limit},
                    result=cc_util_val,
                    units="ratio",
                )
            )

        # ---------------------------------------------------------
        # Feature 5: Income / Employment Stability Index (0 - 100)
        # Deterministic formula:
        # Min(100, (years * 20.0)) with bonuses for permanent employment
        # ---------------------------------------------------------
        stability_val: Optional[float] = None
        if emp_years is not None:
            raw_stab = min(100.0, emp_years * 20.0)  # 5 years = 100
            emp_type = (app.applicant.employment_type.value if app.applicant.employment_type else "") or ""
            if "permanent" in emp_type.lower() or "full_time" in emp_type.lower():
                raw_stab = min(100.0, raw_stab + 10.0)
            stability_val = round(raw_stab, 2)
            traces.append(
                FeatureTrace(
                    feature="income_stability_index",
                    formula="min(100.0, employment_years * 20.0 + permanent_bonus)",
                    inputs={"employment_duration_years": emp_years, "employment_type": emp_type},
                    result=stability_val,
                    units="index_points",
                )
            )
        else:
            traces.append(
                FeatureTrace(
                    feature="income_stability_index",
                    formula="min(100.0, employment_years * 20.0)",
                    inputs={"employment_duration_years": None},
                    result=None,
                    units="index_points",
                    notes="Employment duration years not provided",
                )
            )

        # ---------------------------------------------------------
        # Feature 6: Documentation Completeness (0.0 to 1.0)
        # Count verified documents out of 5 canonical documents
        # ---------------------------------------------------------
        doc_checks = [
            app.documentation.identity_verified.value if app.documentation.identity_verified else False,
            app.documentation.income_document_available.value if app.documentation.income_document_available else False,
            app.documentation.bank_statement_available.value if app.documentation.bank_statement_available else False,
            app.documentation.tax_document_available.value if app.documentation.tax_document_available else False,
            app.documentation.loan_statement_available.value if app.documentation.loan_statement_available else False,
        ]
        available_count = sum(1 for checked in doc_checks if checked is True)
        total_required = len(doc_checks)
        doc_completeness = round(available_count / total_required, 4)

        traces.append(
            FeatureTrace(
                feature="documentation_completeness",
                formula="available_verified_documents / total_required_documents",
                inputs={"available_count": available_count, "total_required": total_required},
                result=doc_completeness,
                units="ratio",
            )
        )

        # ---------------------------------------------------------
        # Feature 7: Bank Statement & Credit Card Transaction Aggregations
        # Extraction -> Parsing -> Refining -> Calculating
        # ---------------------------------------------------------
        total_bank_credits: Optional[float] = None
        total_bank_debits: Optional[float] = None
        derived_salary_bank: Optional[float] = None
        derived_emi_bank: Optional[float] = None

        if app.bank_transactions:
            credit_txs = [tx for tx in app.bank_transactions if tx.transaction_type == "CREDIT"]
            debit_txs = [tx for tx in app.bank_transactions if tx.transaction_type == "DEBIT"]

            total_bank_credits = round(sum(tx.amount for tx in credit_txs), 2)
            total_bank_debits = round(sum(tx.amount for tx in debit_txs), 2)

            traces.append(
                FeatureTrace(
                    feature="total_bank_credits_6m",
                    formula="sum(credit_transactions.amount)",
                    inputs={"credit_transaction_count": len(credit_txs), "credit_amounts": [tx.amount for tx in credit_txs]},
                    result=total_bank_credits,
                    units="currency_inr",
                )
            )

            traces.append(
                FeatureTrace(
                    feature="total_bank_debits_6m",
                    formula="sum(debit_transactions.amount)",
                    inputs={"debit_transaction_count": len(debit_txs), "debit_amounts": [tx.amount for tx in debit_txs]},
                    result=total_bank_debits,
                    units="currency_inr",
                )
            )

            # Refining: Identify salary credits
            salary_txs = [
                tx for tx in credit_txs
                if (tx.category == "SALARY" or any(w in tx.description.lower() for w in ["salary", "payroll", "sal credit"]))
            ]
            if salary_txs:
                total_salary = sum(tx.amount for tx in salary_txs)
                derived_salary_bank = round(total_salary / len(salary_txs), 2)
                traces.append(
                    FeatureTrace(
                        feature="derived_monthly_salary_from_bank",
                        formula="sum(verified_salary_credits) / count_of_salary_credits",
                        inputs={
                            "salary_credits_found": len(salary_txs),
                            "salary_amounts": [tx.amount for tx in salary_txs],
                            "sum_salary_credits": total_salary,
                        },
                        result=derived_salary_bank,
                        units="currency_inr",
                    )
                )

            # Refining: Identify loan EMI debits
            emi_txs = [
                tx for tx in debit_txs
                if (tx.category == "EMI" or any(w in tx.description.lower() for w in ["emi", "loan debit", "nach", "auto-debit"]))
            ]
            if emi_txs:
                total_emi_tx = sum(tx.amount for tx in emi_txs)
                derived_emi_bank = round(total_emi_tx / len(emi_txs), 2)
                traces.append(
                    FeatureTrace(
                        feature="derived_monthly_emi_from_bank",
                        formula="sum(verified_emi_debits) / count_of_emi_debits",
                        inputs={
                            "emi_debits_found": len(emi_txs),
                            "emi_amounts": [tx.amount for tx in emi_txs],
                            "sum_emi_debits": total_emi_tx,
                        },
                        result=derived_emi_bank,
                        units="currency_inr",
                    )
                )

        # Credit card transactions spend calculation
        total_cc_spends: Optional[float] = None
        if app.credit_card_transactions:
            spend_txs = [
                tx for tx in app.credit_card_transactions
                if tx.transaction_type == "DEBIT" or (tx.category and "PAYMENT" not in tx.category)
            ]
            if spend_txs:
                total_cc_spends = round(sum(tx.amount for tx in spend_txs), 2)
                traces.append(
                    FeatureTrace(
                        feature="total_credit_card_spends_6m",
                        formula="sum(credit_card_spend_transactions.amount)",
                        inputs={"spend_transaction_count": len(spend_txs), "spend_amounts": [tx.amount for tx in spend_txs]},
                        result=total_cc_spends,
                        units="currency_inr",
                    )
                )

        return DerivedFeatures(
            application_id=app.application_id,
            dti=dti_val,
            emi_ratio=emi_ratio_val,
            lti=lti_val,
            debt_to_revenue=debt_rev_val,
            credit_card_utilization=cc_util_val,
            total_bank_credits_6m=total_bank_credits,
            total_bank_debits_6m=total_bank_debits,
            derived_monthly_salary_from_bank=derived_salary_bank,
            derived_monthly_emi_from_bank=derived_emi_bank,
            total_credit_card_spends_6m=total_cc_spends,
            income_stability_index=stability_val,
            documentation_completeness=doc_completeness,
            traces=traces,
        )
