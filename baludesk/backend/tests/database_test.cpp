#include <gtest/gtest.h>
#include "db/database.h"
#include "utils/logger.h"
#include <filesystem>
#include <thread>
#include <chrono>
#include <set>
#include <algorithm>

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

// ============================================================================
// NEW COMPREHENSIVE TESTS (15+)
// ============================================================================

// Test 8: Update sync folder
TEST_F(DatabaseTest, UpdateSyncFolder) {
    // Add folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/docs";
    folder.remotePath = "/docs";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;

    ASSERT_TRUE(db_->addSyncFolder(folder));

    // Update folder
    folder.remotePath = "/new_docs";
    folder.status = SyncStatus::SYNCING;
    folder.enabled = false;

    ASSERT_TRUE(db_->updateSyncFolder(folder));

    // Verify update
    SyncFolder retrieved = db_->getSyncFolder(folder.id);
    EXPECT_EQ(retrieved.remotePath, "/new_docs");
    EXPECT_EQ(retrieved.status, SyncStatus::SYNCING);
    EXPECT_FALSE(retrieved.enabled);
}

// Test 9: Remove sync folder
TEST_F(DatabaseTest, RemoveSyncFolder) {
    // Add folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/temp";
    folder.remotePath = "/temp";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;

    ASSERT_TRUE(db_->addSyncFolder(folder));

    // Verify it exists
    auto folders = db_->getSyncFolders();
    EXPECT_EQ(folders.size(), 1);

    // Remove folder
    ASSERT_TRUE(db_->removeSyncFolder(folder.id));

    // Verify removal
    folders = db_->getSyncFolders();
    EXPECT_EQ(folders.size(), 0);

    SyncFolder retrieved = db_->getSyncFolder(folder.id);
    EXPECT_TRUE(retrieved.id.empty());
}

// Test 10: Remove non-existent sync folder (error handling)
TEST_F(DatabaseTest, RemoveNonExistentSyncFolder) {
    std::string fakeId = "nonexistent-id-12345";

    // Should succeed (SQLite DELETE returns success even if 0 rows affected)
    ASSERT_TRUE(db_->removeSyncFolder(fakeId));
}

// Test 11: Get files in folder
TEST_F(DatabaseTest, GetFilesInFolder) {
    // Setup folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/project";
    folder.remotePath = "/project";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    db_->addSyncFolder(folder);

    // Add multiple files
    for (int i = 0; i < 5; i++) {
        FileMetadata metadata;
        metadata.path = "/home/user/project/file" + std::to_string(i) + ".txt";
        metadata.folderId = folder.id;
        metadata.size = 100 * (i + 1);
        metadata.modifiedAt = "2026-01-04T12:00:00Z";
        metadata.checksum = "hash" + std::to_string(i);
        metadata.isDirectory = false;
        metadata.syncStatus = "synced";

        ASSERT_TRUE(db_->upsertFileMetadata(metadata));
    }

    // Retrieve files
    auto files = db_->getFilesInFolder(folder.id);
    EXPECT_EQ(files.size(), 5);

    // Verify files are sorted by path
    for (size_t i = 0; i < files.size() - 1; i++) {
        EXPECT_TRUE(files[i].path <= files[i + 1].path);
    }
}

// Test 12: Get changed files since timestamp
TEST_F(DatabaseTest, GetChangedFilesSince) {
    // Setup folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/sync";
    folder.remotePath = "/sync";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    db_->addSyncFolder(folder);

    // Add files with different timestamps
    FileMetadata file1;
    file1.path = "/home/user/sync/old.txt";
    file1.folderId = folder.id;
    file1.size = 100;
    file1.modifiedAt = "2026-01-01T10:00:00Z";
    file1.checksum = "hash1";
    file1.isDirectory = false;
    file1.syncStatus = "synced";
    db_->upsertFileMetadata(file1);

    FileMetadata file2;
    file2.path = "/home/user/sync/new.txt";
    file2.folderId = folder.id;
    file2.size = 200;
    file2.modifiedAt = "2026-01-10T15:00:00Z";
    file2.checksum = "hash2";
    file2.isDirectory = false;
    file2.syncStatus = "pending_upload";
    db_->upsertFileMetadata(file2);

    // Get files changed after 2026-01-05
    auto changedFiles = db_->getChangedFilesSince("2026-01-05T00:00:00Z");

    EXPECT_EQ(changedFiles.size(), 1);
    EXPECT_EQ(changedFiles[0].path, "/home/user/sync/new.txt");
}

