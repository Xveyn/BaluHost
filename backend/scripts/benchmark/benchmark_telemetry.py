"""
Benchmark script to measure actual telemetry sampling performance.
Run this to determine optimal interval settings for your hardware.
"""
import time
import psutil
from statistics import mean, stdev


def benchmark_single_sample():
    """Measure time for one complete telemetry sample."""
    start = time.perf_counter()
    
    # CPU
    psutil.cpu_percent(interval=None)
    
    # Memory
    psutil.virtual_memory()
    
    # Network
    psutil.net_io_counters()
    
    elapsed = time.perf_counter() - start
    return elapsed * 1000  # Convert to milliseconds


def run_benchmark(samples=1000):
    """Run benchmark with specified number of samples."""
    print(f"Running telemetry benchmark with {samples} samples...")
    print("Priming psutil CPU statistics...")
    psutil.cpu_percent(interval=None)
    time.sleep(0.1)
    
    timings = []
    
    print("Collecting samples...")
    for i in range(samples):
        if (i + 1) % 100 == 0:
            print(f"  Progress: {i + 1}/{samples}")
        
        timing = benchmark_single_sample()
        timings.append(timing)
    
    print("\n" + "=" * 60)
    print("TELEMETRY PERFORMANCE RESULTS")
    print("=" * 60)
    print(f"Total Samples: {samples}")
    print(f"Average Time:  {mean(timings):.4f}ms per sample")
    print(f"Std Deviation: {stdev(timings):.4f}ms")
    print(f"Minimum Time:  {min(timings):.4f}ms")
    print(f"Maximum Time:  {max(timings):.4f}ms")
    print("=" * 60)
    
    # Calculate CPU impact for different intervals
    avg_ms = mean(timings)
    
    print("\nPROJECTED CPU IMPACT:")
    print("-" * 60)
    
    for interval in [1.0, 1.5, 2.0, 3.0, 5.0]:
        samples_per_min = 60 / interval
        time_per_min = avg_ms * samples_per_min
        cpu_percent = (time_per_min / (60 * 1000)) * 100
        
        print(f"  {interval}s interval: {samples_per_min:>5.1f} samples/min "
              f"→ ~{cpu_percent:.3f}% CPU")
    
    print("=" * 60)
    
    print("\nRECOMMENDATIONS:")
    if avg_ms < 0.5:
        print("  ✅ Hardware is EXCELLENT - safe to use 1s interval")
    elif avg_ms < 1.0:
        print("  ✅ Hardware is GOOD - 1s or 1.5s interval recommended")
    elif avg_ms < 2.0:
        print("  ⚠️  Hardware is MODERATE - use 2s or 3s interval")
    else:
        print("  ⚠️  Hardware is SLOW - use 3s or 5s interval")
    
    print("\n")


if __name__ == "__main__":
    run_benchmark(samples=1000)
