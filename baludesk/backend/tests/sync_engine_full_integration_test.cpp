#include <gtest/gtest.h>
#include "sync/sync_engine.h"
#include "api/http_client.h"
#include "db/database.h"
#include "utils/logger.h"
#include <filesystem>
#include <fstream>
#include <chrono>
#include <thread>

namespace fs = std::filesystem;
using namespace baludesk;

// ============================================================================
// Mock HttpClient for Testing
// ============================================================================

class MockHttpClient : public HttpClient {
public:
    MockHttpClient(const std::string& serverUrl) : HttpClient(serverUrl) {}

    // Track uploaded files
    std::vector<std::pair<std::string, std::string>> uploadedFiles_;  // (localPath, remotePath)
    std::vector<std::pair<std::string, std::string>> downloadedFiles_;  // (remotePath, localPath)
    std::vector<std::string> deletedFiles_;

    // Control behavior
    bool shouldFailUpload_ = false;
    bool shouldFailDownload_ = false;
    int failuresBeforeSuccess_ = 0;
    int uploadAttempts_ = 0;
    int downloadAttempts_ = 0;

    // Remote file storage simulation
    std::map<std::string, std::string> remoteFiles_;  // remotePath -> content

    bool login(const std::string& username, const std::string& password) override {
        if (username == "testuser" && password == "testpass") {
            authToken_ = "mock-jwt-token-12345";
            return true;
        }
        return false;
    }

    bool uploadFile(const std::string& localPath, const std::string& remotePath) override {
        uploadAttempts_++;

        // Simulate failures before success
        if (failuresBeforeSuccess_ > 0 && uploadAttempts_ <= failuresBeforeSuccess_) {
            return false;
        }

        if (shouldFailUpload_) {
            return false;
        }

        // Read local file and store in "remote"
        if (fs::exists(localPath)) {
            std::ifstream file(localPath);
            std::string content((std::istreambuf_iterator<char>(file)),
                               std::istreambuf_iterator<char>());
            remoteFiles_[remotePath] = content;
            uploadedFiles_.push_back({localPath, remotePath});
            return true;
        }

        return false;
    }

    bool downloadFile(const std::string& remotePath, const std::string& localPath) override {
        downloadAttempts_++;

        // Simulate failures before success
        if (failuresBeforeSuccess_ > 0 && downloadAttempts_ <= failuresBeforeSuccess_) {
            return false;
        }

        if (shouldFailDownload_) {
            return false;
        }

        // Check if file exists in remote storage
        if (remoteFiles_.find(remotePath) != remoteFiles_.end()) {
            // Create parent directories
            fs::create_directories(fs::path(localPath).parent_path());

            // Write file
            std::ofstream file(localPath);
            file << remoteFiles_[remotePath];
            file.close();

            downloadedFiles_.push_back({remotePath, localPath});
            return true;
        }

        return false;
    }

    bool downloadFileWithProgress(const std::string& remotePath,
                                  const std::string& localPath,
                                  std::function<void(const DownloadProgress&)> callback) override {
        // Simple wrapper around downloadFile for testing
        bool success = downloadFile(remotePath, localPath);

        if (success && callback) {
            DownloadProgress progress;
            progress.totalBytes = remoteFiles_[remotePath].size();
            progress.bytesDownloaded = progress.totalBytes;
            progress.percentComplete = 100;
            progress.speedBytesPerSec = 1000000;  // 1MB/s
            callback(progress);
        }

        return success;
    }

    bool deleteFile(const std::string& remotePath) override {
        if (remoteFiles_.find(remotePath) != remoteFiles_.end()) {
            remoteFiles_.erase(remotePath);
            deletedFiles_.push_back(remotePath);
            return true;
        }
        return false;
    }

    std::vector<RemoteChange> getChangesSince(const std::string& timestamp) override {
        // Return empty for now - can be extended for more complex tests
        return {};
    }

    void reset() {
        uploadedFiles_.clear();
        downloadedFiles_.clear();
        deletedFiles_.clear();
        uploadAttempts_ = 0;
        downloadAttempts_ = 0;
        shouldFailUpload_ = false;
        shouldFailDownload_ = false;
        failuresBeforeSuccess_ = 0;
    }
};

// ============================================================================
// Integration Test Fixture
// ============================================================================

