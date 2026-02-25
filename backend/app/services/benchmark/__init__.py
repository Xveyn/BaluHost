"""
Disk Benchmark Service.

Provides CrystalDiskMark-style disk performance benchmarks using fio.
Supports both production (real fio) and development (simulated) modes.

This package re-exports all public symbols so that existing imports
like ``from app.services.benchmark_service import X`` continue to work
(via the sys.modules alias registered in ``app.services.__init__``).
"""

from app.services.benchmark.api import (
    cancel_benchmark,
    get_available_disks,
    get_benchmark,
    get_benchmark_backend,
    get_benchmark_history,
    get_profile_configs,
    start_benchmark,
)
from app.services.benchmark.dev_backend import DevBenchmarkBackend
from app.services.benchmark.fio_backend import FioBenchmarkBackend
from app.services.benchmark.lifecycle import (
    kill_orphan_fio_processes,
    recover_stale_benchmarks,
    shutdown_benchmarks,
)
from app.services.benchmark.state import (
    BenchmarkBackend,
    FioNotFoundError,
    _active_benchmarks,
    _cancellation_flags,
)
from app.services.benchmark.tokens import (
    generate_confirmation_token,
    validate_confirmation_token,
)

__all__ = [
    # API
    "get_benchmark_backend",
    "get_available_disks",
    "get_profile_configs",
    "start_benchmark",
    "cancel_benchmark",
    "get_benchmark",
    "get_benchmark_history",
    # Backends
    "DevBenchmarkBackend",
    "FioBenchmarkBackend",
    "BenchmarkBackend",
    "FioNotFoundError",
    # Lifecycle
    "recover_stale_benchmarks",
    "kill_orphan_fio_processes",
    "shutdown_benchmarks",
    # Tokens
    "generate_confirmation_token",
    "validate_confirmation_token",
    # State (for monkey-patching in tests)
    "_active_benchmarks",
    "_cancellation_flags",
]
