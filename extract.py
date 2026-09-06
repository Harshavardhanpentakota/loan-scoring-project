"""Document extraction layer for the Loan Ranking Agent.

Strict LLM Boundary:
- Extracts ONLY raw factual data explicitly stated in the supplied documents.
- Attaches source evidence (document, page, snippet) to every field.
- Missing values remain None (no defaults, no zero substitution).
- NEVER calculates derived metrics (no DTI, no annualizing monthly income, etc.).
"""

import json
import logging
from typing import List, Dict, Any, Optional
from models import (
    LoanApplication,
    ApplicantInfo,
    IncomeInfo,
    ExistingObligations,
    LoanRequest,
    CreditInfo,
    AssetsLiabilities,
    DocumentationStatus,
    ExtractedField,
    SourceEvidence,
    TransactionRecord,
    LLMProvider,
)
from prompts.template_manager import TemplateManager
from llm_utils import extract_json_from_response, initialize_llm_provider
from config import DEFAULT_MODEL, MODEL_PARAMETERS

logger = logging.getLogger(__name__)


def build_extracted_field(data: Optional[Dict[str, Any]], target_type=None) -> Optional[ExtractedField]:
    """Helper to convert a raw dictionary into an ExtractedField with SourceEvidence."""
    if not data or not isinstance(data, dict):
        return None
    val = data.get("value")
    if val is None:
        return None

    # Cast to target_type if specified and possible
    if target_type is not None and val is not None:
        try:
            val = target_type(val)
        except (ValueError, TypeError):
            pass

    currency = data.get("currency")
    src_data = data.get("source")
    evidence = None
    if isinstance(src_data, dict):
        evidence = SourceEvidence(
            document=str(src_data.get("document", "unknown")),
            page=src_data.get("page"),
            evidence=str(src_data.get("evidence", "")),
        )
    return ExtractedField(value=val, currency=currency, source=evidence)


