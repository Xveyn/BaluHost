#include <gtest/gtest.h>
#include "sync/conflict_resolver.h"
#include "db/database.h"
#include "api/http_client.h"
#include "utils/logger.h"
#include <filesystem>
#include <fstream>
#include <thread>
#include <chrono>

using namespace baludesk;
namespace fs = std::filesystem;

// ============================================================================
// Mock HttpClient for testing
// ============================================================================

class MockHttpClient : public HttpClient {
public:
    MockHttpClient() : HttpClient("http://mock-server") {}

    // Track operations
    std::vector<std::pair<std::string, std::string>> uploads;   // (local, remote)
    std::vector<std::pair<std::string, std::string>> downloads; // (remote, local)

    // Control behavior
    bool shouldFailUpload = false;
    bool shouldFailDownload = false;

    // Simulated remote file storage
    std::map<std::string, std::string> remoteFiles; // path -> content

    bool uploadFile(const std::string& localPath, const std::string& remotePath) override {
        if (shouldFailUpload) return false;

        // Read local file
        std::ifstream file(localPath);
        if (!file.is_open()) return false;

        std::string content((std::istreambuf_iterator<char>(file)),
                           std::istreambuf_iterator<char>());

        remoteFiles[remotePath] = content;
        uploads.push_back({localPath, remotePath});
        return true;
    }

    bool downloadFile(const std::string& remotePath, const std::string& localPath) override {
        if (shouldFailDownload) return false;

        // Check if remote file exists
        if (remoteFiles.find(remotePath) == remoteFiles.end()) {
            return false;
        }

        // Write to local file
        std::ofstream file(localPath);
        if (!file.is_open()) return false;

        file << remoteFiles[remotePath];
        downloads.push_back({remotePath, localPath});
        return true;
    }

    void reset() {
        uploads.clear();
        downloads.clear();
        remoteFiles.clear();
        shouldFailUpload = false;
        shouldFailDownload = false;
    }
};

// ============================================================================
// Test Fixture
// ============================================================================

class ConflictResolverTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Create unique test directory
        auto timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();

        testDir_ = fs::temp_directory_path() / ("conflict_test_" + std::to_string(timestamp));
        fs::create_directories(testDir_);

        // Initialize logger
        std::string logFile = (testDir_ / "test.log").string();
        Logger::initialize(logFile, false);

        // Create database
        std::string dbPath = (testDir_ / "test.db").string();
        db_ = std::make_unique<Database>(dbPath);
        ASSERT_TRUE(db_->initialize());

        // Create mock HTTP client
        httpClient_ = std::make_unique<MockHttpClient>();

        // Create ConflictResolver
        resolver_ = std::make_unique<ConflictResolver>(
            db_.get(),
            httpClient_.get(),
            ResolutionStrategy::LAST_WRITE_WINS
        );
    }

    void TearDown() override {
        resolver_.reset();
        httpClient_.reset();
        db_.reset();

        Logger::shutdown();

        std::this_thread::sleep_for(std::chrono::milliseconds(100));

        if (fs::exists(testDir_)) {
            std::error_code ec;
            fs::remove_all(testDir_, ec);
        }
    }

    // Helper: Create test file with content
    void createFile(const std::string& path, const std::string& content) {
        fs::create_directories(fs::path(path).parent_path());
        std::ofstream file(path);
        file << content;
    }

    // Helper: Read file content
    std::string readFile(const std::string& path) {
        std::ifstream file(path);
        return std::string((std::istreambuf_iterator<char>(file)),
                          std::istreambuf_iterator<char>());
    }

    fs::path testDir_;
    std::unique_ptr<Database> db_;
    std::unique_ptr<MockHttpClient> httpClient_;
    std::unique_ptr<ConflictResolver> resolver_;
};

// ============================================================================
// Tests
// ============================================================================

// Test 1: Last-Write-Wins with local newer
TEST_F(ConflictResolverTest, LastWriteWins_LocalNewer) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";

    auto localTime = std::chrono::system_clock::now();
    auto remoteTime = localTime - std::chrono::hours(1); // Remote is older

    auto result = resolver_->resolve(localPath, remotePath, localTime, remoteTime,
                                    ResolutionStrategy::LAST_WRITE_WINS);

    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.action, "uploaded");
    EXPECT_EQ(httpClient_->uploads.size(), 1);
    EXPECT_EQ(httpClient_->downloads.size(), 0);
}

// Test 2: Last-Write-Wins with remote newer
TEST_F(ConflictResolverTest, LastWriteWins_RemoteNewer) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";

    auto remoteTime = std::chrono::system_clock::now();
    auto localTime = remoteTime - std::chrono::hours(1); // Local is older

    auto result = resolver_->resolve(localPath, remotePath, localTime, remoteTime,
                                    ResolutionStrategy::LAST_WRITE_WINS);

    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.action, "downloaded");
    EXPECT_EQ(httpClient_->uploads.size(), 0);
    EXPECT_EQ(httpClient_->downloads.size(), 1);
}

