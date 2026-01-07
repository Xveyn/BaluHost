#include "database.h"
#include "../utils/logger.h"
#include <sstream>
#include <random>
#include <iomanip>
#include <ctime>

namespace baludesk {

// ============================================================================
// Constructor & Destructor
// ============================================================================

Database::Database(const std::string& dbPath) 
    : dbPath_(dbPath), db_(nullptr) {
}

Database::~Database() {
    if (db_) {
        sqlite3_close(db_);
        Logger::info("Database closed");
    }
}

// ============================================================================
// Initialization
// ============================================================================

bool Database::initialize() {
    Logger::info("Initializing database: {}", dbPath_);
    
    int rc = sqlite3_open(dbPath_.c_str(), &db_);
    if (rc != SQLITE_OK) {
        Logger::error("Cannot open database: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    // Enable foreign keys
    executeQuery("PRAGMA foreign_keys = ON;");
    
    if (!runMigrations()) {
        Logger::error("Failed to run database migrations");
        return false;
    }
    
    Logger::info("Database initialized successfully");
    return true;
}

bool Database::runMigrations() {
    Logger::info("Running database migrations");
    
    // Create sync_folders table
    std::string createSyncFoldersTable = R"(
        CREATE TABLE IF NOT EXISTS sync_folders (
            id TEXT PRIMARY KEY,
            local_path TEXT NOT NULL UNIQUE,
            remote_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'idle',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_sync TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    )";
    
    if (!executeQuery(createSyncFoldersTable)) {
        return false;
    }
    
    // Create file_metadata table
    std::string createFileMetadataTable = R"(
        CREATE TABLE IF NOT EXISTS file_metadata (
            path TEXT PRIMARY KEY,
            folder_id TEXT NOT NULL,
            size INTEGER NOT NULL DEFAULT 0,
            modified_at TEXT NOT NULL,
            checksum TEXT,
            is_directory INTEGER NOT NULL DEFAULT 0,
            sync_status TEXT NOT NULL DEFAULT 'synced',
            last_synced_at TEXT,
            FOREIGN KEY (folder_id) REFERENCES sync_folders(id) ON DELETE CASCADE
        );
    )";
    
    if (!executeQuery(createFileMetadataTable)) {
        return false;
    }
    
    // Create conflicts table
    std::string createConflictsTable = R"(
        CREATE TABLE IF NOT EXISTS conflicts (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            folder_id TEXT NOT NULL,
            local_modified TEXT NOT NULL,
            remote_modified TEXT NOT NULL,
            resolution TEXT,
            resolved_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (folder_id) REFERENCES sync_folders(id) ON DELETE CASCADE
        );
    )";
    
    if (!executeQuery(createConflictsTable)) {
        return false;
    }
    
    // Create indexes
    executeQuery("CREATE INDEX IF NOT EXISTS idx_file_folder ON file_metadata(folder_id);");
    executeQuery("CREATE INDEX IF NOT EXISTS idx_file_sync_status ON file_metadata(sync_status);");
    executeQuery("CREATE INDEX IF NOT EXISTS idx_conflict_resolved ON conflicts(resolved_at);");
    
    // Create remote_server_profiles table
    std::string createRemoteServerProfilesTable = R"(
        CREATE TABLE IF NOT EXISTS remote_server_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT,
            name TEXT NOT NULL,
            ssh_host TEXT NOT NULL,
            ssh_port INTEGER NOT NULL DEFAULT 22,
            ssh_username TEXT NOT NULL,
            ssh_private_key TEXT NOT NULL,
            vpn_profile_id INTEGER,
            power_on_command TEXT,
            last_used TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (vpn_profile_id) REFERENCES vpn_profiles(id) ON DELETE SET NULL
        );
    )";
    
    if (!executeQuery(createRemoteServerProfilesTable)) {
        return false;
    }
    
    // Create vpn_profiles table
    std::string createVPNProfilesTable = R"(
        CREATE TABLE IF NOT EXISTS vpn_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            vpn_type TEXT NOT NULL,
            description TEXT,
            config_content TEXT NOT NULL,
            certificate TEXT,
            private_key TEXT,
            auto_connect INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    )";
    
    if (!executeQuery(createVPNProfilesTable)) {
        return false;
    }
    
    // Create indexes
    executeQuery("CREATE INDEX IF NOT EXISTS idx_remote_server_ssh_host ON remote_server_profiles(ssh_host);");
    executeQuery("CREATE INDEX IF NOT EXISTS idx_vpn_type ON vpn_profiles(vpn_type);");
    
    Logger::info("Database migrations completed");
    return true;
}

