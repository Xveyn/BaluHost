#include <gtest/gtest.h>
#include "../src/sync/sync_engine.h"
#include "../src/sync/file_watcher_v2.h"
#include "../src/utils/credential_store.h"
#include "../src/utils/logger.h"
#include <chrono>
#include <thread>
#include <fstream>
#include <algorithm>
#define NOMINMAX  // Prevent Windows.h min/max macros
#include <windows.h>
#include <psapi.h>

using namespace baludesk;

// Helper function to get current process memory usage
size_t getCurrentMemoryUsage() {
    PROCESS_MEMORY_COUNTERS_EX pmc;
    if (GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS*)&pmc, sizeof(pmc))) {
        return pmc.WorkingSetSize;  // Physical memory in bytes
    }
    return 0;
}

std::string formatBytes(size_t bytes) {
    const char* units[] = {"B", "KB", "MB", "GB"};
    int unitIndex = 0;
    double size = static_cast<double>(bytes);

    while (size >= 1024.0 && unitIndex < 3) {
        size /= 1024.0;
        unitIndex++;
    }

    char buffer[64];
    snprintf(buffer, sizeof(buffer), "%.2f %s", size, units[unitIndex]);
    return std::string(buffer);
}

class MemoryLeakTest : public ::testing::Test {
protected:
    void SetUp() override {
        Logger::initialize("memory_leak_test.log", false);
    }