// Test 3: Local-Wins always uploads
TEST_F(ConflictResolverTest, LocalWins) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";

    auto now = std::chrono::system_clock::now();

    auto result = resolver_->resolve(localPath, remotePath, now, now,
                                    ResolutionStrategy::LOCAL_WINS);

    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.action, "uploaded");
    EXPECT_EQ(httpClient_->uploads.size(), 1);
    EXPECT_EQ(httpClient_->downloads.size(), 0);
}

// Test 4: Remote-Wins always downloads
TEST_F(ConflictResolverTest, RemoteWins) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";

    auto now = std::chrono::system_clock::now();

    auto result = resolver_->resolve(localPath, remotePath, now, now,
                                    ResolutionStrategy::REMOTE_WINS);

    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.action, "downloaded");
    EXPECT_EQ(httpClient_->uploads.size(), 0);
    EXPECT_EQ(httpClient_->downloads.size(), 1);
}

// Test 5: Keep-Both creates conflict file
TEST_F(ConflictResolverTest, KeepBoth) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";

    auto result = resolver_->resolve(localPath, remotePath,
                                    std::chrono::system_clock::now(),
                                    std::chrono::system_clock::now(),
                                    ResolutionStrategy::KEEP_BOTH);

    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.action, "renamed");

    // Should have: 1 download (remote to conflict file) + 2 uploads (local + conflict)
    EXPECT_EQ(httpClient_->downloads.size(), 1);
    EXPECT_EQ(httpClient_->uploads.size(), 2);

    // Verify conflict file was created locally
    EXPECT_TRUE(fs::exists(result.finalPath));
}

// Test 6: Manual resolution with callback
TEST_F(ConflictResolverTest, ManualWithCallback) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";

    // Set callback to choose LOCAL_WINS
    resolver_->setManualCallback([](const std::string&, const std::string&) {
        return ResolutionStrategy::LOCAL_WINS;
    });

    auto now = std::chrono::system_clock::now();
    auto result = resolver_->resolve(localPath, remotePath, now, now,
                                    ResolutionStrategy::MANUAL);

    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.action, "manual");
    EXPECT_EQ(httpClient_->uploads.size(), 1); // LOCAL_WINS uploads
}

// Test 7: Manual without callback fails
TEST_F(ConflictResolverTest, ManualWithoutCallback) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");

    auto now = std::chrono::system_clock::now();
    auto result = resolver_->resolve(localPath, remotePath, now, now,
                                    ResolutionStrategy::MANUAL);

    EXPECT_FALSE(result.success);
    EXPECT_FALSE(result.errorMessage.empty());
}

// Test 8: Upload failure handling
TEST_F(ConflictResolverTest, UploadFailure) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->shouldFailUpload = true;

    auto now = std::chrono::system_clock::now();
    auto result = resolver_->resolve(localPath, remotePath, now, now,
                                    ResolutionStrategy::LOCAL_WINS);

    EXPECT_FALSE(result.success);
    EXPECT_FALSE(result.errorMessage.empty());
}

// Test 9: Download failure handling
TEST_F(ConflictResolverTest, DownloadFailure) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";
    httpClient_->shouldFailDownload = true;

    auto now = std::chrono::system_clock::now();
    auto result = resolver_->resolve(localPath, remotePath, now, now,
                                    ResolutionStrategy::REMOTE_WINS);

    EXPECT_FALSE(result.success);
    EXPECT_FALSE(result.errorMessage.empty());
}

// Test 10: ResolveAuto uses default strategy
TEST_F(ConflictResolverTest, ResolveAuto) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";

    // Default is LAST_WRITE_WINS
    auto localTime = std::chrono::system_clock::now();
    auto remoteTime = localTime - std::chrono::hours(1);

    auto result = resolver_->resolveAuto(localPath, remotePath, localTime, remoteTime);

    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.action, "uploaded"); // Local is newer
}

// Test 11: Change default strategy
TEST_F(ConflictResolverTest, ChangeDefaultStrategy) {
    resolver_->setDefaultStrategy(ResolutionStrategy::REMOTE_WINS);

    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";

    auto now = std::chrono::system_clock::now();
    auto result = resolver_->resolveAuto(localPath, remotePath, now, now);

    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.action, "downloaded"); // New default is REMOTE_WINS
}