// Test 13: Update sync folder timestamp
TEST_F(DatabaseTest, UpdateSyncFolderTimestamp) {
    // Add folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/backup";
    folder.remotePath = "/backup";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;

    ASSERT_TRUE(db_->addSyncFolder(folder));

    // Update timestamp
    ASSERT_TRUE(db_->updateSyncFolderTimestamp(folder.id));

    // Note: We can't directly verify the timestamp without extending the API
    // but we confirm the operation succeeds
}

// Test 14: Resolve conflict
TEST_F(DatabaseTest, ResolveConflict) {
    // Setup folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/conflicts";
    folder.remotePath = "/conflicts";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    db_->addSyncFolder(folder);

    // Log conflict
    Conflict conflict;
    conflict.id = db_->generateId();
    conflict.path = "/home/user/conflicts/file.txt";
    conflict.folderId = folder.id;
    conflict.localModified = "2026-01-10T10:00:00Z";
    conflict.remoteModified = "2026-01-10T10:05:00Z";

    ASSERT_TRUE(db_->logConflict(conflict));

    // Verify it's pending
    auto pending = db_->getPendingConflicts();
    EXPECT_EQ(pending.size(), 1);

    // Resolve conflict
    ASSERT_TRUE(db_->resolveConflict(conflict.id, "keep_remote"));

    // Verify no more pending conflicts
    pending = db_->getPendingConflicts();
    EXPECT_EQ(pending.size(), 0);
}

// Test 15: Multiple pending conflicts
TEST_F(DatabaseTest, MultiplePendingConflicts) {
    // Setup folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/multi";
    folder.remotePath = "/multi";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    db_->addSyncFolder(folder);

    // Log 3 conflicts
    for (int i = 0; i < 3; i++) {
        Conflict conflict;
        conflict.id = db_->generateId();
        conflict.path = "/home/user/multi/file" + std::to_string(i) + ".txt";
        conflict.folderId = folder.id;
        conflict.localModified = "2026-01-10T10:00:00Z";
        conflict.remoteModified = "2026-01-10T10:05:00Z";

        ASSERT_TRUE(db_->logConflict(conflict));
    }

    // Verify all are pending
    auto pending = db_->getPendingConflicts();
    EXPECT_EQ(pending.size(), 3);
}

// Test 16: Cascading delete (folder deletion deletes files)
TEST_F(DatabaseTest, CascadingDelete) {
    // Setup folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/cascade";
    folder.remotePath = "/cascade";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    db_->addSyncFolder(folder);

    // Add files
    for (int i = 0; i < 3; i++) {
        FileMetadata metadata;
        metadata.path = "/home/user/cascade/file" + std::to_string(i) + ".txt";
        metadata.folderId = folder.id;
        metadata.size = 100;
        metadata.modifiedAt = "2026-01-04T12:00:00Z";
        metadata.checksum = "hash";
        metadata.isDirectory = false;
        metadata.syncStatus = "synced";

        db_->upsertFileMetadata(metadata);
    }

    // Verify files exist
    auto files = db_->getFilesInFolder(folder.id);
    EXPECT_EQ(files.size(), 3);

    // Delete folder (should cascade delete files due to FOREIGN KEY ON DELETE CASCADE)
    ASSERT_TRUE(db_->removeSyncFolder(folder.id));

    // Verify files are also deleted
    files = db_->getFilesInFolder(folder.id);
    EXPECT_EQ(files.size(), 0);
}

// Test 17: Add duplicate sync folder (should fail)
TEST_F(DatabaseTest, AddDuplicateSyncFolder) {
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/unique";
    folder.remotePath = "/unique";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;

    // First add should succeed
    ASSERT_TRUE(db_->addSyncFolder(folder));

    // Second add with same local_path should fail (UNIQUE constraint)
    SyncFolder duplicate;
    duplicate.id = db_->generateId();
    duplicate.localPath = "/home/user/unique";  // Same local path
    duplicate.remotePath = "/another";
    duplicate.status = SyncStatus::IDLE;
    duplicate.enabled = true;

    EXPECT_FALSE(db_->addSyncFolder(duplicate));
}

