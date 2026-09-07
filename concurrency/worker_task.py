"""Pure, stateless task executor for parallel processing of loan applications.

Designed to be safely executed by both ProcessPoolExecutor and ThreadPoolExecutor
with zero shared state and full picklability.
"""

import os
import time
from typing import Dict, Any, Optional

from pdf_loader import (
    load_pdf_documents_from_directory,
    parse_statement_transactions,
    extract_application_from_pdf_text,
)
from validate import LoanValidator
from features import FinancialFeatureEngine
from eligibility import EligibilityEngine, load_product_config
from scoring import DeterministicScoringEngine


def execute_application_task(
    folder_path: str,
    application_id: str,
    product_config_path: str = "loan_products/personal_loan_v1.json",
    use_llm: bool = False,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Stateless worker execution on a single application folder."""
    t_start = time.perf_counter()

    # 1. Document Loading
    pdf_docs = load_pdf_documents_from_directory(folder_path)
    if not pdf_docs:
        raise ValueError(f"No PDF documents found in {folder_path}")

    # 2. Extraction
    if use_llm and model_name:
        from extract import LoanDocumentExtractor
        extractor = LoanDocumentExtractor(model_name=model_name)
        try:
            app = extractor.extract_from_documents(application_id, pdf_docs)
        except Exception:
            app = extract_application_from_pdf_text(application_id, pdf_docs)
    else:
        app = extract_application_from_pdf_text(application_id, pdf_docs)

    # 3. Transaction Parsing
    all_bank_txs = list(app.bank_transactions)
    all_cc_txs = list(app.credit_card_transactions)
    for doc in pdf_docs:
        d_lower = doc["name"].lower()
        if "bank_statement" in d_lower:
            txs = parse_statement_transactions(doc["content"], doc["name"], doc.get("page", 1))
            if txs and len(txs) > len(all_bank_txs):
                all_bank_txs = txs
        elif "credit_card" in d_lower:
            txs = parse_statement_transactions(doc["content"], doc["name"], doc.get("page", 1))
            if txs and len(txs) > len(all_cc_txs):
                all_cc_txs = txs

    app.bank_transactions = all_bank_txs
    app.credit_card_transactions = all_cc_txs

    # 4. Deterministic Processing: Validation, Features, Eligibility, Scoring
    product_config = load_product_config(product_config_path)
    validator = LoanValidator()
    feature_engine = FinancialFeatureEngine()
    eligibility_engine = EligibilityEngine(product_config)
    scoring_engine = DeterministicScoringEngine(product_config)

    val_res = validator.validate(app)
    feat_res = feature_engine.calculate_features(app)
    elig_res = eligibility_engine.evaluate(app, feat_res, val_res)
    score_res = scoring_engine.score(app, feat_res)

    duration = time.perf_counter() - t_start
    real_app_id = app.application_id

    return {
        "folder_id": application_id,
        "application_id": real_app_id,
        "duration": round(duration, 4),
        "document_count": len(pdf_docs),
        "application": app.model_dump(),
        "validation": val_res.model_dump(),
        "features": feat_res.model_dump(),
        "eligibility": elig_res.model_dump(),
        "scoring": score_res.model_dump(),
    }