def parse_extraction_json(raw_json_str: str, application_id: str) -> LoanApplication:
    """Parse raw JSON output from LLM into a validated LoanApplication instance."""
    cleaned = extract_json_from_response(raw_json_str)
    parsed = json.loads(cleaned)

    app_id = parsed.get("application_id") or application_id

    applicant_data = parsed.get("applicant", {})
    applicant = ApplicantInfo(
        applicant_id=app_id,
        applicant_name=build_extracted_field(applicant_data.get("applicant_name"), str),
        applicant_type=build_extracted_field(applicant_data.get("applicant_type"), str),
        age=build_extracted_field(applicant_data.get("age"), int),
        employment_type=build_extracted_field(applicant_data.get("employment_type"), str),
        employer_or_business_name=build_extracted_field(applicant_data.get("employer_or_business_name"), str),
        employment_start_date=build_extracted_field(applicant_data.get("employment_start_date"), str),
        employment_duration_years=build_extracted_field(applicant_data.get("employment_duration_years"), float),
    )

    income_data = parsed.get("income", {})
    income = IncomeInfo(
        monthly_gross_income=build_extracted_field(income_data.get("monthly_gross_income"), float),
        monthly_net_income=build_extracted_field(income_data.get("monthly_net_income"), float),
        annual_income=build_extracted_field(income_data.get("annual_income"), float),
        annual_revenue=build_extracted_field(income_data.get("annual_revenue"), float),
        income_sources=build_extracted_field(income_data.get("income_sources")),
        income_period=build_extracted_field(income_data.get("income_period"), str),
        income_frequency=build_extracted_field(income_data.get("income_frequency"), str),
    )

    ob_data = parsed.get("obligations", {})
    obligations = ExistingObligations(
        existing_monthly_emi=build_extracted_field(ob_data.get("existing_monthly_emi"), float),
        existing_loan_count=build_extracted_field(ob_data.get("existing_loan_count"), int),
        outstanding_debt=build_extracted_field(ob_data.get("outstanding_debt"), float),
        overdue_amount=build_extracted_field(ob_data.get("overdue_amount"), float),
        missed_payments=build_extracted_field(ob_data.get("missed_payments"), int),
        repayment_history=build_extracted_field(ob_data.get("repayment_history"), str),
    )

    req_data = parsed.get("loan_request", {})
    loan_request = LoanRequest(
        requested_loan_amount=build_extracted_field(req_data.get("requested_loan_amount"), float),
        tenure_months=build_extracted_field(req_data.get("tenure_months"), int),
        loan_type=build_extracted_field(req_data.get("loan_type"), str),
        loan_purpose=build_extracted_field(req_data.get("loan_purpose"), str),
    )

    cr_data = parsed.get("credit", {})
    credit = CreditInfo(
        credit_score=build_extracted_field(cr_data.get("credit_score"), int),
        credit_utilization_ratio=build_extracted_field(cr_data.get("credit_utilization_ratio"), float),
        active_credit_accounts=build_extracted_field(cr_data.get("active_credit_accounts"), int),
        delinquency_information=build_extracted_field(cr_data.get("delinquency_information"), str),
        credit_card_limit=build_extracted_field(cr_data.get("credit_card_limit"), float),
        credit_card_total_balance=build_extracted_field(cr_data.get("credit_card_total_balance"), float),
        credit_card_min_payment_due=build_extracted_field(cr_data.get("credit_card_min_payment_due"), float),
    )

    al_data = parsed.get("assets_liabilities", {})
    assets_liabilities = AssetsLiabilities(
        assets=build_extracted_field(al_data.get("assets"), float),
        liabilities=build_extracted_field(al_data.get("liabilities"), float),
        savings=build_extracted_field(al_data.get("savings"), float),
    )

    doc_data = parsed.get("documentation", {})
    documentation = DocumentationStatus(
        identity_verified=build_extracted_field(doc_data.get("identity_verified"), bool),
        income_document_available=build_extracted_field(doc_data.get("income_document_available"), bool),
        bank_statement_available=build_extracted_field(doc_data.get("bank_statement_available"), bool),
        tax_document_available=build_extracted_field(doc_data.get("tax_document_available"), bool),
        loan_statement_available=build_extracted_field(doc_data.get("loan_statement_available"), bool),
        credit_card_statement_available=build_extracted_field(doc_data.get("credit_card_statement_available"), bool),
    )

    # Parse itemized bank transactions
    bank_tx_data = parsed.get("bank_transactions", [])
    bank_transactions: List[TransactionRecord] = []
    if isinstance(bank_tx_data, list):
        for tx in bank_tx_data:
            if isinstance(tx, dict) and "amount" in tx:
                src_data = tx.get("source")
                src = None
                if isinstance(src_data, dict):
                    src = SourceEvidence(
                        document=str(src_data.get("document", "bank_statement.pdf")),
                        page=src_data.get("page"),
                        evidence=str(src_data.get("evidence", "")),
                    )
                try:
                    bank_transactions.append(TransactionRecord(
                        date=tx.get("date"),
                        description=str(tx.get("description", "")),
                        amount=float(tx.get("amount", 0.0)),
                        transaction_type=str(tx.get("transaction_type", "DEBIT")).upper(),
                        balance=float(tx.get("balance")) if tx.get("balance") is not None else None,
                        category=str(tx.get("category")).upper() if tx.get("category") else None,
                        source=src,
                    ))
                except (ValueError, TypeError):
                    pass

    # Parse itemized credit card transactions
    cc_tx_data = parsed.get("credit_card_transactions", [])
    credit_card_transactions: List[TransactionRecord] = []
    if isinstance(cc_tx_data, list):
        for tx in cc_tx_data:
            if isinstance(tx, dict) and "amount" in tx:
                src_data = tx.get("source")
                src = None
                if isinstance(src_data, dict):
                    src = SourceEvidence(
                        document=str(src_data.get("document", "credit_card_statement.pdf")),
                        page=src_data.get("page"),
                        evidence=str(src_data.get("evidence", "")),
                    )
                try:
                    credit_card_transactions.append(TransactionRecord(
                        date=tx.get("date"),
                        description=str(tx.get("description", "")),
                        amount=float(tx.get("amount", 0.0)),
                        transaction_type=str(tx.get("transaction_type", "DEBIT")).upper(),
                        balance=float(tx.get("balance")) if tx.get("balance") is not None else None,
                        category=str(tx.get("category")).upper() if tx.get("category") else None,
                        source=src,
                    ))
                except (ValueError, TypeError):
                    pass

    return LoanApplication(
        application_id=app_id,
        applicant=applicant,
        income=income,
        obligations=obligations,
        loan_request=loan_request,
        credit=credit,
        assets_liabilities=assets_liabilities,
        documentation=documentation,
        bank_transactions=bank_transactions,
        credit_card_transactions=credit_card_transactions,
    )


class LoanDocumentExtractor:
    """Extracts raw facts from loan documents using an LLM with strict evidence requirements."""

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        model_name: str = DEFAULT_MODEL,
        template_manager: Optional[TemplateManager] = None,
    ):
        self.model_name = model_name
        self.provider = provider or initialize_llm_provider(model_name)
        self.template_manager = template_manager or TemplateManager()

    def extract_from_documents(
        self,
        application_id: str,
        documents: List[Dict[str, Any]],
    ) -> LoanApplication:
        """Extract structured facts from a list of document dicts.
        
        Each document dict should have:
            - 'name': str (e.g. 'salary_slip.pdf')
            - 'content': str (text or markdown representation)
            - 'page': optional int
        """
        prompt = self.template_manager.render_template(
            "loan_extraction",
            application_id=application_id,
            documents=documents,
        )
        if not prompt:
            raise ValueError("Failed to render 'loan_extraction' Jinja template.")

        messages = [
            {"role": "system", "content": "You are a precise, factual loan document extraction system."},
            {"role": "user", "content": prompt},
        ]

        logger.info(f"Extracting factual data for application {application_id} using {self.model_name}...")
        response = self.provider.chat(
            model=self.model_name,
            messages=messages,
            options=MODEL_PARAMETERS,
        )

        raw_content = response["message"]["content"]
        loan_app = parse_extraction_json(raw_content, application_id=application_id)
        loan_app.raw_document_names = [d.get("name", "unnamed") for d in documents]
        return loan_app