// ============================================================================
// Sync Folders
// ============================================================================

bool Database::addSyncFolder(const SyncFolder& folder) {
    Logger::info("Adding sync folder: {} -> {}", folder.localPath, folder.remotePath);
    
    const char* sql = R"(
        INSERT INTO sync_folders (id, local_path, remote_path, status, enabled)
        VALUES (?, ?, ?, ?, ?);
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, folder.id.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, folder.localPath.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, folder.remotePath.c_str(), -1, SQLITE_TRANSIENT);
    
    std::string status = "idle";
    if (folder.status == SyncStatus::SYNCING) status = "syncing";
    else if (folder.status == SyncStatus::PAUSED) status = "paused";
    else if (folder.status == SyncStatus::SYNC_ERROR) status = "error";
    
    sqlite3_bind_text(stmt, 4, status.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, 5, folder.enabled ? 1 : 0);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to add sync folder: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    Logger::info("Sync folder added successfully");
    return true;
}

bool Database::updateSyncFolder(const SyncFolder& folder) {
    Logger::debug("Updating sync folder: {}", folder.id);
    
    const char* sql = R"(
        UPDATE sync_folders 
        SET local_path = ?, remote_path = ?, status = ?, enabled = ?, last_sync = ?
        WHERE id = ?;
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, folder.localPath.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, folder.remotePath.c_str(), -1, SQLITE_TRANSIENT);
    
    std::string status = "idle";
    if (folder.status == SyncStatus::SYNCING) status = "syncing";
    else if (folder.status == SyncStatus::PAUSED) status = "paused";
    else if (folder.status == SyncStatus::SYNC_ERROR) status = "error";
    
    sqlite3_bind_text(stmt, 3, status.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, 4, folder.enabled ? 1 : 0);
    
    // TODO: Use actual last_sync timestamp
    sqlite3_bind_null(stmt, 5);
    
    sqlite3_bind_text(stmt, 6, folder.id.c_str(), -1, SQLITE_TRANSIENT);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to update sync folder: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    return true;
}

bool Database::removeSyncFolder(const std::string& folderId) {
    Logger::info("Removing sync folder: {}", folderId);
    
    const char* sql = "DELETE FROM sync_folders WHERE id = ?;";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, folderId.c_str(), -1, SQLITE_TRANSIENT);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to remove sync folder: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    Logger::info("Sync folder removed successfully");
    return true;
}

SyncFolder Database::getSyncFolder(const std::string& folderId) {
    const char* sql = "SELECT id, local_path, remote_path, status, enabled FROM sync_folders WHERE id = ?;";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return SyncFolder();
    
    sqlite3_bind_text(stmt, 1, folderId.c_str(), -1, SQLITE_TRANSIENT);
    
    SyncFolder folder;
    
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        folder.id = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
        folder.localPath = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
        folder.remotePath = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
        
        std::string status = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
        if (status == "syncing") folder.status = SyncStatus::SYNCING;
        else if (status == "paused") folder.status = SyncStatus::PAUSED;
        else if (status == "error") folder.status = SyncStatus::SYNC_ERROR;
        else folder.status = SyncStatus::IDLE;
        
        folder.enabled = sqlite3_column_int(stmt, 4) != 0;
    }
    
    sqlite3_finalize(stmt);
    return folder;
}

std::vector<SyncFolder> Database::getSyncFolders() {
    Logger::debug("Getting all sync folders");
    
    const char* sql = "SELECT id, local_path, remote_path, status, enabled FROM sync_folders WHERE enabled = 1;";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return {};
    
    std::vector<SyncFolder> folders;
    
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        SyncFolder folder;
        folder.id = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
        folder.localPath = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
        folder.remotePath = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
        
        std::string status = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
        if (status == "syncing") folder.status = SyncStatus::SYNCING;
        else if (status == "paused") folder.status = SyncStatus::PAUSED;
        else if (status == "error") folder.status = SyncStatus::SYNC_ERROR;
        else folder.status = SyncStatus::IDLE;
        
        folder.enabled = sqlite3_column_int(stmt, 4) != 0;
        
        folders.push_back(folder);
    }
    
    sqlite3_finalize(stmt);
    
    Logger::debug("Found {} sync folders", folders.size());
    return folders;
}

// ============================================================================
// File Metadata
// ============================================================================