// Test 18: Get non-existent file metadata
TEST_F(DatabaseTest, GetNonExistentFileMetadata) {
    auto result = db_->getFileMetadata("/nonexistent/path/file.txt");
    EXPECT_FALSE(result.has_value());
}

// Test 19: Empty database queries
TEST_F(DatabaseTest, EmptyDatabaseQueries) {
    // Get folders from empty DB
    auto folders = db_->getSyncFolders();
    EXPECT_EQ(folders.size(), 0);

    // Get pending conflicts from empty DB
    auto conflicts = db_->getPendingConflicts();
    EXPECT_EQ(conflicts.size(), 0);

    // Get changed files from empty DB
    auto files = db_->getChangedFilesSince("2026-01-01T00:00:00Z");
    EXPECT_EQ(files.size(), 0);
}

// Test 20: Add and retrieve Remote Server Profile
TEST_F(DatabaseTest, AddRemoteServerProfile) {
    RemoteServerProfile profile;
    profile.owner = "testuser";
    profile.name = "My NAS";
    profile.sshHost = "192.168.1.100";
    profile.sshPort = 22;
    profile.sshUsername = "admin";
    profile.sshPrivateKey = "encrypted_key_data";
    profile.vpnProfileId = 0;  // No VPN
    profile.powerOnCommand = "wakeonlan 00:11:22:33:44:55";

    ASSERT_TRUE(db_->addRemoteServerProfile(profile));

    // Retrieve all profiles
    auto profiles = db_->getRemoteServerProfiles();
    EXPECT_EQ(profiles.size(), 1);
    EXPECT_EQ(profiles[0].name, "My NAS");
    EXPECT_EQ(profiles[0].sshHost, "192.168.1.100");
}

// Test 21: Update Remote Server Profile
TEST_F(DatabaseTest, UpdateRemoteServerProfile) {
    // Add profile
    RemoteServerProfile profile;
    profile.owner = "testuser";
    profile.name = "Test Server";
    profile.sshHost = "192.168.1.50";
    profile.sshPort = 22;
    profile.sshUsername = "user";
    profile.sshPrivateKey = "key123";
    profile.vpnProfileId = 0;
    profile.powerOnCommand = "";

    ASSERT_TRUE(db_->addRemoteServerProfile(profile));

    // Get the auto-generated ID
    auto profiles = db_->getRemoteServerProfiles();
    ASSERT_EQ(profiles.size(), 1);
    int profileId = profiles[0].id;

    // Update profile
    RemoteServerProfile updated = profiles[0];
    updated.sshHost = "10.0.0.50";  // New IP
    updated.sshPort = 2222;         // New port

    ASSERT_TRUE(db_->updateRemoteServerProfile(updated));

    // Verify update
    RemoteServerProfile retrieved = db_->getRemoteServerProfile(profileId);
    EXPECT_EQ(retrieved.sshHost, "10.0.0.50");
    EXPECT_EQ(retrieved.sshPort, 2222);
}

// Test 22: Delete Remote Server Profile
TEST_F(DatabaseTest, DeleteRemoteServerProfile) {
    // Add profile
    RemoteServerProfile profile;
    profile.owner = "testuser";
    profile.name = "Delete Me";
    profile.sshHost = "192.168.1.99";
    profile.sshPort = 22;
    profile.sshUsername = "user";
    profile.sshPrivateKey = "key";
    profile.vpnProfileId = 0;
    profile.powerOnCommand = "";

    ASSERT_TRUE(db_->addRemoteServerProfile(profile));

    auto profiles = db_->getRemoteServerProfiles();
    ASSERT_EQ(profiles.size(), 1);
    int profileId = profiles[0].id;

    // Delete
    ASSERT_TRUE(db_->deleteRemoteServerProfile(profileId));

    // Verify deletion
    profiles = db_->getRemoteServerProfiles();
    EXPECT_EQ(profiles.size(), 0);
}

