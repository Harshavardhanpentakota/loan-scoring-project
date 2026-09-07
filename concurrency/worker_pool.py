"""Worker pool with bounded concurrency, queue backpressure, LLM throttling, and failure isolation."""

import time
import queue
import logging
import threading
from typing import List, Dict, Any, Optional, Callable

from concurrency.models import WorkItem, WorkItemStatus, Batch
from concurrency.result_store import ResultStore
from pdf_loader import load_pdf_documents_from_directory, parse_statement_transactions, extract_application_from_pdf_text
from models import LoanApplication
from extract import LoanDocumentExtractor

import concurrent.futures
from concurrency.worker_task import execute_application_task

logger = logging.getLogger(__name__)


class WorkerPool:
    """Bounded worker pool processing applications from a thread-safe queue."""

    def __init__(
        self,
        num_workers: int = 4,
        max_queue_size: int = 50,
        max_llm_concurrency: int = 4,
        result_store: Optional[ResultStore] = None,
        use_llm_extract: bool = False,
        extractor: Optional[LoanDocumentExtractor] = None,
        pipeline: Optional[Any] = None,
        backend: str = "process",
        on_item_completed: Optional[Callable[[WorkItem], None]] = None,
    ):
        self.num_workers = max(1, num_workers)
        self.queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self.result_store = result_store or ResultStore()
        self.use_llm_extract = use_llm_extract
        self.extractor = extractor
        self.pipeline = pipeline
        self.backend = backend
        self.on_item_completed = on_item_completed

        # Multi-process executor for CPU-bound multi-core extraction
        self._executor = None
        if self.backend == "process":
            self._executor = concurrent.futures.ProcessPoolExecutor(max_workers=self.num_workers)

        # Dedicated concurrency limiter for LLM calls (prevents rate limit spikes and connection storms)
        self.llm_semaphore = threading.BoundedSemaphore(value=max(1, max_llm_concurrency))

        self.workers: List[threading.Thread] = []
        self._shutdown_event = threading.Event()
        self._total_enqueued = 0
        self._completed_count = 0
        self._failed_count = 0
        self._stats_lock = threading.Lock()

    def start(self):
        """Start worker threads."""
        self._shutdown_event.clear()
        self.workers = []
        for i in range(self.num_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"LoanWorker-{i+1:02d}",
                daemon=True,
            )
            t.start()
            self.workers.append(t)
        logger.info(f"🚀 WorkerPool started with {self.num_workers} workers.")

    def submit_item(self, item: WorkItem):
        """Enqueue a work item with backpressure (blocks if queue is full)."""
        with self._stats_lock:
            self._total_enqueued += 1
        self.queue.put(item)  # Blocks when max_queue_size is reached (Backpressure!)

    def submit_batch(self, batch: Batch):
        """Enqueue all items in a batch."""
        for item in batch.items:
            self.submit_item(item)

    def wait_completion(self):
        """Wait until all enqueued items are processed by workers."""
        self.queue.join()

    def shutdown(self):
        """Stop all workers gracefully."""
        self._shutdown_event.set()
        # Put poison pills to awaken idle workers
        for _ in range(self.num_workers):
            try:
                self.queue.put_nowait(None)
            except queue.Full:
                pass
        for t in self.workers:
            t.join(timeout=2.0)
        if self._executor:
            self._executor.shutdown(wait=True)
        logger.info("🛑 WorkerPool shut down.")

    def _worker_loop(self):
        """Main loop for an individual worker."""
        while not self._shutdown_event.is_set():
            try:
                item: Optional[WorkItem] = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if item is None:
                # Poison pill received
                self.queue.task_done()
                break

            try:
                self._process_work_item(item)
            except Exception as e:
                logger.error(f"Unhandled error in worker on {item.application_id}: {e}")
            finally:
                self.queue.task_done()

    def _process_work_item(self, item: WorkItem):
        """Execute processing on a single work item with retry and failure isolation."""
        item.status = WorkItemStatus.RUNNING
        t_start = time.perf_counter()

        # Check if already completed (e.g. from checkpoint)
        if self.result_store.is_completed(item.application_id):
            item.status = WorkItemStatus.COMPLETED
            item.duration = 0.0
            with self._stats_lock:
                self._completed_count += 1
            if self.on_item_completed:
                self.on_item_completed(item)
            return

        success = False
        last_error = ""

        while item.retries <= item.max_retries and not success:
            try:
                result_data = self._execute_application_pipeline(item)
                item.status = WorkItemStatus.COMPLETED
                item.completed_at = time.time()
                item.duration = time.perf_counter() - t_start
                self.result_store.record_success(item.application_id, result_data)
                with self._stats_lock:
                    self._completed_count += 1
                success = True
            except Exception as e:
                item.retries += 1
                last_error = str(e)
                if item.retries <= item.max_retries:
                    item.status = WorkItemStatus.RETRYING
                    # Exponential backoff on retries (e.g., transient network/LLM error)
                    backoff = min(0.5 * (2 ** (item.retries - 1)), 5.0)
                    time.sleep(backoff)
                else:
                    item.status = WorkItemStatus.FAILED
                    item.error = last_error
                    item.duration = time.perf_counter() - t_start
                    self.result_store.record_failure(item.application_id, last_error)
                    with self._stats_lock:
                        self._failed_count += 1
                    logger.warning(f"❌ Application {item.application_id} failed after {item.max_retries} retries: {last_error}")

        if self.on_item_completed:
            self.on_item_completed(item)

    def _execute_application_pipeline(self, item: WorkItem) -> Dict[str, Any]:
        """Execute the loan underwriting pipeline for a single application folder."""
        if self.backend == "process" and self._executor is not None:
            model_name = self.extractor.model_name if (self.extractor and self.use_llm_extract) else None
            p_cfg_path = getattr(self.pipeline, "product_config_path", "loan_products/personal_loan_v1.json")
            future = self._executor.submit(
                execute_application_task,
                item.folder_path,
                item.application_id,
                p_cfg_path,
                self.use_llm_extract,
                model_name,
            )
            return future.result()
        # 1. Document Loading
        pdf_docs = load_pdf_documents_from_directory(item.folder_path)
        if not pdf_docs:
            raise ValueError(f"No PDF documents found in {item.folder_path}")

        app: Optional[LoanApplication] = None

        # 2. Stage 1: Extraction (with bounded LLM semaphore if enabled)
        if self.use_llm_extract and self.extractor:
            with self.llm_semaphore:
                try:
                    app = self.extractor.extract_from_documents(item.application_id, pdf_docs)
                except Exception as e:
                    logger.warning(f"LLM extraction error for {item.application_id}: {e}. Falling back to text docket parser.")
                    app = extract_application_from_pdf_text(item.application_id, pdf_docs)
        else:
            app = extract_application_from_pdf_text(item.application_id, pdf_docs)

        # 3. Stage 2: Transaction Parsing
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

        # 4. Stage 3 & 4: Validation, Feature Derivation, Eligibility, Mathematical Scoring
        if self.pipeline:
            eval_res = self.pipeline.process_application(app)
        else:
            from validate import LoanValidator
            from features import FinancialFeatureEngine
            from eligibility import EligibilityEngine, load_product_config
            from scoring import DeterministicScoringEngine

            p_cfg = load_product_config("loan_products/personal_loan_v1.json")
            val_res = LoanValidator().validate(app)
            feat_res = FinancialFeatureEngine().calculate_features(app)
            elig_res = EligibilityEngine(p_cfg).evaluate(app, feat_res, val_res)
            score_res = DeterministicScoringEngine(p_cfg).score(app, feat_res)
            eval_res = {
                "application": app,
                "validation": val_res,
                "features": feat_res,
                "eligibility": elig_res,
                "scoring": score_res,
            }

        return {
            "application_id": item.application_id,
            "application": eval_res["application"].model_dump(),
            "validation": eval_res["validation"].model_dump(),
            "features": eval_res["features"].model_dump(),
            "eligibility": eval_res["eligibility"].model_dump(),
            "scoring": eval_res["scoring"].model_dump(),
            "document_count": len(pdf_docs),
        }
