#!/usr/bin/env python3
"""
Run All Tests Script
Executes integration tests, performance benchmarks, and optionally load tests.
"""

import subprocess
import sys
import argparse
from pathlib import Path
import time
from datetime import datetime


def print_header(text: str):
    """Print formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")


def run_command(cmd: list, cwd: Path = None) -> tuple[int, str, str]:
    """Run command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out after 5 minutes"
    except Exception as e:
        return -1, "", str(e)


def run_integration_tests(backend_dir: Path) -> bool:
    """Run integration tests."""
    print_header("Running Integration Tests")
    
    test_file = backend_dir / "tests" / "test_sync_integration.py"
    cmd = [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"]
    exit_code, stdout, stderr = run_command(cmd, cwd=backend_dir)
    
    print(stdout)
    if stderr and exit_code != 0:
        print(stderr, file=sys.stderr)
    
    if exit_code == 0:
        print("\n✅ Integration tests PASSED")
        return True
    else:
        print("\n❌ Integration tests FAILED")
        return False


def run_performance_benchmarks(backend_dir: Path) -> bool:
    """Run performance benchmarks."""
    print_header("Running Performance Benchmarks")
    
    benchmark_script = backend_dir / "scripts" / "benchmark_sync.py"
    cmd = [sys.executable, str(benchmark_script)]
    exit_code, stdout, stderr = run_command(cmd, cwd=backend_dir)
    
    print(stdout)
    if stderr and exit_code != 0:
        print(stderr, file=sys.stderr)
    
    if exit_code == 0:
        print("\n✅ Performance benchmarks COMPLETED")
        return True
    else:
        print("\n❌ Performance benchmarks FAILED")
        return False


def run_load_tests(backend_dir: Path) -> bool:
    """Run load tests (requires running backend)."""
    print_header("Running Load Tests")
    print("⚠️  NOTE: Backend must be running on https://localhost:8000")
    print("Press Ctrl+C within 5 seconds to skip load tests...")
    
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n⏭️  Skipping load tests")
        return True
    
    load_test_script = backend_dir / "scripts" / "load_test_sync.py"
    cmd = [sys.executable, str(load_test_script)]
    exit_code, stdout, stderr = run_command(cmd, cwd=backend_dir)
    
    print(stdout)
    if stderr and exit_code != 0:
        print(stderr, file=sys.stderr)
    
    if exit_code == 0:
        print("\n✅ Load tests COMPLETED")
        return True
    else:
        print("\n❌ Load tests FAILED")
        return False


def check_backend_running() -> bool:
    """Check if backend is running."""
    try:
        import requests
        response = requests.get("https://localhost:8000/health", verify=False, timeout=2)
        return response.status_code == 200
    except:
        return False


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Run BaluHost test suite")
    parser.add_argument("--skip-integration", action="store_true", help="Skip integration tests")
    parser.add_argument("--skip-benchmarks", action="store_true", help="Skip performance benchmarks")
    parser.add_argument("--skip-load", action="store_true", help="Skip load tests")
    parser.add_argument("--load-only", action="store_true", help="Run only load tests")
    args = parser.parse_args()
    
    backend_dir = Path(__file__).parent.parent  # Go up from scripts/ to backend/
    start_time = time.time()
    
    print("=" * 70)
    print("  BaluHost Test Suite Runner")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    results = {}
    
    if args.load_only:
        # Check if backend is running
        if not check_backend_running():
            print("\n❌ ERROR: Backend is not running!")
            print("   Start backend with: python start_dev.py")
            return 1
        
        results["load_tests"] = run_load_tests(backend_dir)
    else:
        # Run integration tests
        if not args.skip_integration:
            results["integration_tests"] = run_integration_tests(backend_dir)
        
        # Run performance benchmarks
        if not args.skip_benchmarks:
            results["performance_benchmarks"] = run_performance_benchmarks(backend_dir)
        
        # Run load tests (optional)
        if not args.skip_load:
            if check_backend_running():
                results["load_tests"] = run_load_tests(backend_dir)
            else:
                print_header("Load Tests Skipped")
                print("⚠️  Backend is not running. Start with: python start_dev.py")
                print("   Then run: python scripts/run_all_tests.py --load-only")
                results["load_tests"] = None
    
    # Print summary
    end_time = time.time()
    duration = end_time - start_time
    
    print_header("Test Summary")
    
    passed = 0
    failed = 0
    skipped = 0
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else ("❌ FAILED" if result is not None else "⏭️  SKIPPED")
        print(f"  {test_name.replace('_', ' ').title()}: {status}")
        
        if result is True:
            passed += 1
        elif result is False:
            failed += 1
        else:
            skipped += 1
    
    print(f"\n  Total Duration: {duration:.2f} seconds")
    print(f"  Passed: {passed}, Failed: {failed}, Skipped: {skipped}")
    
    print("\n" + "=" * 70)
    
    if failed > 0:
        print("❌ Some tests FAILED")
        return 1
    elif passed > 0:
        print("✅ All tests PASSED")
        return 0
    else:
        print("⚠️  No tests were run")
        return 0


if __name__ == "__main__":
    sys.exit(main())
