#include <gtest/gtest.h>
#include "db/database.h"
#include "utils/logger.h"
#include <filesystem>
#include <thread>
#include <chrono>

using namespace baludesk;

// Test fixture for Database tests
class DatabaseTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Create temp directory for test database
        testDbDir_ = std::filesystem::temp_directory_path() / "baludesk_test_db";
        std::filesystem::create_directories(testDbDir_);
        
        testDbFile_ = (testDbDir_ / "test.db").string();
        
        // Initialize logger (silent mode for tests)
        std::string logFile = (testDbDir_ / "test.log").string();
        Logger::initialize(logFile, false);
        
        // Create database instance
        db_ = std::make_unique<Database>(testDbFile_);
        ASSERT_TRUE(db_->initialize());
    }

    void TearDown() override {
        // Close database first
        db_.reset();
        
        // CRITICAL: Shutdown logger BEFORE deleting directories
        Logger::shutdown();
        
        // Small delay to ensure Windows releases file handles
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        
        // Clean up test database
        if (std::filesystem::exists(testDbDir_)) {
            std::error_code ec;
            std::filesystem::remove_all(testDbDir_, ec);
            // Ignore errors on cleanup - test already passed/failed
        }
    }

    std::filesystem::path testDbDir_;
    std::string testDbFile_;
    std::unique_ptr<Database> db_;
};

// Test database initialization
TEST_F(DatabaseTest, Initialization) {
    ASSERT_TRUE(std::filesystem::exists(testDbFile_));
}

// Test add sync folder
TEST_F(DatabaseTest, AddSyncFolder) {
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/Documents";
    folder.remotePath = "/Documents";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;

    ASSERT_TRUE(db_->addSyncFolder(folder));
    
    // Retrieve and verify
    SyncFolder retrieved = db_->getSyncFolder(folder.id);
    EXPECT_EQ(retrieved.id, folder.id);
    EXPECT_EQ(retrieved.localPath, folder.localPath);
    EXPECT_EQ(retrieved.remotePath, folder.remotePath);
    EXPECT_EQ(retrieved.status, SyncStatus::IDLE);
    EXPECT_TRUE(retrieved.enabled);
}

// Test get sync folders
TEST_F(DatabaseTest, GetSyncFolders) {
    // Add multiple folders
    for (int i = 0; i < 3; i++) {
        SyncFolder folder;
        folder.id = db_->generateId();
        folder.localPath = "/home/user/folder" + std::to_string(i);
        folder.remotePath = "/folder" + std::to_string(i);
        folder.status = SyncStatus::IDLE;
        folder.enabled = true;
        
        ASSERT_TRUE(db_->addSyncFolder(folder));
    }
    
    auto folders = db_->getSyncFolders();
    EXPECT_EQ(folders.size(), 3);
}

// Test file metadata upsert
TEST_F(DatabaseTest, FileMetadataUpsert) {
    // First add a sync folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/test";
    folder.remotePath = "/test";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    db_->addSyncFolder(folder);

    // Add file metadata
    FileMetadata metadata;
    metadata.path = "/home/user/test/file.txt";
    metadata.folderId = folder.id;
    metadata.size = 1024;
    metadata.modifiedAt = "2026-01-04T12:00:00Z";
    metadata.checksum = "abc123";
    metadata.isDirectory = false;
    metadata.syncStatus = "synced";

    ASSERT_TRUE(db_->upsertFileMetadata(metadata));
    
    // Retrieve and verify
    auto retrieved = db_->getFileMetadata(metadata.path);
    ASSERT_TRUE(retrieved.has_value());
    EXPECT_EQ(retrieved->path, metadata.path);
    EXPECT_EQ(retrieved->size, metadata.size);
    EXPECT_EQ(retrieved->checksum, metadata.checksum);
}

// Test file metadata update
TEST_F(DatabaseTest, FileMetadataUpdate) {
    // Setup folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/test";
    folder.remotePath = "/test";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    db_->addSyncFolder(folder);

    // Initial metadata
    FileMetadata metadata;
    metadata.path = "/home/user/test/file.txt";
    metadata.folderId = folder.id;
    metadata.size = 1024;
    metadata.modifiedAt = "2026-01-04T12:00:00Z";
    metadata.checksum = "abc123";
    metadata.isDirectory = false;
    metadata.syncStatus = "synced";
    
    db_->upsertFileMetadata(metadata);

    // Update metadata
    metadata.size = 2048;
    metadata.checksum = "def456";
    metadata.modifiedAt = "2026-01-04T13:00:00Z";
    
    ASSERT_TRUE(db_->upsertFileMetadata(metadata));
    
    // Verify update
    auto retrieved = db_->getFileMetadata(metadata.path);
    ASSERT_TRUE(retrieved.has_value());
    EXPECT_EQ(retrieved->size, 2048);
    EXPECT_EQ(retrieved->checksum, "def456");
}

// Test conflict logging
TEST_F(DatabaseTest, LogConflict) {
    // Setup folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/test";
    folder.remotePath = "/test";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    db_->addSyncFolder(folder);

    Conflict conflict;
    conflict.id = db_->generateId();
    conflict.path = "/home/user/test/conflict.txt";
    conflict.folderId = folder.id;
    conflict.localModified = "2026-01-04T12:00:00Z";
    conflict.remoteModified = "2026-01-04T12:05:00Z";
    conflict.resolution = "";
    conflict.resolvedAt = "";

    ASSERT_TRUE(db_->logConflict(conflict));
    
    // Verify conflict exists in pending
    auto pending = db_->getPendingConflicts();
    EXPECT_EQ(pending.size(), 1);
    EXPECT_EQ(pending[0].id, conflict.id);
}

// Test delete file metadata
TEST_F(DatabaseTest, DeleteFileMetadata) {
    // Setup
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/test";
    folder.remotePath = "/test";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    db_->addSyncFolder(folder);

    FileMetadata metadata;
    metadata.path = "/home/user/test/file.txt";
    metadata.folderId = folder.id;
    metadata.size = 1024;
    metadata.modifiedAt = "2026-01-04T12:00:00Z";
    metadata.checksum = "abc123";
    metadata.isDirectory = false;
    metadata.syncStatus = "synced";
    
    db_->upsertFileMetadata(metadata);

    // Delete
    ASSERT_TRUE(db_->deleteFileMetadata(metadata.path));
    
    // Verify deletion
    auto retrieved = db_->getFileMetadata(metadata.path);
    EXPECT_FALSE(retrieved.has_value());
}
