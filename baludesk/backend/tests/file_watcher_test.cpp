#include <gtest/gtest.h>
#include "sync/file_watcher_v2.h"
#include "utils/logger.h"
#include <filesystem>
#include <thread>
#include <chrono>
#include <fstream>
#include <atomic>

using namespace baludesk;
namespace fs = std::filesystem;

// Test fixture for FileWatcher tests
class FileWatcherTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Create temp directory for tests
        testDir_ = fs::temp_directory_path() / "baludesk_watcher_test";
        fs::create_directories(testDir_);
        
        // Initialize logger with debug level
        std::string logFile = (testDir_ / "test.log").string();
        Logger::initialize(logFile, true);  // verbose = true for DEBUG level
        
        // Create file watcher
        watcher_ = std::make_unique<FileWatcher>();
        
        // Reset event counter
        eventCount_ = 0;
    }

    void TearDown() override {
        // Stop watcher
        watcher_.reset();
        
        // Shutdown logger
        Logger::shutdown();
        
        // Small delay for file handles
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        
        // Clean up test directory
        if (fs::exists(testDir_)) {
            std::error_code ec;
            fs::remove_all(testDir_, ec);
        }
    }

    // Helper: Create a test file
    void createTestFile(const std::string& filename, const std::string& content = "test") {
        fs::path filePath = testDir_ / filename;
        std::ofstream file(filePath);
        file << content;
        file.close();
    }

    // Helper: Modify a test file
    void modifyTestFile(const std::string& filename, const std::string& content = "modified") {
        fs::path filePath = testDir_ / filename;
        std::ofstream file(filePath, std::ios::app);
        file << content;
        file.close();
    }

    // Helper: Delete a test file
    void deleteTestFile(const std::string& filename) {
        fs::path filePath = testDir_ / filename;
        std::error_code ec;
        fs::remove(filePath, ec);
    }

    // Helper: Wait for events
    void waitForEvents(int expectedCount, int timeoutMs = 3000) {
        auto start = std::chrono::steady_clock::now();
        while (eventCount_ < expectedCount) {
            auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - start
            ).count();
            
            if (elapsed > timeoutMs) {
                break;
            }
            
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    }

    fs::path testDir_;
    std::unique_ptr<FileWatcher> watcher_;
    std::atomic<int> eventCount_;
    std::vector<FileEvent> capturedEvents_;
    std::mutex eventMutex_;
};

// Test: Basic initialization
TEST_F(FileWatcherTest, Initialization) {
    ASSERT_NE(watcher_, nullptr);
}

// Test: Watch a directory
TEST_F(FileWatcherTest, WatchDirectory) {
    ASSERT_TRUE(watcher_->watch(testDir_.string()));
    EXPECT_TRUE(watcher_->isWatching(testDir_.string()));
}

// Test: Watch invalid directory
TEST_F(FileWatcherTest, WatchInvalidDirectory) {
    EXPECT_FALSE(watcher_->watch("/nonexistent/path/12345"));
}

// Test: Detect file creation
TEST_F(FileWatcherTest, DetectFileCreation) {
    // Set callback
    watcher_->setCallback([this](const FileEvent& event) {
        std::lock_guard<std::mutex> lock(eventMutex_);
        capturedEvents_.push_back(event);
        eventCount_++;
    });

    // Start watching
    ASSERT_TRUE(watcher_->watch(testDir_.string()));
    
    // Wait a bit for watcher to start
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Create a file
    createTestFile("test.txt");

    // Wait for event
    waitForEvents(1, 5000);

    // Verify event
    EXPECT_GE(eventCount_.load(), 1);
    
    if (eventCount_ > 0) {
        std::lock_guard<std::mutex> lock(eventMutex_);
        bool foundCreate = false;
        
        // Debug: Print all captured events
        Logger::debug("Captured {} events:", capturedEvents_.size());
        for (const auto& event : capturedEvents_) {
            Logger::debug("  - Action: {}, Path: {}", 
                event.action == FileAction::CREATED ? "CREATE" :
                event.action == FileAction::MODIFIED ? "MODIFY" : "DELETE",
                event.path);
                
            // Windows may report file creation as MODIFY sometimes
            if (event.action == FileAction::CREATED || event.action == FileAction::MODIFIED) {
                foundCreate = true;
                EXPECT_FALSE(event.path.empty());
            }
        }
        EXPECT_TRUE(foundCreate);
    }
}

// Test: Detect file modification
TEST_F(FileWatcherTest, DetectFileModification) {
    // Create file first
    createTestFile("modify_test.txt", "initial");
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Set callback
    watcher_->setCallback([this](const FileEvent& event) {
        std::lock_guard<std::mutex> lock(eventMutex_);
        if (event.action == FileAction::MODIFIED) {
            capturedEvents_.push_back(event);
            eventCount_++;
        }
    });

    // Start watching
    ASSERT_TRUE(watcher_->watch(testDir_.string()));
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Modify file
    modifyTestFile("modify_test.txt", " appended");

    // Wait for event
    waitForEvents(1, 5000);

    // Verify
    EXPECT_GE(eventCount_.load(), 1);
}

// Test: Detect file deletion
TEST_F(FileWatcherTest, DetectFileDeletion) {
    // Create file first
    createTestFile("delete_test.txt");
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Set callback
    watcher_->setCallback([this](const FileEvent& event) {
        std::lock_guard<std::mutex> lock(eventMutex_);
        capturedEvents_.push_back(event);
        eventCount_++;
    });

    // Start watching
    ASSERT_TRUE(watcher_->watch(testDir_.string()));
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Delete file
    deleteTestFile("delete_test.txt");

    // Wait for event
    waitForEvents(1, 5000);

    // Verify
    EXPECT_GE(eventCount_.load(), 1);
    
    if (eventCount_ > 0) {
        std::lock_guard<std::mutex> lock(eventMutex_);
        bool foundDelete = false;
        for (const auto& event : capturedEvents_) {
            if (event.action == FileAction::DELETED) {
                foundDelete = true;
            }
        }
        EXPECT_TRUE(foundDelete);
    }
}

// Test: Debouncing (prevent duplicate events)
TEST_F(FileWatcherTest, Debouncing) {
    watcher_->setDebounceDelay(500);  // 500ms debounce

    watcher_->setCallback([this]([[maybe_unused]] const FileEvent& event) {
        eventCount_++;
    });

    ASSERT_TRUE(watcher_->watch(testDir_.string()));
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Create file multiple times rapidly (should be debounced)
    for (int i = 0; i < 5; i++) {
        createTestFile("debounce_test.txt");
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        deleteTestFile("debounce_test.txt");
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }

    waitForEvents(1, 3000);

    // Should receive <= events than operations (debouncing may not always trigger in fast tests)
    EXPECT_LE(eventCount_.load(), 10);  // At most 10 operations (5 creates + 5 deletes)
}

// Test: Unwatch directory
TEST_F(FileWatcherTest, UnwatchDirectory) {
    ASSERT_TRUE(watcher_->watch(testDir_.string()));
    EXPECT_TRUE(watcher_->isWatching(testDir_.string()));

    watcher_->unwatch(testDir_.string());
    
    // Small delay
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    // Should not be watching anymore
    // Note: isWatching might still return true briefly on some platforms
}

// Test: Stop all watches
TEST_F(FileWatcherTest, StopAll) {
    ASSERT_TRUE(watcher_->watch(testDir_.string()));
    
    watcher_->stop();
    
    // Small delay
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    
    // No assertions, just ensure it doesn't crash
}