// Test 23: Get Remote Server Profiles by owner
TEST_F(DatabaseTest, GetRemoteServerProfilesByOwner) {
    // Add profiles for different owners
    RemoteServerProfile profile1;
    profile1.owner = "alice";
    profile1.name = "Alice Server";
    profile1.sshHost = "192.168.1.10";
    profile1.sshPort = 22;
    profile1.sshUsername = "alice";
    profile1.sshPrivateKey = "key1";
    profile1.vpnProfileId = 0;
    profile1.powerOnCommand = "";
    db_->addRemoteServerProfile(profile1);

    RemoteServerProfile profile2;
    profile2.owner = "bob";
    profile2.name = "Bob Server";
    profile2.sshHost = "192.168.1.20";
    profile2.sshPort = 22;
    profile2.sshUsername = "bob";
    profile2.sshPrivateKey = "key2";
    profile2.vpnProfileId = 0;
    profile2.powerOnCommand = "";
    db_->addRemoteServerProfile(profile2);

    RemoteServerProfile profile3;
    profile3.owner = "alice";
    profile3.name = "Alice Backup";
    profile3.sshHost = "192.168.1.30";
    profile3.sshPort = 22;
    profile3.sshUsername = "alice";
    profile3.sshPrivateKey = "key3";
    profile3.vpnProfileId = 0;
    profile3.powerOnCommand = "";
    db_->addRemoteServerProfile(profile3);

    // Get Alice's profiles
    auto aliceProfiles = db_->getRemoteServerProfiles("alice");
    EXPECT_EQ(aliceProfiles.size(), 2);

    // Get Bob's profiles
    auto bobProfiles = db_->getRemoteServerProfiles("bob");
    EXPECT_EQ(bobProfiles.size(), 1);
}

// Test 24: Add and retrieve VPN Profile
TEST_F(DatabaseTest, AddVPNProfile) {
    VPNProfile profile;
    profile.name = "WireGuard Home";
    profile.vpnType = "WireGuard";
    profile.description = "Home network VPN";
    profile.configContent = "encrypted_config_data";
    profile.certificate = "";
    profile.privateKey = "encrypted_private_key";
    profile.autoConnect = true;

    ASSERT_TRUE(db_->addVPNProfile(profile));

    // Retrieve profiles
    auto profiles = db_->getVPNProfiles();
    EXPECT_EQ(profiles.size(), 1);
    EXPECT_EQ(profiles[0].name, "WireGuard Home");
    EXPECT_EQ(profiles[0].vpnType, "WireGuard");
    EXPECT_TRUE(profiles[0].autoConnect);
}

// Test 25: Update VPN Profile
TEST_F(DatabaseTest, UpdateVPNProfile) {
    // Add profile
    VPNProfile profile;
    profile.name = "OpenVPN Test";
    profile.vpnType = "OpenVPN";
    profile.description = "Test VPN";
    profile.configContent = "config1";
    profile.certificate = "cert1";
    profile.privateKey = "key1";
    profile.autoConnect = false;

    ASSERT_TRUE(db_->addVPNProfile(profile));

    auto profiles = db_->getVPNProfiles();
    ASSERT_EQ(profiles.size(), 1);
    int vpnId = profiles[0].id;

    // Update
    VPNProfile updated = profiles[0];
    updated.description = "Updated description";
    updated.autoConnect = true;

    ASSERT_TRUE(db_->updateVPNProfile(updated));

    // Verify
    VPNProfile retrieved = db_->getVPNProfile(vpnId);
    EXPECT_EQ(retrieved.description, "Updated description");
    EXPECT_TRUE(retrieved.autoConnect);
}

// Test 26: Delete VPN Profile
TEST_F(DatabaseTest, DeleteVPNProfile) {
    // Add profile
    VPNProfile profile;
    profile.name = "Delete Me VPN";
    profile.vpnType = "Custom";
    profile.description = "";
    profile.configContent = "config";
    profile.certificate = "";
    profile.privateKey = "";
    profile.autoConnect = false;

    ASSERT_TRUE(db_->addVPNProfile(profile));

    auto profiles = db_->getVPNProfiles();
    ASSERT_EQ(profiles.size(), 1);
    int vpnId = profiles[0].id;

    // Delete
    ASSERT_TRUE(db_->deleteVPNProfile(vpnId));

    // Verify
    profiles = db_->getVPNProfiles();
    EXPECT_EQ(profiles.size(), 0);
}

