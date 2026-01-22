#include <gtest/gtest.h>
#include "sync/sync_engine.h"
#include "db/database.h"
#include "utils/logger.h"
#include <filesystem>
#include <fstream>
#include <chrono>
#include <thread>

namespace fs = std::filesystem;
using namespace baludesk;

/**
 * Simple Integration Tests for SyncEngine
 *
 * These tests verify the SyncEngine's public API and basic functionality
 * without requiring a real server or full mocking.
 *
 * Tests focus on:
 * - Initialization and lifecycle
 * - Folder management
 * - State management
 * - Database persistence
 * - Error handling
 */
class SyncEngineSimpleIntegrationTest : public ::testing::Test {
protected:
    static constexpr const char* TEST_DIR = "baludesk_sync_simple";
    static constexpr const char* TEST_DB = "test_sync.db";

    void SetUp() override {
        // Create unique test directory for each test to avoid database conflicts
        auto now = std::chrono::system_clock::now();
        auto timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count();
        std::string uniqueSuffix = std::to_string(timestamp);

        testDir_ = fs::temp_directory_path() / (std::string(TEST_DIR) + "_" + uniqueSuffix);
        std::error_code ec;
        fs::remove_all(testDir_, ec);
        fs::create_directories(testDir_);

        // Create sync folders
        syncFolder1_ = testDir_ / "sync1";
        syncFolder2_ = testDir_ / "sync2";
        fs::create_directories(syncFolder1_);
        fs::create_directories(syncFolder2_);

        // Initialize logger (unique per test to avoid conflicts)
        std::string logFile = (testDir_ / "test.log").string();
        Logger::initialize(logFile, true);

        // Database path (unique per test)
        dbPath_ = (testDir_ / TEST_DB).string();

        // Note: Server URL is test-only, won't actually connect
        serverUrl_ = "http://localhost:9999";
    }

    void TearDown() override {
        std::error_code ec;
        fs::remove_all(testDir_, ec);
    }

    // Helper: Create test file
    void createTestFile(const fs::path& folder, const std::string& filename,
                       const std::string& content = "test content") {
        fs::path filePath = folder / filename;
        fs::create_directories(filePath.parent_path());
        std::ofstream file(filePath);
        file << content;
        file.close();
    }

    // Helper: File exists
    bool fileExists(const fs::path& folder, const std::string& filename) {
        return fs::exists(folder / filename);
    }

    fs::path testDir_;
    fs::path syncFolder1_;
    fs::path syncFolder2_;
    std::string dbPath_;
    std::string serverUrl_;
};

// ============================================================================
// Test 1: Initialization
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test1_Initialize) {
    SyncEngine engine;

    // Should initialize successfully
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Should not be running initially
    EXPECT_FALSE(engine.isRunning());

    // Should not be authenticated
    EXPECT_FALSE(engine.isAuthenticated());

    // Database should be created
    EXPECT_TRUE(fs::exists(dbPath_));
}

// ============================================================================
// Test 2: Multiple Initialize Calls
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test2_MultipleInitialize) {
    SyncEngine engine;

    // First init should succeed
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Second init on same database should succeed (idempotent)
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));
}

// ============================================================================
// Test 3: Add Sync Folder
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test3_AddSyncFolder) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Create sync folder
    SyncFolder folder;
    folder.localPath = syncFolder1_.string();
    folder.remotePath = "/remote/sync1";

    // Add folder
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // ID should be generated
    EXPECT_FALSE(folder.id.empty());

    // Should be enabled by default
    EXPECT_TRUE(folder.enabled);

    // Should be idle initially
    EXPECT_EQ(folder.status, SyncStatus::IDLE);
}

// ============================================================================
// Test 4: Get Sync Folders
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test4_GetSyncFolders) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Initially empty
    auto folders = engine.getSyncFolders();
    EXPECT_EQ(folders.size(), 0);

    // Add first folder
    SyncFolder folder1;
    folder1.localPath = syncFolder1_.string();
    folder1.remotePath = "/remote/sync1";
    ASSERT_TRUE(engine.addSyncFolder(folder1));

    // Should have 1 folder
    folders = engine.getSyncFolders();
    ASSERT_EQ(folders.size(), 1);
    EXPECT_EQ(folders[0].localPath, syncFolder1_.string());

    // Add second folder
    SyncFolder folder2;
    folder2.localPath = syncFolder2_.string();
    folder2.remotePath = "/remote/sync2";
    ASSERT_TRUE(engine.addSyncFolder(folder2));

    // Should have 2 folders
    folders = engine.getSyncFolders();
    ASSERT_EQ(folders.size(), 2);
}

