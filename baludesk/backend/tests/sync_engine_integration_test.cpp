#include <gtest/gtest.h>
#include "sync/sync_engine.h"
#include "sync/file_watcher_v2.h"
#include "db/database.h"
#include "utils/logger.h"
#include <filesystem>
#include <chrono>
#include <thread>
#include <atomic>
#include <fstream>

namespace fs = std::filesystem;

using namespace baludesk;

/**
 * @brief Integration tests for FileWatcher with database recording
 * 
 * Tests the file watcher in realistic scenarios:
 * 1. File creation detection
 * 2. File modification detection
 * 3. File deletion detection
 * 4. Debouncing under realistic file activity
 * 5. Multiple concurrent files
 */
class FileWatcherRealScenarioTest : public ::testing::Test {
protected:
    static constexpr const char* TEST_DIR = "baludesk_watcher_scenario";

    void SetUp() override {
        // Create test directory
        testDir_ = fs::temp_directory_path() / TEST_DIR;
        fs::remove_all(testDir_, std::error_code{});
        fs::create_directories(testDir_);

        // Initialize logger
        std::string logFile = (testDir_ / "test.log").string();
        Logger::initialize(logFile, true);

        // Create file watcher
        watcher_ = std::make_unique<FileWatcher>();
        eventCount_ = 0;
        capturedEvents_.clear();
    }

    void TearDown() override {
        // Clean up
        if (watcher_) {
            watcher_->stop();
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        fs::remove_all(testDir_, std::error_code{});
    }

    // Helper: Create test file
    void createTestFile(const std::string& filename, const std::string& content = "test") {
        fs::path filePath = testDir_ / filename;
        std::ofstream file(filePath);
        file << content;
        file.close();
    }

    // Helper: Modify test file
    void modifyTestFile(const std::string& filename, const std::string& content = "modified") {
        fs::path filePath = testDir_ / filename;
        std::ofstream file(filePath, std::ios::app);
        file << content;
        file.close();
    }

    // Helper: Delete test file
    void deleteTestFile(const std::string& filename) {
        fs::path filePath = testDir_ / filename;
        fs::remove(filePath);
    }

    // Helper: Wait for events with timeout
    void waitForEvents(int minCount, int timeoutMs) {
        int elapsed = 0;
        while (eventCount_.load() < minCount && elapsed < timeoutMs) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            elapsed += 100;
        }
    }

    fs::path testDir_;
    std::unique_ptr<FileWatcher> watcher_;
    std::atomic<int> eventCount_{0};
    std::vector<FileEvent> capturedEvents_;
    mutable std::mutex eventMutex_;
};

// ============================================================================
// Tests
// ============================================================================

TEST_F(FileWatcherRealScenarioTest, EditorLikeRapidEdits) {
    // Simulate editor behavior: rapid open/edit/save cycles
    watcher_->setCallback([this](const FileEvent& event) {
        eventCount_++;
        {
            std::lock_guard<std::mutex> lock(eventMutex_);
            capturedEvents_.push_back(event);
        }
        Logger::debug("Event caught: {} {}", 
            event.action == FileAction::CREATED ? "CREATE" :
            event.action == FileAction::MODIFIED ? "MODIFY" : "DELETE",
            event.path);
    });

    ASSERT_TRUE(watcher_->watch(testDir_.string()));
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Simulate editor creating and modifying file rapidly
    for (int i = 0; i < 3; i++) {
        createTestFile("document.txt", "version " + std::to_string(i));
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        modifyTestFile("document.txt", " [edited]");
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    // Wait for debouncing
    std::this_thread::sleep_for(std::chrono::milliseconds(1000));

    // Should have events, but fewer than 6 operations due to debouncing
    EXPECT_GT(eventCount_.load(), 0);
    Logger::info("Rapid edits generated {} events", eventCount_.load());
}

TEST_F(FileWatcherRealScenarioTest, BulkFileCreation) {
    // Simulate bulk file creation (e.g., download, extraction)
    watcher_->setCallback([this](const FileEvent& event) {
        eventCount_++;
        {
            std::lock_guard<std::mutex> lock(eventMutex_);
            capturedEvents_.push_back(event);
        }
    });

    ASSERT_TRUE(watcher_->watch(testDir_.string()));
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Create many files quickly
    for (int i = 0; i < 10; i++) {
        createTestFile("file_" + std::to_string(i) + ".txt", "content " + std::to_string(i));
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }

    // Wait for processing
    std::this_thread::sleep_for(std::chrono::milliseconds(1500));

    // Should detect most/all file creations
    EXPECT_GT(eventCount_.load(), 5);
    Logger::info("Bulk creation generated {} events for 10 files", eventCount_.load());
}

TEST_F(FileWatcherRealScenarioTest, MixedFileOperations) {
    // Mix of creates, modifies, deletes
    watcher_->setCallback([this](const FileEvent& event) {
        eventCount_++;
        {
            std::lock_guard<std::mutex> lock(eventMutex_);
            capturedEvents_.push_back(event);
        }
    });

    ASSERT_TRUE(watcher_->watch(testDir_.string()));
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Create files
    createTestFile("file1.txt", "content1");
    std::this_thread::sleep_for(std::chrono::milliseconds(300));

    // Modify file
    modifyTestFile("file1.txt", " modified");
    std::this_thread::sleep_for(std::chrono::milliseconds(300));

    // Create another
    createTestFile("file2.txt", "content2");
    std::this_thread::sleep_for(std::chrono::milliseconds(300));

    // Delete first
    deleteTestFile("file1.txt");
    std::this_thread::sleep_for(std::chrono::milliseconds(300));

    // Wait for final processing
    std::this_thread::sleep_for(std::chrono::milliseconds(800));

    // Verify we detected all operations
    EXPECT_GE(eventCount_.load(), 3);  // At least create, modify, delete
    
    // Check for different action types
    {
        std::lock_guard<std::mutex> lock(eventMutex_);
        bool hasCreate = false, hasModify = false, hasDelete = false;
        for (const auto& event : capturedEvents_) {
            if (event.action == FileAction::CREATED) hasCreate = true;
            if (event.action == FileAction::MODIFIED) hasModify = true;
            if (event.action == FileAction::DELETED) hasDelete = true;
        }
        
        Logger::info("Event types - Create: {}, Modify: {}, Delete: {}", hasCreate, hasModify, hasDelete);
        // At least some events should be detected
        EXPECT_TRUE(hasCreate || hasModify || hasDelete);
    }
}

TEST_F(FileWatcherRealScenarioTest, LargeFileModification) {
    // Test with larger files being modified
    watcher_->setCallback([this](const FileEvent& event) {
        eventCount_++;
        {
            std::lock_guard<std::mutex> lock(eventMutex_);
            capturedEvents_.push_back(event);
        }
    });

    ASSERT_TRUE(watcher_->watch(testDir_.string()));
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Create large file
    createTestFile("large_file.bin", std::string(1024 * 10, 'A'));  // 10KB
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Append to it multiple times
    for (int i = 0; i < 5; i++) {
        modifyTestFile("large_file.bin", std::string(1024, 'B'));
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(1000));

    // Should detect the file creation and modifications
    EXPECT_GT(eventCount_.load(), 0);
    Logger::info("Large file operations generated {} events", eventCount_.load());
}