// Test 12: Keep-Both with file extension
TEST_F(ConflictResolverTest, KeepBoth_FileExtension) {
    std::string localPath = (testDir_ / "document.pdf").string();
    std::string remotePath = "/remote/document.pdf";

    createFile(localPath, "local PDF content");
    httpClient_->remoteFiles[remotePath] = "remote PDF content";

    auto result = resolver_->resolve(localPath, remotePath,
                                    std::chrono::system_clock::now(),
                                    std::chrono::system_clock::now(),
                                    ResolutionStrategy::KEEP_BOTH);

    EXPECT_TRUE(result.success);

    // Verify conflict file has .pdf extension
    fs::path conflictPath(result.finalPath);
    EXPECT_EQ(conflictPath.extension().string(), ".pdf");
    EXPECT_NE(conflictPath.filename().string().find("conflict"), std::string::npos);
}

// Test 13: Multiple conflicts in sequence
TEST_F(ConflictResolverTest, MultipleConflicts) {
    for (int i = 0; i < 5; i++) {
        std::string localPath = (testDir_ / ("file" + std::to_string(i) + ".txt")).string();
        std::string remotePath = "/remote/file" + std::to_string(i) + ".txt";

        createFile(localPath, "local");
        httpClient_->remoteFiles[remotePath] = "remote";

        auto result = resolver_->resolve(localPath, remotePath,
                                        std::chrono::system_clock::now(),
                                        std::chrono::system_clock::now(),
                                        ResolutionStrategy::LOCAL_WINS);

        EXPECT_TRUE(result.success);
    }

    EXPECT_EQ(httpClient_->uploads.size(), 5);
}

// Test 14: Conflict with equal timestamps (Last-Write-Wins)
TEST_F(ConflictResolverTest, EqualTimestamps) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";

    auto now = std::chrono::system_clock::now();

    auto result = resolver_->resolve(localPath, remotePath, now, now,
                                    ResolutionStrategy::LAST_WRITE_WINS);

    EXPECT_TRUE(result.success);
    // With equal timestamps, remote wins (localTimestamp > remoteTimestamp is false)
    EXPECT_EQ(result.action, "downloaded");
}

// Test 15: Manual callback returns invalid strategy
TEST_F(ConflictResolverTest, ManualCallbackInvalid) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");

    // Callback returns MANUAL (invalid)
    resolver_->setManualCallback([](const std::string&, const std::string&) {
        return ResolutionStrategy::MANUAL;
    });

    auto now = std::chrono::system_clock::now();
    auto result = resolver_->resolve(localPath, remotePath, now, now,
                                    ResolutionStrategy::MANUAL);

    EXPECT_FALSE(result.success);
    EXPECT_NE(result.errorMessage.find("MANUAL again"), std::string::npos);
}

// Test 16: Verify conflict logging to database
TEST_F(ConflictResolverTest, DatabaseLogging) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";

    auto now = std::chrono::system_clock::now();
    auto result = resolver_->resolve(localPath, remotePath, now, now,
                                    ResolutionStrategy::LOCAL_WINS);

    EXPECT_TRUE(result.success);

    // Note: The current implementation logs to database, but we can't easily verify
    // without exposing internal DB methods. This test confirms no exceptions.
}

// Test 17: Keep-Both failure scenarios
TEST_F(ConflictResolverTest, KeepBoth_DownloadFails) {
    std::string localPath = (testDir_ / "file.txt").string();
    std::string remotePath = "/remote/file.txt";

    createFile(localPath, "local content");
    httpClient_->remoteFiles[remotePath] = "remote content";
    httpClient_->shouldFailDownload = true;

    auto result = resolver_->resolve(localPath, remotePath,
                                    std::chrono::system_clock::now(),
                                    std::chrono::system_clock::now(),
                                    ResolutionStrategy::KEEP_BOTH);

    EXPECT_FALSE(result.success);
    EXPECT_NE(result.errorMessage.find("download"), std::string::npos);
}

// Test 18: Verify all strategies work with resolveAuto after changing default
TEST_F(ConflictResolverTest, AllStrategiesViaResolveAuto) {
    std::vector<ResolutionStrategy> strategies = {
        ResolutionStrategy::LAST_WRITE_WINS,
        ResolutionStrategy::LOCAL_WINS,
        ResolutionStrategy::REMOTE_WINS,
        ResolutionStrategy::KEEP_BOTH
    };

    for (auto strategy : strategies) {
        httpClient_->reset();

        resolver_->setDefaultStrategy(strategy);

        std::string localPath = (testDir_ / "file.txt").string();
        std::string remotePath = "/remote/file.txt";

        createFile(localPath, "local content");
        httpClient_->remoteFiles[remotePath] = "remote content";

        auto localTime = std::chrono::system_clock::now();
        auto remoteTime = localTime + std::chrono::seconds(1);

        auto result = resolver_->resolveAuto(localPath, remotePath, localTime, remoteTime);

        EXPECT_TRUE(result.success) << "Strategy " << static_cast<int>(strategy) << " failed";
    }
}
