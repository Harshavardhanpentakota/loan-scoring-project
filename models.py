"""Data models and provider protocols for the Loan Ranking Agent.

Strict separation:
- Models capture factual extractions with attached source evidence.
- Missing values remain None (never silently coerced to 0).
- Downstream deterministic feature traces, component scores, and ranking results
  are fully typed.
"""

from typing import List, Optional, Dict, Any, TypeVar, Generic, Protocol, runtime_checkable
from pydantic import BaseModel, Field


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        options: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send a chat request to the LLM provider."""
        ...


# ---------------------------------------------------------
# Evidence & Extracted Fact Primitives
# ---------------------------------------------------------

class SourceEvidence(BaseModel):
    """Source reference and exact text citation supporting an extracted field."""

    document: str = Field(description="Filename or identifier of the source document")
    page: Optional[int] = Field(default=None, description="Page number where evidence appears")
    evidence: str = Field(description="Exact snippet or verbatim quotation from document")


T = TypeVar("T")


class ExtractedField(BaseModel, Generic[T]):
    """Container for an extracted raw value with explicit provenance.
    
    If the value was not present in the document, value is None.
    Never silently substituted with zero or defaults.
    """

    value: Optional[T] = Field(default=None, description="Raw extracted value, or None if absent")
    currency: Optional[str] = Field(default=None, description="Currency code (e.g. INR, USD) if applicable")
    source: Optional[SourceEvidence] = Field(default=None, description="Documentary evidence supporting this value")


# ---------------------------------------------------------
# Structured Loan Application Sections (Raw Extracted Facts)
# ---------------------------------------------------------

class ApplicantInfo(BaseModel):
    """Factual information about the applicant extracted from application/identity docs."""

    applicant_id: Optional[str] = None
    applicant_name: Optional[ExtractedField[str]] = None
    applicant_type: Optional[ExtractedField[str]] = None  # e.g., "salaried", "self_employed"
    age: Optional[ExtractedField[int]] = None
    employment_type: Optional[ExtractedField[str]] = None  # e.g. "permanent", "contract", "business_owner"
    employer_or_business_name: Optional[ExtractedField[str]] = None
    employment_start_date: Optional[ExtractedField[str]] = None
    employment_duration_years: Optional[ExtractedField[float]] = None


class IncomeInfo(BaseModel):
    """Factual income values explicitly present in documents."""

    monthly_gross_income: Optional[ExtractedField[float]] = None
    monthly_net_income: Optional[ExtractedField[float]] = None
    annual_income: Optional[ExtractedField[float]] = None
    annual_revenue: Optional[ExtractedField[float]] = None  # For business / self-employed applicants
    income_sources: Optional[ExtractedField[List[str]]] = None
    income_period: Optional[ExtractedField[str]] = None
    income_frequency: Optional[ExtractedField[str]] = None  # e.g. "monthly", "annual"


class ExistingObligations(BaseModel):
    """Factual debt obligations explicitly reported in loan statements / credit reports."""

    existing_monthly_emi: Optional[ExtractedField[float]] = None
    existing_loan_count: Optional[ExtractedField[int]] = None
    outstanding_debt: Optional[ExtractedField[float]] = None
    overdue_amount: Optional[ExtractedField[float]] = None
    missed_payments: Optional[ExtractedField[int]] = None
    repayment_history: Optional[ExtractedField[str]] = None  # e.g. "0 missed in 24 months"


class LoanRequest(BaseModel):
    """Loan requirement stated by the applicant."""

    requested_loan_amount: Optional[ExtractedField[float]] = None
    tenure_months: Optional[ExtractedField[int]] = None
    loan_type: Optional[ExtractedField[str]] = None  # e.g. "personal_loan", "business_loan"
    loan_purpose: Optional[ExtractedField[str]] = None


class CreditInfo(BaseModel):
    """Factual credit bureau metrics explicitly stated in credit reports."""

    credit_score: Optional[ExtractedField[int]] = None
    credit_utilization_ratio: Optional[ExtractedField[float]] = None  # e.g. 0.28 for 28%
    active_credit_accounts: Optional[ExtractedField[int]] = None
    delinquency_information: Optional[ExtractedField[str]] = None
    credit_card_limit: Optional[ExtractedField[float]] = None
    credit_card_total_balance: Optional[ExtractedField[float]] = None
    credit_card_min_payment_due: Optional[ExtractedField[float]] = None


class AssetsLiabilities(BaseModel):
    """Factual asset and liability figures explicitly reported."""

    assets: Optional[ExtractedField[float]] = None
    liabilities: Optional[ExtractedField[float]] = None
    savings: Optional[ExtractedField[float]] = None


class DocumentationStatus(BaseModel):
    """Availability and verification status of required documents."""

    identity_verified: Optional[ExtractedField[bool]] = None
    income_document_available: Optional[ExtractedField[bool]] = None
    bank_statement_available: Optional[ExtractedField[bool]] = None
    tax_document_available: Optional[ExtractedField[bool]] = None
    loan_statement_available: Optional[ExtractedField[bool]] = None
    credit_card_statement_available: Optional[ExtractedField[bool]] = None


class TransactionRecord(BaseModel):
    """Raw transaction extracted from bank statement or credit card statement."""

    date: Optional[str] = None
    description: str
    amount: float
    transaction_type: str = "DEBIT"  # "CREDIT" or "DEBIT"
    balance: Optional[float] = None
    category: Optional[str] = None  # "SALARY", "EMI", "UTILITY", "CARD_PAYMENT", "TRANSFER", etc.
    source: Optional[SourceEvidence] = None


class LoanApplication(BaseModel):
    """Top-level container for all raw extracted facts belonging to a loan application."""

    application_id: str
    applicant: ApplicantInfo = Field(default_factory=ApplicantInfo)
    income: IncomeInfo = Field(default_factory=IncomeInfo)
    obligations: ExistingObligations = Field(default_factory=ExistingObligations)
    loan_request: LoanRequest = Field(default_factory=LoanRequest)
    credit: CreditInfo = Field(default_factory=CreditInfo)
    assets_liabilities: AssetsLiabilities = Field(default_factory=AssetsLiabilities)
    documentation: DocumentationStatus = Field(default_factory=DocumentationStatus)
    bank_transactions: List[TransactionRecord] = Field(default_factory=list)
    credit_card_transactions: List[TransactionRecord] = Field(default_factory=list)
    raw_document_names: List[str] = Field(default_factory=list)


# ---------------------------------------------------------
# Validation & Consistency Results
# ---------------------------------------------------------

class ValidationIssue(BaseModel):
    field: str
    issue_type: str  # e.g. "DATA_INCONSISTENCY", "OUT_OF_RANGE", "MISSING_REQUIRED_FIELD", "MISSING_EVIDENCE"
    severity: str  # "ERROR", "WARNING"
    message: str


class ValidationResult(BaseModel):
    status: str  # "VALID", "DATA_INCONSISTENCY", "INSUFFICIENT_DATA"
    is_valid: bool
    issues: List[ValidationIssue] = Field(default_factory=list)


# ---------------------------------------------------------
# Deterministic Financial Features & Traces
# ---------------------------------------------------------

class FeatureTrace(BaseModel):
    feature: str
    formula: str
    inputs: Dict[str, Any]
    result: Optional[float] = None
    units: Optional[str] = None
    notes: Optional[str] = None


class DerivedFeatures(BaseModel):
    application_id: str
    dti: Optional[float] = None  # Debt to Income
    emi_ratio: Optional[float] = None  # Total EMI to Monthly Net Income
    lti: Optional[float] = None  # Loan to Income
    debt_to_revenue: Optional[float] = None  # Outstanding Debt to Annual Revenue
    credit_card_utilization: Optional[float] = None  # CC Balance / CC Limit
    total_bank_credits_6m: Optional[float] = None  # Sum of all credit transactions over 6 months
    total_bank_debits_6m: Optional[float] = None  # Sum of all debit transactions over 6 months
    derived_monthly_salary_from_bank: Optional[float] = None  # Verified average payroll credits
    derived_monthly_emi_from_bank: Optional[float] = None  # Verified recurring loan auto-debits
    total_credit_card_spends_6m: Optional[float] = None  # Sum of credit card purchase transactions
    income_stability_index: Optional[float] = None  # 0 to 100 score
    documentation_completeness: float = 0.0  # 0 to 1.0 (or percentage)
    traces: List[FeatureTrace] = Field(default_factory=list)


# ---------------------------------------------------------
# Eligibility & Scoring Data Models
# ---------------------------------------------------------

class EligibilityResult(BaseModel):
    application_id: str
    status: str  # "ELIGIBLE", "INELIGIBLE", "MANUAL_REVIEW"
    passed_rules: List[str] = Field(default_factory=list)
    failed_rules: List[str] = Field(default_factory=list)
    manual_review_reasons: List[str] = Field(default_factory=list)


class ComponentScore(BaseModel):
    raw_score: float  # Bounded, typically 0 - 100
    weight: float  # e.g. 0.25
    contribution: float  # raw_score * weight
    notes: Optional[str] = None


class CriticalityPoint(BaseModel):
    criticality: str  # "HIGH", "MED", "LOW"
    point: str
    evidence: Optional[str] = None


class ApplicationEvaluationSummary(BaseModel):
    application_id: str
    overall_score: float
    overall_criticality: str  # "LOW", "MED", "HIGH"
    executive_verdict: Optional[str] = None
    pros: List[CriticalityPoint] = Field(default_factory=list)
    cons: List[CriticalityPoint] = Field(default_factory=list)


class ScoringResult(BaseModel):
    application_id: str
    scoring_model: str  # e.g. "personal_loan_v1"
    timestamp: str
    components: Dict[str, ComponentScore]
    final_score: float  # Sum of contributions
    criticality: str = "MED"  # "LOW", "MED", "HIGH"
    calculation_trace: List[Dict[str, Any]]


# ---------------------------------------------------------
# Ranking & Explanation Result Models
# ---------------------------------------------------------

class RankedApplicant(BaseModel):
    rank: int
    application_id: str
    applicant_name: Optional[str] = None
    applicant_type: Optional[str] = None
    final_score: float
    criticality: Optional[str] = None
    eligibility_status: str
    scoring_model: str
    component_scores: Dict[str, float]
    dti: Optional[float] = None
    credit_score: Optional[int] = None
    monthly_income: Optional[float] = None
    explanation: Optional[List[str]] = None
    explanation_status: Optional[str] = None  # "VALID", "INVALID", "SKIPPED"
    validation_status: Optional[str] = None
    evaluation_summary: Optional[ApplicationEvaluationSummary] = None



# ---------------------------------------------------------
# Provider Implementation
# ---------------------------------------------------------

class OpenAICompatibleProvider:
    """Generic OpenAI-chat-compatible LLM provider.

    Works for Ollama (/v1), Gemini (/v1beta/openai), OpenAI, Groq, OpenRouter,
    DeepSeek, LM Studio, vLLM, etc. via a configurable base_url.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        structured_output: str = "json_schema",
        extra_body: Optional[Dict[str, Any]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.structured_output = structured_output
        self.extra_body = extra_body or {}

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        options: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        import requests
        import time
        import random

        options = options or {}
        body: Dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if "temperature" in options:
            body["temperature"] = options["temperature"]
        if "top_p" in options:
            body["top_p"] = options["top_p"]

        if "format" in kwargs and self.structured_output != "none":
            schema = kwargs["format"]
            if self.structured_output == "json_schema":
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "response", "schema": schema},
                }
            elif self.structured_output == "json_object":
                body["response_format"] = {"type": "json_object"}

        body.update(self.extra_body)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url}/chat/completions"

        MAX_RETRIES = 5
        BASE_DELAY = 5.0
        MAX_DELAY = 60.0
        RETRYABLE_SERVER_ERRORS = {500, 502, 503, 504}
        for attempt in range(MAX_RETRIES):
            response = requests.post(url, json=body, headers=headers, timeout=300)

            if response.status_code == 429 and attempt < MAX_RETRIES - 1:
                retry_after = response.headers.get("Retry-After")
                exp_delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                delay = float(retry_after) if retry_after else exp_delay
                sleep_time = round(delay * random.uniform(0.8, 1.2), 2)
                time.sleep(sleep_time)
                continue

            if (
                response.status_code in RETRYABLE_SERVER_ERRORS
                and attempt < MAX_RETRIES - 1
            ):
                exp_delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                sleep_time = round(exp_delay * random.uniform(0.8, 1.2), 2)
                time.sleep(sleep_time)
                continue

            response.raise_for_status()
            data = response.json()
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                raise ValueError(f"Unexpected response shape from {url}: {data}")
            return {"message": {"role": "assistant", "content": content}}
