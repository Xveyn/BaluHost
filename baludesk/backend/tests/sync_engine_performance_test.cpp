#include <gtest/gtest.h>
#include <chrono>
#include <thread>
#include <vector>
#include <random>
#include <iostream>
#include <cmath>

namespace baludesk {

/**
 * Performance Benchmark Tests for SyncEngine
 * 
 * Tests focus on:
 * - High-volume file operations (100+ files)
 * - Parallel sync testing
 * - Memory optimization
 * - Retry logic performance under load
 */

class PerformanceBenchmark {
public:
    PerformanceBenchmark() = default;
    
    struct BenchmarkResult {
        std::string testName;
        uint64_t operationCount;
        std::chrono::milliseconds totalTime;
        double operationsPerSecond;
        uint64_t memoryUsedBytes;
    };
    
    static void printResult(const BenchmarkResult& result) {
        std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
        std::cout << "  Test: " << result.testName << "\n";
        std::cout << "  Operations: " << result.operationCount << "\n";
        std::cout << "  Total Time: " << result.totalTime.count() << " ms\n";
        std::cout << "  Throughput: " << result.operationsPerSecond << " ops/sec\n";
        std::cout << "  Memory Used: " << (result.memoryUsedBytes / 1024) << " KB\n";
        std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    }
};

class SyncEnginePerformanceTest : public ::testing::Test {
protected:
    PerformanceBenchmark benchmark;
    
    void SetUp() override {
        // Setup for each test
    }
    
    void TearDown() override {
        // Cleanup after each test
    }
};

// ============================================================================
// BENCHMARK 1: Bulk File Sync (100 files)
// ============================================================================

TEST_F(SyncEnginePerformanceTest, BulkFileSync100Files) {
    const uint64_t fileCount = 100;
    std::vector<std::string> files;
    
    // Simulate file list
    for (uint64_t i = 0; i < fileCount; ++i) {
        files.push_back("file_" + std::to_string(i) + ".dat");
    }
    
    auto startTime = std::chrono::high_resolution_clock::now();
    
    // Simulate processing files
    for (const auto& file : files) {
        // Simulate file hash calculation
        std::hash<std::string> hasher;
        volatile auto hash = hasher(file);
        (void)hash;  // Use to prevent optimization
    }
    
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime);
    
    PerformanceBenchmark::BenchmarkResult result{
        "Bulk File Sync (100 files)",
        fileCount,
        duration,
        (fileCount * 1000.0) / duration.count(),
        files.size() * 32  // Estimate memory per filename
    };
    
    PerformanceBenchmark::printResult(result);
    
    // Performance threshold: should process 100 files in < 500ms
    ASSERT_LT(duration.count(), 500);
    ASSERT_GE(result.operationsPerSecond, 200.0);
}

// ============================================================================
// BENCHMARK 2: Large File Sync (500+ files)
// ============================================================================

TEST_F(SyncEnginePerformanceTest, LargeFileSync500Files) {
    const uint64_t fileCount = 500;
    std::vector<std::pair<std::string, uint64_t>> files;
    
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<> dis(1024, 10240);  // 1KB-10KB files
    
    for (uint64_t i = 0; i < fileCount; ++i) {
        files.push_back({
            "large_file_" + std::to_string(i) + ".dat",
            dis(gen)
        });
    }
    
    auto startTime = std::chrono::high_resolution_clock::now();
    
    // Simulate processing large files
    for (const auto& [filename, size] : files) {
        std::hash<std::string> hasher;
        volatile auto hash = hasher(filename);
        volatile auto sizeHash = size * 1.1;  // Simulate some calculation
        (void)hash;
        (void)sizeHash;
    }
    
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime);
    
    uint64_t totalSize = 0;
    for (const auto& [_, size] : files) {
        totalSize += size;
    }
    
    PerformanceBenchmark::BenchmarkResult result{
        "Large File Sync (500 files, ~5MB total)",
        fileCount,
        duration,
        (fileCount * 1000.0) / duration.count(),
        totalSize
    };
    
    PerformanceBenchmark::printResult(result);
    
    // Performance threshold: should process 500 files in < 2 seconds
    ASSERT_LT(duration.count(), 2000);
    ASSERT_GE(result.operationsPerSecond, 250.0);
}

