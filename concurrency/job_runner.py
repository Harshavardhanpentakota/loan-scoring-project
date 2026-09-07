"""Job Runner Orchestrator for Scalable Parallel Loan Processing."""

import os
import sys
import time
import uuid
import logging
import resource
from typing import List, Dict, Any, Optional, Set

from concurrency.models import WorkItem, WorkItemStatus, Batch, JobMetrics
from concurrency.batching import distribute_workload, estimate_application_workload
from concurrency.result_store import ResultStore
from concurrency.worker_pool import WorkerPool
from ranking import DeterministicRankingEngine
from models import LoanApplication, ScoringResult, EligibilityResult, DerivedFeatures, ValidationResult

logger = logging.getLogger(__name__)


def get_peak_memory_mb() -> float:
    """Return peak memory usage in MB."""
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return usage / (1024 * 1024)
    return usage / 1024


def percentile(data: List[float], p: float) -> float:
    """Calculate percentile from data array."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_data) else f
    d = k - f
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * d


class JobRunner:
    """Orchestrates job discovery, workload distribution, bounded parallel worker execution,

    completion barrier, ranking, and observability metrics.
    """

    def __init__(
        self,
        num_workers: int = 4,
        max_queue_size: int = 100,
        max_llm_concurrency: int = 4,
        batch_size: Optional[int] = 20,
        checkpoint_path: Optional[str] = None,
        use_llm_extract: bool = False,
        extractor: Optional[Any] = None,
        pipeline: Optional[Any] = None,
        backend: str = "process",
        verbose_progress: bool = False,
    ):
        self.num_workers = max(1, num_workers)
        self.backend = backend
        self.max_queue_size = max(10, max_queue_size)
        self.max_llm_concurrency = max_llm_concurrency
        self.batch_size = batch_size
        self.checkpoint_path = checkpoint_path
        self.use_llm_extract = use_llm_extract
        self.extractor = extractor
        self.pipeline = pipeline
        self.verbose_progress = verbose_progress

        self.result_store = ResultStore(checkpoint_path=checkpoint_path)
        self.ranking_engine = DeterministicRankingEngine()
        self.item_latencies: List[float] = []

    def discover_applications(self, input_dir: str) -> List[WorkItem]:
        """Discover application folders or root PDFs and create WorkItems with estimated workloads."""
        if not os.path.exists(input_dir):
            raise FileNotFoundError(f"Input directory not found: {input_dir}")

        items: List[WorkItem] = []
        pdf_in_root = [f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")]

        if pdf_in_root:
            app_id = os.path.basename(input_dir.rstrip("/"))
            items.append(WorkItem(
                application_id=app_id,
                folder_path=input_dir,
                estimated_workload=len(pdf_in_root),
            ))
        else:
            subdirs = sorted([
                sub for sub in os.listdir(input_dir)
                if os.path.isdir(os.path.join(input_dir, sub))
            ])
            for sub in subdirs:
                folder = os.path.join(input_dir, sub)
                workload = estimate_application_workload(folder)
                items.append(WorkItem(
                    application_id=sub,
                    folder_path=folder,
                    estimated_workload=workload,
                ))

        return items

    def run_job(self, input_dir: str, job_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute end-to-end parallel job across discovered applications."""
        job_id = job_id or f"JOB_{uuid.uuid4().hex[:8]}"
        t_start = time.perf_counter()
        mem_start = get_peak_memory_mb()

        # 1. Discover Workload
        all_items = self.discover_applications(input_dir)
        total_apps = len(all_items)
        if total_apps == 0:
            logger.warning("No applications discovered for processing.")
            return {"job_id": job_id, "metrics": JobMetrics(job_id=job_id).model_dump()}

        # 2. Check Resumability / Checkpoint
        completed_ids = self.result_store.get_completed_ids()
        items_to_process = [it for it in all_items if it.application_id not in completed_ids]
        skipped_count = total_apps - len(items_to_process)

        if skipped_count > 0:
            logger.info(f"🔄 Resuming job {job_id}: {skipped_count}/{total_apps} applications already completed in checkpoint.")

        # 3. Workload-aware Batch Distribution
        target_batches = max(1, self.num_workers * 2)
        batches = distribute_workload(items_to_process, target_batches=target_batches, max_batch_size=self.batch_size)

        # 4. Initialize Worker Pool
        self.item_latencies = []

        def on_item_finished(item: WorkItem):
            if item.duration > 0:
                self.item_latencies.append(item.duration)

        pool = WorkerPool(
            num_workers=self.num_workers,
            max_queue_size=self.max_queue_size,
            max_llm_concurrency=self.max_llm_concurrency,
            result_store=self.result_store,
            use_llm_extract=self.use_llm_extract,
            extractor=self.extractor,
            pipeline=self.pipeline,
            backend=self.backend,
            on_item_completed=on_item_finished,
        )

        pool.start()

        # 5. Enqueue Work Batches under Backpressure
        total_docs = sum(it.estimated_workload for it in all_items)
        for batch in batches:
            for item in batch.items:
                pool.submit_item(item)

        # 6. Completion Barrier: Wait for all enqueued work to finish
        pool.wait_completion()
        pool.shutdown()

        t_processing_end = time.perf_counter()
        processing_duration = t_processing_end - t_start

        # 7. Collect Results from ResultStore for Deterministic Ranking Barrier
        raw_results = self.result_store.get_all_completed_results()
        failed_records = self.result_store.get_all_failed_records()

        # Hydrate Pydantic objects for ranking
        apps: List[LoanApplication] = []
        scores_map: Dict[str, ScoringResult] = {}
        elig_map: Dict[str, EligibilityResult] = {}
        feat_map: Dict[str, DerivedFeatures] = {}
        val_map: Dict[str, ValidationResult] = {}

        folder_to_appid = {}
        for folder_id, data in raw_results.items():
            try:
                app_obj = LoanApplication.model_validate(data["application"])
                app_id = app_obj.application_id
                folder_to_appid[folder_id] = app_id
                apps.append(app_obj)

                sc_obj = ScoringResult.model_validate(data["scoring"])
                el_obj = EligibilityResult.model_validate(data["eligibility"])
                ft_obj = DerivedFeatures.model_validate(data["features"])
                vl_obj = ValidationResult.model_validate(data["validation"])

                scores_map[app_id] = sc_obj
                elig_map[app_id] = el_obj
                feat_map[app_id] = ft_obj
                val_map[app_id] = vl_obj

                scores_map[folder_id] = sc_obj
                elig_map[folder_id] = el_obj
                feat_map[folder_id] = ft_obj
                val_map[folder_id] = vl_obj
            except Exception as e:
                logger.error(f"Error parsing completed record for {folder_id}: {e}")

        # 8. Deterministic Ranking
        t_rank_start = time.perf_counter()
        qualified, review, ineligible = self.ranking_engine.rank(
            applications=apps,
            scores=scores_map,
            eligibilities=elig_map,
            features=feat_map,
            validations=val_map,
        )
        t_rank_end = time.perf_counter()
        ranking_duration = t_rank_end - t_rank_start

        t_total_end = time.perf_counter()
        total_duration = t_total_end - t_start
        mem_end = get_peak_memory_mb()

        # 9. Compute Metrics
        successful_count = len(apps)
        failed_count = len(failed_records)
        apps_per_sec = round(total_apps / max(total_duration, 0.0001), 2)
        docs_per_sec = round(total_docs / max(total_duration, 0.0001), 2)

        metrics = JobMetrics(
            job_id=job_id,
            total_applications=total_apps,
            completed=successful_count,
            failed=failed_count,
            retried=sum(it.retries for it in all_items),
            pending=0,
            total_duration=round(total_duration, 4),
            throughput_apps_per_sec=apps_per_sec,
            throughput_docs_per_sec=docs_per_sec,
            avg_latency=round(total_duration / max(total_apps, 1), 4),
            p50_latency=round(percentile(self.item_latencies, 0.50), 4),
            p95_latency=round(percentile(self.item_latencies, 0.95), 4),
            llm_calls=0,
            llm_failures=0,
            peak_memory_mb=round(mem_end, 2),
        )

        # Optional LLM Summaries / Explanations via pipeline
        summaries = {}
        if self.pipeline and (self.pipeline.enable_evaluation_summary or self.pipeline.enable_explanation):
            summaries = self.pipeline.attach_summaries_and_explanations(
                applications=apps,
                qualified=qualified,
                review=review,
                ineligible=ineligible,
                scores_map=scores_map,
                elig_map=elig_map,
                feat_map=feat_map,
            )
        else:
            for group in (qualified, review, ineligible):
                for applicant in group:
                    aid = applicant.application_id
                    if aid in scores_map:
                        applicant.criticality = scores_map[aid].criticality

        return {
            "job_id": job_id,
            "metrics": metrics.model_dump(),
            "model_version": self.pipeline.product_config.get("model_version") if self.pipeline else "personal_loan_v1",
            "qualified_ranked": qualified,
            "manual_review_queue": review,
            "ineligible_queue": ineligible,
            "evaluation_summaries": {aid: s.model_dump() for aid, s in summaries.items()},
            "failed_applications": failed_records,
            "audit_traces": {
                app_id: {
                    "features": [t.model_dump() for t in feat_map[app_id].traces],
                    "scoring": scores_map[app_id].model_dump(),
                    "eligibility": elig_map[app_id].model_dump(),
                    "validation": val_map[app_id].model_dump(),
                }
                for app_id in scores_map
            },
            "ranking_duration_sec": round(ranking_duration, 6),
            "processing_duration_sec": round(processing_duration, 4),
        }