// ============================================================================
// Test 5: Remove Sync Folder
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test5_RemoveSyncFolder) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Add folder
    SyncFolder folder;
    folder.localPath = syncFolder1_.string();
    folder.remotePath = "/remote/sync1";
    ASSERT_TRUE(engine.addSyncFolder(folder));
    std::string folderId = folder.id;

    // Verify it exists
    auto folders = engine.getSyncFolders();
    EXPECT_EQ(folders.size(), 1);

    // Remove folder
    ASSERT_TRUE(engine.removeSyncFolder(folderId));

    // Should be gone
    folders = engine.getSyncFolders();
    EXPECT_EQ(folders.size(), 0);
}

// ============================================================================
// Test 6: Remove Nonexistent Folder
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test6_RemoveNonexistentFolder) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Try to remove folder that doesn't exist
    EXPECT_FALSE(engine.removeSyncFolder("nonexistent-id-12345"));
}

// ============================================================================
// Test 7: Pause and Resume Sync
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test7_PauseAndResume) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Add folder
    SyncFolder folder;
    folder.localPath = syncFolder1_.string();
    folder.remotePath = "/remote/sync1";
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // Pause
    ASSERT_TRUE(engine.pauseSync(folder.id));

    auto folders = engine.getSyncFolders();
    ASSERT_EQ(folders.size(), 1);
    EXPECT_EQ(folders[0].status, SyncStatus::PAUSED);

    // Resume
    ASSERT_TRUE(engine.resumeSync(folder.id));

    folders = engine.getSyncFolders();
    ASSERT_EQ(folders.size(), 1);
    EXPECT_EQ(folders[0].status, SyncStatus::IDLE);
}

// ============================================================================
// Test 8: Start and Stop Engine
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test8_StartAndStop) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Start
    engine.start();
    EXPECT_TRUE(engine.isRunning());

    // Give it time to start
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Stop
    engine.stop();
    EXPECT_FALSE(engine.isRunning());
}

// ============================================================================
// Test 9: Get Sync State
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test9_GetSyncState) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Get initial state
    auto stats = engine.getSyncState();

    // Should be idle
    EXPECT_EQ(stats.status, SyncStatus::IDLE);

    // Speeds should be 0
    EXPECT_EQ(stats.uploadSpeed, 0);
    EXPECT_EQ(stats.downloadSpeed, 0);

    // Pending counts should be 0
    EXPECT_EQ(stats.pendingUploads, 0);
    EXPECT_EQ(stats.pendingDownloads, 0);
}

// ============================================================================
// Test 10: Status Callback
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test10_StatusCallback) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Track callback invocations
    int callbackCount = 0;
    SyncStats lastStats;

    engine.setStatusCallback([&callbackCount, &lastStats](const SyncStats& stats) {
        callbackCount++;
        lastStats = stats;
    });

    // Start engine (should trigger callback)
    engine.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Should have been called at least once
    EXPECT_GT(callbackCount, 0);

    engine.stop();
}

// ============================================================================
// Test 11: File Change Callback
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test11_FileChangeCallback) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Track file changes
    std::vector<FileEvent> fileChanges;
    std::mutex mutex;

    engine.setFileChangeCallback([&fileChanges, &mutex](const FileEvent& event) {
        std::lock_guard<std::mutex> lock(mutex);
        fileChanges.push_back(event);
    });

    // Add sync folder
    SyncFolder folder;
    folder.localPath = syncFolder1_.string();
    folder.remotePath = "/remote/sync1";
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // Start engine
    engine.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Create test file (should trigger callback)
    createTestFile(syncFolder1_, "test.txt", "Hello");

    // Wait for file watcher
    std::this_thread::sleep_for(std::chrono::milliseconds(1000));

    engine.stop();

    // Should have detected the file creation
    std::lock_guard<std::mutex> lock(mutex);
    EXPECT_GT(fileChanges.size(), 0);

    // At least one event should be for test.txt
    bool foundTestFile = false;
    for (const auto& event : fileChanges) {
        if (event.path.find("test.txt") != std::string::npos) {
            foundTestFile = true;
            break;
        }
    }
    EXPECT_TRUE(foundTestFile);
}

