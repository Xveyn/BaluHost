#pragma once

#include "sync/sync_engine.h"
#include <string>
#include <vector>
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
    FileMetadata getFileMetadata(const std::string& path);
    std::vector<FileMetadata> getChangedFilesSince(const std::string& timestamp);
    bool deleteFileMetadata(const std::string& path);

    // Conflicts
    bool logConflict(const Conflict& conflict);
    std::vector<Conflict> getPendingConflicts();
    bool resolveConflict(const std::string& conflictId, const std::string& resolution);

    // Utilities
    std::string generateId();

private:
    bool executeQuery(const std::string& query);
    sqlite3_stmt* prepareStatement(const std::string& query);

    std::string dbPath_;
    sqlite3* db_;
};

} // namespace baludesk