bool Database::upsertFileMetadata(const FileMetadata& metadata) {
    const char* sql = R"(
        INSERT INTO file_metadata (path, folder_id, size, modified_at, checksum, is_directory, sync_status, last_synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(path) DO UPDATE SET
            size = excluded.size,
            modified_at = excluded.modified_at,
            checksum = excluded.checksum,
            sync_status = excluded.sync_status,
            last_synced_at = datetime('now');
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, metadata.path.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, metadata.folderId.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 3, metadata.size);
    sqlite3_bind_text(stmt, 4, metadata.modifiedAt.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 5, metadata.checksum.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, 6, metadata.isDirectory ? 1 : 0);
    sqlite3_bind_text(stmt, 7, metadata.syncStatus.c_str(), -1, SQLITE_TRANSIENT);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to upsert file metadata: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    return true;
}

std::optional<FileMetadata> Database::getFileMetadata(const std::string& path) {
    const char* sql = R"(
        SELECT path, folder_id, size, modified_at, checksum, is_directory, sync_status
        FROM file_metadata WHERE path = ?;
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return std::nullopt;
    
    sqlite3_bind_text(stmt, 1, path.c_str(), -1, SQLITE_TRANSIENT);
    
    FileMetadata metadata;
    
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        metadata.path = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
        metadata.folderId = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
        metadata.size = sqlite3_column_int64(stmt, 2);
        metadata.modifiedAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
        
        const char* checksum = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 4));
        if (checksum) metadata.checksum = checksum;
        
        metadata.isDirectory = sqlite3_column_int(stmt, 5) != 0;
        metadata.syncStatus = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 6));
        
        sqlite3_finalize(stmt);
        return metadata;
    }
    
    sqlite3_finalize(stmt);
    return std::nullopt;
}

bool Database::upsertFileMetadata(const std::string& path, const std::string& folderId, 
                                  uint64_t size, const std::string& checksum, 
                                  const std::string& modifiedAt) {
    FileMetadata metadata;
    metadata.path = path;
    metadata.folderId = folderId;
    metadata.size = size;
    metadata.checksum = checksum;
    metadata.modifiedAt = modifiedAt;
    metadata.isDirectory = false;
    metadata.syncStatus = "synced";
    
    return upsertFileMetadata(metadata);
}

std::vector<FileMetadata> Database::getFilesInFolder(const std::string& folderId) {
    const char* sql = R"(
        SELECT path, folder_id, size, modified_at, checksum, is_directory, sync_status
        FROM file_metadata 
        WHERE folder_id = ?
        ORDER BY path;
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return {};
    
    sqlite3_bind_text(stmt, 1, folderId.c_str(), -1, SQLITE_TRANSIENT);
    
    std::vector<FileMetadata> files;
    
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        FileMetadata metadata;
        metadata.path = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
        metadata.folderId = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
        metadata.size = sqlite3_column_int64(stmt, 2);
        metadata.modifiedAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
        
        const char* checksum = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 4));
        if (checksum) metadata.checksum = checksum;
        
        metadata.isDirectory = sqlite3_column_int(stmt, 5) != 0;
        metadata.syncStatus = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 6));
        
        files.push_back(metadata);
    }
    
    sqlite3_finalize(stmt);
    return files;
}

std::vector<FileMetadata> Database::getChangedFilesSince(const std::string& timestamp) {
    const char* sql = R"(
        SELECT path, folder_id, size, modified_at, checksum, is_directory, sync_status
        FROM file_metadata 
        WHERE modified_at > ? 
        ORDER BY modified_at DESC;
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return {};
    
    sqlite3_bind_text(stmt, 1, timestamp.c_str(), -1, SQLITE_TRANSIENT);
    
    std::vector<FileMetadata> files;
    
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        FileMetadata metadata;
        metadata.path = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
        metadata.folderId = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
        metadata.size = sqlite3_column_int64(stmt, 2);
        metadata.modifiedAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
        
        const char* checksum = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 4));
        if (checksum) metadata.checksum = checksum;
        
        metadata.isDirectory = sqlite3_column_int(stmt, 5) != 0;
        metadata.syncStatus = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 6));
        
        files.push_back(metadata);
    }
    
    sqlite3_finalize(stmt);
    return files;
}

bool Database::deleteFileMetadata(const std::string& path) {
    const char* sql = "DELETE FROM file_metadata WHERE path = ?;";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, path.c_str(), -1, SQLITE_TRANSIENT);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    return rc == SQLITE_DONE;
}

