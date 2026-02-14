"""
Performance Benchmark Suite for BaluHost Sync System
Measures file operations, memory usage, CPU usage, and database performance.
"""

import asyncio
import time
import psutil
import os
from pathlib import Path
import tempfile
import shutil
from typing import Dict, List, Tuple
import statistics
import json
from datetime import datetime
import hashlib
import random
import string


class PerformanceBenchmark:
    """Comprehensive performance benchmarking for sync system."""
    
    def __init__(self):
        self.results: Dict[str, any] = {}
        self.process = psutil.Process()
        self.start_memory = 0
        self.start_cpu_times = None
        
    def start_monitoring(self):
        """Start performance monitoring."""
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.start_cpu_times = self.process.cpu_times()
        
    def get_metrics(self) -> Dict:
        """Get current performance metrics."""
        current_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        memory_delta = current_memory - self.start_memory
        
        current_cpu_times = self.process.cpu_times()
        cpu_time = (current_cpu_times.user - self.start_cpu_times.user) + \
                   (current_cpu_times.system - self.start_cpu_times.system)
        
        return {
            "memory_mb": current_memory,
            "memory_delta_mb": memory_delta,
            "cpu_time_seconds": cpu_time,
            "cpu_percent": self.process.cpu_percent(interval=0.1)
        }
    
    async def benchmark_file_upload(self, file_sizes: List[int], iterations: int = 10) -> Dict:
        """Benchmark file upload performance for different file sizes."""
        print("\n=== File Upload Benchmark ===")
        results = {}
        
        for size_kb in file_sizes:
            print(f"\nTesting {size_kb}KB files...")
            times = []
            throughputs = []
            
            # Generate test data
            test_data = os.urandom(size_kb * 1024)
            
            for i in range(iterations):
                self.start_monitoring()
                start_time = time.time()
                
                # Simulate upload by calculating hash and writing to temp file
                file_hash = hashlib.sha256(test_data).hexdigest()
                temp_file = Path(tempfile.gettempdir()) / f"bench_upload_{i}.tmp"
                temp_file.write_bytes(test_data)
                
                end_time = time.time()
                elapsed = end_time - start_time
                times.append(elapsed)
                
                # Calculate throughput (MB/s)
                throughput = (size_kb / 1024) / elapsed
                throughputs.append(throughput)
                
                # Cleanup
                temp_file.unlink()
            
            metrics = self.get_metrics()
            
            results[f"{size_kb}KB"] = {
                "avg_time_ms": statistics.mean(times) * 1000,
                "min_time_ms": min(times) * 1000,
                "max_time_ms": max(times) * 1000,
                "std_dev_ms": statistics.stdev(times) * 1000 if len(times) > 1 else 0,
                "avg_throughput_mbps": statistics.mean(throughputs),
                "memory_delta_mb": metrics["memory_delta_mb"],
                "cpu_percent": metrics["cpu_percent"]
            }
            
            print(f"  Avg: {results[f'{size_kb}KB']['avg_time_ms']:.2f}ms")
            print(f"  Throughput: {results[f'{size_kb}KB']['avg_throughput_mbps']:.2f} MB/s")
        
        return results
    
    async def benchmark_file_download(self, file_sizes: List[int], iterations: int = 10) -> Dict:
        """Benchmark file download performance."""
        print("\n=== File Download Benchmark ===")
        results = {}
        
        for size_kb in file_sizes:
            print(f"\nTesting {size_kb}KB files...")
            times = []
            throughputs = []
            
            # Create test file
            test_data = os.urandom(size_kb * 1024)
            temp_file = Path(tempfile.gettempdir()) / f"bench_download_source.tmp"
            temp_file.write_bytes(test_data)
            
            for i in range(iterations):
                self.start_monitoring()
                start_time = time.time()
                
                # Simulate download by reading and hashing
                data = temp_file.read_bytes()
                file_hash = hashlib.sha256(data).hexdigest()
                
                end_time = time.time()
                elapsed = end_time - start_time
                times.append(elapsed)
                
                throughput = (size_kb / 1024) / elapsed
                throughputs.append(throughput)
            
            metrics = self.get_metrics()
            temp_file.unlink()
            
            results[f"{size_kb}KB"] = {
                "avg_time_ms": statistics.mean(times) * 1000,
                "min_time_ms": min(times) * 1000,
                "max_time_ms": max(times) * 1000,
                "std_dev_ms": statistics.stdev(times) * 1000 if len(times) > 1 else 0,
                "avg_throughput_mbps": statistics.mean(throughputs),
                "memory_delta_mb": metrics["memory_delta_mb"],
                "cpu_percent": metrics["cpu_percent"]
            }
            
            print(f"  Avg: {results[f'{size_kb}KB']['avg_time_ms']:.2f}ms")
            print(f"  Throughput: {results[f'{size_kb}KB']['avg_throughput_mbps']:.2f} MB/s")
        
        return results
    
    async def benchmark_hash_computation(self, file_sizes: List[int], iterations: int = 10) -> Dict:
        """Benchmark SHA256 hash computation performance."""
        print("\n=== Hash Computation Benchmark ===")
        results = {}
        
        for size_kb in file_sizes:
            print(f"\nTesting {size_kb}KB files...")
            times = []
            
            test_data = os.urandom(size_kb * 1024)
            
            for i in range(iterations):
                start_time = time.time()
                file_hash = hashlib.sha256(test_data).hexdigest()
                end_time = time.time()
                
                times.append(end_time - start_time)
            
            results[f"{size_kb}KB"] = {
                "avg_time_ms": statistics.mean(times) * 1000,
                "min_time_ms": min(times) * 1000,
                "max_time_ms": max(times) * 1000,
                "throughput_mbps": (size_kb / 1024) / statistics.mean(times)
            }
            
            print(f"  Avg: {results[f'{size_kb}KB']['avg_time_ms']:.2f}ms")
        
        return results
    
    async def benchmark_concurrent_operations(self, num_concurrent: int, operation_count: int) -> Dict:
        """Benchmark concurrent file operations."""
        print(f"\n=== Concurrent Operations Benchmark ({num_concurrent} concurrent) ===")
        
        async def mock_file_operation(op_id: int):
            """Mock file operation with I/O simulation."""
            # Simulate file I/O
            test_data = os.urandom(100 * 1024)  # 100KB
            await asyncio.sleep(random.uniform(0.01, 0.05))  # Simulate I/O delay
            file_hash = hashlib.sha256(test_data).hexdigest()
            return op_id, len(test_data)
        
        self.start_monitoring()
        start_time = time.time()
        
        # Run operations in batches
        tasks = []
        for i in range(operation_count):
            tasks.append(mock_file_operation(i))
            
            # Run in batches to simulate concurrent limit
            if len(tasks) >= num_concurrent or i == operation_count - 1:
                await asyncio.gather(*tasks)
                tasks = []
        
        end_time = time.time()
        elapsed = end_time - start_time
        metrics = self.get_metrics()
        
        results = {
            "total_operations": operation_count,
            "concurrent_limit": num_concurrent,
            "total_time_seconds": elapsed,
            "operations_per_second": operation_count / elapsed,
            "avg_time_per_operation_ms": (elapsed / operation_count) * 1000,
            "memory_delta_mb": metrics["memory_delta_mb"],
            "cpu_percent": metrics["cpu_percent"]
        }
        
        print(f"  Total time: {elapsed:.2f}s")
        print(f"  Ops/sec: {results['operations_per_second']:.2f}")
        print(f"  Avg per op: {results['avg_time_per_operation_ms']:.2f}ms")
        
        return results
    
    async def benchmark_memory_usage(self, num_files: int, file_size_kb: int) -> Dict:
        """Benchmark memory usage with many files."""
        print(f"\n=== Memory Usage Benchmark ({num_files} files @ {file_size_kb}KB) ===")
        
        self.start_monitoring()
        initial_memory = self.process.memory_info().rss / 1024 / 1024
        
        # Simulate loading many files into memory
        files_data = []
        for i in range(num_files):
            data = os.urandom(file_size_kb * 1024)
            file_hash = hashlib.sha256(data).hexdigest()
            files_data.append({
                "id": i,
                "hash": file_hash,
                "size": len(data),
                "data": data  # Keep in memory
            })
            
            # Monitor memory every 10 files
            if i % 10 == 0:
                current_memory = self.process.memory_info().rss / 1024 / 1024
                print(f"  Files loaded: {i}, Memory: {current_memory:.2f}MB")
        
        final_memory = self.process.memory_info().rss / 1024 / 1024
        memory_used = final_memory - initial_memory
        memory_per_file = memory_used / num_files
        
        results = {
            "num_files": num_files,
            "file_size_kb": file_size_kb,
            "initial_memory_mb": initial_memory,
            "final_memory_mb": final_memory,
            "memory_used_mb": memory_used,
            "memory_per_file_kb": memory_per_file * 1024,
            "total_data_size_mb": (num_files * file_size_kb) / 1024
        }
        
        print(f"  Memory used: {memory_used:.2f}MB")
        print(f"  Per file: {memory_per_file * 1024:.2f}KB")
        
        # Cleanup
        del files_data
        
        return results
    
    async def benchmark_database_queries(self, num_records: int) -> Dict:
        """Benchmark database query performance (simulated)."""
        print(f"\n=== Database Query Benchmark ({num_records} records) ===")
        
        # Simulate database records in memory
        records = []
        for i in range(num_records):
            records.append({
                "id": i,
                "path": f"/user/folder{i % 100}/file{i}.txt",
                "hash": hashlib.sha256(f"file{i}".encode()).hexdigest(),
                "size": random.randint(1024, 1024*1024),
                "modified": time.time()
            })
        
        # Benchmark: Find by ID
        start_time = time.time()
        for _ in range(100):
            target_id = random.randint(0, num_records - 1)
            result = next((r for r in records if r["id"] == target_id), None)
        end_time = time.time()
        find_by_id_time = (end_time - start_time) / 100
        
        # Benchmark: Filter by path prefix
        start_time = time.time()
        for _ in range(100):
            folder_num = random.randint(0, 99)
            results = [r for r in records if r["path"].startswith(f"/user/folder{folder_num}")]
        end_time = time.time()
        filter_by_path_time = (end_time - start_time) / 100
        
        # Benchmark: Sort by modified time
        start_time = time.time()
        sorted_records = sorted(records, key=lambda r: r["modified"])
        end_time = time.time()
        sort_time = end_time - start_time
        
        results = {
            "num_records": num_records,
            "find_by_id_avg_ms": find_by_id_time * 1000,
            "filter_by_path_avg_ms": filter_by_path_time * 1000,
            "sort_all_records_ms": sort_time * 1000,
        }
        
        print(f"  Find by ID: {results['find_by_id_avg_ms']:.3f}ms")
        print(f"  Filter by path: {results['filter_by_path_avg_ms']:.3f}ms")
        print(f"  Sort all: {results['sort_all_records_ms']:.2f}ms")
        
        return results
    
    def save_results(self, filename: str = None):
        """Save benchmark results to JSON file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_results_{timestamp}.json"
        
        output_path = Path(__file__).parent.parent / "benchmark_results" / filename
        output_path.parent.mkdir(exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n✓ Results saved to: {output_path}")
        return output_path


async def run_all_benchmarks():
    """Run complete benchmark suite."""
    print("=" * 70)
    print("BaluHost Sync System - Performance Benchmark Suite")
    print("=" * 70)
    
    benchmark = PerformanceBenchmark()
    
    # File sizes to test (in KB)
    file_sizes = [1, 10, 100, 1000, 5000]  # 1KB to 5MB
    
    # Run benchmarks
    benchmark.results["file_upload"] = await benchmark.benchmark_file_upload(file_sizes)
    benchmark.results["file_download"] = await benchmark.benchmark_file_download(file_sizes)
    benchmark.results["hash_computation"] = await benchmark.benchmark_hash_computation(file_sizes)
    
    # Concurrent operations
    benchmark.results["concurrent_10"] = await benchmark.benchmark_concurrent_operations(10, 100)
    benchmark.results["concurrent_50"] = await benchmark.benchmark_concurrent_operations(50, 200)
    benchmark.results["concurrent_100"] = await benchmark.benchmark_concurrent_operations(100, 500)
    
    # Memory usage
    benchmark.results["memory_usage"] = await benchmark.benchmark_memory_usage(100, 100)
    
    # Database queries
    benchmark.results["database_queries_1000"] = await benchmark.benchmark_database_queries(1000)
    benchmark.results["database_queries_10000"] = await benchmark.benchmark_database_queries(10000)
    
    # Save results
    results_file = benchmark.save_results()
    
    # Print summary
    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY")
    print("=" * 70)
    
    # Upload performance
    upload_100kb = benchmark.results["file_upload"]["100KB"]
    print(f"\n📤 Upload (100KB): {upload_100kb['avg_time_ms']:.2f}ms @ {upload_100kb['avg_throughput_mbps']:.2f} MB/s")
    
    # Download performance
    download_100kb = benchmark.results["file_download"]["100KB"]
    print(f"📥 Download (100KB): {download_100kb['avg_time_ms']:.2f}ms @ {download_100kb['avg_throughput_mbps']:.2f} MB/s")
    
    # Concurrent operations
    concurrent_50 = benchmark.results["concurrent_50"]
    print(f"\n⚡ Concurrent (50): {concurrent_50['operations_per_second']:.2f} ops/sec")
    
    # Memory
    memory = benchmark.results["memory_usage"]
    print(f"\n💾 Memory (100 files): {memory['memory_used_mb']:.2f}MB ({memory['memory_per_file_kb']:.2f}KB/file)")
    
    # Database
    db_1000 = benchmark.results["database_queries_1000"]
    print(f"\n🗄️  Database (1000 records):")
    print(f"   Find: {db_1000['find_by_id_avg_ms']:.3f}ms")
    print(f"   Filter: {db_1000['filter_by_path_avg_ms']:.3f}ms")
    
    print("\n" + "=" * 70)
    
    return benchmark.results


if __name__ == "__main__":
    asyncio.run(run_all_benchmarks())