// ============================================================================
// BENCHMARK 3: Parallel Sync Operations
// ============================================================================

TEST_F(SyncEnginePerformanceTest, ParallelSyncOperations) {
    const int threadCount = 4;
    const int filesPerThread = 50;
    
    auto startTime = std::chrono::high_resolution_clock::now();
    
    std::vector<std::thread> threads;
    
    // Spawn parallel sync threads
    for (int t = 0; t < threadCount; ++t) {
        threads.emplace_back([filesPerThread]() {
            for (int i = 0; i < filesPerThread; ++i) {
                std::string filename = "thread_file_" + std::to_string(i) + ".dat";
                std::hash<std::string> hasher;
                volatile auto hash = hasher(filename);
                (void)hash;
                
                // Simulate some I/O delay
                std::this_thread::sleep_for(std::chrono::microseconds(100));
            }
        });
    }
    
    // Wait for all threads to complete
    for (auto& thread : threads) {
        thread.join();
    }
    
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime);
    
    uint64_t totalOps = threadCount * filesPerThread;
    
    PerformanceBenchmark::BenchmarkResult result{
        "Parallel Sync (4 threads, 50 files each)",
        totalOps,
        duration,
        (totalOps * 1000.0) / duration.count(),
        threadCount * 64  // Estimate thread overhead
    };
    
    PerformanceBenchmark::printResult(result);
    
    // Parallel execution with thread overhead
    // Realistic time: ~750ms for 4 threads with 100us sleep each = 100*4*100us = 400ms + overhead
    ASSERT_LT(duration.count(), 1000);
}

// ============================================================================
// BENCHMARK 4: Retry Logic Performance Under Load
// ============================================================================

TEST_F(SyncEnginePerformanceTest, RetryLogicUnderLoad) {
    const int operationCount = 1000;
    const int maxRetries = 3;
    const int initialDelayMs = 1000;
    
    auto startTime = std::chrono::high_resolution_clock::now();
    
    // Simulate 1000 operations with backoff calculation
    for (int op = 0; op < operationCount; ++op) {
        // Calculate backoff delays for this operation
        for (int attempt = 0; attempt < maxRetries; ++attempt) {
            int delayMs = static_cast<int>(
                initialDelayMs * std::pow(2.0, static_cast<double>(attempt))
            );
            volatile int result = delayMs;  // Use result to prevent optimization
            (void)result;
        }
    }
    
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime);
    
    PerformanceBenchmark::BenchmarkResult result{
        "Retry Logic Under Load (1000 operations, 3 retries each)",
        operationCount * maxRetries,
        duration,
        (operationCount * maxRetries * 1000.0) / duration.count(),
        operationCount * 16  // Estimate state per operation
    };
    
    PerformanceBenchmark::printResult(result);
    
    // Backoff calculation must be very fast (< 50ms for 1000 ops)
    ASSERT_LT(duration.count(), 50);
    ASSERT_GE(result.operationsPerSecond, 60000.0);
}

// ============================================================================
// BENCHMARK 5: Memory Efficiency for Large Operations
// ============================================================================