class SyncEngineIntegrationTest : public ::testing::Test {
protected:
    static constexpr const char* TEST_DIR = "baludesk_sync_integration";
    static constexpr const char* TEST_DB = "test_sync.db";

    void SetUp() override {
        // Create test directory
        testDir_ = fs::temp_directory_path() / TEST_DIR;
        std::error_code ec;
        fs::remove_all(testDir_, ec);
        fs::create_directories(testDir_);

        // Create sync folder
        syncFolder_ = testDir_ / "sync";
        fs::create_directories(syncFolder_);

        // Initialize logger
        std::string logFile = (testDir_ / "test.log").string();
        Logger::initialize(logFile, true);

        // Database path
        dbPath_ = (testDir_ / TEST_DB).string();
    }

    void TearDown() override {
        std::error_code ec;
        fs::remove_all(testDir_, ec);
    }

    // Helper: Create test file
    void createTestFile(const std::string& filename, const std::string& content = "test content") {
        fs::path filePath = syncFolder_ / filename;
        fs::create_directories(filePath.parent_path());
        std::ofstream file(filePath);
        file << content;
        file.close();
    }

    // Helper: Read test file
    std::string readTestFile(const std::string& filename) {
        fs::path filePath = syncFolder_ / filename;
        if (!fs::exists(filePath)) {
            return "";
        }
        std::ifstream file(filePath);
        return std::string((std::istreambuf_iterator<char>(file)),
                          std::istreambuf_iterator<char>());
    }

    // Helper: Wait for async operations
    void waitForSync(int milliseconds = 500) {
        std::this_thread::sleep_for(std::chrono::milliseconds(milliseconds));
    }

    fs::path testDir_;
    fs::path syncFolder_;
    std::string dbPath_;
};

// ============================================================================
// Integration Tests
// ============================================================================

TEST_F(SyncEngineIntegrationTest, InitializeAndLogin) {
    SyncEngine engine;

    // Initialize
    ASSERT_TRUE(engine.initialize(dbPath_, "http://localhost:3001"));
    EXPECT_FALSE(engine.isAuthenticated());

    // Login
    ASSERT_TRUE(engine.login("testuser", "testpass"));
    EXPECT_TRUE(engine.isAuthenticated());

    // Logout
    engine.logout();
    EXPECT_FALSE(engine.isAuthenticated());
}

TEST_F(SyncEngineIntegrationTest, AddAndRemoveSyncFolder) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, "http://localhost:3001"));
    ASSERT_TRUE(engine.login("testuser", "testpass"));

    // Add sync folder
    SyncFolder folder;
    folder.localPath = syncFolder_.string();
    folder.remotePath = "/remote/sync";

    ASSERT_TRUE(engine.addSyncFolder(folder));
    EXPECT_FALSE(folder.id.empty());  // ID should be generated

    // Verify folder exists
    auto folders = engine.getSyncFolders();
    ASSERT_EQ(folders.size(), 1);
    EXPECT_EQ(folders[0].localPath, syncFolder_.string());
    EXPECT_EQ(folders[0].remotePath, "/remote/sync");

    // Remove folder
    ASSERT_TRUE(engine.removeSyncFolder(folder.id));

    folders = engine.getSyncFolders();
    EXPECT_EQ(folders.size(), 0);
}

TEST_F(SyncEngineIntegrationTest, UploadFlow_LocalFileToServer) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, "http://localhost:3001"));
    ASSERT_TRUE(engine.login("testuser", "testpass"));

    // Get mock HTTP client
    auto* mockHttp = dynamic_cast<MockHttpClient*>(engine.getDatabase()->getHttpClient());
    ASSERT_NE(mockHttp, nullptr);

    // Add sync folder
    SyncFolder folder;
    folder.localPath = syncFolder_.string();
    folder.remotePath = "/remote/sync";
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // Create test file
    createTestFile("test.txt", "Hello World");

    // Trigger sync
    engine.triggerBidirectionalSync(folder.id);
    waitForSync(1000);

    // Verify upload
    ASSERT_GT(mockHttp->uploadedFiles_.size(), 0);
    auto uploaded = mockHttp->uploadedFiles_[0];
    EXPECT_TRUE(uploaded.first.find("test.txt") != std::string::npos);
    EXPECT_TRUE(uploaded.second.find("/remote/sync") != std::string::npos);

    // Verify remote file content
    EXPECT_EQ(mockHttp->remoteFiles_["/remote/sync/test.txt"], "Hello World");
}