bool Database::updateSyncFolderTimestamp(const std::string& folderId) {
    const char* sql = "UPDATE sync_folders SET last_sync = datetime('now') WHERE id = ?;";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, folderId.c_str(), -1, SQLITE_TRANSIENT);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to update sync folder timestamp: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    return true;
}

// ============================================================================
// Conflicts
// ============================================================================

bool Database::logConflict(const Conflict& conflict) {
    Logger::warn("Logging conflict for: {}", conflict.path);
    
    const char* sql = R"(
        INSERT INTO conflicts (id, path, folder_id, local_modified, remote_modified)
        VALUES (?, ?, ?, ?, ?);
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, conflict.id.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, conflict.path.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, conflict.folderId.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 4, conflict.localModified.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 5, conflict.remoteModified.c_str(), -1, SQLITE_TRANSIENT);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to log conflict: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    return true;
}

std::vector<Conflict> Database::getPendingConflicts() {
    const char* sql = R"(
        SELECT id, path, folder_id, local_modified, remote_modified, resolution, resolved_at
        FROM conflicts 
        WHERE resolved_at IS NULL
        ORDER BY created_at DESC;
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return {};
    
    std::vector<Conflict> conflicts;
    
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        Conflict conflict;
        conflict.id = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
        conflict.path = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
        conflict.folderId = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
        conflict.localModified = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
        conflict.remoteModified = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 4));
        
        const char* resolution = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 5));
        if (resolution) conflict.resolution = resolution;
        
        const char* resolvedAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 6));
        if (resolvedAt) conflict.resolvedAt = resolvedAt;
        
        conflicts.push_back(conflict);
    }
    
    sqlite3_finalize(stmt);
    return conflicts;
}

bool Database::resolveConflict(const std::string& conflictId, const std::string& resolution) {
    Logger::info("Resolving conflict: {} with strategy: {}", conflictId, resolution);
    
    const char* sql = R"(
        UPDATE conflicts 
        SET resolution = ?, resolved_at = datetime('now')
        WHERE id = ?;
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, resolution.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, conflictId.c_str(), -1, SQLITE_TRANSIENT);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to resolve conflict: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    return true;
}

// ============================================================================
// Remote Server Profiles
// ============================================================================

bool Database::addRemoteServerProfile(const RemoteServerProfile& profile) {
    Logger::info("Adding remote server profile: {}", profile.name);
    
    const char* sql = R"(
        INSERT INTO remote_server_profiles (owner, name, ssh_host, ssh_port, ssh_username, ssh_private_key, vpn_profile_id, power_on_command)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, profile.owner.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, profile.name.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, profile.sshHost.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, 4, profile.sshPort);
    sqlite3_bind_text(stmt, 5, profile.sshUsername.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 6, profile.sshPrivateKey.c_str(), -1, SQLITE_TRANSIENT);
    if (profile.vpnProfileId > 0) {
        sqlite3_bind_int(stmt, 7, profile.vpnProfileId);
    } else {
        sqlite3_bind_null(stmt, 7);
    }
    sqlite3_bind_text(stmt, 8, profile.powerOnCommand.c_str(), -1, SQLITE_TRANSIENT);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to add remote server profile: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    Logger::info("Remote server profile added successfully");
    return true;
}

bool Database::updateRemoteServerProfile(const RemoteServerProfile& profile) {
    Logger::info("Updating remote server profile: {}", profile.name);
    
    const char* sql = R"(
        UPDATE remote_server_profiles
        SET ssh_host = ?, ssh_port = ?, ssh_username = ?, ssh_private_key = ?, vpn_profile_id = ?, power_on_command = ?, updated_at = datetime('now')
        WHERE id = ?;
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, profile.sshHost.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, 2, profile.sshPort);
    sqlite3_bind_text(stmt, 3, profile.sshUsername.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 4, profile.sshPrivateKey.c_str(), -1, SQLITE_TRANSIENT);
    if (profile.vpnProfileId > 0) {
        sqlite3_bind_int(stmt, 5, profile.vpnProfileId);
    } else {
        sqlite3_bind_null(stmt, 5);
    }
    sqlite3_bind_text(stmt, 6, profile.powerOnCommand.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, 7, profile.id);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to update remote server profile: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    return true;
}

bool Database::deleteRemoteServerProfile(int id) {
    Logger::info("Deleting remote server profile: {}", id);
    
    const char* sql = "DELETE FROM remote_server_profiles WHERE id = ?;";
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_int(stmt, 1, id);
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to delete remote server profile: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    return true;
}

