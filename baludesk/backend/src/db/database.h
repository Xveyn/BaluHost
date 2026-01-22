#pragma once

#include "sync/sync_engine.h"
#include <string>
#include <vector>
#include <optional>
#include <sqlite3.h>

namespace baludesk {

struct FileMetadata {
    std::string path;
    std::string folderId;
    uint64_t size;
    std::string modifiedAt;
    std::string checksum;
    bool isDirectory;
    std::string syncStatus; // synced, pending_upload, pending_download
};

struct Conflict {
    std::string id;
    std::string path;
    std::string folderId;
    std::string localModified;
    std::string remoteModified;
    std::string resolution;
    std::string resolvedAt;
};

struct RemoteServerProfile {
    int id;
    std::string owner;  // Username who owns this profile
    std::string name;
    std::string sshHost;
    int sshPort;
    std::string sshUsername;
    std::string sshPrivateKey;  // Encrypted
    int vpnProfileId;
    std::string powerOnCommand;
    std::string lastUsed;
    std::string createdAt;
    std::string updatedAt;
};

struct VPNProfile {
    int id;
    std::string name;
    std::string vpnType;  // OpenVPN, WireGuard, Custom
    std::string description;
    std::string configContent;  // Encrypted
    std::string certificate;    // Encrypted
    std::string privateKey;     // Encrypted
    bool autoConnect;
    std::string createdAt;
    std::string updatedAt;
};

struct ActivityLog {
    int id;
    std::string timestamp;
    std::string activityType;  // upload, download, delete, conflict, error
    std::string filePath;
    std::string folderId;
    std::string details;  // JSON or text details
    int64_t fileSize;  // bytes
    std::string status;  // success, failed, pending
};

/**
 * Database - SQLite database for local metadata
 * 
 * Stores sync folders, file metadata, sync state, and conflicts
 */
class Database {
public:
    explicit Database(const std::string& dbPath);
    ~Database();

    bool initialize();
    bool runMigrations();

    // Sync folders
    bool addSyncFolder(const SyncFolder& folder);
    bool updateSyncFolder(const SyncFolder& folder);
    bool removeSyncFolder(const std::string& folderId);
    SyncFolder getSyncFolder(const std::string& folderId);
    std::vector<SyncFolder> getSyncFolders();

    // File metadata
    bool upsertFileMetadata(const FileMetadata& metadata);
    bool upsertFileMetadata(const std::string& path, const std::string& folderId, uint64_t size, const std::string& checksum, const std::string& modifiedAt);
    std::optional<FileMetadata> getFileMetadata(const std::string& path);
    std::vector<FileMetadata> getFilesInFolder(const std::string& folderId);
    std::vector<FileMetadata> getChangedFilesSince(const std::string& timestamp);
    bool deleteFileMetadata(const std::string& path);
    bool updateSyncFolderTimestamp(const std::string& folderId);

    // Conflicts
    bool logConflict(const Conflict& conflict);
    std::vector<Conflict> getPendingConflicts();
    bool resolveConflict(const std::string& conflictId, const std::string& resolution);

    // Remote Server Profiles
    bool addRemoteServerProfile(const RemoteServerProfile& profile);
    bool updateRemoteServerProfile(const RemoteServerProfile& profile);
    bool deleteRemoteServerProfile(int id);
    bool clearAllRemoteServerProfiles();  // Clear all profiles for user isolation
    RemoteServerProfile getRemoteServerProfile(int id);
    std::vector<RemoteServerProfile> getRemoteServerProfiles(const std::string& owner);  // Get profiles for owner
    std::vector<RemoteServerProfile> getRemoteServerProfiles();  // Get ALL profiles (for login screen)

    // VPN Profiles
    bool addVPNProfile(const VPNProfile& profile);
    bool updateVPNProfile(const VPNProfile& profile);
    bool deleteVPNProfile(int id);
    VPNProfile getVPNProfile(int id);
    std::vector<VPNProfile> getVPNProfiles();

    // Activity Logs
    bool logActivity(const std::string& activityType, const std::string& filePath, const std::string& folderId,
                    const std::string& details, int64_t fileSize, const std::string& status);
    std::vector<ActivityLog> getActivityLogs(int limit = 100, const std::string& activityType = "",
                                            const std::string& startDate = "", const std::string& endDate = "");
    bool clearActivityLogs(const std::string& beforeDate = "");

    // Utilities
    std::string generateId();

private:
    bool executeQuery(const std::string& query);
    sqlite3_stmt* prepareStatement(const std::string& query);

    std::string dbPath_;
    sqlite3* db_;
};

} // namespace baludesk
