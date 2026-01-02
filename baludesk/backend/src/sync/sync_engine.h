#pragma once

#include <string>
#include <memory>
#include <functional>
#include <vector>
#include <queue>
#include <mutex>
#include <atomic>
#include <thread>

// Forward declarations
class FileWatcher;
class HttpClient;
class Database;
class ConflictResolver;
class ChangeDetector;

namespace baludesk {

// Sync status enumeration
enum class SyncStatus {
    IDLE,
    SYNCING,
    PAUSED,
    ERROR
};

// File change action
enum class FileAction {
    CREATED,
    MODIFIED,
    DELETED
};

// File event structure
struct FileEvent {
    std::string path;
    FileAction action;
    uint64_t size;
    std::string timestamp;
};

// Sync folder configuration
struct SyncFolder {
    std::string id;
    std::string localPath;
    std::string remotePath;
    SyncStatus status;
    bool enabled;
    std::string createdAt;
    std::string lastSync;
};

// Sync statistics
struct SyncStats {
    SyncStatus status;
    uint64_t uploadSpeed;      // bytes/sec
    uint64_t downloadSpeed;
    uint32_t pendingUploads;
    uint32_t pendingDownloads;
    std::string lastSync;
};

/**
 * SyncEngine - Core synchronization engine
 * 
 * Responsibilities:
 * - Manage sync folders
 * - Coordinate file watching, change detection, and sync operations
 * - Handle conflicts
 * - Provide sync status updates
 */
class SyncEngine {
public:
    SyncEngine();
    ~SyncEngine();

    // Lifecycle
    bool initialize(const std::string& dbPath, const std::string& serverUrl);
    void start();
    void stop();
    bool isRunning() const;

    // Authentication
    bool login(const std::string& username, const std::string& password);
    void logout();
    bool isAuthenticated() const;

    // Sync folder management
    std::string addSyncFolder(const std::string& localPath, const std::string& remotePath);
    bool removeSyncFolder(const std::string& folderId);
    bool pauseSyncFolder(const std::string& folderId);
    bool resumeSyncFolder(const std::string& folderId);
    std::vector<SyncFolder> getSyncFolders() const;

    // Sync operations
    void triggerSync(const std::string& folderId = "");
    SyncStats getStats() const;

    // Callbacks for status updates
    using StatusCallback = std::function<void(const SyncStats&)>;
    using FileChangeCallback = std::function<void(const FileEvent&)>;
    using ErrorCallback = std::function<void(const std::string&)>;

    void setStatusCallback(StatusCallback callback);
    void setFileChangeCallback(FileChangeCallback callback);
    void setErrorCallback(ErrorCallback callback);

private:
    // Internal sync loop
    void syncLoop();
    void processFileEvent(const FileEvent& event);
    void scanLocalChanges(const SyncFolder& folder);
    void fetchRemoteChanges(const SyncFolder& folder);
    void uploadFile(const std::string& localPath, const std::string& remotePath);
    void downloadFile(const std::string& remotePath, const std::string& localPath);
    void handleConflict(const std::string& path);

    // Update stats
    void updateStats();
    void notifyStatusChange();

    // Components
    std::unique_ptr<FileWatcher> fileWatcher_;
    std::unique_ptr<HttpClient> httpClient_;
    std::unique_ptr<Database> database_;
    std::unique_ptr<ConflictResolver> conflictResolver_;
    std::unique_ptr<ChangeDetector> changeDetector_;

    // State
    std::atomic<bool> running_{false};
    std::atomic<bool> authenticated_{false};
    std::thread syncThread_;
    std::mutex mutex_;

    // Event queue
    std::queue<FileEvent> eventQueue_;
    std::mutex queueMutex_;

    // Callbacks
    StatusCallback statusCallback_;
    FileChangeCallback fileChangeCallback_;
    ErrorCallback errorCallback_;

    // Stats
    SyncStats stats_;
    std::mutex statsMutex_;
};

} // namespace baludesk