bool Database::clearAllRemoteServerProfiles() {
    Logger::info("Clearing all remote server profiles");
    
    const char* sql = "DELETE FROM remote_server_profiles;";
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to clear remote server profiles: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    return true;
}

RemoteServerProfile Database::getRemoteServerProfile(int id) {
    const char* sql = "SELECT id, owner, name, ssh_host, ssh_port, ssh_username, ssh_private_key, vpn_profile_id, power_on_command, last_used, created_at, updated_at FROM remote_server_profiles WHERE id = ?;";
    sqlite3_stmt* stmt = prepareStatement(sql);
    
    RemoteServerProfile profile{};
    if (stmt) {
        sqlite3_bind_int(stmt, 1, id);
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            profile.id = sqlite3_column_int(stmt, 0);
            profile.owner = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
            profile.name = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
            profile.sshHost = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
            profile.sshPort = sqlite3_column_int(stmt, 4);
            profile.sshUsername = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 5));
            profile.sshPrivateKey = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 6));
            profile.vpnProfileId = sqlite3_column_int(stmt, 7);
            profile.powerOnCommand = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 8));
            if (sqlite3_column_text(stmt, 9)) {
                profile.lastUsed = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 9));
            }
            profile.createdAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 10));
            profile.updatedAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 11));
        }
        sqlite3_finalize(stmt);
    }
    
    return profile;
}

std::vector<RemoteServerProfile> Database::getRemoteServerProfiles(const std::string& owner) {
    std::vector<RemoteServerProfile> profiles;
    
    const char* sql = "SELECT id, owner, name, ssh_host, ssh_port, ssh_username, ssh_private_key, vpn_profile_id, power_on_command, last_used, created_at, updated_at FROM remote_server_profiles WHERE owner = ? ORDER BY name;";
    sqlite3_stmt* stmt = prepareStatement(sql);
    
    if (stmt) {
        sqlite3_bind_text(stmt, 1, owner.c_str(), -1, SQLITE_TRANSIENT);
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            RemoteServerProfile profile;
            profile.id = sqlite3_column_int(stmt, 0);
            profile.owner = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
            profile.name = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
            profile.sshHost = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
            profile.sshPort = sqlite3_column_int(stmt, 4);
            profile.sshUsername = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 5));
            profile.sshPrivateKey = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 6));
            profile.vpnProfileId = sqlite3_column_int(stmt, 7);
            profile.powerOnCommand = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 8));
            if (sqlite3_column_text(stmt, 9)) {
                profile.lastUsed = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 9));
            }
            profile.createdAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 10));
            profile.updatedAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 11));
            profiles.push_back(profile);
        }
        sqlite3_finalize(stmt);
    }
    
    return profiles;
}

std::vector<RemoteServerProfile> Database::getRemoteServerProfiles() {
    std::vector<RemoteServerProfile> profiles;
    
    const char* sql = "SELECT id, owner, name, ssh_host, ssh_port, ssh_username, ssh_private_key, vpn_profile_id, power_on_command, last_used, created_at, updated_at FROM remote_server_profiles ORDER BY name;";
    sqlite3_stmt* stmt = prepareStatement(sql);
    
    if (stmt) {
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            RemoteServerProfile profile;
            profile.id = sqlite3_column_int(stmt, 0);
            profile.owner = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
            profile.name = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
            profile.sshHost = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
            profile.sshPort = sqlite3_column_int(stmt, 4);
            profile.sshUsername = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 5));
            profile.sshPrivateKey = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 6));
            profile.vpnProfileId = sqlite3_column_int(stmt, 7);
            profile.powerOnCommand = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 8));
            if (sqlite3_column_text(stmt, 9)) {
                profile.lastUsed = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 9));
            }
            profile.createdAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 10));
            profile.updatedAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 11));
            profiles.push_back(profile);
        }
        sqlite3_finalize(stmt);
    }
    
    return profiles;
}


// ============================================================================
// VPN Profiles
// ============================================================================

bool Database::addVPNProfile(const VPNProfile& profile) {
    Logger::info("Adding VPN profile: {}", profile.name);
    
    const char* sql = R"(
        INSERT INTO vpn_profiles (name, vpn_type, description, config_content, certificate, private_key, auto_connect)
        VALUES (?, ?, ?, ?, ?, ?, ?);
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, profile.name.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, profile.vpnType.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, profile.description.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 4, profile.configContent.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 5, profile.certificate.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 6, profile.privateKey.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, 7, profile.autoConnect ? 1 : 0);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to add VPN profile: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    Logger::info("VPN profile added successfully");
    return true;
}