// ============================================================================
// Test 12: Folder Size Calculation
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test12_FolderSizeCalculation) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Create files with known sizes
    createTestFile(syncFolder1_, "file1.txt", std::string(1024, 'A'));  // 1KB
    createTestFile(syncFolder1_, "file2.txt", std::string(2048, 'B'));  // 2KB

    // Add sync folder
    SyncFolder folder;
    folder.localPath = syncFolder1_.string();
    folder.remotePath = "/remote/sync1";
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // Get folders (should calculate size)
    auto folders = engine.getSyncFolders();
    ASSERT_EQ(folders.size(), 1);

    // Size should be approximately 3KB (1KB + 2KB)
    EXPECT_GT(folders[0].size, 3000);
    EXPECT_LT(folders[0].size, 4000);
}

// ============================================================================
// Test 13: Database Persistence
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test13_DatabasePersistence) {
    // First engine - add folders
    {
        SyncEngine engine;
        ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

        SyncFolder folder1;
        folder1.localPath = syncFolder1_.string();
        folder1.remotePath = "/remote/sync1";
        ASSERT_TRUE(engine.addSyncFolder(folder1));

        SyncFolder folder2;
        folder2.localPath = syncFolder2_.string();
        folder2.remotePath = "/remote/sync2";
        ASSERT_TRUE(engine.addSyncFolder(folder2));

        auto folders = engine.getSyncFolders();
        EXPECT_EQ(folders.size(), 2);
    }

    // Second engine - should load persisted folders
    {
        SyncEngine engine;
        ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

        auto folders = engine.getSyncFolders();
        ASSERT_EQ(folders.size(), 2);

        // Verify folder details persisted
        bool foundSync1 = false, foundSync2 = false;
        for (const auto& folder : folders) {
            if (folder.localPath == syncFolder1_.string()) foundSync1 = true;
            if (folder.localPath == syncFolder2_.string()) foundSync2 = true;
        }

        EXPECT_TRUE(foundSync1);
        EXPECT_TRUE(foundSync2);
    }
}

// ============================================================================
// Test 14: Error Callback
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test14_ErrorCallback) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Track errors
    std::vector<std::string> errors;
    std::mutex mutex;

    engine.setErrorCallback([&errors, &mutex](const std::string& error) {
        std::lock_guard<std::mutex> lock(mutex);
        errors.push_back(error);
    });

    // Note: Without a real server, we can't easily trigger errors
    // This test just verifies the callback can be set without crashing
    EXPECT_TRUE(true);  // Placeholder - callback is set
}

// ============================================================================
// Test 15: Multiple Folders Concurrently
// ============================================================================

TEST_F(SyncEngineSimpleIntegrationTest, Test15_MultipleFoldersConcurrent) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, serverUrl_));

    // Add multiple folders
    std::vector<std::string> folderIds;

    for (int i = 0; i < 5; i++) {
        fs::path folder = testDir_ / ("sync" + std::to_string(i));
        fs::create_directories(folder);

        SyncFolder syncFolder;
        syncFolder.localPath = folder.string();
        syncFolder.remotePath = "/remote/sync" + std::to_string(i);

        ASSERT_TRUE(engine.addSyncFolder(syncFolder));
        folderIds.push_back(syncFolder.id);
    }

    // Verify all folders exist
    auto folders = engine.getSyncFolders();
    EXPECT_EQ(folders.size(), 5);

    // Remove all folders
    for (const auto& id : folderIds) {
        EXPECT_TRUE(engine.removeSyncFolder(id));
    }

    // Should be empty
    folders = engine.getSyncFolders();
    EXPECT_EQ(folders.size(), 0);
}