// Test 27: Foreign key constraint (VPN profile reference)
TEST_F(DatabaseTest, ForeignKeyVPNProfile) {
    // Add VPN profile
    VPNProfile vpn;
    vpn.name = "Test VPN";
    vpn.vpnType = "WireGuard";
    vpn.description = "";
    vpn.configContent = "config";
    vpn.certificate = "";
    vpn.privateKey = "";
    vpn.autoConnect = false;

    ASSERT_TRUE(db_->addVPNProfile(vpn));

    auto vpnProfiles = db_->getVPNProfiles();
    ASSERT_EQ(vpnProfiles.size(), 1);
    int vpnId = vpnProfiles[0].id;

    // Add server profile with VPN reference
    RemoteServerProfile server;
    server.owner = "testuser";
    server.name = "VPN Server";
    server.sshHost = "10.0.0.1";
    server.sshPort = 22;
    server.sshUsername = "user";
    server.sshPrivateKey = "key";
    server.vpnProfileId = vpnId;
    server.powerOnCommand = "";

    ASSERT_TRUE(db_->addRemoteServerProfile(server));

    // Verify reference
    auto servers = db_->getRemoteServerProfiles();
    EXPECT_EQ(servers[0].vpnProfileId, vpnId);
}

// Test 28: Generate unique IDs
TEST_F(DatabaseTest, GenerateUniqueIds) {
    std::set<std::string> ids;

    // Generate 100 IDs
    for (int i = 0; i < 100; i++) {
        std::string id = db_->generateId();

        // Verify format (UUID-like with dashes)
        EXPECT_GT(id.length(), 30);
        EXPECT_NE(id.find('-'), std::string::npos);

        // Verify uniqueness
        EXPECT_TRUE(ids.find(id) == ids.end()) << "Duplicate ID generated: " << id;
        ids.insert(id);
    }

    EXPECT_EQ(ids.size(), 100);
}

// Test 29: Clear all remote server profiles
TEST_F(DatabaseTest, ClearAllRemoteServerProfiles) {
    // Add multiple profiles
    for (int i = 0; i < 5; i++) {
        RemoteServerProfile profile;
        profile.owner = "user" + std::to_string(i);
        profile.name = "Server " + std::to_string(i);
        profile.sshHost = "192.168.1." + std::to_string(i + 10);
        profile.sshPort = 22;
        profile.sshUsername = "user";
        profile.sshPrivateKey = "key";
        profile.vpnProfileId = 0;
        profile.powerOnCommand = "";

        db_->addRemoteServerProfile(profile);
    }

    // Verify they exist
    auto profiles = db_->getRemoteServerProfiles();
    EXPECT_EQ(profiles.size(), 5);

    // Clear all
    ASSERT_TRUE(db_->clearAllRemoteServerProfiles());

    // Verify all are deleted
    profiles = db_->getRemoteServerProfiles();
    EXPECT_EQ(profiles.size(), 0);
}

// Test 30: File metadata with directory flag
TEST_F(DatabaseTest, FileMetadataWithDirectory) {
    // Setup folder
    SyncFolder folder;
    folder.id = db_->generateId();
    folder.localPath = "/home/user/tree";
    folder.remotePath = "/tree";
    folder.status = SyncStatus::IDLE;
    folder.enabled = true;
    db_->addSyncFolder(folder);

    // Add directory metadata
    FileMetadata dir;
    dir.path = "/home/user/tree/subfolder";
    dir.folderId = folder.id;
    dir.size = 0;
    dir.modifiedAt = "2026-01-10T12:00:00Z";
    dir.checksum = "";
    dir.isDirectory = true;  // Directory
    dir.syncStatus = "synced";

    ASSERT_TRUE(db_->upsertFileMetadata(dir));

    // Add file metadata
    FileMetadata file;
    file.path = "/home/user/tree/file.txt";
    file.folderId = folder.id;
    file.size = 512;
    file.modifiedAt = "2026-01-10T12:01:00Z";
    file.checksum = "abc";
    file.isDirectory = false;  // File
    file.syncStatus = "synced";

    ASSERT_TRUE(db_->upsertFileMetadata(file));

    // Retrieve and verify
    auto files = db_->getFilesInFolder(folder.id);
    EXPECT_EQ(files.size(), 2);

    // Find directory
    auto dirIt = std::find_if(files.begin(), files.end(),
        [](const FileMetadata& m) { return m.isDirectory; });
    ASSERT_NE(dirIt, files.end());
    EXPECT_EQ(dirIt->path, "/home/user/tree/subfolder");

    // Find file
    auto fileIt = std::find_if(files.begin(), files.end(),
        [](const FileMetadata& m) { return !m.isDirectory; });
    ASSERT_NE(fileIt, files.end());
    EXPECT_EQ(fileIt->path, "/home/user/tree/file.txt");
}