    void TearDown() override {
        // Force cleanup
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
};

// ============================================================================
// FileWatcher Memory Tests
// ============================================================================

TEST_F(MemoryLeakTest, FileWatcherRepeatedStartStop) {
    const int iterations = 1000;

    size_t initialMemory = getCurrentMemoryUsage();
    std::cout << "[Memory] Initial: " << formatBytes(initialMemory) << std::endl;

    std::string testDir = std::string(std::getenv("TEMP")) + "\\baludesk_memory_test";
    CreateDirectoryA(testDir.c_str(), NULL);

    for (int i = 0; i < iterations; ++i) {
        FileWatcher watcher;
        watcher.watch(testDir);
        watcher.stop();

        if (i % 100 == 0) {
            size_t currentMemory = getCurrentMemoryUsage();
            std::cout << "[Memory] Iteration " << i << ": " << formatBytes(currentMemory)
                      << " (+" << formatBytes(currentMemory - initialMemory) << ")" << std::endl;
        }
    }

    // Allow OS to reclaim memory
    std::this_thread::sleep_for(std::chrono::seconds(1));

    size_t finalMemory = getCurrentMemoryUsage();
    size_t memoryGrowth = finalMemory - initialMemory;

    std::cout << "[Memory] Final: " << formatBytes(finalMemory)
              << " (growth: " << formatBytes(memoryGrowth) << ")" << std::endl;

    // Allow up to 50MB growth for 1000 iterations (50KB per iteration average)
    EXPECT_LT(memoryGrowth, 50 * 1024 * 1024)
        << "Memory grew by " << formatBytes(memoryGrowth)
        << " over " << iterations << " iterations";

    RemoveDirectoryA(testDir.c_str());
}

TEST_F(MemoryLeakTest, FileWatcherEventProcessing) {
    const int iterations = 500;

    size_t initialMemory = getCurrentMemoryUsage();
    std::cout << "[Memory] Initial: " << formatBytes(initialMemory) << std::endl;

    std::string testDir = std::string(std::getenv("TEMP")) + "\\baludesk_memory_test";
    CreateDirectoryA(testDir.c_str(), NULL);

    FileWatcher watcher;
    int eventCount = 0;

    watcher.setCallback([&eventCount](const FileEvent&) {
        eventCount++;
    });

    watcher.watch(testDir);

    // Create and delete files repeatedly
    for (int i = 0; i < iterations; ++i) {
        std::string filename = testDir + "\\test_" + std::to_string(i) + ".txt";

        // Create file
        std::ofstream file(filename);
        file << "test content " << i;
        file.close();

        std::this_thread::sleep_for(std::chrono::milliseconds(10));

        // Delete file
        DeleteFileA(filename.c_str());

        if (i % 50 == 0) {
            size_t currentMemory = getCurrentMemoryUsage();
            std::cout << "[Memory] Files: " << i << ", Events: " << eventCount
                      << ", Memory: " << formatBytes(currentMemory) << std::endl;
        }
    }

    watcher.stop();
    std::this_thread::sleep_for(std::chrono::seconds(1));

    size_t finalMemory = getCurrentMemoryUsage();
    size_t memoryGrowth = finalMemory - initialMemory;

    std::cout << "[Memory] Final: " << formatBytes(finalMemory)
              << ", Events processed: " << eventCount
              << ", Growth: " << formatBytes(memoryGrowth) << std::endl;

    EXPECT_LT(memoryGrowth, 30 * 1024 * 1024)
        << "Memory grew by " << formatBytes(memoryGrowth);

    RemoveDirectoryA(testDir.c_str());
}

// ============================================================================
// CredentialStore Memory Tests
// ============================================================================

TEST_F(MemoryLeakTest, CredentialStoreRepeatedOperations) {
    const int iterations = 10000;

    size_t initialMemory = getCurrentMemoryUsage();
    std::cout << "[Memory] Initial: " << formatBytes(initialMemory) << std::endl;

    const std::string username = "memory_test_user";
    const std::string token = "test_token_for_memory_leak_detection_12345";

    for (int i = 0; i < iterations; ++i) {
        // Save
        CredentialStore::saveToken(username, token);

        // Load
        std::string loaded = CredentialStore::loadToken(username);

        // Has
        (void)CredentialStore::hasToken(username);

        // Delete
        CredentialStore::deleteToken(username);

        if (i % 1000 == 0 && i > 0) {
            size_t currentMemory = getCurrentMemoryUsage();
            std::cout << "[Memory] Iteration " << i << ": " << formatBytes(currentMemory)
                      << " (+" << formatBytes(currentMemory - initialMemory) << ")" << std::endl;
        }
    }

    std::this_thread::sleep_for(std::chrono::seconds(1));

    size_t finalMemory = getCurrentMemoryUsage();
    size_t memoryGrowth = finalMemory - initialMemory;

    std::cout << "[Memory] Final: " << formatBytes(finalMemory)
              << " (growth: " << formatBytes(memoryGrowth) << ")" << std::endl;

    // Allow up to 10MB growth for 10000 iterations (1KB per iteration)
    EXPECT_LT(memoryGrowth, 10 * 1024 * 1024)
        << "Memory grew by " << formatBytes(memoryGrowth);
}

// ============================================================================
// Long-Running Test (Simulates hours of operation)
// ============================================================================

TEST_F(MemoryLeakTest, LongRunningSimulation) {
    const int durationSeconds = 60;  // 1 minute (simulates 1 hour of operation)
    const int samplesPerSecond = 10;

    size_t initialMemory = getCurrentMemoryUsage();
    std::cout << "[Memory] Starting long-running test (" << durationSeconds << "s)" << std::endl;
    std::cout << "[Memory] Initial: " << formatBytes(initialMemory) << std::endl;

    auto startTime = std::chrono::steady_clock::now();
    int iteration = 0;
    size_t maxMemory = initialMemory;
    size_t minMemory = initialMemory;

    std::string testDir = std::string(std::getenv("TEMP")) + "\\baludesk_longrun_test";
    CreateDirectoryA(testDir.c_str(), NULL);

    FileWatcher watcher;
    watcher.watch(testDir);

    while (true) {
        auto now = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - startTime);

        if (elapsed.count() >= durationSeconds) {
            break;
        }

        // Simulate activity
        std::string filename = testDir + "\\test_" + std::to_string(iteration % 10) + ".txt";
        std::ofstream file(filename);
        file << "iteration " << iteration;
        file.close();

        // Credential operations
        CredentialStore::saveToken("longrun_user", "token_" + std::to_string(iteration));
        CredentialStore::loadToken("longrun_user");
        CredentialStore::deleteToken("longrun_user");

        iteration++;

        // Sample memory every 10th iteration
        if (iteration % samplesPerSecond == 0) {
            size_t currentMemory = getCurrentMemoryUsage();
            maxMemory = std::max(maxMemory, currentMemory);
            minMemory = std::min(minMemory, currentMemory);

            if (iteration % (samplesPerSecond * 10) == 0) {  // Log every 10 seconds
                std::cout << "[Memory] Time: " << elapsed.count() << "s"
                          << ", Iter: " << iteration
                          << ", Current: " << formatBytes(currentMemory)
                          << ", Min: " << formatBytes(minMemory)
                          << ", Max: " << formatBytes(maxMemory)
                          << std::endl;
            }
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    watcher.stop();
    std::this_thread::sleep_for(std::chrono::seconds(2));

    size_t finalMemory = getCurrentMemoryUsage();
    size_t memoryGrowth = finalMemory - initialMemory;
    size_t peakGrowth = maxMemory - initialMemory;

    std::cout << "\n[Memory] Long-running test complete:" << std::endl;
    std::cout << "  Initial: " << formatBytes(initialMemory) << std::endl;
    std::cout << "  Final:   " << formatBytes(finalMemory) << std::endl;
    std::cout << "  Min:     " << formatBytes(minMemory) << std::endl;
    std::cout << "  Max:     " << formatBytes(maxMemory) << std::endl;
    std::cout << "  Growth:  " << formatBytes(memoryGrowth) << std::endl;
    std::cout << "  Peak:    " << formatBytes(peakGrowth) << std::endl;
    std::cout << "  Iterations: " << iteration << std::endl;

    // Allow up to 100MB growth over 1 minute (scaled down from 1 hour)
    EXPECT_LT(memoryGrowth, 100 * 1024 * 1024)
        << "Memory grew by " << formatBytes(memoryGrowth) << " over " << durationSeconds << " seconds";

    // Peak memory shouldn't be more than 150MB above baseline
    EXPECT_LT(peakGrowth, 150 * 1024 * 1024)
        << "Peak memory was " << formatBytes(peakGrowth) << " above baseline";

    RemoveDirectoryA(testDir.c_str());
}

// ============================================================================
// Specific Leak Pattern Tests
// ============================================================================

TEST_F(MemoryLeakTest, StringAllocationPattern) {
    const int iterations = 100000;

    size_t initialMemory = getCurrentMemoryUsage();
    std::cout << "[Memory] Initial: " << formatBytes(initialMemory) << std::endl;

    // Simulate string-heavy operations (common in file paths, tokens, etc.)
    for (int i = 0; i < iterations; ++i) {
        std::string path = "C:\\Users\\TestUser\\Documents\\Folder" + std::to_string(i) + "\\file.txt";
        std::string token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload." + std::to_string(i);

        // Simulate processing
        (void)path.length();
        (void)token.length();

        // Strings should go out of scope here
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    size_t finalMemory = getCurrentMemoryUsage();
    size_t memoryGrowth = finalMemory - initialMemory;

    std::cout << "[Memory] Final: " << formatBytes(finalMemory)
              << " (growth: " << formatBytes(memoryGrowth) << ")" << std::endl;

    // Should have minimal growth (< 5MB) for string allocations
    EXPECT_LT(memoryGrowth, 5 * 1024 * 1024)
        << "Memory grew by " << formatBytes(memoryGrowth);
}

TEST_F(MemoryLeakTest, VectorResizePattern) {
    const int iterations = 1000;

    size_t initialMemory = getCurrentMemoryUsage();
    std::cout << "[Memory] Initial: " << formatBytes(initialMemory) << std::endl;

    for (int i = 0; i < iterations; ++i) {
        std::vector<std::string> paths;

        // Simulate building a large vector (like file list)
        for (int j = 0; j < 1000; ++j) {
            paths.push_back("C:\\path\\to\\file" + std::to_string(j) + ".txt");
        }

        // Vector should be destroyed here
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    size_t finalMemory = getCurrentMemoryUsage();
    size_t memoryGrowth = finalMemory - initialMemory;

    std::cout << "[Memory] Final: " << formatBytes(finalMemory)
              << " (growth: " << formatBytes(memoryGrowth) << ")" << std::endl;

    // Should have minimal growth (< 10MB)
    EXPECT_LT(memoryGrowth, 10 * 1024 * 1024)
        << "Memory grew by " << formatBytes(memoryGrowth);
}

// ============================================================================
// Memory Report Summary
// ============================================================================

TEST_F(MemoryLeakTest, GenerateMemorySummary) {
    std::cout << "\n";
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" << std::endl;
    std::cout << "  BaluDesk Memory Leak Test Summary" << std::endl;
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" << std::endl;
    std::cout << "  Platform: Windows" << std::endl;
    std::cout << "  Tool: GetProcessMemoryInfo (WorkingSetSize)" << std::endl;
    std::cout << "  Date: " << __DATE__ << " " << __TIME__ << std::endl;
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" << std::endl;
    std::cout << "\n";
    std::cout << "Tests run above check for:" << std::endl;
    std::cout << "  • FileWatcher start/stop cycles (1000x)" << std::endl;
    std::cout << "  • FileWatcher event processing (500 files)" << std::endl;
    std::cout << "  • CredentialStore operations (10000x)" << std::endl;
    std::cout << "  • Long-running simulation (1 minute)" << std::endl;
    std::cout << "  • String allocation patterns (100000x)" << std::endl;
    std::cout << "  • Vector resize patterns (1000x)" << std::endl;
    std::cout << "\n";
    std::cout << "All tests passed = No significant memory leaks detected" << std::endl;
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" << std::endl;
    std::cout << "\n";

    SUCCEED();
}