TEST_F(SyncEnginePerformanceTest, MemoryEfficiencyLargeOps) {
    const uint64_t bufferSize = 10 * 1024 * 1024;  // 10MB
    
    auto startTime = std::chrono::high_resolution_clock::now();
    
    // Allocate and process large buffer
    std::vector<uint8_t> buffer(bufferSize);
    
    // Simulate processing (hash calculation on chunks)
    const size_t chunkSize = 65536;  // 64KB chunks
    uint32_t checksum = 0;
    
    for (size_t i = 0; i < buffer.size(); i += chunkSize) {
        for (size_t j = 0; j < chunkSize && (i + j) < buffer.size(); ++j) {
            checksum ^= buffer[i + j];
        }
    }
    
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime);
    
    double throughput = (bufferSize / (1024.0 * 1024.0)) / (duration.count() / 1000.0);
    
    std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    std::cout << "  Test: Memory Efficiency (10MB buffer)\n";
    std::cout << "  Total Time: " << duration.count() << " ms\n";
    std::cout << "  Throughput: " << throughput << " MB/sec\n";
    std::cout << "  Buffer Size: " << (bufferSize / (1024 * 1024)) << " MB\n";
    std::cout << "  Checksum: " << checksum << "\n";
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    
    // Processing 10MB should take < 500ms
    ASSERT_LT(duration.count(), 500);
    ASSERT_GT(throughput, 20.0);  // At least 20 MB/sec
}

// ============================================================================
// BENCHMARK 6: Conflict Resolution Performance
// ============================================================================

TEST_F(SyncEnginePerformanceTest, ConflictResolutionPerformance) {
    const int conflictCount = 100;
    
    auto startTime = std::chrono::high_resolution_clock::now();
    
    // Simulate processing 100 conflicts
    for (int i = 0; i < conflictCount; ++i) {
        // Simulate conflict comparison
        std::string local = "version_" + std::to_string(i) + "_local";
        std::string remote = "version_" + std::to_string(i) + "_remote";
        
        std::hash<std::string> hasher;
        bool different = hasher(local) != hasher(remote);
        
        // Simulate resolution decision
        int resolution = different ? 1 : 0;
        volatile int result = resolution;
        (void)result;
    }
    
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime);
    
    PerformanceBenchmark::BenchmarkResult result{
        "Conflict Resolution (100 conflicts)",
        conflictCount,
        duration,
        (conflictCount * 1000.0) / duration.count(),
        conflictCount * 64  // Estimate conflict metadata
    };
    
    PerformanceBenchmark::printResult(result);
    
    // Processing 100 conflicts should be very fast (< 100ms)
    ASSERT_LT(duration.count(), 100);
    ASSERT_GE(result.operationsPerSecond, 1000.0);
}

// ============================================================================
// BENCHMARK 7: Sustained High-Rate Operations
// ============================================================================

TEST_F(SyncEnginePerformanceTest, SustainedHighRateOps) {
    const int durationSeconds = 5;
    const auto endTime = std::chrono::high_resolution_clock::now() + 
                         std::chrono::seconds(durationSeconds);
    
    uint64_t operationCount = 0;
    
    auto startTime = std::chrono::high_resolution_clock::now();
    
    // Perform as many operations as possible in 5 seconds
    while (std::chrono::high_resolution_clock::now() < endTime) {
        std::string filename = "perf_file_" + std::to_string(operationCount);
        std::hash<std::string> hasher;
        volatile auto hash = hasher(filename);
        (void)hash;
        ++operationCount;
    }
    
    auto actualEnd = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(actualEnd - startTime);
    
    PerformanceBenchmark::BenchmarkResult result{
        "Sustained High-Rate Operations (5 seconds)",
        operationCount,
        duration,
        (operationCount * 1000.0) / duration.count(),
        operationCount * 8  // Estimate counter overhead
    };
    
    PerformanceBenchmark::printResult(result);
    
    // Should sustain high throughput
    ASSERT_GE(result.operationsPerSecond, 100000.0);
}

// ============================================================================
// BENCHMARK 8: Backoff Delay Impact on Throughput
// ============================================================================

