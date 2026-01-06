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
    RemoteServerProfile getRemoteServerProfile(int id);
    std::vector<RemoteServerProfile> getRemoteServerProfiles();

    // VPN Profiles
    bool addVPNProfile(const VPNProfile& profile);
    bool updateVPNProfile(const VPNProfile& profile);
    bool deleteVPNProfile(int id);
    VPNProfile getVPNProfile(int id);
    std::vector<VPNProfile> getVPNProfiles();

    // Utilities
    std::string generateId();

private:
    bool executeQuery(const std::string& query);
    sqlite3_stmt* prepareStatement(const std::string& query);

    std::string dbPath_;
    sqlite3* db_;
};

} // namespace baludesk