TEST_F(SyncEngineIntegrationTest, DownloadFlow_ServerFileToLocal) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, "http://localhost:3001"));
    ASSERT_TRUE(engine.login("testuser", "testpass"));

    // Get mock HTTP client
    auto* mockHttp = dynamic_cast<MockHttpClient*>(engine.getDatabase()->getHttpClient());
    ASSERT_NE(mockHttp, nullptr);

    // Add sync folder
    SyncFolder folder;
    folder.localPath = syncFolder_.string();
    folder.remotePath = "/remote/sync";
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // Simulate remote file
    mockHttp->remoteFiles_["/remote/sync/remote.txt"] = "Remote Content";

    // Trigger download
    engine.downloadFile("/remote/sync/remote.txt",
                       (syncFolder_ / "remote.txt").string());
    waitForSync();

    // Verify download
    ASSERT_TRUE(fs::exists(syncFolder_ / "remote.txt"));
    EXPECT_EQ(readTestFile("remote.txt"), "Remote Content");

    ASSERT_GT(mockHttp->downloadedFiles_.size(), 0);
    auto downloaded = mockHttp->downloadedFiles_[0];
    EXPECT_EQ(downloaded.first, "/remote/sync/remote.txt");
}

TEST_F(SyncEngineIntegrationTest, ConflictDetection_BothModified) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, "http://localhost:3001"));
    ASSERT_TRUE(engine.login("testuser", "testpass"));

    // Get mock HTTP client
    auto* mockHttp = dynamic_cast<MockHttpClient*>(engine.getDatabase()->getHttpClient());
    ASSERT_NE(mockHttp, nullptr);

    // Add sync folder
    SyncFolder folder;
    folder.localPath = syncFolder_.string();
    folder.remotePath = "/remote/sync";
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // Create local file
    createTestFile("conflict.txt", "Local Version");

    // Create different remote version
    mockHttp->remoteFiles_["/remote/sync/conflict.txt"] = "Remote Version";

    // Trigger sync - should detect conflict
    engine.triggerBidirectionalSync(folder.id);
    waitForSync(1000);

    // Check if conflict was detected and logged to database
    // Note: This requires ConflictResolver to be working
    // For now, we just verify that the sync completed without crashing
    EXPECT_TRUE(engine.getSyncState().status != SyncStatus::SYNC_ERROR);
}

TEST_F(SyncEngineIntegrationTest, RetryLogic_NetworkFailure) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, "http://localhost:3001"));
    ASSERT_TRUE(engine.login("testuser", "testpass"));

    // Get mock HTTP client
    auto* mockHttp = dynamic_cast<MockHttpClient*>(engine.getDatabase()->getHttpClient());
    ASSERT_NE(mockHttp, nullptr);

    // Configure to fail 2 times, then succeed on 3rd attempt
    mockHttp->failuresBeforeSuccess_ = 2;

    // Add sync folder
    SyncFolder folder;
    folder.localPath = syncFolder_.string();
    folder.remotePath = "/remote/sync";
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // Create test file
    createTestFile("retry.txt", "Retry Test");

    // Trigger sync
    engine.triggerBidirectionalSync(folder.id);
    waitForSync(3000);  // Longer wait for retries

    // Verify that upload eventually succeeded
    EXPECT_EQ(mockHttp->uploadAttempts_, 3);  // Should have tried 3 times
    ASSERT_GT(mockHttp->uploadedFiles_.size(), 0);  // Should have succeeded
}

