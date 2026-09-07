"""Thread-safe Result Store with Checkpointing, Resumability, and Completion Barrier."""

import os
import json
import threading
from typing import Dict, Any, List, Set, Optional


class ResultStore:
    """Thread-safe storage for processed application results with checkpointing support."""

    def __init__(self, checkpoint_path: Optional[str] = None):
        self.checkpoint_path = checkpoint_path
        self._lock = threading.Lock()
        self._completed_results: Dict[str, Dict[str, Any]] = {}
        self._failed_records: Dict[str, str] = {}
        self._completed_ids: Set[str] = set()

        if self.checkpoint_path and os.path.exists(self.checkpoint_path):
            self.load_checkpoint()

    def load_checkpoint(self):
        """Load previously completed results from checkpoint file."""
        with self._lock:
            try:
                with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            app_id = record.get("application_id")
                            if app_id:
                                self._completed_results[app_id] = record
                                self._completed_ids.add(app_id)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                print(f"⚠️ Error reading checkpoint file {self.checkpoint_path}: {e}")

    def is_completed(self, application_id: str) -> bool:
        """Check if an application has already been processed."""
        with self._lock:
            return application_id in self._completed_ids

    def get_completed_ids(self) -> Set[str]:
        """Return a copy of all completed application IDs."""
        with self._lock:
            return set(self._completed_ids)

    def record_success(self, application_id: str, result: Dict[str, Any]):
        """Record a successful application result and append to checkpoint."""
        with self._lock:
            self._completed_results[application_id] = result
            self._completed_ids.add(application_id)

            if self.checkpoint_path:
                try:
                    with open(self.checkpoint_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(result) + "\n")
                except Exception as e:
                    print(f"⚠️ Error appending to checkpoint {self.checkpoint_path}: {e}")

    def record_failure(self, application_id: str, error_message: str):
        """Record a failed application."""
        with self._lock:
            self._failed_records[application_id] = error_message

    def get_completed_count(self) -> int:
        with self._lock:
            return len(self._completed_results)

    def get_failed_count(self) -> int:
        with self._lock:
            return len(self._failed_records)

    def get_all_completed_results(self) -> Dict[str, Dict[str, Any]]:
        """Retrieve all completed results for ranking barrier."""
        with self._lock:
            return dict(self._completed_results)

    def get_all_failed_records(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._failed_records)