bool Database::updateVPNProfile(const VPNProfile& profile) {
    Logger::info("Updating VPN profile: {}", profile.name);
    
    const char* sql = R"(
        UPDATE vpn_profiles
        SET vpn_type = ?, description = ?, config_content = ?, certificate = ?, private_key = ?, auto_connect = ?, updated_at = datetime('now')
        WHERE id = ?;
    )";
    
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_text(stmt, 1, profile.vpnType.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, profile.description.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, profile.configContent.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 4, profile.certificate.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 5, profile.privateKey.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, 6, profile.autoConnect ? 1 : 0);
    sqlite3_bind_int(stmt, 7, profile.id);
    
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to update VPN profile: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    return true;
}

bool Database::deleteVPNProfile(int id) {
    Logger::info("Deleting VPN profile: {}", id);
    
    const char* sql = "DELETE FROM vpn_profiles WHERE id = ?;";
    sqlite3_stmt* stmt = prepareStatement(sql);
    if (!stmt) return false;
    
    sqlite3_bind_int(stmt, 1, id);
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc != SQLITE_DONE) {
        Logger::error("Failed to delete VPN profile: {}", sqlite3_errmsg(db_));
        return false;
    }
    
    return true;
}

VPNProfile Database::getVPNProfile(int id) {
    const char* sql = "SELECT id, name, vpn_type, description, config_content, certificate, private_key, auto_connect, created_at, updated_at FROM vpn_profiles WHERE id = ?;";
    sqlite3_stmt* stmt = prepareStatement(sql);
    
    VPNProfile profile{};
    if (stmt) {
        sqlite3_bind_int(stmt, 1, id);
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            profile.id = sqlite3_column_int(stmt, 0);
            profile.name = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
            profile.vpnType = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
            profile.description = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
            profile.configContent = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 4));
            profile.certificate = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 5));
            profile.privateKey = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 6));
            profile.autoConnect = sqlite3_column_int(stmt, 7) != 0;
            profile.createdAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 8));
            profile.updatedAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 9));
        }
        sqlite3_finalize(stmt);
    }
    
    return profile;
}

std::vector<VPNProfile> Database::getVPNProfiles() {
    std::vector<VPNProfile> profiles;
    
    const char* sql = "SELECT id, name, vpn_type, description, config_content, certificate, private_key, auto_connect, created_at, updated_at FROM vpn_profiles ORDER BY name;";
    sqlite3_stmt* stmt = prepareStatement(sql);
    
    if (stmt) {
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            VPNProfile profile;
            profile.id = sqlite3_column_int(stmt, 0);
            profile.name = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
            profile.vpnType = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
            profile.description = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
            profile.configContent = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 4));
            profile.certificate = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 5));
            profile.privateKey = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 6));
            profile.autoConnect = sqlite3_column_int(stmt, 7) != 0;
            profile.createdAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 8));
            profile.updatedAt = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 9));
            profiles.push_back(profile);
        }
        sqlite3_finalize(stmt);
    }
    
    return profiles;
}

// ============================================================================
// Utilities
// ============================================================================

std::string Database::generateId() {
    // Generate a UUID-like ID
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<> dis(0, 15);
    
    const char* hex = "0123456789abcdef";
    std::string id = "";
    
    for (int i = 0; i < 32; ++i) {
        if (i == 8 || i == 12 || i == 16 || i == 20) {
            id += '-';
        }
        id += hex[dis(gen)];
    }
    
    return id;
}

bool Database::executeQuery(const std::string& query) {
    char* errMsg = nullptr;
    int rc = sqlite3_exec(db_, query.c_str(), nullptr, nullptr, &errMsg);
    
    if (rc != SQLITE_OK) {
        Logger::error("SQL error: {}", errMsg);
        sqlite3_free(errMsg);
        return false;
    }
    
    return true;
}

sqlite3_stmt* Database::prepareStatement(const std::string& query) {
    sqlite3_stmt* stmt = nullptr;
    int rc = sqlite3_prepare_v2(db_, query.c_str(), -1, &stmt, nullptr);
    
    if (rc != SQLITE_OK) {
        Logger::error("Failed to prepare statement: {}", sqlite3_errmsg(db_));
        return nullptr;
    }
    
    return stmt;
}

} // namespace baludesk