TEST_F(SyncEngineIntegrationTest, BidirectionalSync_MultipleFiles) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, "http://localhost:3001"));
    ASSERT_TRUE(engine.login("testuser", "testpass"));

    // Get mock HTTP client
    auto* mockHttp = dynamic_cast<MockHttpClient*>(engine.getDatabase()->getHttpClient());
    ASSERT_NE(mockHttp, nullptr);

    // Add sync folder
    SyncFolder folder;
    folder.localPath = syncFolder_.string();
    folder.remotePath = "/remote/sync";
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // Create multiple local files
    createTestFile("file1.txt", "Content 1");
    createTestFile("file2.txt", "Content 2");
    createTestFile("file3.txt", "Content 3");

    // Create remote files
    mockHttp->remoteFiles_["/remote/sync/remote1.txt"] = "Remote 1";
    mockHttp->remoteFiles_["/remote/sync/remote2.txt"] = "Remote 2";

    // Trigger sync
    engine.triggerBidirectionalSync(folder.id);
    waitForSync(2000);

    // Verify uploads (3 local files)
    EXPECT_GE(mockHttp->uploadedFiles_.size(), 3);

    // Note: Downloads won't work without proper remote change detection
    // which requires mocking getChangesSince()
}

TEST_F(SyncEngineIntegrationTest, PauseAndResumeSync) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, "http://localhost:3001"));
    ASSERT_TRUE(engine.login("testuser", "testpass"));

    // Add sync folder
    SyncFolder folder;
    folder.localPath = syncFolder_.string();
    folder.remotePath = "/remote/sync";
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // Pause sync
    ASSERT_TRUE(engine.pauseSync(folder.id));

    auto folders = engine.getSyncFolders();
    ASSERT_EQ(folders.size(), 1);
    EXPECT_EQ(folders[0].status, SyncStatus::PAUSED);

    // Resume sync
    ASSERT_TRUE(engine.resumeSync(folder.id));

    folders = engine.getSyncFolders();
    ASSERT_EQ(folders.size(), 1);
    EXPECT_EQ(folders[0].status, SyncStatus::IDLE);
}

TEST_F(SyncEngineIntegrationTest, UploadFailure_ErrorHandling) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, "http://localhost:3001"));
    ASSERT_TRUE(engine.login("testuser", "testpass"));

    // Get mock HTTP client
    auto* mockHttp = dynamic_cast<MockHttpClient*>(engine.getDatabase()->getHttpClient());
    ASSERT_NE(mockHttp, nullptr);

    // Configure to always fail
    mockHttp->shouldFailUpload_ = true;

    // Add sync folder
    SyncFolder folder;
    folder.localPath = syncFolder_.string();
    folder.remotePath = "/remote/sync";
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // Create test file
    createTestFile("fail.txt", "This should fail");

    // Set error callback
    std::string lastError;
    engine.setErrorCallback([&lastError](const std::string& error) {
        lastError = error;
    });

    // Trigger sync
    engine.uploadFile((syncFolder_ / "fail.txt").string(), "/remote/sync/fail.txt");
    waitForSync();

    // Verify that upload failed
    EXPECT_EQ(mockHttp->uploadedFiles_.size(), 0);

    // Verify error state
    auto stats = engine.getSyncState();
    EXPECT_EQ(stats.status, SyncStatus::SYNC_ERROR);
}

TEST_F(SyncEngineIntegrationTest, StatusCallbacks_SyncStateUpdates) {
    SyncEngine engine;
    ASSERT_TRUE(engine.initialize(dbPath_, "http://localhost:3001"));
    ASSERT_TRUE(engine.login("testuser", "testpass"));

    // Track status updates
    std::vector<SyncStatus> statusUpdates;
    engine.setStatusCallback([&statusUpdates](const SyncStats& stats) {
        statusUpdates.push_back(stats.status);
    });

    // Add sync folder
    SyncFolder folder;
    folder.localPath = syncFolder_.string();
    folder.remotePath = "/remote/sync";
    ASSERT_TRUE(engine.addSyncFolder(folder));

    // Create test file and trigger sync
    createTestFile("status.txt", "Status Test");
    engine.triggerBidirectionalSync(folder.id);
    waitForSync(1000);

    // Verify we got status updates
    EXPECT_GT(statusUpdates.size(), 0);

    // Should include SYNCING state
    bool hadSyncing = false;
    for (auto status : statusUpdates) {
        if (status == SyncStatus::SYNCING) {
            hadSyncing = true;
            break;
        }
    }
    EXPECT_TRUE(hadSyncing);
}

// ============================================================================
// Main
// ============================================================================

// Note: These tests require proper MockHttpClient integration with SyncEngine
// The SyncEngine constructor needs to be modified to accept a mock HttpClient
// or we need dependency injection. For now, these tests serve as a blueprint.