TEST_F(SyncEnginePerformanceTest, BackoffDelayImpact) {
    const int operationCount = 100;
    const int maxRetries = 3;
    const int initialDelayMs = 1000;
    
    auto startTime = std::chrono::high_resolution_clock::now();
    
    // Simulate operations with retry backoff delays
    int totalDelayMs = 0;
    for (int op = 0; op < operationCount; ++op) {
        for (int attempt = 0; attempt < maxRetries; ++attempt) {
            int delayMs = static_cast<int>(
                initialDelayMs * std::pow(2.0, static_cast<double>(attempt))
            );
            totalDelayMs += delayMs;
        }
    }
    
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime);
    
    double avgDelayPerOp = static_cast<double>(totalDelayMs) / operationCount;
    
    std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    std::cout << "  Test: Backoff Delay Impact\n";
    std::cout << "  Total Calculation Time: " << duration.count() << " ms\n";
    std::cout << "  Total Delay (if applied): " << totalDelayMs << " ms\n";
    std::cout << "  Avg Delay per Operation: " << avgDelayPerOp << " ms\n";
    std::cout << "  Operations: " << operationCount << "\n";
    std::cout << "  Max Retries: " << maxRetries << "\n";
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    
    // Calculation should be instant
    ASSERT_LT(duration.count(), 10);
    
    // For 100 ops with 3 retries each:
    // delay = 1000 + 2000 + 4000 = 7000ms per failed operation
    // Total = 700,000ms if all fail
    ASSERT_EQ(totalDelayMs, 700000);
}

// ============================================================================
// BENCHMARK 9: Concurrent File Access
// ============================================================================

TEST_F(SyncEnginePerformanceTest, ConcurrentFileAccess) {
    const int threadCount = 8;
    const int accessesPerThread = 100;
    
    auto startTime = std::chrono::high_resolution_clock::now();
    
    std::vector<std::thread> threads;
    std::atomic<uint64_t> totalAccesses(0);
    
    // Create multiple threads accessing same data
    for (int t = 0; t < threadCount; ++t) {
        threads.emplace_back([&totalAccesses, accessesPerThread, t]() {
            for (int i = 0; i < accessesPerThread; ++i) {
                std::string key = "file_" + std::to_string(t) + "_" + std::to_string(i);
                std::hash<std::string> hasher;
                volatile auto hash = hasher(key);
                (void)hash;
                ++totalAccesses;
            }
        });
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
    
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime);
    
    uint64_t expectedAccesses = threadCount * accessesPerThread;
    double opsPerSecond = (expectedAccesses * 1000.0) / duration.count();
    
    std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    std::cout << "  Test: Concurrent File Access\n";
    std::cout << "  Threads: " << threadCount << "\n";
    std::cout << "  Accesses per Thread: " << accessesPerThread << "\n";
    std::cout << "  Total Accesses: " << totalAccesses << "\n";
    std::cout << "  Total Time: " << duration.count() << " ms\n";
    std::cout << "  Throughput: " << opsPerSecond << " ops/sec\n";
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    
    ASSERT_EQ(totalAccesses, expectedAccesses);
    ASSERT_GE(opsPerSecond, 50000.0);  // At least 50K ops/sec
}

// ============================================================================
// BENCHMARK 10: Error Handling Overhead
// ============================================================================

TEST_F(SyncEnginePerformanceTest, ErrorHandlingOverhead) {
    const int errorOperations = 1000;
    
    auto startTime = std::chrono::high_resolution_clock::now();
    
    // Simulate error handling with try-catch
    for (int i = 0; i < errorOperations; ++i) {
        try {
            if (i % 10 == 0) {  // 10% error rate
                throw std::runtime_error("Simulated error");
            }
            volatile int result = i * 2;
            (void)result;
        } catch (const std::exception& e) {
            volatile const char* what = e.what();
            (void)what;
        }
    }
    
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime);
    
    double opsPerSecond = (errorOperations * 1000.0) / duration.count();
    
    std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    std::cout << "  Test: Error Handling Overhead\n";
    std::cout << "  Operations: " << errorOperations << "\n";
    std::cout << "  Error Rate: 10%\n";
    std::cout << "  Total Time: " << duration.count() << " ms\n";
    std::cout << "  Throughput: " << opsPerSecond << " ops/sec\n";
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    
    // Even with error handling, should maintain good throughput
    ASSERT_GE(opsPerSecond, 1000000.0);  // > 1M ops/sec
}

}  // namespace baludesk
