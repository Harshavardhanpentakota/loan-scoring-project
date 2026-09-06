"""Automated Test Runner for Loan Ranking Agent.

Runs all 4 independent test layers and end-to-end integration tests:
- Layer 1: Extraction & Ground Truth Tests
- Layer 2: Financial Feature Engine Tests
- Layer 3: Deterministic Scoring Tests
- Layer 4: Explanation Grounding Validation Tests
- Layer 5: End-to-End Pipeline Integration & Ranking Tests
"""

import sys
import os
import inspect
import importlib.util
import traceback
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


def load_module_from_file(file_path):
    module_name = os.path.splitext(os.path.basename(file_path))[0]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    test_dir = os.path.join(os.path.dirname(__file__), "tests")
    test_files = sorted([
        f for f in os.listdir(test_dir)
        if f.startswith("test_") and f.endswith(".py")
    ])

    total_run = 0
    total_passed = 0
    failures = []

    print("\n" + "=" * 80)
    print("  LOAN RANKING AGENT: 4-LAYER AUTOMATED TEST SUITE")
    print("=" * 80 + "\n")

    start_time = time.time()

    for tf in test_files:
        full_path = os.path.join(test_dir, tf)
        print(f"📦 Running test module: {tf}")
        try:
            mod = load_module_from_file(full_path)
        except Exception as e:
            print(f"  ❌ Failed to load {tf}: {e}")
            failures.append((tf, "module_load", str(e), traceback.format_exc()))
            continue

        test_funcs = [
            (name, func)
            for name, func in inspect.getmembers(mod, inspect.isfunction)
            if name.startswith("test_")
        ]

        for name, func in test_funcs:
            total_run += 1
            try:
                func()
                print(f"  ✅ {name}")
                total_passed += 1
            except AssertionError as ae:
                print(f"  ❌ {name} [ASSERTION FAILED]")
                failures.append((tf, name, str(ae), traceback.format_exc()))
            except Exception as ex:
                print(f"  💥 {name} [UNEXPECTED ERROR]")
                failures.append((tf, name, str(ex), traceback.format_exc()))

        print()

    elapsed = round(time.time() - start_time, 3)

    print("=" * 80)
    print(f"TEST SUMMARY: {total_passed}/{total_run} PASSED in {elapsed}s")
    if failures:
        print(f"🚨 {len(failures)} FAILURES DETECTED:")
        for file_name, test_name, err, tb in failures:
            print(f"\n--- Failure in {file_name} :: {test_name} ---")
            print(err)
            print(tb)
        print("=" * 80 + "\n")
        sys.exit(1)
    else:
        print("🎉 ALL TESTS PASSED! Strict determinism and invariants verified.")
        print("=" * 80 + "\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
