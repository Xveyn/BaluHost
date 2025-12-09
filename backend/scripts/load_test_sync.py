"""
Load Testing Suite for BaluHost Sync System
Tests system under high concurrent load with 100+ simultaneous sync operations.
"""

import asyncio
import aiohttp
import time
import statistics
from pathlib import Path
import tempfile
import os
import random
import string
from typing import List, Dict, Tuple
import json
from datetime import datetime
import psutil
from dataclasses import dataclass, asdict


@dataclass
class LoadTestResult:
    """Result from a single load test operation."""
    operation_id: int
    operation_type: str
    start_time: float
    end_time: float
    duration: float
    status_code: int
    success: bool
    error_message: str = None
    
    def to_dict(self):
        return asdict(self)


class LoadTester:
    """Load testing for sync system with concurrent operations."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: List[LoadTestResult] = []
        self.tokens: List[str] = []
        self.process = psutil.Process()
        
    async def create_test_users(self, num_users: int) -> List[Dict]:
        """Create multiple test users for load testing."""
        print(f"Creating {num_users} test users...")
        users = []
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(num_users):
                username = f"loadtest_user_{i}_{int(time.time())}"
                user_data = {
                    "username": username,
                    "email": f"{username}@loadtest.com",
                    "password": "LoadTest123!"
                }
                tasks.append(self._register_and_login(session, user_data))
            
            users_with_tokens = await asyncio.gather(*tasks)
            users = [u for u in users_with_tokens if u is not None]
        
        print(f"✓ Created {len(users)} users")
        return users
    
    async def _register_and_login(self, session: aiohttp.ClientSession, user_data: Dict) -> Dict:
        """Register and login a user, return user data with token."""
        try:
            # Register
            async with session.post(
                f"{self.base_url}/api/auth/register",
                json=user_data,
                ssl=False
            ) as response:
                if response.status != 201:
                    return None
            
            # Login
            async with session.post(
                f"{self.base_url}/api/auth/login",
                json={
                    "username": user_data["username"],
                    "password": user_data["password"]
                },
                ssl=False
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    user_data["token"] = data["access_token"]
                    return user_data
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    async def load_test_concurrent_uploads(
        self, 
        num_concurrent: int, 
        num_uploads_per_user: int,
        file_size_kb: int = 100
    ) -> Dict:
        """Load test with concurrent file uploads."""
        print(f"\n{'='*70}")
        print(f"Load Test: {num_concurrent} Concurrent Uploads")
        print(f"Files per user: {num_uploads_per_user}, Size: {file_size_kb}KB")
        print(f"{'='*70}")
        
        # Create test users
        users = await self.create_test_users(num_concurrent)
        if len(users) < num_concurrent:
            print(f"Warning: Only created {len(users)} users instead of {num_concurrent}")
        
        # Generate test file data
        test_data = os.urandom(file_size_kb * 1024)
        
        # Track system resources
        start_memory = self.process.memory_info().rss / 1024 / 1024
        start_cpu_percent = self.process.cpu_percent()
        
        start_time = time.time()
        results = []
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            operation_id = 0
            
            for user in users:
                for upload_num in range(num_uploads_per_user):
                    tasks.append(
                        self._upload_file(
                            session,
                            user["token"],
                            f"/loadtest/{user['username']}/file_{upload_num}.dat",
                            test_data,
                            operation_id
                        )
                    )
                    operation_id += 1
            
            results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Calculate system resource usage
        end_memory = self.process.memory_info().rss / 1024 / 1024
        memory_delta = end_memory - start_memory
        
        # Analyze results
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        durations = [r.duration for r in successful]
        
        report = {
            "test_type": "concurrent_uploads",
            "num_concurrent_users": len(users),
            "uploads_per_user": num_uploads_per_user,
            "total_operations": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": len(successful) / len(results) * 100,
            "total_duration_seconds": total_duration,
            "operations_per_second": len(results) / total_duration,
            "avg_operation_time_ms": statistics.mean(durations) * 1000 if durations else 0,
            "min_operation_time_ms": min(durations) * 1000 if durations else 0,
            "max_operation_time_ms": max(durations) * 1000 if durations else 0,
            "median_operation_time_ms": statistics.median(durations) * 1000 if durations else 0,
            "std_dev_ms": statistics.stdev(durations) * 1000 if len(durations) > 1 else 0,
            "memory_delta_mb": memory_delta,
            "total_data_transferred_mb": (len(results) * file_size_kb) / 1024,
            "throughput_mbps": ((len(successful) * file_size_kb) / 1024) / total_duration
        }
        
        self._print_report(report)
        self.results.extend(results)
        
        return report
    
    async def _upload_file(
        self,
        session: aiohttp.ClientSession,
        token: str,
        path: str,
        data: bytes,
        operation_id: int
    ) -> LoadTestResult:
        """Upload a single file."""
        start_time = time.time()
        
        try:
            form = aiohttp.FormData()
            form.add_field('file', data, filename=Path(path).name, content_type='application/octet-stream')
            form.add_field('path', path)
            
            async with session.post(
                f"{self.base_url}/api/files/upload",
                headers={"Authorization": f"Bearer {token}"},
                data=form,
                ssl=False
            ) as response:
                end_time = time.time()
                
                return LoadTestResult(
                    operation_id=operation_id,
                    operation_type="upload",
                    start_time=start_time,
                    end_time=end_time,
                    duration=end_time - start_time,
                    status_code=response.status,
                    success=response.status == 200
                )
        except Exception as e:
            end_time = time.time()
            return LoadTestResult(
                operation_id=operation_id,
                operation_type="upload",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                status_code=0,
                success=False,
                error_message=str(e)
            )
    
    async def load_test_concurrent_downloads(
        self,
        num_concurrent: int,
        num_downloads_per_user: int
    ) -> Dict:
        """Load test with concurrent file downloads."""
        print(f"\n{'='*70}")
        print(f"Load Test: {num_concurrent} Concurrent Downloads")
        print(f"Downloads per user: {num_downloads_per_user}")
        print(f"{'='*70}")
        
        # Create users and upload files first
        users = await self.create_test_users(num_concurrent)
        
        # Upload test files
        print("Uploading test files...")
        test_data = os.urandom(50 * 1024)  # 50KB test files
        
        async with aiohttp.ClientSession() as session:
            upload_tasks = []
            for user in users:
                for i in range(num_downloads_per_user):
                    upload_tasks.append(
                        self._upload_file(
                            session,
                            user["token"],
                            f"/loadtest/{user['username']}/download_test_{i}.dat",
                            test_data,
                            i
                        )
                    )
            await asyncio.gather(*upload_tasks)
        
        print("✓ Test files uploaded")
        
        # Now perform concurrent downloads
        start_time = time.time()
        results = []
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            operation_id = 0
            
            for user in users:
                for i in range(num_downloads_per_user):
                    tasks.append(
                        self._download_file(
                            session,
                            user["token"],
                            f"/loadtest/{user['username']}/download_test_{i}.dat",
                            operation_id
                        )
                    )
                    operation_id += 1
            
            results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Analyze results
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        durations = [r.duration for r in successful]
        
        report = {
            "test_type": "concurrent_downloads",
            "num_concurrent_users": len(users),
            "downloads_per_user": num_downloads_per_user,
            "total_operations": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": len(successful) / len(results) * 100,
            "total_duration_seconds": total_duration,
            "operations_per_second": len(results) / total_duration,
            "avg_operation_time_ms": statistics.mean(durations) * 1000 if durations else 0,
            "min_operation_time_ms": min(durations) * 1000 if durations else 0,
            "max_operation_time_ms": max(durations) * 1000 if durations else 0,
            "median_operation_time_ms": statistics.median(durations) * 1000 if durations else 0,
        }
        
        self._print_report(report)
        self.results.extend(results)
        
        return report
    
    async def _download_file(
        self,
        session: aiohttp.ClientSession,
        token: str,
        path: str,
        operation_id: int
    ) -> LoadTestResult:
        """Download a single file."""
        start_time = time.time()
        
        try:
            async with session.get(
                f"{self.base_url}/api/files/download{path}",
                headers={"Authorization": f"Bearer {token}"},
                ssl=False
            ) as response:
                # Read the full response
                data = await response.read()
                end_time = time.time()
                
                return LoadTestResult(
                    operation_id=operation_id,
                    operation_type="download",
                    start_time=start_time,
                    end_time=end_time,
                    duration=end_time - start_time,
                    status_code=response.status,
                    success=response.status == 200
                )
        except Exception as e:
            end_time = time.time()
            return LoadTestResult(
                operation_id=operation_id,
                operation_type="download",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                status_code=0,
                success=False,
                error_message=str(e)
            )
    
    async def load_test_mixed_operations(
        self,
        num_concurrent: int,
        operations_per_user: int
    ) -> Dict:
        """Load test with mixed upload/download/sync operations."""
        print(f"\n{'='*70}")
        print(f"Load Test: {num_concurrent} Concurrent Mixed Operations")
        print(f"Operations per user: {operations_per_user}")
        print(f"{'='*70}")
        
        users = await self.create_test_users(num_concurrent)
        test_data = os.urandom(75 * 1024)  # 75KB
        
        start_time = time.time()
        results = []
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            operation_id = 0
            
            for user in users:
                for op_num in range(operations_per_user):
                    # Randomly choose operation type
                    op_type = random.choice(["upload", "download", "sync_state"])
                    
                    if op_type == "upload":
                        tasks.append(
                            self._upload_file(
                                session,
                                user["token"],
                                f"/loadtest/{user['username']}/mixed_{op_num}.dat",
                                test_data,
                                operation_id
                            )
                        )
                    elif op_type == "download":
                        tasks.append(
                            self._download_file(
                                session,
                                user["token"],
                                f"/loadtest/{user['username']}/mixed_0.dat",
                                operation_id
                            )
                        )
                    else:  # sync_state
                        tasks.append(
                            self._get_sync_state(session, user["token"], operation_id)
                        )
                    
                    operation_id += 1
            
            results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Analyze results
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        durations = [r.duration for r in successful]
        
        # Group by operation type
        uploads = [r for r in successful if r.operation_type == "upload"]
        downloads = [r for r in successful if r.operation_type == "download"]
        syncs = [r for r in successful if r.operation_type == "sync_state"]
        
        report = {
            "test_type": "mixed_operations",
            "num_concurrent_users": len(users),
            "operations_per_user": operations_per_user,
            "total_operations": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": len(successful) / len(results) * 100,
            "total_duration_seconds": total_duration,
            "operations_per_second": len(results) / total_duration,
            "uploads": len(uploads),
            "downloads": len(downloads),
            "sync_states": len(syncs),
            "avg_operation_time_ms": statistics.mean(durations) * 1000 if durations else 0,
        }
        
        self._print_report(report)
        self.results.extend(results)
        
        return report
    
    async def _get_sync_state(
        self,
        session: aiohttp.ClientSession,
        token: str,
        operation_id: int
    ) -> LoadTestResult:
        """Get sync state."""
        start_time = time.time()
        
        try:
            async with session.get(
                f"{self.base_url}/api/sync/state",
                headers={"Authorization": f"Bearer {token}"},
                ssl=False
            ) as response:
                await response.json()
                end_time = time.time()
                
                return LoadTestResult(
                    operation_id=operation_id,
                    operation_type="sync_state",
                    start_time=start_time,
                    end_time=end_time,
                    duration=end_time - start_time,
                    status_code=response.status,
                    success=response.status == 200
                )
        except Exception as e:
            end_time = time.time()
            return LoadTestResult(
                operation_id=operation_id,
                operation_type="sync_state",
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                status_code=0,
                success=False,
                error_message=str(e)
            )
    
    def _print_report(self, report: Dict):
        """Print formatted load test report."""
        print(f"\n📊 Results:")
        print(f"   Total Operations: {report['total_operations']}")
        print(f"   Successful: {report['successful']} ({report['success_rate']:.1f}%)")
        print(f"   Failed: {report['failed']}")
        print(f"   Duration: {report['total_duration_seconds']:.2f}s")
        print(f"   Throughput: {report['operations_per_second']:.2f} ops/sec")
        print(f"   Avg Time: {report['avg_operation_time_ms']:.2f}ms")
        
        if 'min_operation_time_ms' in report:
            print(f"   Min Time: {report['min_operation_time_ms']:.2f}ms")
            print(f"   Max Time: {report['max_operation_time_ms']:.2f}ms")
            print(f"   Median: {report['median_operation_time_ms']:.2f}ms")
        
        if 'throughput_mbps' in report:
            print(f"   Data Throughput: {report['throughput_mbps']:.2f} MB/s")
            print(f"   Memory Delta: {report['memory_delta_mb']:.2f} MB")
    
    def save_results(self, filename: str = None):
        """Save all load test results to file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"load_test_results_{timestamp}.json"
        
        output_path = Path(__file__).parent.parent / "load_test_results" / filename
        output_path.parent.mkdir(exist_ok=True)
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "results": [r.to_dict() for r in self.results]
        }
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\n✓ Results saved to: {output_path}")
        return output_path


