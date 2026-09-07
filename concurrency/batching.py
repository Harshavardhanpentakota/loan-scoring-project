"""Workload-aware batch distribution algorithm.

Distributes applications across batches/workers using a greedy load-balancing
strategy based on estimated application workload (e.g. document count).
"""

import os
import heapq
from typing import List, Optional
from concurrency.models import WorkItem, Batch


def estimate_application_workload(folder_path: str) -> int:
    """Estimate workload of an application folder based on PDF document count."""
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return 1
    try:
        pdf_count = sum(1 for f in os.listdir(folder_path) if f.lower().endswith(".pdf"))
        return max(pdf_count, 1)
    except Exception:
        return 1


def distribute_workload(
    items: List[WorkItem],
    target_batches: int,
    max_batch_size: Optional[int] = None,
) -> List[Batch]:
    """Distribute work items across batches using a greedy min-heap load-balancing algorithm.

    Algorithm:
    1. Filter non-empty items. If fewer items than target_batches, create at most len(items) batches.
    2. Sort items by workload descending (heaviest items first).
    3. Maintain a min-heap of (current_workload, batch_index, Batch).
    4. For each item:
       - Pop the batch with the lowest accumulated workload.
       - If max_batch_size is set and this batch is full, find the lowest workload non-full batch.
       - Append the item and update its total workload.
       - Push back into the min-heap.
    5. Discard any empty batches.
    """
    if not items:
        return []

    num_batches = max(1, min(target_batches, len(items)))

    # Initialize empty batches
    batches = [Batch(batch_id=f"batch_{i+1:03d}") for i in range(num_batches)]

    # Sort items by workload descending
    sorted_items = sorted(items, key=lambda it: it.estimated_workload, reverse=True)

    # Min-heap storing (total_workload, tie_breaker_id, batch_index)
    heap = [(0, i, i) for i in range(num_batches)]
    heapq.heapify(heap)

    for item in sorted_items:
        if max_batch_size is None:
            load, _, idx = heapq.heappop(heap)
            batches[idx].add_item(item)
            heapq.heappush(heap, (batches[idx].total_workload, idx, idx))
        else:
            # Need to respect max_batch_size
            temp_popped = []
            assigned = False
            while heap:
                load, _, idx = heapq.heappop(heap)
                if len(batches[idx].items) < max_batch_size:
                    batches[idx].add_item(item)
                    heapq.heappush(heap, (batches[idx].total_workload, idx, idx))
                    assigned = True
                    break
                else:
                    temp_popped.append((load, idx))

            # Put back any skipped full batches
            for pload, pidx in temp_popped:
                heapq.heappush(heap, (pload, pidx, pidx))

            # If all current batches are at max_batch_size, create a new batch
            if not assigned:
                new_idx = len(batches)
                new_batch = Batch(batch_id=f"batch_{new_idx+1:03d}")
                new_batch.add_item(item)
                batches.append(new_batch)
                heapq.heappush(heap, (new_batch.total_workload, new_idx, new_idx))

    # Return only non-empty batches
    return [b for b in batches if len(b.items) > 0]
