"""Data models and state definitions for concurrent execution engine."""

import time
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class WorkItemStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class WorkItem(BaseModel):
    """Represents a single application folder to be processed."""
    application_id: str
    folder_path: str
    estimated_workload: int = 1  # Number of documents/pages
    status: WorkItemStatus = WorkItemStatus.PENDING
    retries: int = 0
    max_retries: int = 3
    error: Optional[str] = None
    duration: float = 0.0
    created_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None


class Batch(BaseModel):
    """Represents a group of work items allocated together."""
    batch_id: str
    items: List[WorkItem] = Field(default_factory=list)
    total_workload: int = 0

    def add_item(self, item: WorkItem):
        self.items.append(item)
        self.total_workload += item.estimated_workload


class JobMetrics(BaseModel):
    """Tracks end-to-end execution statistics and latencies."""
    job_id: str
    total_applications: int = 0
    completed: int = 0
    failed: int = 0
    retried: int = 0
    pending: int = 0
    total_duration: float = 0.0
    throughput_apps_per_sec: float = 0.0
    throughput_docs_per_sec: float = 0.0
    avg_latency: float = 0.0
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    llm_calls: int = 0
    llm_failures: int = 0
    peak_memory_mb: float = 0.0