async def run_load_tests():
    """Run complete load testing suite."""
    print("=" * 70)
    print("BaluHost Sync System - Load Testing Suite")
    print("=" * 70)
    
    tester = LoadTester("https://localhost:8000")
    
    all_reports = []
    
    # Test 1: 50 concurrent uploads
    report = await tester.load_test_concurrent_uploads(
        num_concurrent=50,
        num_uploads_per_user=5,
        file_size_kb=100
    )
    all_reports.append(report)
    
    # Test 2: 100 concurrent uploads
    report = await tester.load_test_concurrent_uploads(
        num_concurrent=100,
        num_uploads_per_user=3,
        file_size_kb=50
    )
    all_reports.append(report)
    
    # Test 3: 50 concurrent downloads
    report = await tester.load_test_concurrent_downloads(
        num_concurrent=50,
        num_downloads_per_user=5
    )
    all_reports.append(report)
    
    # Test 4: Mixed operations
    report = await tester.load_test_mixed_operations(
        num_concurrent=75,
        operations_per_user=10
    )
    all_reports.append(report)
    
    # Save results
    tester.save_results()
    
    # Print final summary
    print("\n" + "=" * 70)
    print("LOAD TEST SUMMARY")
    print("=" * 70)
    
    for report in all_reports:
        print(f"\n{report['test_type'].upper()}:")
        print(f"  Success Rate: {report['success_rate']:.1f}%")
        print(f"  Throughput: {report['operations_per_second']:.2f} ops/sec")
        print(f"  Avg Time: {report['avg_operation_time_ms']:.2f}ms")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(run_load_tests())
